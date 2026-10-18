# API Reference — BidSynq V3

Base URL for local development: `http://127.0.0.1:8000`. Interactive OpenAPI: `/docs`. Send `Authorization: Bearer <access_token>` to protected endpoints.

## Existing V2 endpoints

- `POST /auth/register`, `POST /auth/login`, `GET /auth/me`
- `GET /dashboard/summary`
- `POST /tenders`, `GET /tenders`, `GET /tenders/{id}`, `PATCH /tenders/{id}/status`
- `POST /tenders/{id}/bids`, `PUT /tenders/{id}/bids/me`, `GET /tenders/{id}/bids`, `GET /tenders/{id}/ranking`

## V3 document intelligence

### Upload a document
`POST /tenders/{tender_id}/documents` as `multipart/form-data`, field `file`.

Supported: PDF, DOCX, TXT. Max size is configured by `MAX_DOCUMENT_MB` (default 15 MB). Only a buyer who owns the tender or an admin may upload. Returns document metadata and `chunks_indexed`.

### List documents
`GET /tenders/{tender_id}/documents`

Returns source metadata, not file bytes.

### Delete a document
`DELETE /tenders/{tender_id}/documents/{document_id}`

Deletes the source metadata and its indexed chunks, then removes the stored file.

### Ask a question
`POST /tenders/{tender_id}/assistant/ask`

Request:
```json
{"question":"Which certificates are mandatory for suppliers?"}
```

Response includes:
- `answer`: grounded generated answer when Groq is configured, or relevant evidence excerpts without an API key
- `mode`: indicates which answer path was used
- `citations`: source ID, filename, PDF page when available, section, excerpt and lexical relevance score
- `disclaimer`: reminder to verify the original document

### Requirement evidence checklist
`GET /tenders/{tender_id}/assistant/requirements`

Splits the tender's `mandatory_requirements` text on newlines and semicolons, then finds a best matching document passage for each line. `evidence_found` is only a retrieval signal. Every row is explicitly marked for human review.

## Common errors

- `401`: missing/invalid token
- `403`: role or tender ownership restriction
- `404`: tender/document unavailable
- `413`: upload exceeds size limit
- `415`: unsupported file extension
- `422`: unreadable, encrypted or image-only PDF; invalid question; or text extraction failure


## V4 intelligence endpoints

### Record outcome
`POST /tenders/{tender_id}/supplier-outcomes` (buyer/admin)
```json
{"supplier_id": 7, "quality_score": 4.5, "on_time": true, "issue_count": 0, "notes": "Delivery inspected by buyer"}
```
One outcome per supplier/tender; tender must be closed and the supplier must have a bid.

### Supplier trust
`GET /suppliers/{supplier_id}/trust` or `GET /suppliers/me/trust` (supplier self-only for supplier role).

### Similar tenders
`GET /tenders/{tender_id}/similar?limit=5`

### Price intelligence
`GET /tenders/{tender_id}/price-intelligence`
Returns model/baseline, price range when supported, training sample counts, explanation, and a human-review disclaimer.


## V5 Risk & Audit
- `POST /tenders/{id}/risk/scan` — buyer/admin, creates deduplicated review alerts.
- `GET /risk/alerts` — buyer/admin, filter by tender and status.
- `PATCH /risk/alerts/{id}/review` — buyer/admin; JSON body `{"status":"reviewed|dismissed","note":"review notes"}`.
- `GET /audit/logs` — buyer/admin, paginated events.
- `GET /audit/verify` — admin only; verifies current hash chain.
