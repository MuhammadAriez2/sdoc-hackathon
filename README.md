# QuayProof

**Every BL decision, backed by evidence.**

Shipping teams receive hundreds of emails a day. A handful of them are a customer asking someone to check a draft Bill of Lading against the Shipping Instruction that produced it. Getting that check wrong is expensive — a wrong consignee or a wrong weight is a manifest correction, a delayed release, sometimes a fine. Getting it done at all means a human reading two documents side by side, in whatever format they arrived in, and comparing seven fields by eye.

QuayProof reads the inbox, finds those emails, reads both attachments in their original format, compares the seven fields, and shows an operator exactly which source text each value came from. When it cannot read something, it says so instead of guessing.

**Live application:** https://quayproof.onrender.com — access token supplied separately
**Repository:** https://github.com/MuhammadAriez2/sdoc-hackathon

## What it scores

Measured against the organizers' own evaluator (`score_cli.py`), not self-reported:

| Pipeline | Records | Score | Detail |
|---|---|---|---|
| **Deployed app (Gemini)** | 37 of 520 | **0.9757** | Every planted defect caught with the exact field set — defect P/R/F1 all 1.000 |
| Deterministic baseline (`baseline/`) | 520 of 520 | 0.8258 | No AI; rule classifier + text extraction |

The deployed figure covers the 37 records processed under the app's daily AI budget, not the full inbox. `RESULTS.md` has the complete breakdown, the confusion matrix, and the one weakness this measurement exposed.

## How it works

```
email ──▶ classify ──▶ parse both attachments ──▶ extract 7 fields ──▶ compare ──▶ verdict
          (Gemini)      (native / OCR)             (Gemini + source    (pure Python,
                                                    verification)       no AI)
```

Three decisions define the system:

**The comparison contains no AI.** Once both sides are extracted and normalised, comparing seven values is `==`. A model that occasionally decides `131,058 KG` differs from `131058` destroys a result you can no longer reproduce. Extraction is the hard part; comparison is deliberately the boring part.

**Every extracted value must be provable.** The model returns a value, a quote, and the block IDs it came from. If the quote is not in the source block, or the value is not in the quote, the value is rejected — not downgraded, rejected. A confident model that cites nothing gets no credit.

**A field we could not read is never a mismatch.** Two unknowns are not a discrepancy. Sending an operator to chase a correction that was never needed is the failure mode that makes people stop trusting the tool, so unreadable input escalates to human review with the reason attached.

## Stack

React + TypeScript (Vite) → FastAPI → pdfplumber / python-docx / openpyxl / Tesseract → Gemini → deterministic comparator → Supabase (Postgres + private object storage) → Render.

Handles TXT, native PDF, scanned PDF via OCR, DOCX tables and XLSX sheets. Weights normalise across kg / MT / lbs with Decimal arithmetic; container counts accept `6` or `6 x 40'HC`; party and port text is normalised by NFKC + casefold + punctuation collapse. Semantic and bilingual label variants (`Load Port` → `port_of_loading`, `毛重` → `gross_weight_kg`) are resolved by the model under a prompt that forbids inventing values; the offline demo provider resolves 28 of them from a static table. Port codes are **not** mapped to port names — `Port Klang` and `MYPKG` compare as different, and that is deliberate until an alias rule is reviewed against authorized data.

## Running it

Full setup instructions — Docker, native development, AI provider, Supabase and Render — are below. The fastest path is Docker:

```bash
cd quayproof
cp .env.example .env
docker compose up --build
```

Then open http://localhost:8000 and click **Load demo inbox**. No API key needed for the offline demo.

Tests: `python -m pytest backend/tests -q` — 53 passing, including all four document formats against real Tesseract.

---

## 1. Fastest local start: Docker

Prerequisite: Docker Desktop with Docker Compose, or Docker Engine + Compose. Open a terminal in the `quayproof` folder.

macOS / Linux:

```bash
cp .env.example .env
docker compose up --build
```

Windows PowerShell:

```powershell
Copy-Item .env.example .env
docker compose up --build
```

Open **http://localhost:8000**. Click **Load demo inbox**, wait for the nine requests to finish, then open:

1. **demo-01:** all seven fields match, including equivalent labels and weight units.
2. **demo-02:** the BL contains a different gross weight. Click its value to see the source text and normalized kilograms.
3. **demo-03:** a missing weight is escalated. Upload `demo-files/draft-corrected.txt` using **New revision** beside the active draft. Both versions remain in the history; the new comparison should become `OK` in demo mode.
4. **demo-04:** supply `demo-files/draft-matching.txt` through **Add missing attachment**.
5. **demo-06:** a misleading BL subject and quoted old request are routed to a new SI request based on current intent.

The Docker image includes Tesseract and all parsers. No AI/cloud account is required for these demonstrations. Local case data lives in the `quayproof-data` named volume and survives normal restarts. `docker compose down` stops the app without deleting that volume. Do not add `-v` unless intentionally deleting local data.

## 2. Native development: edit React and Python

Use Python **3.12** and Node.js **22 or newer**. The Python and frontend dependency manifests are separate. All commands below start in the repository root.

macOS / Linux, terminal 1:

```bash
cp .env.example .env
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -r backend/requirements-dev.txt
python -m uvicorn app.main:app --app-dir backend --reload --port 8000
```

Windows PowerShell, terminal 1:

```powershell
Copy-Item .env.example .env
py -3.12 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r backend/requirements-dev.txt
.\.venv\Scripts\python.exe -m uvicorn app.main:app --app-dir backend --reload --port 8000
```

Terminal 2, either platform:

```bash
cd frontend
npm ci
npm run dev
```

Open **http://localhost:5173**. Vite proxies `/api` to the backend on port 8000; no extra CORS setup is needed. The backend API reference is **http://localhost:8000/docs** in local mode.

For scanned PDFs, install the **Tesseract executable**, not just a Python package. On macOS use `brew install tesseract`; on Ubuntu/Debian use `sudo apt-get install tesseract-ocr tesseract-ocr-eng`. On Windows, use a Windows build linked by [Tesseract's installation guide](https://tesseract-ocr.github.io/tessdoc/Installation.html), add it to PATH and check `tesseract --version`. Docker avoids these OS-specific steps. English OCR is included; other languages require the corresponding language packs and `OCR_LANGUAGE` configuration.

TXT, native PDF, Word tables and Excel sheets do not require Tesseract. A missing OCR executable produces a visible processing failure, not a false `OK` result.

## 3. Enable actual AI

### Option A: Gemini on permitted non-sensitive inputs

1. Create a Gemini Developer API key in [Google AI Studio](https://aistudio.google.com/).
2. Check [model pricing](https://ai.google.dev/gemini-api/docs/pricing) and the project's [active rate limits](https://ai.google.dev/gemini-api/docs/rate-limits). Choose a model with available free quota that supports `generateContent` and structured JSON output. Model access is account-dependent, so no model ID is hardcoded; the measured results in `RESULTS.md` come from `gemini-3.5-flash-lite`.
3. Edit the **root `.env`**:

```dotenv
AI_PROVIDER=gemini
GEMINI_API_KEY=your_private_key
GEMINI_MODEL=your_available_flash_model_id
AI_DAILY_CALL_LIMIT=100
```

4. Restart the backend. With Docker: `docker compose up -d --build --force-recreate`. With native development: stop and restart Uvicorn; changing `.env` alone is not guaranteed to reload settings.
5. Import a **synthetic** request using `demo-files/instruction.txt` and `demo-files/draft-mismatch.txt`. Tick the cloud permission declaration. Submit it and confirm the app's provider banner says Gemini.
6. Inspect the classification explanation, source-backed extracted values and comparison. A failed API call is visible and retryable; it never silently falls back to fabricated answers or a paid provider.

If the built-in nine cases already exist, **Load demo inbox does not reset them**. Open a case and use **Run / resume** to recompute it with the newly selected provider. The provider/model/prompt fingerprint invalidates previous extraction caches; past comparisons remain in history.

**Data restriction:** Google's unpaid-service terms restrict sensitive, confidential and personal inputs, and describe use of submissions for product improvement and possible human review. Do not upload the participant bundle unchanged merely because you have a competition copy. Use synthetic data, or obtain authorization and properly sanitize it. The backend checks `cloud_permitted` before making Gemini calls. That checkbox records a user declaration; it is not automated anonymization or a legal determination. [Gemini API terms](https://ai.google.dev/gemini-api/terms)

### Option B: a local model instead

`providers.py` also ships an Ollama adapter that posts to a local `/api/chat`
endpoint with the same JSON schema, so the pipeline is not coupled to one
vendor. It was not used for this submission, has no test coverage, and has
never been executed — see `docs/VALIDATION.md`. Gemini is the provider the
measured results come from.

## 4. Connect Supabase for durable cloud state

1. Create a **Free** project in [Supabase](https://supabase.com/).
2. Open its SQL editor and run the complete contents of `supabase/schema.sql` once. This creates the case/checkpoint table, AI-call counter, three atomic RPCs and the private `quayproof-documents` bucket.
3. Copy the project URL and the **server-only service-role key** from project API settings. This code uses the service-role JWT as both `apikey` and bearer credential. Do not substitute a frontend publishable/anon key.
4. Edit `.env`:

```dotenv
STORAGE_BACKEND=supabase
SUPABASE_URL=https://your-project.supabase.co
SUPABASE_SERVICE_ROLE_KEY=your_server_only_service_role_key
SUPABASE_BUCKET=quayproof-documents
```

5. Restart QuayProof. Load the synthetic demo, restart again, and confirm its cases and original documents still open.

Switching the backend does **not** migrate existing SQLite cases automatically. Use a new synthetic demo or explicitly reimport authorized files. Keep original business data local until cloud storage is authorized.

The frontend never contacts Supabase directly. RLS is enabled and grants are removed for `anon` and `authenticated`; the trusted backend uses the service-role key. That key is powerful: keep `.env` out of Git and use Render's secret environment settings. The demo uses a shared team access token, not full per-user identity or tenant isolation.

Supabase's published free allowances include 500 MB database storage and 1 GB file storage; inactive projects may pause. Check current allowances and usage in your project. [Supabase pricing](https://supabase.com/pricing)

## 5. Deploy publicly on Render Free

1. Finish the Supabase steps. A public deployment refuses to start with ephemeral local storage or a weak/missing access token.
2. Create a **public GitHub repository** containing this project's source. Exclude `.env`, real participant files, databases, generated submissions and all organizer private material. Review `git status` before committing.
3. In Render, create a Blueprint from that repository using `render.yaml`, or create one **Docker web service** manually on the **Free** plan.
4. Supply `SUPABASE_URL` and `SUPABASE_SERVICE_ROLE_KEY`. The Blueprint generates `APP_ACCESS_TOKEN`; retrieve it from service environment settings and share it privately with teammates/judges. Do not commit it to a public README.
5. Deploy. Render builds React, installs Python/Tesseract and runs one Uvicorn worker. Check `/api/health`, open the public app URL and enter the team token.
6. Initially the Blueprint uses `AI_PROVIDER=demo`. Once the cloud workflow is healthy, add `GEMINI_API_KEY`, `GEMINI_MODEL` and change `AI_PROVIDER=gemini` in Render. Redeploy and process a permitted synthetic case.
7. In a fresh browser, verify inbox → comparison → evidence → human action. Give judges both the deployment URL and the token through the permitted submission channel.

Free Render web services sleep after 15 minutes of inactivity and use ephemeral files. This is why cases, checkpoints and attachments are in Supabase. One bounded runner works **inside the web process**; there is no separate free worker and no promise that jobs continue while the service sleeps. Interrupted processing can resume after its 30-minute lease expires. Checkpointed classification/extraction are reused; a crash after an external AI request but before its checkpoint can cause that call to repeat. [Render free-service limits](https://render.com/docs/free)

Do not upgrade plans or enable paid fallback for this zero-budget setup. The application cap is a safety bound, not a guarantee of a provider's quota or billing status. Monitor both account quotas. If your account cannot obtain the required free capacity, retain the local demonstration and resolve public hosting access before submission.

## 6. Import the authorized participant bundle

Use only the **participant bundle's extracted folder**, with `inbox/` and `attachments/`. The importer never opens archives, imports the organizer loader as code, or reads scorer source, answer keys or ground-truth files. It reads `inbox/email_*.json` and only their referenced files contained in `attachments/`, with path checks.

With the API running locally:

```bash
python scripts/import_bundle.py --source /path/to/participant-bundle --limit 5 --run
```

If your app has authentication, set `QP_ACCESS_TOKEN` in the importer's process environment. Use `--api https://your-app.onrender.com` only when the selected data is authorized for cloud storage. Do not put the token on a command line shared in screenshots.

Start with `AI_PROVIDER=demo` for plumbing or `AI_PROVIDER=ollama` for local AI. The default importer sends `cloud_permitted=false`. Do not add `--cloud-permitted` to an unsanitized bundle. That option is only for input sets that you have independently checked and authorized for the unpaid Gemini service.

```bash
# Import every record without automatically using AI quota:
python scripts/import_bundle.py --source /path/to/participant-bundle --limit 0
```

`--run` queues newly imported cases. Already imported IDs are skipped, not overwritten or rerun. Use **Run / resume** for existing cases. The default maximum is 600 cases, enough for the observed 520 records plus nine demo fixtures; this is a prototype guard, not a scaling claim.

After processing, the inbox **Export** button downloads `submission.json`. Demo fixtures are excluded. Export is blocked for queued/failed cases, uncertain classifications and cases combining confirmed defects with unresolved fields. Ordinary complete `NEEDS_REVIEW` cases export with their valid reason. Non-BL entries use `status: "OK"` as a sample-compatible filler; the product UI still distinguishes these from a BL match.

Confirm that the exported email-ID set exactly matches the authorized inbox before submitting. The app cannot know about records you never imported. To use an organizer-authorized scoring endpoint:

```bash
python scripts/submit.py --url http://organizer-authorized-host:8080 --file submission.json
```

This script only submits predictions and prints the numeric aggregate `final_score`. It never requests private labels.

## 7. How to work on the code

| Location | Responsibility |
|---|---|
| `frontend/src/App.tsx` | Application shell: data loading, filters, review actions, upload and revisions |
| `frontend/src/components/` | `InboxList`, `ComparisonTable`, `EvidenceDrawer`, `NewRequestModal` |
| `frontend/src/labels.ts` | Field labels, category filters and shared display helpers |
| `frontend/src/style.css` | Responsive UI; plain CSS keeps the dependency surface small |
| `backend/app/main.py` | API routes, access token, upload limits, review and export |
| `backend/app/providers.py` | Gemini/Ollama adapters, prompts, explicit offline demo provider |
| `backend/app/parsers.py` | TXT, PDF/native/OCR, DOCX tables, XLSX row evidence |
| `backend/app/normalize.py` | Conservative text, Decimal weights and container-count handling |
| `backend/app/pipeline.py` | Evidence validation, comparisons, checkpoints and retries |
| `backend/app/storage.py` | SQLite or Supabase persistence, optimistic concurrency and call budget |
| `supabase/schema.sql` | RLS, atomic case writes, job claims and quota reservation |
| `backend/tests/` | Automated behavior and format tests |
| `scripts/` | Import, aggregate submission, synthetic fixtures, browser smoke test |
| `docs/ARCHITECTURE.md` | API contract, reliability policy and known limitations |
| `docs/TEAM_GUIDE.md` | Suggested work split, acceptance checks and five-minute demo |

The UI uses plain CSS rather than adding Tailwind/shadcn dependencies. It shows text evidence and original-file downloads; an in-page PDF.js coordinate-overlay viewer is the next step. Everything the application does runs from this repository — there is no hidden backend, mailbox integration or separately trained model.

## 8. Test and build

With the Python virtual environment active, from the repository root:

```bash
python -m pytest backend/tests -q
npm --prefix frontend run build
```

`backend/pytest.ini` configures the backend import path. The OCR test skips only when the Tesseract executable is missing. Synthetic DOCX/XLSX/native PDF/scanned PDF and damaged-PDF fixtures are included in `demo-files/`; regenerate them with `python scripts/make_demo_files.py` if needed.

For the browser smoke test, use a **disposable local demo workspace** with no access token. Keep a local Uvicorn process serving the built frontend, then:

```bash
cd frontend
npx playwright install chromium
cd ..
node scripts/smoke-browser.mjs
```

It seeds the synthetic demo, checks mismatch evidence and blocked approval, captures desktop/mobile screenshots under `test-results/`, and fails on browser exceptions. It does not call a real AI service.

## 9. Troubleshooting

| Symptom | What to check |
|---|---|
| App says API ready but no UI at port 8000 | Run `npm --prefix frontend run build`, then restart Uvicorn; or use Vite at port 5173. |
| `ModuleNotFoundError` | Use the intended virtual environment and install `backend/requirements-dev.txt`. |
| `401` / access-token dialog | Enter `APP_ACCESS_TOKEN`, not a Gemini/Supabase key. Native unauthenticated localhost leaves it blank. |
| Gemini configuration failure | Confirm model access, key, free quota and `AI_PROVIDER`; restart backend after `.env` changes. |
| Cloud AI blocked | Use approved synthetic/sanitized inputs with recorded consent, or local Ollama. |
| Rate limit / daily cap | Wait for quota availability and use **Retry processing**; do not enable paid fallback. |
| Supabase HTTP failure | Run schema.sql, confirm private bucket and URL/service-role JWT, check whether project paused. |
| OCR missing / timed out | Check Tesseract/language pack, try Docker, or provide a smaller/readable revision. |
| Unknown fields in scanned PDF | Critical OCR digits deliberately need human confirmation against the source evidence. |
| Case stays processing after host restart | Its 30-minute lease must expire before automatic reclamation; keep the service active and inspect status. |
| Correct value rejected by reviewer API | Correction must be an exact substring of the selected source blocks. Wrong OCR needs a readable revision; correcting OCR text in place is not supported. |
| Render cold start | Allow the service to wake and verify Supabase is active before the demonstration. |
| Export blocked | Resolve failed/pending processing, category uncertainty and mixed defect/unknown cases. |

## 10. What is and is not validated

`docs/VALIDATION.md` lists every check performed on this delivery, with the date and the evidence, and a matching list of what has **not** been checked. A passing unit test, a working deployment and a measured evaluator score are three different kinds of evidence, and that file keeps them apart.

The short version: the pipeline, the deployment and the Gemini integration are all live and exercised, measured at 0.9757 on the 37 records processed. 483 of the 520 records have not been run, because the free-tier quota does not permit it. The Ollama provider is implemented but has never been executed. No real customer document has been through this system — all validation is against organizer-supplied synthetic data.

This is a prototype, not a production system: one Render free instance, one worker, a shared team token rather than per-user identity, and a 100-call daily AI budget. `docs/ARCHITECTURE.md` §Security and scope limits states what would have to change before it handled real traffic.