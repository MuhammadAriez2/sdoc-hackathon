"""Native text first; OCR only pages without dependable native text."""
import csv
import io
import re
import shutil
import subprocess
import tempfile
import zipfile
from pathlib import Path
from .config import MAX_FILE_BYTES, MAX_TEXT_CHARS


class DocumentError(ValueError):
    def __init__(self, message, reason='unreadable'):
        super().__init__(message)
        self.reason = reason


class ToolUnavailable(RuntimeError):
    pass


def parse_document(name: str, data: bytes, settings) -> list[dict]:
    if len(data) > MAX_FILE_BYTES:
        raise DocumentError('Attachment exceeds the 10 MB prototype limit')
    ext = Path(name).suffix.lower()
    blocks = []

    def add(text, location, method='native', quality=1.0, bbox=None):
        if text and text.strip():
            blocks.append(dict(id=f'b{len(blocks)+1}', text=text.strip(), location=location,
                               method=method, quality=round(quality, 3), bbox=bbox))

    try:
        if ext in {'.docx', '.xlsx'}:
            with zipfile.ZipFile(io.BytesIO(data)) as z:
                if len(z.infolist()) > 2000 or sum(i.file_size for i in z.infolist()) > 50*1024*1024:
                    raise DocumentError('Office archive exceeds expansion limit')
        if ext == '.txt':
            text = data.decode('utf-8-sig')
            for n, line in enumerate(text.splitlines(), 1):
                add(line, {'line': n})
        elif ext == '.docx':
            from docx import Document
            doc = Document(io.BytesIO(data))
            for n, p in enumerate(doc.paragraphs, 1):
                add(p.text, {'paragraph': n})
            for t, table in enumerate(doc.tables, 1):
                for r, row in enumerate(table.rows, 1):
                    texts = list(dict.fromkeys(c.text for c in row.cells))
                    add(' | '.join(texts), {'table': t, 'row': r})
        elif ext == '.xlsx':
            from openpyxl import load_workbook
            book = load_workbook(io.BytesIO(data), read_only=True, data_only=False)
            count = 0
            try:
                for sheet in book:
                    for row in sheet:
                        count += len(row)
                        if count > 20000:
                            raise DocumentError('Worksheet exceeds 20,000-cell prototype limit')
                        cells = [c for c in row if c.value is not None]
                        if any(c.data_type == 'f' for c in cells):
                            raise DocumentError('Formula values require a trusted rendered document', 'missing_value')
                        if cells:
                            add(' | '.join(str(c.value) for c in cells), {'sheet': sheet.title, 'cells': ', '.join(c.coordinate for c in cells)})
            finally:
                book.close()
        elif ext == '.pdf':
            import pdfplumber
            import pypdfium2 as pdfium
            with pdfplumber.open(io.BytesIO(data)) as pdf:
                if len(pdf.pages) > settings.max_pages:
                    raise DocumentError(f'PDF exceeds {settings.max_pages}-page prototype limit')
                for page_num, page in enumerate(pdf.pages, 1):
                    lines = page.extract_text_lines(return_chars=False)
                    meaningful = sum(len(x['text'].strip()) for x in lines)
                    if meaningful >= 30:
                        for line in lines:
                            add(line['text'], {'page': page_num}, bbox=[line['x0'], line['top'], line['x1'], line['bottom']])
                    else:
                        if not shutil.which('tesseract'):
                            raise ToolUnavailable('Tesseract is missing; install it or use Docker')
                        rendered = pdfium.PdfDocument(data)
                        try:
                            p = rendered[page_num-1]
                            # Bound raster memory for oversized pages.
                            scale = min(2.0, 2400/max(p.get_size()))
                            bitmap = p.render(scale=scale)
                            pil = bitmap.to_pil()
                            with tempfile.TemporaryDirectory() as folder:
                                source = Path(folder)/'page.png'
                                pil.save(source)
                                result = subprocess.run(['tesseract', str(source), 'stdout', '-l', settings.ocr_language, '--psm', '6', 'tsv'], capture_output=True, text=True, timeout=40)
                                if result.returncode:
                                    raise ToolUnavailable('Tesseract failed; check installed language packs')
                                groups = {}
                                for word in csv.DictReader(io.StringIO(result.stdout), delimiter='\t'):
                                    if not word.get('text', '').strip() or float(word.get('conf', -1)) < 0:
                                        continue
                                    key = (word['block_num'], word['par_num'], word['line_num'])
                                    groups.setdefault(key, []).append(word)
                                for words in groups.values():
                                    x0 = min(int(w['left']) for w in words)/scale
                                    y0 = min(int(w['top']) for w in words)/scale
                                    x1 = max(int(w['left'])+int(w['width']) for w in words)/scale
                                    y1 = max(int(w['top'])+int(w['height']) for w in words)/scale
                                    add(' '.join(w['text'] for w in words), {'page': page_num}, 'tesseract', min(float(w['conf']) for w in words)/100, [x0,y0,x1,y1])
                            pil.close()
                            bitmap.close()
                            p.close()
                        finally:
                            rendered.close()
        else:
            raise DocumentError('Supported formats: TXT, PDF, DOCX, XLSX', 'wrong_doc_type')
    except (DocumentError, ToolUnavailable):
        raise
    except ImportError as exc:
        raise ToolUnavailable('A document parser dependency is missing') from exc
    except subprocess.TimeoutExpired as exc:
        raise ToolUnavailable('OCR exceeded its execution timeout') from exc
    except Exception as exc:
        raise DocumentError('The attachment could not be parsed') from exc
    if not blocks:
        raise DocumentError('No readable text found')
    if sum(len(x['text']) for x in blocks) > MAX_TEXT_CHARS:
        raise DocumentError('Text exceeds the prototype limit; split the document')
    return blocks
