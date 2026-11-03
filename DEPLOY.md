# Deploying BrandProof AI

Backend on Render (or Railway), frontend on Vercel. Never put the Gemini key in the repository: set it as an environment variable in the host's dashboard.

## 1. Backend (Render web service)

- Root directory: `backend`. Runtime: Docker (uses `backend/Dockerfile`) or Python with start command `uvicorn app.main:app --host 0.0.0.0 --port $PORT`.
- Environment variables:

| Variable | Value |
|---|---|
| `LLM_PROVIDER` | `gemini` |
| `LLM_API_KEY` | your Google AI Studio key |
| `LLM_MODEL` | `gemini-flash-latest` |
| `PASSPORT_SECRET` | a long random string |
| `CORS_ORIGINS` | your Vercel URL, for example `https://brandproof.vercel.app` (no trailing slash) |
| `DATABASE_URL` | optional PostgreSQL URL (`postgresql+psycopg://...`); omit to use SQLite |
| `DEMO_MODE` | `true` |

- Free instances have an ephemeral disk. With SQLite the demo data is re-seeded on every restart and uploaded files are lost. For a stable demo use a Render PostgreSQL database; uploaded files are still lost on restart unless you configure S3-compatible storage (`STORAGE_BACKEND=s3`).
- Free instances sleep when idle, and the first request can take about a minute. Open the live link a few minutes before any demo.
- Check `https://<backend>/api/health`: it should report the provider and model.

## 2. Frontend (Vercel)

- Root directory: `frontend`. Framework: Next.js.
- Environment variable: `NEXT_PUBLIC_API_URL=https://<backend>/api`. It is read at build time, so redeploy after changing it.
- After the first deploy, add the Vercel URL to the backend's `CORS_ORIGINS` and redeploy the backend.

## 3. Check before you submit

1. Settings > Test AI connection (as Administrator) shows connected, with the model name.
2. Run the demo script in `submission/judge_demo_script.md` once on the live link, including on a phone.
3. Run `python eval/run_eval.py --gemini` locally with the key and paste the numbers into the report.
