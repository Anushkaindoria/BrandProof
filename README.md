# BrandProof AI

**Trusted Content. Stronger Brands.**

BrandProof AI is a deployable Round 2 hackathon MVP for evidence-backed brand governance. It helps a creator audit content against approved product facts, terminology, and policies; revise it; submit it to a human reviewer; create a content passport; and see dependency-aware Brand Drift when an approved fact changes.

## What works now

- Next.js + TypeScript frontend with responsive B2B SaaS UI.
- FastAPI + SQLAlchemy backend with organization-scoped demo records.
- Seeded NovaTech X1 illustrative campaign demonstrating 7000 mAh, waterproof, and superlative findings.
- Deterministic rules-only audit mode with structured findings and source-linked evidence.
- Content versions, SHA-256 hashes, audit history, resolution actions, review queue, approval record, and passport.
- Fact/policy/terminology knowledge base and admin-only creation controls in demo mode.
- Dependency records and Brand Drift revalidation queue.
- Dashboard metrics calculated from persisted records.
- PDF/text/Markdown upload extraction with safe extension and size checks.
- Automated backend tests for the core audit and review workflow.

## Local setup

Requirements: Node.js 20+ (Node 24 tested), Python 3.11+ (Python 3.12 tested). Docker is optional; the default local database is SQLite to keep the judge demo reliable.

```bash
cp .env.example .env

cd backend
python3 -m venv .venv
. .venv/bin/activate
pip install -r requirements.txt
uvicorn app.main:app --reload --port 8000
```

In another terminal:

```bash
cd frontend
npm install
npm run dev
```

Open `http://localhost:3000`. The frontend calls `http://localhost:8000/api` by default. Set `NEXT_PUBLIC_API_URL` to a deployed backend URL when deploying.

### Windows PowerShell setup

From PowerShell, use the Windows virtual-environment activation script:

```powershell
cd C:\Users\samai\Desktop\hackathon
Copy-Item .env.example .env

cd backend
py -3 -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
python -m uvicorn app.main:app --reload --port 8000
```

If PowerShell blocks activation, allow it only for the current terminal:

```powershell
Set-ExecutionPolicy -Scope Process -ExecutionPolicy Bypass
.\.venv\Scripts\Activate.ps1
```

Open a second PowerShell window for the frontend:

```powershell
cd C:\Users\samai\Desktop\hackathon\frontend
npm install
npm run dev
```

Do not use `. .venv/bin/activate` in Windows PowerShell; `bin/activate` is the Linux/macOS path. On Windows the path is `.\.venv\Scripts\Activate.ps1`.

### One-click Windows launcher

Double-click [`run_brandproof.bat`](run_brandproof.bat) from File Explorer, or run it from PowerShell:

```powershell
.\run_brandproof.bat
```

The launcher creates the backend virtual environment if needed, installs missing backend/frontend dependencies, starts the backend and frontend in separate windows, and opens `http://localhost:3000`. Close both server windows to stop the application.

To explicitly reset the synthetic data:

```bash
cd backend
. .venv/bin/activate
python seed.py
```

For a persistent deployment database, apply the versioned schema before starting the API:

```bash
cd backend
. .venv/bin/activate
alembic upgrade head
```

## Judge demo path

1. Open the Dashboard and click **NovaTech X1 launch ad** or open **Content Audit**.
2. Run the audit. Inspect the contradictory battery finding and its approved product brief evidence.
3. Inspect the unsupported waterproof claim and unsupported superlative.
4. Replace the draft with the suggested clean copy or edit it manually; run the audit again.
5. Submit for review.
6. Switch the visible Demo role selector to Reviewer and open Review Queue. The selected role is sent in `X-Demo-Role` and checked by the demo backend; it is not production authentication.
7. Approve the clean version, then open Content History to see its hash and passport.
8. Switch to Brand Administrator, open Brand Knowledge, and add/edit an approved fact, approve a source document, or upload an asset. A dependency-aware changed fact is surfaced in Brand Drift for content that previously depended on it.

The sample campaign and all product facts are fictional illustrative data.

## Environment variables

See `.env.example`:

- `DATABASE_URL`: SQLite or PostgreSQL SQLAlchemy URL. Default is SQLite.
- `DEMO_MODE`: keeps the synthetic workspace enabled.
- `LLM_PROVIDER`, `LLM_API_KEY`: optional provider configuration. Use `gemini` plus a key to enable semantic suggestions; no key is required for rules-only mode.
- `LLM_MODEL`: Gemini model name when `LLM_PROVIDER=gemini`.
- `MAX_UPLOAD_BYTES`: upload limit.
- `STORAGE_DIR`: private local asset storage directory. Default is `uploads`.
- `CORS_ORIGINS`: comma-separated frontend origins.
- `NEXT_PUBLIC_API_URL`: browser-visible backend API base URL.

## Tests and checks

Backend:

```bash
cd backend
. .venv/bin/activate
pytest -q
```

Frontend:

```bash
cd frontend
npm run build
```

## Deployment

Deploy the backend as a Python web service running `uvicorn app.main:app --host 0.0.0.0 --port $PORT`, with a persistent PostgreSQL `DATABASE_URL` recommended for production. Deploy the frontend as a Next.js service using `npm run build` and `npm run start`, setting `NEXT_PUBLIC_API_URL` to the backend origin. Add the backend origin to `CORS_ORIGINS`.

Docker is not available in the current build environment, so no unverified image build is claimed. The application is structured for separate frontend/backend deployment and can be containerized with the commands above.

## Known limitations

- This is a synthetic-data demo workspace, not production authentication or full multi-tenant identity. Backend organization scoping is present for demo records, but production auth middleware and account provisioning remain necessary.
- Rules remain authoritative for high-risk checks. An optional Gemini adapter is implemented, but no external key is bundled or live-tested.
- PostgreSQL/Alembic migration support is included but PostgreSQL/Docker was not executed here. Semantic pgvector retrieval, visual asset comparison, and object storage remain deferred.
- Image OCR requires the Python packages plus a separately installed Tesseract executable. Without it, the UI reports OCR as unavailable.
- The passport records evidence and process, but is not a mathematical or legal guarantee.

## Submission artifacts

See [`submission/`](submission/) for the Round 2 report source, feature status, implementation notes, changes from Round 1, Round 3 roadmap, contributions, and judge script. A PDF report is generated when the local PDF toolchain is available; the source report remains authoritative and readable.

## User guide and build status

For a page-by-page usage guide, complete build-status matrix, API reference, demo instructions, code map, test status, and limitations, see [`docs/BrandProof_User_Guide.md`](docs/BrandProof_User_Guide.md).
