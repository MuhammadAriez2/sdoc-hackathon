# Measured results

Every number on this page was produced by the organizers' own evaluator
(`score_cli.py` / `scoring.py` from the participant bundle) against
`ground_truth.json`. Nothing here is self-assessed, and nothing here is an
estimate. Where a measurement is partial, the scope is stated in the same
sentence as the number.

The ground-truth file was used only as a scoring oracle through the supplied
evaluator. It is not read by any pipeline in this repository, it is not
committed here, and no value from it is hardcoded anywhere.

---

## 1. Deployed application — QuayProof with Gemini

**Score: 0.9757 on the 37 records processed.** Measured 21 Sep 2026.

Provider fingerprint recorded with every prediction:
`quayproof-1.0:gemini:gemini-3.5-flash-lite:prompt-1:gemini-schema-2`

| Axis | Value |
|---|---|
| **Final (weighted)** | **0.9757** |
| Stage 1 — classification macro-F1 | 0.9190 |
| Stage 1 — classification accuracy | 0.9459 (35/37) |
| Stage 3 — defect precision | **1.000** |
| Stage 3 — defect recall | **1.000** |
| Stage 3 — defect F1 | **1.000** |
| Field-level F1 | **1.000** |
| Exact defect-set match | **1.000** |
| End-to-end defect catch | **1.000** (4/4) |

The end-to-end metric is the strictest one in the evaluator: a defect only
counts if the email was routed to `BL_COMPARISON` *and* the exact set of
mismatched fields was flagged — no extras, no omissions. Four of four.

**Scope, stated plainly.** 37 of 520 records. The application enforces a
100-call daily AI budget (`AI_DAILY_CALL_LIMIT`), and a full 520-record pass
exceeds the free-tier quota available to this team. These 37 are
`email_001`–`email_037`, processed in order, not selected for favourability.
Thirty-seven records is a small sample and the macro-F1 in particular is noisy
at this size — two of the five categories appear only twice each. It is
reported because it is real, not because it is sufficient.

### Classification confusion matrix

Actual → predicted, 37 records:

| Actual | Predicted |
|---|---|
| BL_COMPARISON (14) | BL_COMPARISON 14 |
| SI_REQUEST (13) | SI_REQUEST 13 |
| INVOICE_QUERY (4) | INVOICE_QUERY 4 |
| SPAM (2) | SPAM 2 |
| GENERAL (4) | GENERAL 2, BL_COMPARISON 1, SI_REQUEST 1 |

Both errors are the same shape: an automated internal notice pulled into a work
category. These emails deliberately contain decoy phrasing — an HR or RPA
notice whose body mentions "submit SI" or "outstanding BL". No document-work
email was ever misrouted *out* of its category, which is the error that would
actually cost a customer.

### The weakness this measurement found

**Escalation precision: 0.000. Seven cases escalated, zero genuinely needed
it.**

This is the honest headline alongside the good one, and it is worth more than
the score is.

Six of the seven are one bug with one cause. `backend/app/pipeline.py` returns
`missing_attachment` whenever a comparison email carries fewer than two
documents:

```python
if len(docs) < 2:
    reason = 'missing_attachment'
```

But `email_003`, `006`, `011`, `016`, `018` and `036` have zero attachments
*because the sender is asking a colleague to send the draft BL* — "please
assist to send the draft BL for SIN832764835 for checking asap". Ground truth
marks all six **OK**. Nobody forgot an attachment; there was never one to
forget. Across the full 520 there are roughly 91 emails of this shape.

The distinction is entirely in the wording of the body: an email that says
"the attachments appear to have been dropped" is a genuine escalation, and an
email that says "please send me the draft" is a valid request with nothing to
check yet.

**This is now fixed.** `pipeline.attachment_intent` reads the sender's own
words, with any quoted reply chain stripped, and escalates only when the body
reports attachments as expected-and-missing — or when one document is already
present, in which case its counterpart is genuinely absent regardless of
wording. Five tests in `test_core.py` cover it; sixteen real wordings were
checked, including the exact sentence above. `docs/VALIDATION.md` states the
trade-off the fix accepts.

The measured 0.9757 predates the fix. The fix touches neither classification,
extraction nor comparison, and the evaluator excludes escalation from the
weighted score, so the figure is expected to hold — but it has not been re-run,
and this file does not claim a number it has not measured.

The seventh, `email_005`, escalated `missing_value` on two XLSX attachments
that ground truth marks OK — a gap in the Excel extraction path, not the same
cause.

**This does not affect the weighted score.** The evaluator computes the final
figure from stage 1, stage 3 and end-to-end only; escalation is a diagnostic
axis. But a tool that sends operators to check ninety-one cases that were
already fine is a tool operators learn to ignore, so it is a product defect
regardless of what it does to a leaderboard.

---

## 2. Deterministic baseline — `baseline/`

**Score: 0.8258 across all 520 records.** No AI of any kind.

| Axis | Value |
|---|---|
| Final (weighted) | 0.8258 |
| Stage 1 macro-F1 | 1.000 |
| Defect precision | 1.000 |
| Defect recall | 0.717 (33/46) |
| Escalation recall | 1.000 (20/20) |
| Escalation precision | 0.444 |
| End-to-end | 0.717 |

This exists as a control, and it earns its place by making one thing
measurable: a rule-based classifier reaches macro-F1 1.000 on *this* generated
inbox, which tells you the inbox is synthetic, not that classification is
solved. The 13 missed defects are all in PDF / XLSX / DOCX attachments the
baseline does not parse — it escalates them honestly rather than guessing,
which is why its escalation precision is low and its defect precision is
perfect.

Development history is in `RUNLOG.md`. The single most expensive bug was worth
0.073: every `SI_REQUEST` email in the dataset signs off "Please revert with
draft BL once available", and a classifier matching the bare string `draft bl`
swallowed all 125 of them into `BL_COMPARISON`.

---

## 3. Reproducing these numbers

Deterministic baseline, full dataset. This needs the organizers' `loader.py`,
`inbox/`, `attachments/`, `tools/score_cli.py` and `secrets/ground_truth.json`
copied into the repository root — none of them are redistributed here, and
`score_baseline.py` says so rather than failing with an import error:

```bash
python score_baseline.py --score
```

Deployed application: the inbox **Export** button produces `submission.json`,
which the organizers' CLI scores directly:

```bash
python tools/score_cli.py submission.json --ground-truth ground_truth.json
```

The 0.9757 figure was produced by scoring the predictions in
`quayproof/ai-test-report.json` with `scoring.score_all`, restricting ground
truth to the 37 record IDs that file contains. That report is committed, so the
measurement is checkable without rerunning any AI calls.

---

## 4. What is not claimed

- **No full-dataset score for the deployed application.** 37 records were
  processed; 520 were not. Any figure quoted for the deployed app carries that
  scope or it is wrong.
- **No claim is made for a 1.0000 score.** A separate pure-Python pipeline
  reached that figure during development. It is not in this repository and is
  not scored here, so it is not this project's result and is not presented as
  one anywhere in this submission.
- **No production readiness claim.** One Render free instance, one worker, a
  shared team token rather than per-user identity, and a 100-call daily budget.
- **Live accuracy is measured on synthetic organizer data only.** No real
  customer document has been through this system.
