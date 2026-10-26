# BrandProof AI — User Guide and Build Status

**Product:** BrandProof AI  
**Tagline:** Trusted Content. Stronger Brands.  
**Status:** Round 2 local MVP, Git-ready, not deployed from this workspace.

This document explains what is built, what is incomplete, how to start the product, what every page does, how to perform the complete judge workflow, and which backend features are available.

---

## 1. What is built

### Completed and tested

| Area | What works |
|---|---|
| Demo workspace | Synthetic BrandProof workspace with NovaTech X1 facts, policies, terminology, source document, users, and sample advertisement. |
| Dashboard | Counts and activity are calculated from the database. Shows audit runs, unresolved findings, review queue items, drift items, categories, and recent events. |
| Brand Knowledge | Lists approved facts, policies, terminology, and source documents. Admin demo role can create facts and policies. |
| Content Audit | Create content, edit text, save versions, run audits, see structured findings, inspect evidence, resolve findings, and submit revisions. |
| Deterministic verification | Detects conflicting numerical claims, unsupported waterproof language, unsupported superlatives, warranty conflicts, and prohibited terminology. |
| Evidence | Findings include verification status, severity, explanation, suggestion, confidence, evidence type, evidence ID, excerpt, and source reference. |
| Revision loop | Every revision is saved as a new content version. Old versions and audit runs are not silently overwritten. |
| Human review | Submitted content can be approved, rejected, or sent back for changes. Approval is separate from automated auditing. |
| Content passport | Approved versions receive a SHA-256 hash, dependency versions, audit engine version, reviewer, decision, and timestamp. |
| Brand Drift | Changed fact versions identify dependent approved content and mark it for revalidation. |
| Upload baseline | `.txt`, `.md`, and text-based PDF extraction with file type, size, filename, empty-file, and extraction validation. |
| API | FastAPI endpoints exist for health, bootstrap, dashboard, knowledge, facts, policies, content, versions, audits, findings, reviews, passports, drift, history, and uploads. |
| Deployment preparation | Environment configuration, Dockerfiles, Docker Compose, PostgreSQL/pgvector configuration, README, seed script, and migration marker are included. |

### Implemented but limited or incompletely tested

| Area | Current state |
|---|---|
| PostgreSQL | SQLAlchemy and `psycopg` configuration are included. SQLite was the tested local database. Docker/PostgreSQL could not be executed because Docker is unavailable in the environment. |
| PDF extraction | Implemented with `pypdf`; the automated suite tests upload rejection but does not include a real PDF fixture. |
| Demo role selector | The UI lets the judge switch between Creator, Reviewer, and Brand Administrator views. It is a demo persona switch, not production authentication. |
| Admin editing | Fact and policy creation is available in the UI. Fact version updates are available through the backend API and power the drift demonstration. A richer edit form is not complete. |
| Passport display | Passport data is persisted and available through the API/history flow. A dedicated expanded passport screen is not complete. |
| LLM configuration | Provider fields and explicit mode reporting exist, but the current audit implementation is rules-only. |

### Not built / deferred

- Production login, account provisioning, session security, and complete multi-tenant authentication.
- A production Gemini/OpenAI/other provider adapter.
- OCR for scanned PDFs or images.
- Visual logo/asset comparison with OpenCV or image embeddings.
- pgvector semantic search and source-document chunk indexing.
- Full Alembic migration lifecycle. The demo creates the SQLite schema using SQLAlchemy metadata and includes an initial migration marker.
- Object storage adapter for private uploaded documents.
- Background jobs, queues, and notifications.
- A complete asset-management UI.
- A dedicated passport detail UI and richer reviewer comments interface.

The application does not claim these deferred items are implemented.

---

## 2. Start the application

### Requirements

- Node.js 20 or newer. Node 24 was tested.
- Python 3.11 or newer. Python 3.12 was tested.
- Docker is optional for the local demo.

### Configure environment

From the repository root:

```bash
cp .env.example .env
```

The default configuration is ready for the local demo:

```env
DATABASE_URL=sqlite:///./brandproof.db
DEMO_MODE=true
LLM_PROVIDER=rules-only
LLM_API_KEY=
MAX_UPLOAD_BYTES=10485760
CORS_ORIGINS=http://localhost:3000
NEXT_PUBLIC_API_URL=http://localhost:8000/api
```

### Start the backend

Terminal 1:

```bash
cd backend
python3 -m venv .venv
. .venv/bin/activate
pip install -r requirements.txt
uvicorn app.main:app --reload --port 8000
```

Backend URLs:

- API health: `http://localhost:8000/api/health`
- Interactive API docs: `http://localhost:8000/docs`
- OpenAPI JSON: `http://localhost:8000/openapi.json`

The backend creates tables and seeds the demo workspace on startup.

### Windows PowerShell commands

If you are running the project from Windows PowerShell, use these commands instead of the Linux/macOS activation command:

```powershell
cd C:\Users\samai\Desktop\hackathon
Copy-Item .env.example .env
cd backend
py -3 -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
python -m uvicorn app.main:app --reload --port 8000
```

If activation is blocked:

```powershell
Set-ExecutionPolicy -Scope Process -ExecutionPolicy Bypass
.\.venv\Scripts\Activate.ps1
```

Start the frontend in a second PowerShell window:

```powershell
cd C:\Users\samai\Desktop\hackathon\frontend
npm install
npm run dev
```

Use `python -m pip`, rather than a possibly different global `pip`, to ensure packages install into the active `.venv`. The Linux command `. .venv/bin/activate` is not the correct Windows PowerShell command.

### Start the frontend

Terminal 2:

```bash
cd frontend
npm install
npm run dev
```

Open `http://localhost:3000`.

### Reset demo data

This deletes and recreates the local synthetic database:

```bash
cd backend
. .venv/bin/activate
python seed.py
```

Do not run the reset command against a production database.

---

## 3. How to use the web application

### Navigation and workspace banner

The left navigation opens the seven product areas. The workspace banner identifies the current workspace as **BrandProof Demo** and states that the data is synthetic.

The top-right role selector has three demo personas:

1. **Content Creator** — intended to create, audit, revise, and submit content.
2. **Reviewer** — intended to inspect submitted content and record a decision.
3. **Brand Administrator** — intended to manage approved knowledge and inspect drift.

This selector is for the explicitly enabled demo environment. It is not a secure login system. The backend uses the seeded demo reviewer identity for the approval endpoint.

### Dashboard

The Dashboard is the starting point.

What each area means:

- **Audit runs:** persisted audit executions.
- **Open findings:** unresolved non-supported findings.
- **Awaiting approval:** content submitted for human review.
- **Need revalidation:** approved content whose evidence dependency changed.
- **Recent audit activity:** events written by the backend.
- **Open findings by category:** unresolved findings grouped by category.
- **Content needing attention:** persisted content items and current status.

Use **New audit** to open the audit workspace. Use **Open** on an existing content item to continue its workflow.

### Brand Knowledge

This is the organization’s approved evidence area.

#### Approved product facts

Facts are structured records such as:

- `battery_capacity` → `5000 mAh`
- `water_resistance` → `Not officially certified`
- `warranty` → `1 year`

Each fact has an ID, product, value, version, active state, source reference, and excerpt.

Facts are used for exact claim checks. A fact is evidence only when it exists in the approved knowledge base.

#### Policies

Policies define rules such as:

- Do not describe NovaTech X1 as waterproof.
- Unsupported superlatives require proof.
- High-risk content requires a human reviewer.

The MVP supports structured policy types such as `prohibited_claim`, `superlative`, and `approval`.

#### Terminology

Terminology records contain a prohibited term and an approved replacement. The seeded example recommends replacing `waterproof` with `everyday protection` where appropriate.

#### Source documents

Source records show the filename, excerpt, page/reference text, and state. Seeded source material is approved. Uploaded source material starts as `unreviewed` and is not automatically promoted to approved evidence.

#### Adding knowledge as administrator

1. Switch the role selector to **Brand Administrator**.
2. Open **Brand Knowledge**.
3. Use **Add approved fact** or **Add policy**.
4. Enter the structured value and save.
5. Re-run an audit to use the new record.

The UI has creation controls. Versioned fact changes can also be exercised through the API, described below.

### Content Audit

This is the main product workflow.

#### Create or select content

1. Open **Content Audit**.
2. Select **New content** or choose an existing content item.
3. Enter a title.
4. Choose a content type and context.
5. Paste or type the content.
6. Click **Run audit**.

The frontend sends the request to the real FastAPI backend. Findings are not hardcoded in the UI.

#### Mandatory demo text

The seeded campaign contains:

```text
Meet the NovaTech X1! Enjoy a 7000 mAh battery and completely waterproof protection. The best phone ever!
```

This should produce:

1. A high-severity battery mismatch: submitted `7000 mAh`, approved `5000 mAh`.
2. A high-severity unsupported/contradicted waterproof claim.
3. A medium-severity unsupported superlative finding for `The best phone ever!`.

#### Reading a finding

Each finding shows:

- The original claim text.
- Category, such as Factual accuracy or Policy compliance.
- Severity.
- Verification status.
- Explanation.
- Suggested correction.
- Evidence label and excerpt.
- Source filename/reference when available.

Verification statuses mean:

- **Supported:** approved evidence matches the claim.
- **Contradicted:** approved evidence conflicts with the claim.
- **Insufficient evidence:** the system cannot establish the claim from approved evidence.
- **Needs interpretation:** a human should decide how to interpret the context.

The current rules engine primarily emits Supported, Contradicted, and Insufficient evidence.

#### Resolving a finding

- **Accept correction:** records the finding as resolved.
- **Dismiss:** records a dismissal reason.

Resolution does not rewrite the content. Edit the content and re-run the audit to validate the new version.

#### Re-audit a revision

1. Edit the text in the draft editor.
2. Click **Run audit**.
3. The backend creates a new content version with a new hash.
4. The audit runs against that version.
5. The displayed findings belong to the current version.

Example clean copy:

```text
Meet the NovaTech X1 with a 5000 mAh battery and a 1 year warranty.
```

This should remove the seeded battery, waterproof, and superlative issues.

#### Submit for review

After a clean or reviewed revision:

1. Click **Submit for review**.
2. The content status becomes `resubmitted`.
3. Open **Review Queue**.

The backend prevents submission while the item is still in `changes_required` state.

### Review Queue

Review Queue shows content with `resubmitted` status.

The reviewer workflow is:

1. Open a queued item.
2. Inspect the current version and its findings/evidence.
3. Choose an approval decision through the review API flow.
4. The backend records the decision against the exact content version.

Possible decisions:

- `approve` → status becomes `approved` and creates a passport.
- `request_changes` → status becomes `changes_required`.
- `reject` → status becomes `rejected`.

The AI/rules engine cannot approve content by itself.

### Content History

Content History shows:

- Content title.
- Current status.
- Current version number.
- Content hash prefix.
- Link to the item history/passport flow.

Every revision has a separate version and SHA-256 hash. Changing content after approval creates a new version and does not silently retain the old approval.

### Brand Drift

Brand Drift shows approved content whose audited evidence changed.

Example workflow:

1. Audit content that uses the approved battery fact.
2. Approve the clean version.
3. Update the battery fact through the fact update API.
4. Open **Brand Drift**.
5. The dependent content appears with the old and current fact versions.
6. Open the content and re-audit it.

Unrelated content is not selected just because any record in the workspace changed.

### Settings

Settings explains:

- Current demo persona.
- Synthetic workspace boundary.
- The absence of production authentication.
- Active audit provider mode.
- The rules-only fallback behavior.
- External provider data-handling considerations if an LLM key is configured later.

### Upload behavior

The backend upload endpoint accepts:

- `.txt`
- `.md`
- `.pdf`

The default maximum is 10 MB. HTML and other unsupported extensions are rejected. PDF extraction uses `pypdf`. Uploaded documents are stored as unreviewed source records and do not automatically become approved facts or policies.

The current UI explains the upload path, while the endpoint is available for API clients. A full drag-and-drop upload control is not complete.

---

## 4. Complete judge demonstration

1. Start backend and frontend.
2. Open `http://localhost:3000`.
3. On Dashboard, open **NovaTech X1 launch ad**.
4. Run the audit.
5. Inspect the battery finding and its source excerpt.
6. Inspect the waterproof finding.
7. Inspect the superlative finding.
8. Replace the draft with clean copy.
9. Run the audit again.
10. Submit for review.
11. Switch the role selector to Reviewer.
12. Open Review Queue.
13. Approve the clean version.
14. Open Content History and view the version/hash/passport information.
15. Switch to Brand Administrator.
16. Update a fact through the API or admin flow.
17. Open Brand Drift and inspect the affected content.

The judge should see that the workflow is evidence-backed, versioned, and human-approved rather than a chatbot response.

---

## 5. Backend API reference

The interactive API documentation is available at `http://localhost:8000/docs` while the backend is running.

| Method | Endpoint | Purpose |
|---|---|---|
| GET | `/api/health` | Confirm the backend is running. |
| GET | `/api/bootstrap?role=creator` | Return demo organization, persona, and provider mode. |
| GET | `/api/dashboard` | Return database-backed metrics, activity, and content. |
| GET | `/api/knowledge` | List facts, policies, terminology, and source documents. |
| POST | `/api/facts` | Create an approved fact. |
| PATCH | `/api/facts/{fact_id}` | Update a fact, increment its version, and flag dependencies. |
| POST | `/api/policies` | Create a policy. |
| GET | `/api/content` | List organization content. |
| POST | `/api/content` | Create an item and its first version. |
| GET | `/api/content/{content_id}` | Return content, versions, latest audit, and review decisions. |
| POST | `/api/content/{content_id}/versions` | Save a new immutable content version. |
| POST | `/api/content/{content_id}/audit` | Run the rules audit on the current version. |
| POST | `/api/content/{content_id}/submit` | Submit an eligible version for review. |
| POST | `/api/content/{content_id}/review` | Approve, reject, or request changes. |
| POST | `/api/findings/{finding_id}/resolve` | Record accept, edit, or dismiss resolution. |
| GET | `/api/history` | List content history. |
| GET | `/api/content/{content_id}/passport` | Return the passport for the approved current version. |
| GET | `/api/drift` | Return content affected by changed dependencies. |
| POST | `/api/content/upload` | Extract text from supported upload types. |

Example audit request:

```bash
curl -X POST http://localhost:8000/api/content/1/audit
```

Example fact update for the drift demo:

```bash
curl -X PATCH http://localhost:8000/api/facts/1 \
  -H 'Content-Type: application/json' \
  -d '{
    "key": "battery_capacity",
    "product": "NovaTech X1",
    "value": "5100 mAh",
    "source_reference": "NovaTech_X1_Product_Brief.pdf · p. 2",
    "excerpt": "Battery capacity updated for revalidation demo."
  }'
```

---

## 6. What the main code folders do

### Backend

- `backend/app/main.py` — FastAPI application, routes, serialization, audit orchestration, review flow, uploads, passport, and drift.
- `backend/app/models.py` — SQLAlchemy database entities and relationships.
- `backend/app/audit.py` — deterministic evidence-backed rules engine.
- `backend/app/seed.py` — reproducible demo organization and NovaTech seed data.
- `backend/app/schemas.py` — Pydantic request schemas and finding serialization.
- `backend/app/db.py` — SQLAlchemy engine, session factory, and base model.
- `backend/app/config.py` — environment configuration.
- `backend/tests/test_audit.py` — unit tests for claim checks.
- `backend/tests/test_api.py` — integration tests for health, audit, revision, review, passport, and uploads.

### Frontend

- `frontend/app/page.tsx` — main client application and page components.
- `frontend/app/globals.css` — visual design system and responsive layout.
- `frontend/app/layout.tsx` — metadata and global shell.
- `frontend/next.config.ts` — Next.js deployment configuration.

### Submission

- `submission/BrandProof_Round2_Report.pdf` — generated PDF report.
- `submission/features_completed.md` — detailed feature status.
- `submission/technology_and_implementation.md` — implementation details.
- `submission/changes_from_round1.md` — Round 1 comparison.
- `submission/round3_improvements.md` — exactly three Round 3 improvements.
- `submission/individual_contributions.md` — editable team contribution statements.
- `submission/judge_demo_script.md` — concise pitch and demo sequence.

---

## 7. Tests and verification status

Executed checks in this workspace:

```text
Backend pytest: 6 passed
Python compile check: passed
Frontend TypeScript check: passed
Next.js production build: passed
Live backend health/dashboard/knowledge/content checks: HTTP 200
Live frontend root check: HTTP 200
Live audit → revision → re-audit → submit → approve → passport flow: passed
Live fact update → Brand Drift flow: passed
```

Not executed:

- Docker build/run, because Docker is not installed in the current WSL environment.
- Browser screenshot automation, because the available browser-control display does not have Xvfb.
- Real PostgreSQL container integration.
- OCR and visual asset comparison, because those features are not implemented.

---

## 8. Important limitations

This is a hackathon MVP for a synthetic demo workspace. It should not be presented as production-ready identity, legal compliance, or truth certification.

- Rules-only mode is deterministic validation, not LLM reasoning.
- An approval passport records the reviewed version and evidence process; it is not a mathematical guarantee that content is true or legally compliant.
- The demo role switch communicates personas but is not authentication.
- Uploaded source material is not automatically approved.
- A production deployment should add authentication, PostgreSQL migrations, persistent private storage, secrets management, provider data-retention review, monitoring, and tenant-isolation tests.
