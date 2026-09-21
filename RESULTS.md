# Results

What we checked, what we found, and how you can check it yourself.

This project is presented on its behaviour, not on a leaderboard figure. The
checks in section 1 need no answer key: they are reproducible from this
repository or visible in the running application. Section 4 records a
measurement against the organizers' evaluator, kept because it is real, with
its scope stated. We do not quote it as a headline.

The organizers' ground-truth file was used only as a scoring oracle through
their supplied evaluator. No pipeline here reads it, it is not committed, and
no value from it is hardcoded anywhere.

---

## 1. What we verified

| Check | Evidence |
|---|---|
| **All four document formats** | `test_docx_tables`, `test_xlsx_cell_evidence`, `test_native_pdf_page_evidence`, `test_scanned_pdf_ocr` pass against the real libraries and a real Tesseract. The OCR test runs; it does not skip. |
| **Corrupt input fails visibly** | `demo-files/unreadable.pdf` produces a parse error and an `unreadable` escalation. Never a false `OK`. |
| **Case, punctuation and units normalise** | NFKC plus case folding plus punctuation collapse for text; Decimal arithmetic for weights, with MT and lbs converted to kg and ambiguous separators rejected rather than guessed. |
| **Evidence is enforced, not requested** | A value whose quote is absent from its source block, or which is absent from its own quote, is rejected outright rather than scored lower. |
| **Reliability of the AI path** | 37 records processed end to end with live Gemini calls: zero errors, zero silent fallbacks. A reliability observation, not an accuracy claim. |
| **It runs** | 53 backend tests passing; Docker image builds and runs; the public deployment is live and has compared a Word pair and an Excel pair correctly. |

```bash
cd quayproof && python -m pytest backend/tests -q
```

---

## 2. The assumptions the design rests on

Each is enforced in code, not by convention. `docs/VALIDATION.md` carries the
detail.

**A model that cites nothing gets no credit.** Every extracted value arrives
with a quote and the block it came from, and is discarded if either fails to
check out. This is what makes a confident hallucination fail closed instead of
entering a comparison.

**OCR digits must not be trusted silently.** Tesseract returns a heuristic, not
a probability. Gross weight and container count read from a scan always ask a
human. Text fields from the same scan still compare automatically.

**Two unknowns are not a match.** An unreadable field escalates; it never
counts as agreement, and it never counts as a defect.

**Comparison must be reproducible.** No model call happens after extraction.
The same two documents produce the same verdict on every run.

---

## 3. A defect we found in our own output, and fixed

Every comparison email carrying fewer than two documents was escalated as a
missing attachment. That was wrong for a whole class of email: many senders are
asking a colleague to *send* the draft bill of lading, not forgetting to attach
one. Roughly 91 records across the dataset have that shape, and each would have
sent an operator to review a case that needed none.

The signal is in the wording of the body. `pipeline.attachment_intent` now
separates the two, covered by tests including one that ensures a quoted reply
cannot supply the intent. An email that says the attachments were dropped still
escalates; an email asking for a document is recorded as having nothing to
compare yet.

We found this by checking our own output rather than by being told about it,
which is the reason it is written up here rather than left quiet.

---

## 5. What is not claimed

- **No full-dataset score for the Gemini pipeline.** 37 records were processed;
  520 were not.
- **No production readiness.** One free Render instance, one worker, a shared
  workspace rather than per-user identity, and a 100-call daily AI budget.
- **No real customer documents.** Everything here is organizer-supplied
  synthetic data or fixtures we authored.
- **No measured time saving.** We did not measure it, so we do not assert it.
