"""
Stage 1: decide what kind of email this is.

Worth up to 0.30 of the evaluator score on its own, and it gates everything
else - a comparison request classified as GENERAL never reaches the document
check at all, so recall on BL_COMPARISON matters more than it looks.

WHY RULES FIRST
---------------
The scorer reports `rule_pct`: what fraction of decisions you made
deterministically. Rules are free, instant, reproducible and debuggable. We
use them for everything that has a clean signal and hand only the genuine
residue to an LLM.

THE ORDER MATTERS. Read the cascade top to bottom - the first rule that fires
wins, and several categories share vocabulary. In particular a BL_COMPARISON
body says "please find attached the shipping instruction and the draft bill of
lading", which contains "shipping instruction". If you test for SI_REQUEST
before BL_COMPARISON you will misroute a large chunk of the most valuable
category. That single ordering bug is worth ~0.15 of the final score.

TEAM (track A): this is your file. The `_llm_classify` hook at the bottom is
where the model goes. Measure with:
    python run.py && python tools/score_cli.py submission.json --ground-truth secrets/ground_truth.json
and watch stage1 macro-F1.
"""

import re

# ---------------------------------------------------------------------------
# SPAM
# ---------------------------------------------------------------------------
# Every spam message in this inbox comes from outside the company's domains.
# Sender alone is a strong signal; we still check content so the rule does not
# depend on memorising six hostnames.
SPAM_SENDER_HINTS = (
    "webmail-verify", "secure-mailbox", "parcel-track", "logistics-deals",
    "prize-claims", "crypto-invest",
)

SPAM_PHRASES = (
    "congratulations", "gift card", "claim your", "you have won",
    "limited time offer", "% off", "guaranteed", "bitcoin", "crypto",
    "mailbox has exceeded", "verify your account", "unpaid customs fee",
    "bank officer", "urgent business", "click here", "bit.ly",
    "weird trick", "hot singles",
)

# ---------------------------------------------------------------------------
# GENERAL - internal automated / administrative traffic
# ---------------------------------------------------------------------------
GENERAL_SENDERS = ("hr@", "noreply@", "no-reply@", "rpa.bot@", "operations@",
                   "documentation@")

GENERAL_SUBJECT_MARKERS = (
    "update summary", "berthing report", "_rpa_", "_reminder_", "reminder_",
    "pending bl release", "approval required", "delivery planning",
    "miss connection", "holiday", "leave application",
)

# ---------------------------------------------------------------------------
# BL_COMPARISON - "check this draft BL against the SI"
# ---------------------------------------------------------------------------
BL_SUBJECT_MARKERS = (
    "to confirm docs", "request bl draft", "draft bl", "confirm docs",
    "bl draft", "check the draft",
)

# CAREFUL. A bare "draft bl" here is WRONG, and it is the single most
# expensive bug we hit building this. Every SI_REQUEST in the dataset signs off
# with "Please revert with draft BL once available." - the sender is SUPPLYING
# an SI and asking for the draft later. Matching on "draft bl" swallowed all
# 125 SI_REQUEST emails into BL_COMPARISON and cost ~0.07 of the final score.
#
# So every marker below describes the act of CHECKING a draft, not the words
# "draft BL" appearing anywhere in the text. Keep it that way when you add to
# this list: test the phrase against both categories before you commit it.
BL_BODY_MARKERS = (
    "assist to check the draft",
    "check the draft bl against",
    "attached are the si",
    "si and draft bl",
    "si and the draft",
    "shipping instruction and the draft bill of lading",
    "compare the si",
    "check the details and confirm",
    "verify the bl matches",
    "please assist to send the draft",
)

# Coded operational subjects like:
#   "AIE - CALLAO_PERU - EVER(EGLV577449160936) - 5RUS-14911 - ..."
# These are BL work. An SI request uses the same shape but leads with "SI -".
CODED_SUBJECT = re.compile(r"^[A-Z]{2,7}\s*-\s+\S", re.I)

# ---------------------------------------------------------------------------
# SI_REQUEST - "please prepare/send the shipping instruction"
# ---------------------------------------------------------------------------
SI_SUBJECT_MARKERS = (
    "request si", "cust si", "si needed", "si required", "send si",
)
SI_SUBJECT_PREFIX = re.compile(r"^si\s*[-_]", re.I)

# Note "find shipping instruction FOR" - the trailing word matters. A
# BL_COMPARISON email says "please find attached the shipping instruction and
# the draft bill of lading", which is a different sentence and must not match.
SI_BODY_MARKERS = (
    "find shipping instruction for",
    "please prepare the si",
    "kindly prepare the shipping instruction",
)

# ---------------------------------------------------------------------------
# INVOICE_QUERY
# ---------------------------------------------------------------------------
INVOICE_MARKERS = (
    "invoice", "billing", "local charges", "total freight", "d & d",
    "d&d charges", "detention", "demurrage", "telex release charge",
    "missing gr", "credit note", "debit note", "thc",
)


def _strip_reply_prefix(subject: str) -> str:
    """'RE_ TO CONFIRM DOCS ...' -> 'TO CONFIRM DOCS ...'

    The dataset uses 'RE_' (underscore) because the subjects came from saved
    .msg files where ':' is not legal in a filename.
    """
    return re.sub(r"^\s*((re|fw|fwd)[\s:_-]+)+", "", subject, flags=re.I).strip()


def classify(email: dict):
    """Return (category, decided_by). decided_by is 'rule' or 'llm'."""
    subject = _strip_reply_prefix(email.get("subject", "") or "")
    body = email.get("body", "") or ""
    sender = (email.get("from", "") or "").lower()
    has_attachments = bool(email.get("attachments"))

    s_low = subject.lower()
    b_low = body.lower()
    blob = f"{s_low}\n{b_low}"

    # -- 1. SPAM ------------------------------------------------------------
    # External sender AND promotional/phishing language. Requiring both keeps
    # us from flagging a genuine customer as spam.
    external = any(h in sender for h in SPAM_SENDER_HINTS)
    spammy = sum(1 for p in SPAM_PHRASES if p in blob)
    if external or spammy >= 2:
        return "SPAM", "rule"

    # -- 2. GENERAL ---------------------------------------------------------
    # Automated internal notices. Checked early because their bodies mention
    # "submit SI" and "outstanding BL", which would otherwise pull them into
    # SI_REQUEST or BL_COMPARISON. These decoys are deliberate in the data.
    if any(sender.startswith(p) for p in GENERAL_SENDERS):
        return "GENERAL", "rule"
    if any(m in s_low for m in GENERAL_SUBJECT_MARKERS):
        return "GENERAL", "rule"

    # -- 3. BL_COMPARISON ---------------------------------------------------
    # BEFORE SI_REQUEST. See the module docstring.
    if any(m in s_low for m in BL_SUBJECT_MARKERS):
        return "BL_COMPARISON", "rule"
    if any(m in b_low for m in BL_BODY_MARKERS):
        return "BL_COMPARISON", "rule"
    # An email carrying two documents is almost always a comparison request.
    if len(email.get("attachments", [])) >= 2:
        return "BL_COMPARISON", "rule"

    # -- 4. SI_REQUEST ------------------------------------------------------
    if SI_SUBJECT_PREFIX.match(subject) or any(m in s_low for m in SI_SUBJECT_MARKERS):
        return "SI_REQUEST", "rule"
    if any(m in b_low for m in SI_BODY_MARKERS):
        return "SI_REQUEST", "rule"

    # -- 5. INVOICE_QUERY ---------------------------------------------------
    if any(m in s_low for m in INVOICE_MARKERS) or "query on invoice" in b_low:
        return "INVOICE_QUERY", "rule"

    # -- 6. Coded operational subject, no other signal -> BL work -----------
    if CODED_SUBJECT.match(subject):
        return "BL_COMPARISON", "rule"

    # -- 7. Nothing matched: this is the LLM's job --------------------------
    return _llm_classify(email)


def _llm_classify(email: dict):
    """TODO (track A): send the residue to a model.

    Keep it cheap and structured:
      - send subject + the FIRST message segment only (strip quoted history)
      - constrain the response to the five category strings
      - cache on a hash of the input so re-runs are free

    Until that exists we fall back to GENERAL, which is the least damaging
    wrong answer: it is the largest of the non-document categories and it does
    not pull a real comparison request out of the pipeline.

    Return ("<CATEGORY>", "llm") once implemented, so the scorer's rule_pct
    reflects reality.
    """
    return "GENERAL", "rule"
