# BrandProof AI API

FastAPI backend for the BrandProof AI demo workspace. The default database is local SQLite so a judge can run it without Docker or PostgreSQL. The schema uses SQLAlchemy models and can be pointed at PostgreSQL through `DATABASE_URL` for deployment.

```bash
python3 -m venv .venv
. .venv/bin/activate
pip install -r requirements.txt
uvicorn app.main:app --reload --port 8000
```

The app creates the schema and seeds the synthetic BrandProof Demo Workspace on startup. Use `python seed.py` to reset the seed data. For a persistent deployment database, run `alembic upgrade head` before starting the API.

Optional integrations:

- Set `LLM_PROVIDER=gemini`, `LLM_API_KEY`, and `LLM_MODEL` to enable provider-backed semantic review. Rules remain authoritative for deterministic checks and provider failures are recorded visibly.
- Image OCR uses Pillow/pytesseract and requires the Tesseract executable installed separately on the host.
- Upload storage defaults to organization-scoped local files. Set `STORAGE_BACKEND=s3`, `S3_STORAGE_BUCKET`, and compatible credentials for the S3 adapter.
- `POST /api/content/{id}/audit/jobs` runs the persisted local background-audit flow; distributed queues are not required for the demo.
