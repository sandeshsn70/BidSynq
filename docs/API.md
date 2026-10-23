# API
Interactive docs: `/docs` (OpenAPI at `/openapi.json`). Auth: `Authorization: Bearer <JWT>`.
Groups: `/auth/*`, `/dashboard/summary`, `/tenders*` (tenders, bids, ranking, documents, assistant, supplier-outcomes, similar, price-intelligence, risk/scan), `/bids/me`, `/suppliers/*/trust`, `/risk/alerts*`, `/audit/*`, `/health`.
A test (`tests/test_frontend_contract.py`) checks the frontend API client and types against the live schema.
Behaviour changes versus the old version: risk-alert review and `/audit/verify` are admin-only; sealed bids stay hidden until closed AND past deadline; suppliers cannot see cancelled tenders they did not bid on; price intelligence needs >=3 comparables; SECRET_KEY must be >=32 chars in production.
