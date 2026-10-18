# V3 Tender Document Intelligence

## Scope

V3 adds a document ingestion and retrieval-augmented question-answering workflow to the V2 procurement workspace. A buyer/admin uploads a tender document; the API extracts text, chunks it with source locations, stores chunks in the relational database, retrieves relevant chunks for a question, and returns answer evidence with citations.

## Supported documents

- PDF with selectable text (page numbers are retained)
- DOCX (paragraph and table text; page numbers are unavailable in this format)
- TXT (plain UTF-8 text)

Maximum size defaults to 15 MB. Password-protected PDFs are rejected. Scanned/image-only PDFs return an actionable error; OCR is not implemented in this release. Only these extensions are accepted. Files are assigned random server-side names and never served as public static files.

## Retrieval and generation

1. **Extract:** `app/rag.py` reads the supported format.
2. **Chunk:** text is normalized and split into overlapping passages; PDF page references are retained.
3. **Index:** passages are stored in `document_chunks` and linked to the tender and uploaded source.
4. **Retrieve:** a dependency-light lexical term-overlap ranker selects up to five passages. This is an explainable baseline, not semantic/vector search.
5. **Answer:** with `GROQ_API_KEY`, the API sends only retrieved passages and the question to the configured Groq chat-completions model. The prompt instructs it to abstain when evidence is insufficient and cite `[S1]`-style sources. Without a key, the app returns concise evidence excerpts rather than pretending an LLM answered.
6. **Cite:** the API returns each source filename, PDF page (when known), section, excerpt, and retrieval score.

V3 deliberately does **not** claim pgvector or embedding-based retrieval. V4/V5 can add semantic/hybrid retrieval, reranking, OCR, and production evaluation after the lexical baseline has measurable acceptance results.

## API

- `POST /tenders/{tender_id}/documents` — multipart `file` upload; buyer owner/admin only.
- `GET /tenders/{tender_id}/documents` — list indexed source metadata.
- `DELETE /tenders/{tender_id}/documents/{document_id}` — delete a source and its indexed chunks.
- `POST /tenders/{tender_id}/assistant/ask` — JSON body `{ "question": "..." }`; returns answer, mode, citations and disclaimer.
- `GET /tenders/{tender_id}/assistant/requirements` — matches tender mandatory-requirement lines to source passages as an evidence checklist.

All endpoints require authentication. Buyers are limited to their own tenders. Suppliers can access indexed documents only for open, closed, or awarded tenders. Suppliers cannot upload or delete tender documents.

## Safety and limitations

- Treat all uploaded document text as untrusted data; it is evidence, not instructions for the model.
- LLM responses can still be wrong. Inspect citations and the original document before making a procurement decision.
- A lexical match does not establish supplier compliance or legal sufficiency.
- Avoid uploading confidential or regulated data to an external LLM without organizational approval. When Groq is enabled, retrieved passages are sent to its API.
- Configure a strong `SECRET_KEY`, restrict API origins, set reverse-proxy upload limits, and add rate limits/virus scanning before public deployment.
- V3 uses `create_all` as in V2; production should use reviewed Alembic migrations and tested backups.
