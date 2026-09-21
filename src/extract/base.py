"""
Shared extraction machinery.

THE IMPORTANT IDEA: every format eventually becomes text. So each format
adapter only has to answer one question - "what is the text of this document?"
- and then hands it to `parse_labelled_text` below, which does the label
matching once, in one place, for everybody.

That is why adding PDF or DOCX support is a small job rather than a rewrite:
you write ~20 lines that produce a string, and all the synonym handling,
blank detection and provenance tracking is already done.

    txt   -> read the file           -> parse_labelled_text
    pdf   -> pdfplumber extract_text -> parse_labelled_text
    xlsx  -> openpyxl cells joined   -> parse_labelled_text
    docx  -> paragraphs + table cells-> parse_labelled_text
"""

import re

from ..contracts import Extracted, Field, COMPARE_FIELDS
from ..synonyms import field_for_label, WRONG_DOC_MARKERS, DOC_TYPE_MARKERS
from ..normalize import normalise, is_blank


def sniff_doc_type(text: str):
    """What IS this document, by its content?

    We never trust the filename. The dataset contains files named
    `email_501_BL.txt` that are actually Commercial Invoices - that is the
    `wrong_doc_type` escalation, and the only way to catch it is to read the
    document and see what it calls itself.
    """
    head = text[:600].lower()
    for marker, kind in WRONG_DOC_MARKERS.items():
        if marker in head:
            return kind
    for marker, kind in DOC_TYPE_MARKERS.items():
        if marker in head:
            return kind
    return None


# A "Label: value" line. We only split on the FIRST colon, and only on lines
# that are not indented - indented lines are address continuations belonging to
# the field above.
LABEL_LINE = re.compile(r"^(?P<label>[^:|]{1,60})\s*[:|]\s*(?P<value>.*)$")


def parse_labelled_text(text: str, doc_role: str, path: str = "") -> Extracted:
    """Pull the seven fields out of any labelled plain text.

    Records, for every field: the normalised value, a confidence, and where in
    the document it came from. A field that is present but blank ("???",
    "N/A", "_______") is recorded with confidence 0.0 - found, but unusable -
    which is what later routes the case to `missing_value` review rather than
    to a false mismatch.
    """
    out = Extracted(doc_role=doc_role, path=path, readable=True)
    out.doc_type = sniff_doc_type(text)

    for lineno, line in enumerate(text.splitlines(), start=1):
        if not line.strip() or line[:1].isspace():
            continue                        # blank, or an indented continuation
        m = LABEL_LINE.match(line)
        if not m:
            continue

        field_name = field_for_label(m.group("label"))
        if field_name is None:
            continue                        # a label we don't care about

        # First occurrence wins. Documents repeat labels (a per-container table
        # then a stated total); the first labelled line is the header value.
        existing = out.get(field_name)
        if existing.raw is not None:
            continue

        raw = m.group("value").strip()
        value = normalise(field_name, raw)

        setattr(out, field_name, Field(
            value=value,
            # 0.0 when the field was found but empty - uncertainty, not equality
            confidence=0.0 if (value is None or is_blank(raw)) else 1.0,
            source=f"{doc_role} {path.split('/')[-1]} line {lineno}",
            raw=raw,
        ))

    return out


def unreadable(doc_role: str, path: str, why: str) -> Extracted:
    """Build the 'I could not read this at all' result.

    Used for image-only PDFs with no text layer, 0-byte files and corrupt
    bytes. Note this is NOT a mismatch and NOT a match - it is the system
    correctly declining to decide.
    """
    return Extracted(doc_role=doc_role, path=path, readable=False, error=why)
