# BidSynq V5 — Supplier and Price Intelligence

BidSynq is a B2B procurement workspace for buyers and suppliers. V4 carries forward V1–V3 capabilities (authentication, tender workflows, bids, explainable bid ranking and tender-document RAG) and adds advisory supplier performance scoring, similar-tender discovery and historical price estimates.

> **Important:** This is a development MVP. Price estimates and trust scores are advisory only. They must not automatically determine supplier eligibility or tender awards.

## V4 additions

- **Supplier trust profile:** Buyer-recorded quality, on-time delivery and issue-count outcomes, smoothed toward a neutral prior when evidence is sparse.
- **Similar tenders:** Transparent category, title/description token overlap and quantity similarity baseline.
- **Price intelligence:** Attempts XGBoost if installed, otherwise scikit-learn Random Forest when enough history exists; falls back to a same-category median or returns no estimate.
- **Explainability:** API returns method, sample counts, confidence/limitations and human-review warnings. Full SHAP reports and time-aware MAE/MAPE validation are not yet implemented.
- **Documentation and tests:** See `docs/INTELLIGENCE.md`, `docs/API.md` and `tests/`.

## Run locally on Windows

Open PowerShell in the extracted `BidSynq_V5` directory:

```powershell
py -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
Copy-Item .env.example .env
uvicorn app.main:app --reload
```

Open a second PowerShell window:

```powershell
cd frontend
Copy-Item .env.local.example .env.local
npm install
npm run dev
```

Open the workspace at `http://localhost:3000` and API documentation at `http://127.0.0.1:8000/docs`. The UI is carried forward from V3; V4 intelligence is exposed through the documented API endpoints and Swagger UI rather than a dedicated analytics screen.

## Key V4 API endpoints

- `POST /tenders/{tender_id}/supplier-outcomes` — buyer/admin records a supplier outcome after the tender closes. The supplier must have bid on that tender.
- `GET /suppliers/{supplier_id}/trust` — view an advisory supplier trust profile. A supplier may view only their own profile.
- `GET /suppliers/me/trust` — current supplier's trust profile.
- `GET /tenders/{tender_id}/similar?limit=5` — find similar closed/awarded tenders.
- `GET /tenders/{tender_id}/price-intelligence` — get an indicative historical-price estimate when data supports one.

Use the **Authorize** control in Swagger UI and paste the access token returned by `/auth/login`. The token field should contain the bearer token; Swagger will send it as an Authorization header.

## Optional model packages

The requirements install scikit-learn and NumPy for the baseline price model. To try XGBoost, install it separately inside the virtual environment:

```powershell
pip install xgboost
```

SHAP is not yet used to generate validated per-prediction explanations in this version.

## Docker Compose

```powershell
docker compose up --build
```

Docker Compose starts PostgreSQL, FastAPI and the Next.js frontend. Change development credentials/secrets before any shared deployment.

## Run tests

```powershell
pytest -q
```

The current unit suite covers ranking, RAG helpers and supplier/price intelligence helpers. API integration, browser workflow, load, penetration and real-world price-model validation are not certified by these unit tests.

## Limitations and safe use

- Trust data is manually recorded and can be incomplete or biased. No history returns a neutral prior, not a negative rating.
- Similar-tender matching is lexical and category-based, not embedding-based semantic retrieval.
- Price features are limited to category and quantity. Shipping, taxes, geography, specifications, currency, supplier quality and time effects are not fully represented.
- Historical bid samples may not be comparable. A median baseline is not a validated forecast.
- Do not use the model as the sole basis for pricing, supplier screening or procurement awards.
- Before production, add database migrations, rate limits, file and API security review, robust authorization tests, audit trails, monitoring, backups and time-aware MAE/MAPE validation.


## V5 additions
- Explainable bid risk signals and a buyer/admin review workflow.
- SHA-256 hash-chained audit log with an admin-only chain verification endpoint.
- Risk and audit documentation: `docs/V5_SECURITY_RISK_AUDIT.md`.

### V5 endpoints
- `POST /tenders/{id}/risk/scan`
- `GET /risk/alerts?tender_id=...&status=open`
- `PATCH /risk/alerts/{id}/review` with `{"status":"reviewed","note":"..."}` or `dismissed`
- `GET /audit/logs`
- `GET /audit/verify` (admin only)

Risk alerts are not proof of misconduct and must never be used for automatic rejection or award. The audit chain is tamper-evident, not an immutable store. See the V5 security guide before deployment.

## Deploy to Render
See [`docs/RENDER_DEPLOYMENT.md`](docs/RENDER_DEPLOYMENT.md) for the current two-service + PostgreSQL deployment guide.
