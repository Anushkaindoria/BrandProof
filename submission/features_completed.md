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
- **Structured claim persistence** — Every audit stores extracted claim text, claim type, entity, structured values, and character positions.
- **Brand Compiler baseline** — Administrators can create prohibited-claim, required-phrase/disclaimer, and superlative policies that the deterministic engine applies.
- **Demo authorization** — Mutating requests accept an explicit `X-Demo-Role` and enforce creator/reviewer/admin permissions. Administrators can view and change demo user roles.
- **Document and asset approval** — Uploaded source documents remain unreviewed until admin approval. Logo/image assets are stored under safe organization-scoped keys with checksums and approval state.
- **Visual asset comparison** — Approved PNG/JPG/WEBP assets can be compared against candidate uploads using a local RGB pixel-similarity calculation. The result is persisted as match, review, or mismatch with a similarity score. Tested with matching and contrasting generated images.
- **Lexical evidence retrieval** — Audits retrieve relevant facts and policies using token overlap, exact-value boosts, and product matching. Retrieved IDs, labels, source references, and scores are stored with each audit and shown in the UI.
- **Storage backend abstraction** — Uploads use an organization-scoped local storage backend or an S3-compatible backend selected by environment configuration. Path traversal is rejected by the local backend.
- **Background audit jobs** — Audits can be queued into a persisted pending/running/completed/failed job record and executed by a bounded worker pool. The UI polls job status and refreshes findings on completion.
- **Passport UI** — Content History can fetch and display the approved version passport, dependencies, findings, reviewer, timestamp, and limitation notice.
- **Migration lifecycle** — Alembic configuration and versioned schema migrations for retrieval traces, background jobs, and asset comparisons are included and verified against a fresh SQLite database.
- **Responsive product UI** — Next.js + TypeScript UI includes Dashboard, Brand Knowledge, Content Audit, Review Queue, Content History, Brand Drift, and Settings pages with empty states and explicit rules-only status.
- **Health check and deployment files** — `/api/health`, `.env.example`, `.gitignore`, Dockerfiles, Docker Compose, and startup instructions are present.

## Implemented; environment validation still pending

- **PostgreSQL compatibility** — SQLAlchemy URLs, `psycopg`, Alembic, and Docker Compose pgvector configuration are included, but Docker/PostgreSQL execution was not possible in this environment.
- **PDF extraction** — The code path is implemented through `pypdf` with page markers; the automated suite does not include a real PDF fixture.
- **OCR** — The image OCR endpoint uses Pillow/pytesseract and reports a clear error when the Tesseract executable is unavailable. The executable was not available in this environment.
- **Gemini provider** — A real HTTP adapter, retrieved-context prompt, Pydantic output validation, evidence-ID validation, and visible fallback error are implemented. No external API key was available for live provider testing.
- **S3-compatible storage** — The adapter is implemented through boto3 and requires a configured bucket/credentials or endpoint for live validation. Local storage is fully exercised.

## Planned, not implemented in Round 2

- pgvector semantic retrieval and source-document chunk indexing. The tested lexical retrieval fallback is implemented and persisted.
- Production authentication and organization provisioning.
- Notifications, distributed queues, and provider-specific telemetry.
