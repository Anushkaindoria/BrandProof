# BrandProof AI Round 2 feature status

## Completed and tested

- **Seeded demo workspace** — A fictional BrandProof Demo Workspace with NovaTech X1 facts, policies, terminology, source document, users, and an illustrative campaign is created reproducibly by `backend/app/seed.py`. Tested via API and backend integration tests.
- **Content audit pipeline** — Content versions are saved with SHA-256 hashes and audited through deterministic claim extraction, exact fact checks, terminology checks, policy checks, structured findings, and evidence references. Tested against the mandatory 7000 mAh / waterproof / superlative example.
- **Explainable evidence** — Findings carry verification status, severity, explanation, suggestion, confidence, evidence type, evidence ID, excerpt, and source reference. Tests assert the battery finding points to the approved fact.
- **Correction and re-audit loop** — New revisions are persisted, audited independently, and shown as the current version. The API integration test exercises revision, re-audit, submission, and approval.
- **Human review and approval record** — Review decisions are persisted against a content version; approval creates a passport with content hash, dependency versions, audit engine version, reviewer, and timestamp. Tested through the API.
- **Brand Drift dependency tracking** — Audit evidence creates dependency records. Fact version updates identify affected content versions and mark approved content for revalidation. The endpoint and UI are implemented.
- **Dashboard analytics** — Review counts, unresolved findings, queue counts, drift counts, category breakdown, and recent events are calculated from database records, not hardcoded metrics.
- **Knowledge base UI/API** — Facts, policies, terminology, and source documents are listed. Demo admin role can create facts and policies. The API enforces organization scope on mutations.
- **Safe document upload baseline** — `.txt`, `.md`, and PDF text extraction are supported with extension, size, safe filename handling, empty-text, and extraction errors. Unsupported HTML uploads are tested and rejected.
- **Responsive product UI** — Next.js + TypeScript UI includes Dashboard, Brand Knowledge, Content Audit, Review Queue, Content History, Brand Drift, and Settings pages with empty states and explicit rules-only status.
- **Health check and deployment files** — `/api/health`, `.env.example`, `.gitignore`, Dockerfiles, Docker Compose, and startup instructions are present.

## Implemented but incompletely tested

- **PostgreSQL compatibility** — SQLAlchemy URLs and `psycopg` are included and Docker Compose includes pgvector PostgreSQL, but Docker is unavailable in this environment, so the PostgreSQL container path was not executed.
- **PDF extraction** — The code path is implemented through `pypdf`; a malformed and a real PDF fixture were not exercised in the automated suite.
- **UI role switching** — The visible demo selector changes the persona view; the backend remains on a seeded demo identity. Production authentication is intentionally out of scope.

## Partially implemented

- **Optional LLM provider** — Configuration fields and explicit provider-mode reporting exist, but the MVP ships with a rules-only fallback and does not claim an external Gemini/OpenAI integration is complete.
- **Admin fact editing in the UI** — Fact/policy creation is available in the UI; the versioning edit path is available as an API and is used for the Brand Drift demo. A richer edit form remains.
- **Content passport UI** — Passport data is persisted and exposed through the API/history flow; a dedicated expanded passport panel is a small UI follow-up.

## Planned, not implemented

- OCR and visual asset comparison with OpenCV.
- pgvector semantic retrieval and source-document chunk indexing.
- Full Alembic migration lifecycle; the demo creates SQLite schema from SQLAlchemy metadata and includes a migration marker for the initial schema.
- Production authentication, organization provisioning, and object-storage adapter.
- A production-grade external LLM adapter with structured response validation and provider-specific error telemetry.
