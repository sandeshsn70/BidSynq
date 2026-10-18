# V5: Risk Review, Audit Chain, Deployment Hardening

## Risk review
- `POST /tenders/{id}/risk/scan` runs explainable checks for robust price outliers, repeated rounded prices, near-deadline bids, and (with at least eight bids) optional IsolationForest multivariate outliers.
- `GET /risk/alerts` lists alerts; buyers are restricted to their own tenders.
- `PATCH /risk/alerts/{id}/review` lets authorized buyers/admins mark a signal reviewed or dismissed and record a note.
- Alerts are review leads, not fraud labels. Never auto-reject suppliers or automatically award a tender based on them. Preserve due process and verify scope, units, taxes, delivery terms and source evidence.

## Audit trail
- Key events append SHA-256 chained entries with canonical JSON and a previous-entry hash. Events include user registration, tender creation/status changes, bid submission/revision, document upload/deletion, supplier outcome recording, risk scans and alert reviews.
- Admin-only `GET /audit/verify` recomputes the chain. `GET /audit/logs` lists events; buyer access is scoped as far as entity/tender references permit.
- This is tamper-evident, not inherently immutable. A privileged database attacker can rewrite the entire chain. Production should periodically anchor the head hash to independent storage, use append-only/WORM storage, protect backups, and restrict database permissions.

## Production hardening checklist
- Replace `create_all` with Alembic migrations before upgrading an existing database.
- Set a strong unique `SECRET_KEY`; keep secrets out of source control.
- Use TLS, rate limits, secure headers, centralized logging, backups and restore drills.
- Move document storage to private object storage with malware scanning and retention controls.
- Add database-level serialization/locking for concurrent audit writers; current single-process helper is not a distributed sequencing service.
- Configure least-privilege service accounts, monitoring, alerting and a documented incident response plan.
- Run dependency scanning, API authorization tests, integration tests and a frontend production build before release.
