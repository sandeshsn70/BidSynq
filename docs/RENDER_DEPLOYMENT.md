# Deploy BidSynq V5 to Render

## Architecture
Deploy three Render resources: PostgreSQL, a Python web service for FastAPI, and a Node web service for Next.js. This repository is a monorepo: the backend runs from the repository root and the frontend uses `frontend` as its root directory.

## 1. Push the project to GitHub
Create a repository and push the contents of the `BidSynq_V5` folder to its root. Do not commit `.env`, database files, virtual environments, or API keys.

## 2. Create PostgreSQL
In Render, choose **New + → PostgreSQL**. Create a database and copy its **Internal Database URL** for services in the same Render region.

## 3. Create the backend web service
Choose **New + → Web Service**, connect the repository, and set:
- Root Directory: leave blank (repository root)
- Runtime: Python
- Build Command: `pip install -r requirements.txt`
- Start Command: `uvicorn app.main:app --host 0.0.0.0 --port $PORT`
- Health Check Path: `/health`

Set environment variables:
- `DATABASE_URL`: Internal Database URL from Render PostgreSQL. The code converts `postgres://`/`postgresql://` to the installed `psycopg` driver format.
- `SECRET_KEY`: a long random secret; never use the example value.
- `CORS_ORIGINS`: the frontend URL, e.g. `https://bidsynq-frontend.onrender.com` (no trailing slash).
- `BIDSYNQ_ALLOW_ADMIN_REGISTRATION`: `false`
- `GROQ_API_KEY`: optional; only set if you use the Groq-powered RAG answer generation.
- `GROQ_MODEL`: `llama-3.3-70b-versatile` or a currently supported model for your key.

## 4. Create the frontend web service
Create another **Web Service** from the same GitHub repository. Set:
- Root Directory: `frontend`
- Runtime: Node
- Build Command: `npm install && npm run build`
- Start Command: `npm start`

Set build/runtime environment variable:
- `NEXT_PUBLIC_API_URL`: the backend URL, e.g. `https://bidsynq-api.onrender.com` (no trailing slash).

Next.js embeds `NEXT_PUBLIC_*` values into the browser bundle at build time, so set this before building and redeploy after changing it.

## 5. Verify
1. Open `https://YOUR-BACKEND.onrender.com/health`; expect JSON with `status: ok`.
2. Open `https://YOUR-BACKEND.onrender.com/docs`.
3. Open the frontend URL, register buyer and supplier test accounts, create a tender, and submit a test bid.
4. Check backend logs if the browser reports CORS, database, or 500 errors. Ensure `CORS_ORIGINS` exactly matches the frontend origin.

## Storage and security caveats
- Render's ordinary service filesystem is ephemeral. Uploaded tender documents are stored under `storage/tender_documents`; they may disappear on redeploy/restart unless you attach a persistent disk at a suitable path or change the app to use object storage. Persistent disks may require a paid service.
- A new PostgreSQL database starts empty. `Base.metadata.create_all()` creates tables, but this project does not yet use Alembic migrations. Back up data before schema changes.
- Do not enable public admin registration. Provision an admin account through a controlled process.
- For production, add rate limiting, stronger authorization/integration tests, secure document storage, backups, monitoring, and an external immutable audit checkpoint.
- Free services may sleep when idle and cold-start on the next request; check current Render plan limits and pricing.
