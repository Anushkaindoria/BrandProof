# Changes from Round 1

## Stayed the same

- The BrandProof identity remains an evidence-backed brand governance product rather than a generic chat interface.
- The core navigation and visual direction remain: warm ivory canvas, navy typography, purple primary accent, soft evidence/status panels, and rounded B2B cards.
- The central workflow remains audit → explain → revise → human approval → traceability.
- The architecture remains a TypeScript/React frontend with a Python API and relational persistence.

## Changed for Round 2 reliability

- The Round 2 demo defaults to SQLite instead of requiring PostgreSQL before the first page loads. This removes the biggest judge-demo setup risk while keeping a PostgreSQL/pgvector Docker Compose path and SQLAlchemy compatibility.
- The first working audit engine is deterministic rules-only. This is an honest fallback for a missing provider key and makes the mandatory NovaTech demonstration reproducible. Provider configuration is surfaced, but no unavailable LLM integration is claimed.
- Retrieval is deterministic lexical lookup with exact-value and product boosts, persisted scores, and source references rather than an unverified vector similarity layer. This keeps numerical claims and source references dependable within the three-day build window.
- OCR endpoint/UI, Gemini adapter, Alembic configuration, local/S3-compatible storage, visual comparison, and persisted background audit jobs were added for Round 2. Live OCR requires the host Tesseract executable, live Gemini/S3 testing requires external configuration, and PostgreSQL/Docker execution was unavailable here. pgvector retrieval, production authentication, distributed queues, and notifications remain deferred rather than being represented by nonfunctional controls.

## Functionality retained

- Approved facts and policies are versioned and source-linked.
- Content versions are immutable records with hashes.
- Findings distinguish contradiction, support, and insufficient evidence.
- Human reviewer approval is separate from automated audit.
- Dependency-based Brand Drift is implemented with a relational table.
- Dashboard values come from persisted application data.

## Deferred work

The largest deferred components are pgvector retrieval, production identity, distributed queues, and notifications. The MVP preserves upgrade points: provider settings, evidence types, dependency rows, source documents, storage backends, persisted jobs, Alembic configuration, and PostgreSQL deployment configuration are already represented in the API/data model.
