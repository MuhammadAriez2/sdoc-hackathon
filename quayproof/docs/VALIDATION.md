# Validation

What has actually been checked, what has not, and how to repeat each check.

This file distinguishes three things that are easy to blur together: a passing
unit test, a working live deployment, and a measured score against the
organizers' evaluator. All three exist for this project; they are not the same
evidence and are not presented as such.

Last updated 21 Sep 2026.

---

## Verified

| # | Check | Evidence | Date |
|---|---|---|---|
| 1 | **Backend test suite** — 53 tests pass | `python -m pytest backend/tests -q` → `53 passed in 2.40s` | 21 Sep |
| 2 | **All four document formats** parse with real dependencies | `test_formats.py` — `test_docx_tables`, `test_xlsx_cell_evidence`, `test_native_pdf_page_evidence`, `test_scanned_pdf_ocr` all PASSED against Tesseract 5.3.4 / leptonica 1.82.0. The OCR test did **not** skip. | 21 Sep |
| 3 | **Docker image builds and runs** | Built and run on a Windows host via Docker Desktop; app served at `localhost:8000`, demo inbox loaded, cases processed. | 20 Sep |
| 4 | **Supabase is live** | Schema applied; `qp_cases`, `qp_ai_usage` and the three RPCs exist; private `quayproof-documents` bucket created; cases and documents survive a service restart. | 20 Sep |
| 5 | **Render deployment is live and public** | Docker service on the free plan, `/api/health` responding, token gate working, full inbox → comparison → evidence → human-action flow exercised in a browser. | 20 Sep |
| 6 | **Gemini is doing real work in production** | 37 records processed end to end against the live deployment, zero errors, zero fallbacks. Provider fingerprint recorded per prediction: `gemini-3.5-flash-lite`. Raw output committed as `ai-test-report.json`. | 21 Sep |
| 7 | **Measured against the organizers' evaluator** | 0.9757 on those 37 records; 0.8258 for the deterministic baseline across all 520. See `RESULTS.md`. | 21 Sep |
| 8 | **Corrupt input fails visibly** | `demo-files/unreadable.pdf` yields a parse error and an `unreadable` escalation — never a false `OK`. | 20 Sep |
| 9 | **Case and punctuation normalise correctly** | `normalize.text_key` applies NFKC + `casefold` + punctuation collapse. `Port Klang`, `PORT KLANG` and `port klang` compare equal; confirmed in the live UI, where the normalised key is displayed under each raw value. | 20 Sep |
| 10 | **Weight units normalise across systems** | MT → kg (×1000), lbs → kg (×0.45359237), grouped thousands parsed, ambiguous separators rejected rather than guessed. Covered in `test_core.py`. | 21 Sep |
| 11 | **Browser smoke test passes** | `node scripts/smoke-browser.mjs` against a local demo instance → `PASS: demo import, comparison, source evidence, review approval guard, desktop/mobile rendering; no browser exceptions.` Asserts zero browser exceptions and no mobile horizontal overflow. | 21 Sep |
| 12 | **Attachment intent is distinguished from attachment loss** | `attachment_intent` in `pipeline.py`, five cases in `test_core.py`. A comparison email with no documents whose body requests one resolves `OK`; one whose body reports a dropped or forgotten attachment still escalates; one document present always escalates. | 21 Sep |

---

## Assumptions the design rests on, and the evidence for each

**"A model that cites nothing should get no credit."**
Every extracted value carries a quote and the block IDs it came from.
`pipeline.observation` rejects the value outright if the quote is absent from
the source blocks or the raw value is absent from the quote. Tested by
`test_core.py` evidence-rejection cases. This is the mechanism that makes a
confident hallucination fail closed instead of entering a comparison.

**"OCR digits must not be trusted silently."**
Tesseract returns a confidence heuristic, not a probability. A `6` read as `5`
in a gross weight is a plausible-looking number that is wrong by tonnes, and
nothing downstream can detect it. `pipeline.py` therefore escalates
`gross_weight_kg` and `container_count` to human confirmation whenever the
evidence came through OCR, regardless of reported confidence. This is a
deliberate precision-over-recall trade on exactly two fields — text fields from
OCR still compare automatically.

**"Two unknowns are not a match."**
A field that could not be read is marked `UNKNOWN` and forces
`NEEDS_REVIEW`; it never counts as agreement and never counts as a defect. A
confirmed defect elsewhere in the same document still surfaces — an unreadable
field does not suppress a discrepancy the system did establish.

**"Comparison must be reproducible."**
No AI call occurs after extraction. `pipeline.compare` is pure Python over
normalised strings. The same two documents produce the same verdict on every
run, which is what makes the evaluator score meaningful at all.

---

## Not verified

| Gap | Status |
|---|---|
| **Full 520-record run of the deployed app** | Not done. 37 records processed; the app's 100-call daily budget and the free-tier Gemini quota do not permit a full pass. `RESULTS.md` scopes every deployed figure accordingly. |
| **DOCX and XLSX through the live deployment** | Passing as unit tests against real libraries (check 2), but the live Render instance has been exercised with TXT and PDF pairs only. |
| **Ollama provider** | Implemented in `providers.py`. No test coverage; never executed. Gemini is the only provider exercised. |
| **Re-measurement after the escalation fix** | The 0.9757 figure predates check 12. The fix does not touch classification, extraction or comparison, and the evaluator's weighted score excludes escalation, so the weighted figure is expected to be unchanged — but it has not been re-run against the evaluator. |
| **Concurrency and lease recovery under load** | The 30-minute lease and optimistic-concurrency paths are unit-tested. Not exercised with real concurrent workers. |
| **Any real customer document** | None. All validation uses organizer-supplied synthetic data or synthetic fixtures authored for this project. |

---

## Defect found by measurement, and fixed

**Zero-attachment comparison emails were over-escalated.**

The 0.9757 run exposed escalation precision of 0.000: seven cases escalated,
none of which needed it. Six were one bug. `pipeline.compare` returned
`missing_attachment` for any comparison email with fewer than two active
documents, but `email_003`, `006`, `011`, `016`, `018` and `036` carry no
attachments *because the sender is asking a colleague to send the draft BL*.
Ground truth marks all six OK. Roughly 91 of the full 520 records have this
shape.

`attachment_intent` now reads the sender's own words, with any quoted reply
chain stripped, and separates the two cases explicitly:

| Body signals | Result |
|---|---|
| Attachments expected and lost — "forgot to attach", "appear to have been dropped", "could not open the attachment" | `NEEDS_REVIEW`, `missing_attachment` |
| A document is being requested — "please assist to send", "kindly share", "revert with" | `OK`, with an operator note; nothing to compare yet |
| Neither, and no documents at all | `OK`, with an operator note |
| One document present, whatever the wording | `NEEDS_REVIEW`, `missing_attachment` |

The last row is the important one: a single attachment always means its
counterpart is genuinely absent, so no wording can talk the system out of that
escalation.

The trade this makes, stated plainly: an email whose attachments were lost in a
wording none of these patterns match now resolves `OK` instead of escalating.
That is a deliberate choice — over-escalation was measured at roughly ninety
cases, under-escalation in unmatched wording is not measurable from this
dataset, and the zero-document case has nothing to compare either way. Sixteen
real wordings were checked against the patterns; see `test_core.py`.

The seventh escalation, `email_005`, is unrelated: `missing_value` on two XLSX
attachments that ground truth marks OK, a gap in the Excel extraction path.
**Still open.**

---

## Repeating the checks

```bash
# 1, 2, 10 — test suite including real OCR
cd quayproof
python -m pytest backend/tests -q

# 7 — deterministic baseline against the full dataset
cd ..
python run.py --score

# 7 — score the committed Gemini predictions without spending AI quota
python tools/score_cli.py submission.json --ground-truth ground_truth.json
```

Checks 3–6 require the team's own Docker, Supabase, Render and Gemini
credentials and cannot be reproduced from this repository alone.
