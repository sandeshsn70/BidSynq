# BidSynq V5.1

Tender and bidding platform: FastAPI + PostgreSQL backend, Next.js frontend.
Features: RFQ / sealed / reverse-auction tenders, explainable bid ranking, document Q&A (RAG, optional Groq),
supplier trust, price intelligence, risk alerts, tamper-evident audit log.

## Layout
- `app/` backend (routers, models, security, RAG, ranking, audit) - `alembic/` migrations - `tests/` backend tests
- `frontend/` Next.js app - `docs/` documentation (start with `docs/DEPLOYMENT.md`)

## Run locally
Backend (Python 3.12+):
```
python -m venv .venv
.venv\Scripts\Activate.ps1        # PowerShell;  Linux/macOS: source .venv/bin/activate
pip install -r requirements-dev.txt
copy .env.example .env             # then edit SECRET_KEY
alembic upgrade head
uvicorn app.main:app --reload
```
Frontend (Node 20+):
```
cd frontend
copy .env.local.example .env.local
npm install
npm run dev
```
Tests: `pytest` (backend, uses temporary SQLite, never real Groq) and in `frontend/`: `npm run lint`, `npx tsc --noEmit`, `npm run build`.

## Docs
DEPLOYMENT, AUDIT_REPORT, DATABASE, API, SECURITY, TESTING in `docs/`.
