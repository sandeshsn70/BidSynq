# Testing
- Backend: `pytest` (SQLite temp DB, mocked Groq via HTTPX MockTransport). PostgreSQL tests in `tests/test_postgres.py` run when `TEST_DATABASE_URL` points at a disposable PostgreSQL DB; otherwise they skip.
- Frontend contract: `tests/test_frontend_contract.py`.
- Frontend: `npm run lint`, `npx tsc --noEmit`, `npm run build`.
