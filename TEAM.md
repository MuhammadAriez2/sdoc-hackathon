# Team handoff — where the skeleton is, and what each of us takes

## Current score: 0.8258

```
stage1 macro-F1     1.000   classification — done
defect recall       0.717   33/46 — the 13 misses are all PDF/XLSX/DOCX pairs
defect precision    1.000   no false alarms
escalation recall   1.000   20/20 — all four review reasons caught
escalation precision 0.444  45 flagged vs 20 real — the 25 extra are the
                            unimplemented formats honestly declining to guess
end-to-end          0.717
```

Reproduce it:

```
python run.py --score
```

## What's built

| Module | State |
|---|---|
| `src/contracts.py` | The shared types. **Agree before changing** — everything imports this. |
| `src/synonyms.py` | Label → field map. **Append-only, shared.** |
| `src/classify.py` | Rule cascade, all five categories |
| `src/normalize.py` | Value normalisation (weights, ports, container counts) |
| `src/extract/base.py` | The parser every format feeds into |
| `src/extract/__init__.py` | Dispatcher — **txt done, xlsx/pdf/docx are stubs** |
| `src/compare.py` | Deterministic comparison, three outcomes |
| `src/pipeline.py` | Orchestration |
| `run.py` | Entry point + debug view |

No third-party packages needed yet — it runs on a clean Python. That changes when the format extractors land.

Inspect any single email:

```
python run.py --email 004    # a real mismatch, shows the field table
python run.py --email 516    # missing_value escalation
python run.py --email 501    # wrong_doc_type — the "BL" is an invoice
```

## The four tracks

Each is independent once `contracts.py` is agreed. Every one of them is measured by re-running `python run.py --score`.

**A — Classifier + LLM (`src/classify.py`)**
Rules hit 1.000 on this dataset, which means they fit *this* generated inbox closely, not that classification is solved. Your job is the part that generalises: implement `_llm_classify` for the residue, and replace the brittle `ATTACHMENT_EXPECTED` string match in `pipeline.py` with a real intent question. This is also where the "meaningful AI" requirement gets satisfied — make sure the model is doing visible work, not decoration.

**B — XLSX extraction (`_extract_xlsx`)**
The sketch in the docstring is most of it. Watch for bare numeric weights with no unit (`341715`) and labels in column A with values spread across B and C.

**C — PDF + DOCX extraction (`_extract_pdf`, `_extract_docx`)**
The 13 missed defects are mostly here. DOCX puts everything in tables with bilingual labels; PDF is column-based so you may need a `LABEL<spaces>VALUE` pattern alongside `Label: value`. A PDF yielding zero characters is a deliberate `unreadable` case — escalate it, don't reach for OCR first.

**D — Streamlit UI + validation evidence**
The case view is the demo: seven field rows, SI vs BL, mismatches marked, review reason and evidence shown. `run.py --email` already prints exactly this — port it. Also own `RUNLOG.md` (below), which is worth real marks on its own.

## The run log — do not skip this

`Technical Feasibility & Validation` is 15 points and the "Excellent" band reads *"critical assumptions are validated with clear evidence."* Almost no team will walk in with a measured number. We will.

After every scoring run, append one line to `RUNLOG.md`:

```
| time | score | what changed |
|------|-------|--------------|
| 16:45 | 0.0124 | do-nothing baseline |
| 17:30 | 0.7525 | rule classifier + txt extraction |
| 17:40 | 0.8258 | fixed "draft BL" decoy swallowing SI_REQUEST |
```

That table goes straight into the deck and the video.

## Rules that will cost us if broken

- **Never commit `secrets/`, `tools/`, `inbox/`, `attachments/`.** The repo is public. The answer key must never enter git history.
- **No LLM in `compare.py`.** Comparison stays deterministic and reproducible.
- **A blank or unreadable field is never a mismatch.** Two unknowns are not a match.
- **Understand the code you ship.** Judges ask. Every module here is commented with the reasoning — read it before you present it.
