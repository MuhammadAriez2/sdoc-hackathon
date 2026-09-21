"""
The contract every module codes against.

WHY THIS FILE EXISTS
--------------------
Four people are working in parallel. If the extractors, the comparator and the
UI each invent their own shape for "a field I read out of a document", nothing
integrates until the last night. So we fix the shape here, first, and everyone
builds against it.

THE KEY DESIGN DECISION
-----------------------
A Field carries THREE things, not one:

    value       what we read
    confidence  how sure we are we read it correctly
    source      where in the document it came from

That third-and-second pair is what makes NEEDS_REVIEW possible. Without them,
"I could not read the consignee" and "the consignee is blank" and "the
consignee differs" all collapse into the same thing, and the system reports a
mismatch when it should be asking a human. Almost every false alarm in this
problem comes from losing that distinction.

`source` also feeds the UI: clicking a field should show where the value came
from. That is the evidence trail the judges' rubric rewards.
"""

from dataclasses import dataclass, field as dc_field
from typing import Optional, Union

# ---------------------------------------------------------------------------
# Enums (plain strings so they serialise straight into submission.json)
# ---------------------------------------------------------------------------

CATEGORIES = ["BL_COMPARISON", "SI_REQUEST", "INVOICE_QUERY", "GENERAL", "SPAM"]

STATUSES = ["OK", "MISMATCH", "NEEDS_REVIEW"]

REVIEW_REASONS = [
    "wrong_doc_type",      # the "BL" is actually an invoice / packing list / COO
    "missing_attachment",  # a comparison was asked for but a document is absent
    "unreadable",          # scan with no text layer, empty file, corrupt bytes
    "missing_value",       # document readable but a required field is blank
]

# The seven fields we compare. Order matters only for display.
COMPARE_FIELDS = [
    "shipper",
    "consignee",
    "notify_party",
    "port_of_loading",
    "port_of_discharge",
    "container_count",
    "gross_weight_kg",
]


# ---------------------------------------------------------------------------
# One field read out of one document
# ---------------------------------------------------------------------------

@dataclass
class Field:
    """A single value read from a document, with its provenance.

    confidence convention (keep this consistent across all extractors):
        1.0  read cleanly from an unambiguous labelled line
        0.5  read, but something was odd (guessed label, ambiguous layout)
        0.0  NOT FOUND, or found but blank ("???", "N/A", "_____")

    Anything at 0.0 must never be compared. It routes to NEEDS_REVIEW.
    """
    value: Optional[Union[str, int]] = None
    confidence: float = 0.0
    source: str = ""            # e.g. "SI line 7" or "BL sheet1!B4"
    raw: Optional[str] = None   # the text exactly as it appeared, before parsing

    @property
    def usable(self) -> bool:
        """True if this value is trustworthy enough to compare."""
        return self.value is not None and self.confidence > 0.0


@dataclass
class Extracted:
    """Everything we managed to read out of ONE document (an SI or a BL).

    Every extractor — txt, xlsx, pdf, docx — returns this exact type. That is
    what lets the comparator stay format-blind, and it is what lets four people
    write four extractors without talking to each other.
    """
    doc_role: str = ""              # "SI" or "BL"
    doc_type: Optional[str] = None  # what the document actually IS, by content
    readable: bool = True           # False => no text could be pulled out at all
    error: Optional[str] = None     # why it was unreadable, if it was
    path: str = ""

    shipper: Field = dc_field(default_factory=Field)
    consignee: Field = dc_field(default_factory=Field)
    notify_party: Field = dc_field(default_factory=Field)
    port_of_loading: Field = dc_field(default_factory=Field)
    port_of_discharge: Field = dc_field(default_factory=Field)
    container_count: Field = dc_field(default_factory=Field)
    gross_weight_kg: Field = dc_field(default_factory=Field)

    def get(self, name: str) -> Field:
        """Fetch a field by name, so the comparator can loop over COMPARE_FIELDS."""
        return getattr(self, name)

    def missing_fields(self):
        """Which of the seven we could not read. Drives `missing_value`."""
        return [f for f in COMPARE_FIELDS if not self.get(f).usable]


# ---------------------------------------------------------------------------
# The verdict for one email — this is what becomes submission.json
# ---------------------------------------------------------------------------

@dataclass
class EmailResult:
    email_id: str
    category: str = "GENERAL"
    status: str = "OK"
    review_reason: Optional[str] = None
    has_defect: bool = False
    defect_fields: list = dc_field(default_factory=list)

    # Not exported to the scorer, but used by the UI and for debugging.
    decided_by: str = "rule"        # "rule" or "llm" - the scorer reports this
    evidence: dict = dc_field(default_factory=dict)
    notes: str = ""

    def to_submission(self) -> dict:
        """The exact five keys the evaluator wants. Nothing else."""
        return {
            "category": self.category,
            "status": self.status,
            "review_reason": self.review_reason,
            "has_defect": self.has_defect,
            "defect_fields": sorted(self.defect_fields),
        }
