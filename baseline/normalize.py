"""
Turn raw document text into comparable values.

THIS FILE IS WHERE FALSE ALARMS ARE PREVENTED.

The same clean shipment renders differently depending on the file format:

    gross weight   "131,058 KG"  (txt)   "341715"  (xlsx)   "243,588"  (docx)
    containers     "6 x 40'HC"           "15 x 20'GP"
    ports          "KARACHI, PAKISTAN (PKKHI)"  (txt)
                   "KARACHI, PAKISTAN"          (pdf / xlsx - no code)

A naive string comparison marks every single PDF and XLSX pair as a mismatch
on ports and weight. Those are not defects, they are rendering differences,
and reporting them destroys the precision score AND the operator's trust in
the tool - which is the actual point of the product.

RULE OF THUMB: normalise away things that cannot change meaning (case,
whitespace, thousands separators, unit suffixes, port codes). NEVER normalise
away things that can (digits, party names, the difference between two ports).
Over-normalising hides real defects, which is the worse failure of the two.
"""

import re

# ---------------------------------------------------------------------------
# Blank markers - a field that is present but empty
# ---------------------------------------------------------------------------
# The dataset deliberately includes SIs with required fields blanked out. These
# must become "I don't know" (-> NEEDS_REVIEW / missing_value), NEVER an empty
# string that happens to equal another empty string. Two unknowns are not a
# match; that is the single most dangerous bug available in this problem.
BLANK_MARKERS = {
    "", "-", "--", "n/a", "na", "tba", "tbd", "???", "?", "none", "nil",
    "to be advised", "to be confirmed", "xxx",
}


def is_blank(raw) -> bool:
    if raw is None:
        return True
    s = str(raw).strip().lower()
    s = s.strip("_ .:")           # "_______" and "___ MTS" style placeholders
    return s in BLANK_MARKERS or not s


# ---------------------------------------------------------------------------
# Text fields: shipper, consignee, notify_party
# ---------------------------------------------------------------------------

def norm_party(raw):
    """Normalise a company name for comparison.

    Case, punctuation and spacing are noise. Everything else is signal - two
    different companies is exactly the defect we are hunting, so we do NOT
    fuzzy-match here. "EAST BRIGHT FZ-LLC" and "UAB NOVAKOPA" must stay
    different, and so must two companies with similar names.
    """
    if is_blank(raw):
        return None
    s = str(raw).strip()
    s = s.split("\n")[0]              # name is the first line; address follows
    s = re.sub(r"[.,]", " ", s)
    s = re.sub(r"\s+", " ", s)
    return s.upper().strip()


# ---------------------------------------------------------------------------
# Ports
# ---------------------------------------------------------------------------

# A trailing UN/LOCODE in brackets: "KARACHI, PAKISTAN (PKKHI)". Present in the
# txt renderings, absent from pdf/xlsx. Stripping it is safe - the city and
# country still carry the identity - and NOT stripping it false-alarms every
# mixed-format pair.
PORT_CODE = re.compile(r"\(\s*[A-Z]{5}\s*\)\s*$")


def norm_port(raw):
    if is_blank(raw):
        return None
    s = str(raw).strip().split("\n")[0]
    s = PORT_CODE.sub("", s).strip()
    s = re.sub(r"[.,]", " ", s)
    s = re.sub(r"\s+", " ", s)
    return s.upper().strip(" -")


# ---------------------------------------------------------------------------
# Container count
# ---------------------------------------------------------------------------

# "6 x 40'HC" -> 6.  The 40 is the container SIZE, not a quantity. Reading the
# wrong number here is a listed judging trap, and it is an easy mistake because
# "40" looks more like a count than "6" does.
CONTAINER_COUNT = re.compile(r"^\s*(\d+)\s*(?:x|X|\*)?", re.I)


def norm_container_count(raw):
    if is_blank(raw):
        return None
    s = str(raw).strip()
    m = CONTAINER_COUNT.match(s)
    if not m:
        return None
    try:
        return int(m.group(1))
    except ValueError:
        return None


# ---------------------------------------------------------------------------
# Gross weight
# ---------------------------------------------------------------------------

WEIGHT_NUM = re.compile(r"(\d[\d,\s.]*)")


def norm_weight_kg(raw):
    """Return an integer number of kilograms, or None.

    Handles "131,058 KG", "341715", "243,588", "131058.0".
    Converts metric tonnes when the unit says so (1 MT = 1000 kg).

    Returns None rather than guessing when the number cannot be parsed
    confidently - an unparseable weight is uncertainty, not a discrepancy.
    """
    if is_blank(raw):
        return None
    s = str(raw).strip().upper()

    is_tonnes = bool(re.search(r"\b(MT|MTS|TONNE|TONNES|TON)\b", s))

    m = WEIGHT_NUM.search(s)
    if not m:
        return None
    num = m.group(1).replace(",", "").replace(" ", "").rstrip(".")
    if not num:
        return None
    try:
        val = float(num)
    except ValueError:
        return None

    if is_tonnes:
        val *= 1000
    return int(round(val))


# ---------------------------------------------------------------------------
# Dispatcher - one entry point the extractors and comparator both use
# ---------------------------------------------------------------------------

NORMALISERS = {
    "shipper": norm_party,
    "consignee": norm_party,
    "notify_party": norm_party,
    "port_of_loading": norm_port,
    "port_of_discharge": norm_port,
    "container_count": norm_container_count,
    "gross_weight_kg": norm_weight_kg,
}


def normalise(field_name: str, raw):
    """Normalise `raw` according to which of the seven fields it is."""
    fn = NORMALISERS.get(field_name)
    return fn(raw) if fn else (None if is_blank(raw) else str(raw).strip())
