"""
Format dispatcher: hand it a path, get back an `Extracted`.

The whole rest of the pipeline goes through this one function and never learns
what file type it was looking at. That is the seam that lets the four
extractors be built in parallel and swapped independently.

SCOPE: PLAIN TEXT ONLY
----------------------
    .txt    parsed
    .xlsx   returns unreadable, by design
    .pdf    returns unreadable, by design
    .docx   returns unreadable, by design

Parsing PDF, XLSX and DOCX is QuayProof's job. Duplicating those parsers here
would defeat the purpose of a control: the gap between this baseline and the
application is the measurement, so closing it in the control destroys the very
thing the control exists to show.

Binary formats therefore return `unreadable`, which escalates to NEEDS_REVIEW
rather than guessing. That costs 13 of the 46 defects in the dataset, and the
cost is the point — it is the measurable distance the document pipeline in
`quayproof/` closes. It is also why this baseline's defect precision is 1.000
while its escalation precision is 0.444: it never invents a reading it cannot
support.
"""

import os

from .base import parse_labelled_text, unreadable
from ..contracts import Extracted


def extract(path: str, doc_role: str, root: str = ".") -> Extracted:
    """Read one attachment into the common `Extracted` shape.

    `path` is exactly the string from email["attachments"],
    e.g. "attachments/email_004_SI.txt".
    """
    full = os.path.join(root, path)
    ext = os.path.splitext(path)[1].lower()

    if not os.path.exists(full):
        return unreadable(doc_role, path, "file not found")
    if os.path.getsize(full) == 0:
        return unreadable(doc_role, path, "empty file")

    try:
        if ext == ".txt":
            return _extract_txt(full, doc_role, path)
        if ext == ".xlsx":
            return _extract_xlsx(full, doc_role, path)
        if ext == ".pdf":
            return _extract_pdf(full, doc_role, path)
        if ext == ".docx":
            return _extract_docx(full, doc_role, path)
    except Exception as exc:                      # noqa: BLE001
        # A parser blowing up is an unreadable document, not a crashed run.
        # 520 emails must always produce 520 outputs.
        return unreadable(doc_role, path, f"{type(exc).__name__}: {exc}")

    return unreadable(doc_role, path, f"unsupported format {ext}")


# ---------------------------------------------------------------------------
# .txt - working
# ---------------------------------------------------------------------------

def _extract_txt(full: str, doc_role: str, path: str) -> Extracted:
    with open(full, "r", encoding="utf-8", errors="replace") as fh:
        text = fh.read()
    if len(text.strip()) < 20:
        return unreadable(doc_role, path, "no readable text")
    return parse_labelled_text(text, doc_role, path)


# ---------------------------------------------------------------------------
# .xlsx - out of scope for the control
# ---------------------------------------------------------------------------

def _extract_xlsx(full: str, doc_role: str, path: str) -> Extracted:
    """Not parsed here. Spreadsheet extraction belongs to QuayProof.

    `quayproof/backend/app/parsers.py` reads XLSX with openpyxl in read-only
    mode, keeps the worksheet and contributing cell coordinates as evidence,
    and refuses formula cells outright rather than trusting a cached value.
    None of that is reproduced here, deliberately.

    Two traps it has to handle that a naive reader would not: weights arrive
    as bare numbers with no unit and no thousands separator (341715), and a
    label can sit in column A with its value spread across B and C.
    """
    return unreadable(doc_role, path, "xlsx is out of scope for the baseline")


# ---------------------------------------------------------------------------
# .pdf - out of scope for the control
# ---------------------------------------------------------------------------

def _extract_pdf(full: str, doc_role: str, path: str) -> Extracted:
    """Not parsed here. PDF extraction belongs to QuayProof.

    `quayproof/backend/app/parsers.py` takes native text first via pdfplumber,
    keeps per-line bounding boxes, and falls back to Tesseract only for pages
    with no dependable text layer — retaining per-word confidence and
    transforming OCR coordinates back through the raster scale. A page that
    yields no characters escalates rather than being guessed at.

    The layout here is column-based, so a label and its value can share a line
    separated by wide spaces rather than a colon — which is why coordinates,
    not just text, matter for this format.
    """
    return unreadable(doc_role, path, "pdf is out of scope for the baseline")


# ---------------------------------------------------------------------------
# .docx - out of scope for the control
# ---------------------------------------------------------------------------

def _extract_docx(full: str, doc_role: str, path: str) -> Extracted:
    """Not parsed here. DOCX extraction belongs to QuayProof.

    `quayproof/backend/app/parsers.py` walks paragraphs and tables separately
    with python-docx, keeping the table and row number as evidence — which
    matters because every DOCX in this dataset puts the fields in a TABLE, so
    a paragraph-only reader finds nothing at all.

    Its labels are bilingual — "PORT OF LOADING (装货港)". `normalise_label` in
    `baseline/synonyms.py` already strips the bracket and the CJK characters,
    so the synonym table would cope; the file format is the obstacle, not the
    vocabulary.
    """
    return unreadable(doc_role, path, "docx is out of scope for the baseline")
