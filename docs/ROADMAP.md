# BidSynq — Five-version roadmap

## V1 — Core API starter
Authentication, roles, tender CRUD, bids and explainable ranking.

## V2 — Procurement workspace
Next.js dashboard, RFQ/sealed/reverse-auction workflows, bid visibility controls, anti-sniping and Docker setup.

## V3 — Tender document intelligence
PDF/DOCX/TXT extraction, lexical retrieval, optional Groq grounded answers and source citations.

## V4 — Supplier and price intelligence (this package)
- Buyer-recorded supplier performance outcomes and smoothed explainable trust score
- Similar tender retrieval using category, lexical overlap and quantity similarity
- Indicative price estimate using XGBoost when available, scikit-learn random forest fallback, or category median baseline
- Model/data provenance, sample counts and human-review warnings
- Unit tests and documented limitations

## V5 — Risk, audit and deployment hardening
Isolation Forest anomaly signals routed to human review, hash-chained audit events, notifications, monitoring, tracing, rate limiting, CI, migrations, backups, security review and controlled pilot rollout.

Each version should ship only after acceptance criteria, automated tests and a documented rollback path are met.


## V5 extension
Risk review signals, hash-chained audit events, chain verification and deployment hardening. Risk signals remain advisory and require human review.
