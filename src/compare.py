"""
Stage 3: compare the SI against the BL.

NO AI IN THIS FILE, EVER.

Once both sides are extracted and normalised, comparing seven values is `==`.
Putting a model here buys nothing and costs everything: the end-to-end metric
requires the EXACT set of defect fields, so a model that occasionally decides
"131,058 KG" differs from "131058" silently destroys a result you can no
longer reproduce. Extraction is the hard part of this problem; comparison
should be the boring part.

THE THREE OUTCOMES, AND WHY THE THIRD EXISTS
--------------------------------------------
    OK            all seven read cleanly and all seven agree
    MISMATCH      all seven read cleanly and at least one differs
    NEEDS_REVIEW  we could not read enough to say either way

The third is not a cop-out - it is the product feature. A blank field or an
unreadable scan is genuinely not evidence of a discrepancy, and reporting one
sends an operator to chase a correction that was never needed. The dataset
scores escalation separately for exactly this reason.
"""

from .contracts import COMPARE_FIELDS


def compare(si, bl):
    """Compare two `Extracted` documents.

    Returns (status, review_reason, defect_fields, evidence).
    `evidence` is a per-field record for the UI and for debugging.
    """
    evidence = {}

    # -- 1. Could we read them at all? --------------------------------------
    # Checked first: you cannot sniff the type of a document you cannot read.
    if not si.readable:
        return "NEEDS_REVIEW", "unreadable", [], {"_why": f"SI: {si.error}"}
    if not bl.readable:
        return "NEEDS_REVIEW", "unreadable", [], {"_why": f"BL: {bl.error}"}

    # -- 2. Are they the documents we were promised? ------------------------
    # Before missing_value, because a Commercial Invoice has no ports and would
    # otherwise look like a document with blank fields rather than the wrong
    # document entirely.
    for doc, role in ((si, "SI"), (bl, "BL")):
        if doc.doc_type in ("invoice", "packing_list", "certificate_of_origin"):
            pretty = doc.doc_type.replace("_", " ")
            return ("NEEDS_REVIEW", "wrong_doc_type", [],
                    {"_why": f"attachment supplied as the {role} is a {pretty}"})

    # -- 3. Did we get all seven from both sides? ---------------------------
    missing = []
    for name in COMPARE_FIELDS:
        s, b = si.get(name), bl.get(name)
        if not s.usable or not b.usable:
            missing.append(name)
            evidence[name] = {
                "si": s.raw, "bl": b.raw, "result": "unknown",
                "si_source": s.source, "bl_source": b.source,
            }

    if missing:
        # NOTE: has_defect stays False and defect_fields stays empty here even
        # if some OTHER field visibly differs. Two unknowns are not a match and
        # a partial read is not a clean comparison - the case needs a human.
        return ("NEEDS_REVIEW", "missing_value", [],
                {**evidence, "_why": f"could not read: {', '.join(missing)}"})

    # -- 4. The actual comparison -------------------------------------------
    defects = []
    for name in COMPARE_FIELDS:
        s, b = si.get(name), bl.get(name)
        same = s.value == b.value
        if not same:
            defects.append(name)
        evidence[name] = {
            "si": s.value, "bl": b.value,
            "si_raw": s.raw, "bl_raw": b.raw,
            "si_source": s.source, "bl_source": b.source,
            "result": "match" if same else "differs",
        }

    if defects:
        return "MISMATCH", None, sorted(defects), evidence
    return "OK", None, [], evidence
