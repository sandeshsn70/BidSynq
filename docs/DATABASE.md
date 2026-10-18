# Database model — V2

## Entities

- **users** — identity, company, role and password hash.
- **tenders** — buyer owner, sourcing description, type, deadline, lifecycle status, requirements, ranking weights and anti-sniping switch.
- **bids** — one initial row per `(tender_id, supplier_id)` with price, delivery, validity, requirement match, compliance declaration and timestamps.

## Relationships

```text
users (1) ───── (many) tenders   via tenders.buyer_id
users (1) ───── (many) bids      via bids.supplier_id
tenders (1) ─── (many) bids      via bids.tender_id
```

The database enforces unique email and unique supplier/tender bid pairs. The API additionally checks ownership, role, tender status, deadlines and reverse-auction price revision rules.

## Important implementation note

The V2 demo uses `Base.metadata.create_all()` at API startup so it is easy to run from scratch. That does not migrate an existing V1 database: V1 and V2 have different columns/constraints. Start V2 with a fresh database. Before using persistent or production data, add Alembic migrations, explicit indexes, retention/backups and a reviewed migration path.

## V3 document-intelligence tables

### `tender_documents`
Stores metadata for uploaded PDF/DOCX/TXT files: tender, uploader, original filename, randomized server-side storage filename, type, size, processing status and timestamp. File bytes are stored under `storage/tender_documents/` rather than in the database.

### `document_chunks`
Stores extracted text passages linked to both the source document and tender. Each chunk records its index, optional PDF page number, section label and text content. V3 uses SQL-backed lexical retrieval; it does not currently store embeddings or use pgvector.

Deleting a document deletes its chunks and its stored file. Production migrations should create indexes appropriate to the chosen database and retrieval engine.
