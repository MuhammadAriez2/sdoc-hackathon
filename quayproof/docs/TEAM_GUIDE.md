# Team runbook

Assumption: four students and approximately 120 total person-hours. The delivered starter reduces scaffolding work; budget the team's time around validating real AI, improving extraction and delivering the competition assets.

## Work allocation

| Member | Primary ownership | First acceptance check |
|---|---|---|
| A: frontend/product | Inbox, evidence, review UX and demo script | A teammate can explain a discrepancy from the source evidence in under 20 seconds |
| B: AI/document pipeline | Prompts, full-address extraction, OCR/layout failure analysis | Permitted SI/BL cases produce source-backed seven-field observations |
| C: backend/cloud | Supabase schema, Render deployment, secrets and recovery | Public app survives redeployment without losing cases or originals |
| D: evaluation/QA | Authorized test cases, submission completeness, tests and docs | All imported IDs export once; failures cannot masquerade as matches |

Suggested hours: integration and environment verification 12; parser/prompt improvements 30; UX polish 18; reliability and evaluation 24; public deployment and demo assets 24; contingency 12.

## First day

1. Everyone runs the Docker demo. Assign one owner to integration settings and keep API keys out of chat/screenshots.
2. Make a single permitted synthetic Gemini call and inspect its structured classification and field evidence. Check quota before any batch run.
3. Run the same request through local Ollama if confidentiality or Gemini access is a blocker. Measure latency instead of assuming the laptop is fast enough.
4. Create Supabase, run the schema and verify upload → restart → download on synthetic data.
5. Deploy the starter to Render Free and test from a separate device. Check an actual OCR page on the free instance; memory and latency are unverified until then.
6. Compare source text with observations on a small authorized set spanning TXT, tables, scans, missing values and misleading subjects. Record failures without guessing organizer answers.

The first viability experiment is one complete live-AI SI/BL comparison on each important input format, with every accepted value traced to the correct source and known synthetic mutations caught. Stop adding features if this fails; improve parsing/evidence first.

## Must / should / could / won't

| Priority | Work |
|---|---|
| Must | Connect actual AI; validate seven-field decisions and five categories; make cloud persistence work; publicly deploy; test review/revision; complete public repo/README, deck or technical documentation, <=5-minute video |
| Should | Improve multiline addresses/table grouping, add authorized port aliases, validate OCR on host, measure category and field metrics on independently labelled permitted cases |
| Could | PDF.js highlights using stored coordinates, per-user Supabase Auth, focused batch controls, processing-time dashboard |
| Won't for MVP | Train a model, deploy Kubernetes, add a vector DB, implement mailbox OAuth, automatically email carriers, use private ground truth, promise production compliance |

## MVP definition of done

- Public app opens for judges using the supplied token; GitHub source and instructions reproduce it.
- Provider banner identifies **Gemini or Ollama** during the AI demonstration; offline demo mode is not represented as AI.
- A normal match, a real discrepancy and a review case complete end to end.
- The source document, revision/hash, block location, original value and normalized value are visible for accepted fields.
- A missing/damaged document and a cloud failure each produce the right kind of visible state.
- Source-backed corrections are audited; approving a mismatch never changes it to `OK`.
- Supplying a new readable revision preserves old evidence, invalidates approval and triggers a new comparison.
- All authorized imported email IDs appear exactly once in a valid export, or export explains what blocks it.
- No real API keys, personal/confidential participant files or private organizer material are committed.
- Measured latency/accuracy/review results clearly state their test set and limitations.

## Validation without private answers

The included fixtures have expected behavior because the team authors their content and controlled mutations; they are not organizer labels. For actual participant inputs, review only authorized documents and build an independent human-labelled validation subset if the rules permit. Preserve reviewer disagreements and avoid claiming labels for unreviewed cases.

Measure five-class macro-F1, end-to-end defect recall, defect-field F1, unresolved review rate, false approvals, processing failures, calls per case, and median/p95 latency. Separate synthetic development results from any legitimate organizer aggregate score. Do not tune solely to repeated leaderboard feedback.

Run the official evaluator only through participant-authorized submission mechanisms. The submission helper prints aggregate final score only. Never inspect the Docker package's private labels or scoring internals.

## Five-minute demonstration

| Time | Screen and action | What to say |
|---|---|---|
| 0:00–0:25 | Project and team; inbox | “QuayProof helps shipping operators decide which drafts are safe to approve and which need attention.” |
| 0:25–0:50 | Five-category inbox routing | Explain mixed inboxes, misleading subjects and SI as the source of truth. |
| 0:50–1:25 | `demo-01`, recomputed with live AI beforehand | Show seven matches despite label/unit differences; identify actual provider. |
| 1:25–2:10 | `demo-02`; click BL gross weight | Show raw 12.8 MT vs SI 12,500 kg, normalized comparison and exact source blocks. |
| 2:10–2:45 | `demo-03` or synthetic damaged PDF | Show `NEEDS_REVIEW`; approval is blocked and the reason is specific. |
| 2:45–3:25 | Upload `draft-corrected.txt` as new revision | Show recomparison, preserved original and audit. Use a short synthetic pair that fits live quota. |
| 3:25–3:50 | Acknowledge report; review history | Human action is accountable in the shared-workspace audit and does not overwrite evidence. |
| 3:50–4:25 | Architecture diagram and cloud settings summary | One Render service; private Supabase persistence; bounded jobs; AI extraction; deterministic decisions. Never display keys. |
| 4:25–5:00 | Inbox counts and close | State measured results, prototype limits and time saved only if measured. Provide public URL and repository. |

**Strongest 20 seconds:** click a suspicious gross-weight field, show its original units and source location, then reveal that 12.8 tonnes becomes 12,800 kg and disagrees with the instruction's 12,500 kg. The audience sees both the decision and its proof.

## Cloud-failure fallback

Keep the Docker image built, the app running locally and synthetic fixtures ready before judging. Prepare an honest prerecorded end-to-end clip from the actual deployed AI workflow. If the cloud fails, announce the outage and show either the recorded run or explicitly labelled local demo. Previously stored results may be shown as past runs, not as new live inference. Do not pretend the deterministic fallback is AI.

Public access remains a competition requirement even if a local fallback saves the live presentation. Test the public deployment before submission and explain any current outage.

## Main risks and honest answers

| Risk | Mitigation / judge answer |
|---|---|
| AI copies the wrong address/weight from valid text | Evidence existence is necessary but insufficient. Evaluate field assignment; reject ambiguity and review critical values. |
| Free API quota exhausts during demo | Precheck quotas; app cap; reuse checkpoints; keep a recorded run; never claim unlimited free inference. |
| OCR cannot reliably read a scan | Numeric OCR requires confirmation; cap page size; show the original; obtain a readable revision when text itself is wrong. |
| Render sleeps or runs out of memory | Wake normally before demo, persist state in Supabase, benchmark one scan on the real host. |
| Production security questions | This is a token-protected shared prototype. Individual authentication, retention controls and hardened parsing are explicitly pending. |
| Private dataset leakage | Local Ollama/local storage for restricted data; only authorized sanitized/synthetic cloud input. No private scoring files inspected. |
| Accuracy claim exceeds evidence | Report test-set size/source, review rate and confidence intervals where feasible; separate synthetic checks from organizer aggregate scores. |

Future priorities: per-user authentication; layout-aware table extraction; evidence overlays; calibrated review thresholds; batch cost controls; retention/deletion; then mailbox integrations only after the core decision workflow is reliable.
