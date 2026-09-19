# Delivery validation

The following checks were performed during creation of this starter. They are implementation checks, not organizer scoring results.

| Check | Result / scope |
|---|---|
| Backend automated tests | **38 passed**. Normalization, evidence rejection, conflicting candidates, missing values, mixed outcomes, human review, revision history, stale-write protection, daily cap, mocked Gemini JSON contract, consent gating, API authentication and file scoping. |
| Document formats | Synthetic TXT, native PDF page/coordinate evidence, scanned PDF through real Tesseract, DOCX table rows and XLSX cell evidence tested. |
| Cloud-style checkpoint behavior | Regression test passed with JSON serialization/replacement after each checkpoint, matching REST's object-replacement behavior. This is not a live Supabase test. |
| Frontend | TypeScript checking and Vite production build passed. |
| Actual local HTTP workflow | Uvicorn served the compiled frontend and API; the multipart importer submitted an independently authored synthetic SI/BL pair; the background runner detected the weight discrepancy; the strict export contained the expected email ID and mismatch. |
| Browser visual/end-to-end test | Script included but **not completed in the creation environment**: Chromium was unavailable and its installer failed. Run `scripts/smoke-browser.mjs` on a development laptop before judging. |
| Docker image | Configuration supplied; image build/run not performed because Docker was unavailable in the creation environment. |
| Gemini and Ollama live inference | Not called. Credentials/local model were not available. Gemini request/response handling was tested with a mock only. |
| Supabase / Render | Schema, HTTP adapters and deployment configuration supplied; no live project or deployment provisioned or tested. |
| Participant evaluator | Not run. No private ground truth, answer key or secret label was inspected, extracted or used. |

Creation runtime: Python 3.12; React/TypeScript production build with Vite 6.4.3. The frontend lockfile pins its installed dependency graph. Backend test dependencies include the exact FastAPI/Uvicorn/Pydantic versions in requirements; document dependencies use bounded versions to keep platform installation practical. The test environment used pdfplumber 0.11.8, python-docx 1.2.0, openpyxl 3.1.5 and Pillow 12.3.0.

Two dependency deprecation warnings were emitted by the Starlette/httpx TestClient path. They did not fail tests. Recheck dependency compatibility when upgrading; do not suppress functional failures.

Before the hackathon demo, complete the unverified integration checks above, run one authorized scan on the actual host, and measure live AI extraction quality. Do not present synthetic fixture success or mocked API tests as dataset accuracy or a deployed-cloud reliability claim.
