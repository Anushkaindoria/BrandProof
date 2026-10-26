# Technology and implementation details

## Product flow

The judge enters a synthetic workspace, opens the seeded NovaTech X1 campaign, runs an audit, inspects evidence-backed findings, edits the draft, creates a new immutable content version, re-audits it, submits it, and records a human reviewer approval. The approved version has a content passport. If an approved fact version changes later, dependency records drive Brand Drift revalidation.

## Frontend

The frontend is a Next.js 16.4.3 App Router application written in TypeScript and React. It uses `lucide-react` icons, CSS custom properties, and responsive CSS rather than a heavy component framework. `frontend/app/page.tsx` calls the FastAPI endpoints for dashboard, knowledge, content, audit, resolution, review, passport, and drift state. It does not hardcode successful audit output.

## Backend and data layer

The backend is FastAPI with Pydantic request models and SQLAlchemy ORM models. The default local database is SQLite for reliable zero-configuration judging. `DATABASE_URL` can point to PostgreSQL using the included `psycopg` dependency. Organization IDs are applied to demo queries and write paths. The schema also includes extracted claims, assets, asset comparisons, persisted audit jobs, and retrieval traces.

## Audit and retrieval

`backend/app/audit.py` implements a deterministic baseline. It extracts numerical battery/warranty claims with regex, identifies water-resistance language and superlatives, checks prohibited terms, and applies administrator-authored prohibited-claim and required-phrase rules. Exact structured facts are preferred for numerical validation. Each emitted finding receives an evidence ID only from the retrieved facts/policies/terminology passed to the engine. Missing evidence is represented as `Insufficient evidence`, not as a false claim. Extracted claims are persisted with sentence positions and structured values.

`backend/app/retrieval.py` performs deterministic lexical retrieval using token overlap, exact-value boosts, and product matching. The selected context and scores are persisted with the audit and shown in the audit UI. `backend/app/main.py` persists audit findings, extracted claims, retrieval traces, and dependency rows. The engine clearly reports `provider_mode: rules-only` when no key is configured. If `LLM_PROVIDER=gemini` and `LLM_API_KEY` are set, `backend/app/ai.py` sends retrieved facts/policies with untrusted content treated as data, validates returned JSON with Pydantic, strips unknown evidence IDs, and records provider failures while retaining deterministic findings. No general model knowledge is presented as organization authority.

## Approval and passport

Every revision receives a SHA-256 hash. Reviewer approval is a separate endpoint and creates an `ApprovalRecord` tied to the exact content version and hash. The passport snapshots the dependency IDs and versions, audit engine version, reviewer, timestamp, and a limitation notice. New versions do not inherit the prior approval.

## Drift

When an approved fact is updated, its integer version increases. Dependencies recorded during audit are compared with current versions, and approved content with a changed dependency is marked `needs_revalidation`. `/api/drift` explains the changed record and version transition.

## Document processing, assets, migrations, and security baseline

Uploads accept only text, Markdown, and PDF extensions, enforce a 10 MB default limit, use `Path(...).name` for the stored filename, extract PDF text with page markers, reject empty extraction, and store uploaded source documents as `unreviewed` until admin approval. `backend/app/storage.py` provides organization-scoped local storage and an S3-compatible boto3 adapter. Assets accept safe image/logo extensions, store SHA-256 checksums, and can be compared with a local RGB pixel-similarity calculation. Optional image OCR uses Pillow and pytesseract when the Tesseract executable is installed. Alembic configuration includes the audit-job, retrieval-trace, and asset-comparison migration. Uploaded content is treated as data, not executable instructions. External model handling is documented in Settings and README. This build intentionally uses fictional demo data and does not imply production authentication or confidentiality guarantees.

## Background processing

`POST /api/content/{id}/audit/jobs` creates a database-backed job. A bounded in-process worker opens its own SQLAlchemy session, marks the job running, executes the same audit pipeline, stores the resulting audit ID, and reports failures in the job record. This is reliable for the local demo; a distributed queue remains a deployment extension.

## Deployment

The backend and frontend each have a Dockerfile, and `docker-compose.yml` includes PostgreSQL/pgvector for a deployment-shaped local setup. Docker was not installed in the build environment, so image execution is not claimed as tested. The README gives direct process commands for local and hosted deployment.
