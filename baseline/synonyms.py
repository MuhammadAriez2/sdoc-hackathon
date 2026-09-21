"""
Label synonym map: the "same information looks different" problem.

The SI and the BL describe the SAME shipment but label the fields differently.
The SI says "Port of Loading (POL)", the BL says "Load Port". The DOCX files
label them bilingually: "PORT OF LOADING (装货港)". Across the dataset there are
roughly 60 distinct labels for these 7 fields.

HOW WE MATCH
------------
We do NOT substring-search for "consignee" or "weight". That breaks on two
real traps in this data:

    "Notify Party/Intermediate Consignee"  contains "Consignee" but is NOT it
    "NET WEIGHT"                           contains "WEIGHT" but is NOT gross

Instead we normalise the label (lowercase it, strip CJK characters, drop any
parenthetical, collapse whitespace) and look it up EXACTLY in the table below.
Exact lookup on a normalised key is both safer and easier to debug than fuzzy
matching, and when a new label shows up you get a clean miss instead of a
silent wrong answer.

The table below is append-only by convention: a new label is a new row, never
a restructure, so that a miss stays traceable to the exact label that caused
it. It covers the labels reachable from the plain-text documents this baseline
parses, not all ~60 in the dataset — the rest live in the PDF, DOCX and XLSX
files that are out of scope here.
"""

import re
import unicodedata

# normalised label -> canonical field name
LABEL_MAP = {
    # ---- shipper -----------------------------------------------------------
    "shipper": "shipper",
    "shipper/exporter": "shipper",
    # "Shipper (Principal or Seller)" -> parenthetical stripped -> "shipper"

    # ---- consignee ---------------------------------------------------------
    "consignee": "consignee",
    "to the order of": "consignee",

    # ---- notify party ------------------------------------------------------
    "notify": "notify_party",
    "notify party": "notify_party",
    "notify party/intermediate consignee": "notify_party",

    # ---- port of loading ---------------------------------------------------
    "port of loading": "port_of_loading",
    "load port": "port_of_loading",
    "pol": "port_of_loading",

    # ---- port of discharge -------------------------------------------------
    "port of discharge": "port_of_discharge",
    "discharge port": "port_of_discharge",
    "pod": "port_of_discharge",

    # ---- container count ---------------------------------------------------
    "total containers": "container_count",
    "container count": "container_count",
    "no. of containers": "container_count",
    "no. of containers or packages": "container_count",
    "number of containers": "container_count",

    # ---- gross weight ------------------------------------------------------
    # NOTE: "net weight" is deliberately absent. Net is not gross.
    "gross weight": "gross_weight_kg",
    "gross wt": "gross_weight_kg",
    "total gross weight": "gross_weight_kg",
    "gross weight kgs": "gross_weight_kg",
}


# Labels that tell us the document is NOT an SI or a BL. Seeing these means the
# attachment is a Commercial Invoice / Packing List / Certificate of Origin,
# which is a `wrong_doc_type` escalation, not something to compare.
WRONG_DOC_MARKERS = {
    "commercial invoice": "invoice",
    "packing list": "packing_list",
    "certificate of origin": "certificate_of_origin",
}

# Titles that confirm a document IS what we expect.
DOC_TYPE_MARKERS = {
    "shipping instruction": "SI",
    "bill of lading": "BL",
    "bl instruction": "SI",
}


def normalise_label(label: str) -> str:
    """Turn a raw document label into a lookup key.

    "Gross Weight毛重(KGS)"        -> "gross weight"
    "Port of Loading (POL)"        -> "port of loading"
    "Shipper (Principal or Seller)"-> "shipper"
    "NOTIFY PARTY"                 -> "notify party"

    Note the parenthetical is dropped BEFORE we strip CJK, so "(装货港)" goes
    with the bracket it lives in.
    """
    if not label:
        return ""
    s = label.strip()
    s = re.sub(r"\([^)]*\)", " ", s)          # drop parentheticals
    # drop any CJK / non-latin characters left over (bilingual DOCX labels)
    s = "".join(c for c in s if not _is_cjk(c))
    s = unicodedata.normalize("NFKD", s)
    s = s.lower()
    s = s.replace("：", ":").rstrip(":").strip()
    s = re.sub(r"\s+", " ", s)
    return s.strip(" .;,")


def _is_cjk(ch: str) -> bool:
    return any(start <= ord(ch) <= end for start, end in (
        (0x4E00, 0x9FFF),    # CJK unified ideographs
        (0x3400, 0x4DBF),
        (0x3000, 0x303F),    # CJK punctuation
        (0xFF00, 0xFFEF),    # fullwidth forms
    ))


def field_for_label(label: str):
    """Canonical field name for a raw label, or None if we don't recognise it.

    Returning None (rather than guessing) is deliberate: an unrecognised label
    should surface as a missing field and route to review, not be silently
    mapped to the wrong thing.
    """
    return LABEL_MAP.get(normalise_label(label))
