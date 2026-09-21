# Scoring run log

Every scoring run against the organizers' evaluator gets a line here, including
the ones that went backwards. This is the development record, not a summary —
`RESULTS.md` has the breakdown of the two figures that matter.

| time | score | what changed |
|------|-------|--------------|
| Sat 16:20 | 0.0124 | do-nothing baseline (organizers' sample_submission.json) |
| Sat 16:45 | 0.7525 | rule classifier + txt extraction + deterministic comparator |
| Sat 16:50 | 0.8258 | fixed "draft BL" decoy that swallowed all 125 SI_REQUEST emails |
| Mon 16:04 | — | QuayProof + Gemini live run over 37 of 520 records, 0 errors (`ai-test-report.json`) |
| Mon 17:10 | **0.9757** | scored that run on its 37 records: defect P/R/F1 all 1.000, end-to-end 4/4, classification 35/37 |

Scope note: 0.8258 is the deterministic baseline across **all 520** records.
0.9757 is the deployed Gemini application across the **37** records it has
processed. They are not comparable figures and must never be quoted as if they
were. Full breakdown in `RESULTS.md`.
