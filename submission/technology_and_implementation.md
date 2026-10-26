# Technology and implementation details

## Product flow

The judge enters a synthetic workspace, opens the seeded NovaTech X1 campaign, runs an audit, inspects evidence-backed findings, edits the draft, creates a new immutable content version, re-audits it, submits it, and records a human reviewer approval. The approved version has a content passport. If an approved fact version changes later, dependency records drive Brand Drift revalidation.

## Frontend

The frontend is a Next.js 16.4.3 App Router application written in TypeScript and React. It uses `lucide-react` icons, CSS custom properties, and responsive CSS rather than a heavy component framework. `frontend/app/page.tsx` calls the FastAPI endpoints for dashboard, knowledge, content, audit, resolution, review, passport, and drift state. It does not hardcode successful audit output.

## Backend and data layer

The backend is FastAPI with Pydantic request models and SQLAlchemy ORM models. The default local database is SQLite for reliable zero-configuration judging. `DATABASE_URL` can point to PostgreSQL using the included `psycopg` dependency. Organization IDs are applied to demo queries and write paths. The main schema includes organizations, users, source documents, approved facts, policies, terminology, content items, content versions, audit runs, findings, dependencies, review decisions, approval records, and audit events.

## Audit and retrieval

`backend/app/audit.py` implements a deterministic baseline. It extracts numerical battery/warranty claims with regex, identifies water-resistance language and superlatives, and checks prohibited terms. Exact structured facts are preferred for numerical validation. Each emitted finding receives an evidence ID only from the retrieved facts/policies/terminology passed to the engine. Missing evidence is represented as `Insufficient evidence`, not as a false claim.

`backend/app/main.py` persists audit findings and dependency rows. The current engine is rules-only and clearly reports `provider_mode: rules-only` when no external key is configured. No general model knowledge is presented as organization authority.

## Approval and passport

Every revision receives a SHA-256 hash. Reviewer approval is a separate endpoint and creates an `ApprovalRecord` tied to the exact content version and hash. The passport snapshots the dependency IDs and versions, audit engine version, reviewer, timestamp, and a limitation notice. New versions do not inherit the prior approval.

## Drift

When an approved fact is updated, its integer version increases. Dependencies recorded during audit are compared with current versions, and approved content with a changed dependency is marked `needs_revalidation`. `/api/drift` explains the changed record and version transition.

## Document processing and security baseline

Uploads accept only text, Markdown, and PDF extensions, enforce a 10 MB default limit, use `Path(...).name` for the stored filename, extract PDF text with `pypdf`, reject empty extraction, and store uploaded source documents as `unreviewed`. Uploaded content is treated as data, not executable instructions. External model handling is documented in Settings and README. This build intentionally uses fictional demo data and does not imply production authentication or confidentiality guarantees.

## Deployment

The backend and frontend each have a Dockerfile, and `docker-compose.yml` includes PostgreSQL/pgvector for a deployment-shaped local setup. Docker was not installed in the build environment, so image execution is not claimed as tested. The README gives direct process commands for local and hosted deployment.
