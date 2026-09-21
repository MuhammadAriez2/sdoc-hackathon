# Baseline — the same task, without AI

A rule-based classifier and plain text extraction over the same 520-record
inbox, scored by the same evaluator. **This is a control, not a product. The
submission is QuayProof, in `quayproof/`.**

| | Records | Score |
|---|---|---|
| This baseline | 520 of 520 | 0.8258 |
| QuayProof (Gemini) | 37 of 520 | 0.9757 |

It exists to answer one question: what did the AI actually buy? Without a
control, "we used a model" is an assertion. With one, the difference is
measurable.

It earns its place a second way. A keyword classifier reaches macro-F1 **1.000**
on this inbox. That does not mean classification is solved; it means the inbox
is generated. Knowing that changes how much weight the 0.9190 macro-F1 in
`RESULTS.md` deserves, and it is not something you can learn without building
the baseline.

Where it loses: 13 defects in PDF, XLSX and DOCX attachments it cannot parse.
It escalates them rather than guessing, which is why its defect precision is
1.000 and its escalation precision is 0.444.

## Running it

Needs the organizers' material copied into the repository root — `loader.py`,
`inbox/`, `attachments/`, `tools/score_cli.py` and `secrets/ground_truth.json`.
None of it is redistributed here.

```bash
python score_baseline.py --score      # full run, then score
python score_baseline.py --email 004  # one email, verbosely
```

Full breakdown in `RESULTS.md` §2. Development history in `RUNLOG.md`.
