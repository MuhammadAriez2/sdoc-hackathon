What changed and when, including the things that went wrong. No scores: those
are the organizers' to produce.

| time      | what changed                                                                                                                                                                                                                                                                                                                                                         |
| --------- | -------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| Sat 16:20 | Repository scaffolded; submission shape matched to `sample_submission.json`                                                                                                                                                                                                                                                                                          |
| Sat 16:45 | Rule classifier, plain-text extraction and the deterministic comparator working end to end over the full inbox                                                                                                                                                                                                                                                       |
| Sat 16:50 | Fixed the **"draft BL" decoy**: every `SI_REQUEST` email in the dataset signs off _"Please revert with draft BL once available"_, and a classifier matching the bare string `draft bl` swallowed all 125 of them into `BL_COMPARISON`. Ordering the cascade so `BL_COMPARISON` is tested before `SI_REQUEST` is the single most consequential change in the project. |
| Sun       | QuayProof built: FastAPI backend, React inbox, evidence-backed extraction, Supabase persistence, Render deployment                                                                                                                                                                                                                                                   |
| Mon 16:04 | Gemini live run over 37 of 520 records, zero errors, zero fallbacks — raw output committed as `quayproof/ai-test-report.json`                                                                                                                                                                                                                                        |
| Mon 17:10 | Reviewing that run's own output: six comparison emails escalated as `missing_attachment` whose bodies were _requests_ for a draft, not reports of a lost one. Fixed in `pipeline.attachment_intent`.                                                                                                                                                                 |
| Mon 18:30 | Cross-checking QuayProof against the `baseline/` control surfaced a second defect: QuayProof was not stripping trailing port codes, so every mixed-format port pair reported a discrepancy on documents that agreed. Fixed in `normalize.PORT_CODE`.                                                                                                                 |

The last two rows are the ones worth reading. Both are defects we found in our
own work rather than ones that were reported to us, and both are the kind that
cost an operator's trust rather than a test case.

Full detail in `RESULTS.md`; the complete verification list is in
`quayproof/docs/VALIDATION.md`.
