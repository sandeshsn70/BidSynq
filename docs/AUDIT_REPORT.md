# Audit report (original BidSynq-main -> V5.1)
Summary of the issues addressed in the rebuild:
- Authorization: role/ownership checks centralised in `app/access.py`; alert review and audit verification restricted to admins.
- Sealed bids: visibility now considers deadline as well as status.
- Concurrency: row locks on bid/deadline updates, advisory lock for the audit chain, IntegrityError -> 409.
- Secrets/config: weak SECRET_KEY rejected on Render; explicit CORS; no admin self-registration in production.
- AI: Groq prompt hardened against injection from documents; safe fallback with notice; improved lexical retrieval.
- Price intelligence: minimum 3 comparables; supplier trust used in ranking with explanations.
- Database: Alembic idempotent baseline, no schema change, production data preserved.
- Frontend: rebuilt typed client and pages; Next.js 14 -> 15.5.28 and React 19 because 14.x had unpatched critical/high advisories.
- Tests: backend suite, PostgreSQL tests, API contract test, browser e2e run locally.
See SECURITY.md for what is not verified or remains risky.
