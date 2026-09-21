"""
Orchestration: one email in, one EmailResult out.

This is the file that encodes the decision tree from the brief. Read `process`
top to bottom and you have the whole system.
"""

import os

from .contracts import EmailResult
from .classify import classify
from .extract import extract
from .compare import compare

# Phrases that mean "documents were supposed to be here and are not".
#
# THE SUBTLEST RULE IN THE WHOLE PROBLEM:
# 91 comparison emails have zero attachments and are correctly OK - they are
# asking a colleague to SEND the draft BL ("please assist to send the draft BL
# for SIN832764835 for checking asap"). Only a handful are genuine escalations,
# where the sender believed they had attached something.
#
# Treat every empty comparison email as missing_attachment and you wreck both
# classification and escalation precision. The difference is entirely in the
# wording of the body.
#
# This is deliberately string matching, and deliberately narrow. QuayProof
# solves the same problem in `pipeline.attachment_intent`, where it is still
# rules rather than a model: "did the sender believe they attached documents?"
# has to be reproducible, because it decides whether an operator is sent to
# review a case that was never broken.
ATTACHMENT_EXPECTED = (
    "appear to have been dropped",
    "still missing",
    "did not attach",
    "forgot to attach",
    "attachment missing",
)


def _looks_like_si(path: str) -> bool:
    """Filename hint only - the content check in compare() is the real test.

    The brief warns that a file named BL may not be a BL, which is why this is
    a hint for PAIRING and never the basis for a verdict.
    """
    return "_si" in os.path.basename(path).lower()


def process(email: dict, root: str = ".") -> EmailResult:
    eid = email["email_id"]
    attachments = email.get("attachments", []) or []

    # -- Stage 1: what kind of email is this? -------------------------------
    category, decided_by = classify(email)
    res = EmailResult(email_id=eid, category=category, decided_by=decided_by)

    # Four of the five categories are classify-only. They are done here, and
    # that is most of the inbox.
    if category != "BL_COMPARISON":
        return res

    body = (email.get("body", "") or "").lower()

    # -- No attachments -----------------------------------------------------
    if not attachments:
        if any(p in body for p in ATTACHMENT_EXPECTED):
            res.status = "NEEDS_REVIEW"
            res.review_reason = "missing_attachment"
            res.notes = "body implies documents were attached, but none present"
        else:
            # "Please send me the draft BL" - a valid request, nothing to check
            # yet, and emphatically not a defect.
            res.notes = "comparison requested, documents not sent yet"
        return res

    # -- Exactly one attachment: we cannot compare one document -------------
    if len(attachments) < 2:
        res.status = "NEEDS_REVIEW"
        res.review_reason = "missing_attachment"
        res.notes = f"only {len(attachments)} document supplied"
        return res

    # -- Two documents: pair them, read them, compare them ------------------
    si_path = next((a for a in attachments if _looks_like_si(a)), attachments[0])
    bl_path = next((a for a in attachments if a != si_path), attachments[-1])

    si = extract(si_path, "SI", root=root)
    bl = extract(bl_path, "BL", root=root)

    status, reason, defects, evidence = compare(si, bl)

    res.status = status
    res.review_reason = reason
    res.defect_fields = defects
    res.has_defect = status == "MISMATCH"
    res.evidence = evidence
    return res


def run_all(emails, root: str = "."):
    """Process every email. Returns {email_id: EmailResult}.

    Never let one bad document stop the run - the submission must contain all
    520 ids or the evaluator treats the missing ones as wrong.
    """
    results = {}
    for email in emails:
        eid = email["email_id"]
        try:
            results[eid] = process(email, root=root)
        except Exception as exc:                  # noqa: BLE001
            r = EmailResult(email_id=eid, category="BL_COMPARISON",
                            status="NEEDS_REVIEW", review_reason="unreadable")
            r.notes = f"pipeline error: {type(exc).__name__}: {exc}"
            results[eid] = r
    return results
