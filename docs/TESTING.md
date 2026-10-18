# Testing — BidSynq V3

## Automated tests

```powershell
py -m pip install -r requirements.txt
py -m pytest -q
```

The RAG unit tests cover chunking/page references, lexical retrieval ranking, evidence-only fallback, and empty results. The existing ranking unit test remains from V2.

## Manual acceptance checklist

1. Register and sign in as a buyer.
2. Create a tender with a future deadline and enter mandatory requirements on separate lines.
3. Open **Document assistant** from the sidebar.
4. Upload a selectable-text PDF, DOCX, or TXT file for that tender.
5. Confirm the document appears in the indexed-document list.
6. Ask a question whose answer is explicitly present in the uploaded file.
7. Confirm at least one citation points to the right file and, for PDF, page number.
8. Repeat without `GROQ_API_KEY`; the response should clearly identify extractive mode and show evidence passages.
9. Set `GROQ_API_KEY` in `.env`, restart the API, ask again, and verify the answer references retrieved source IDs.
10. Upload a scanned PDF and confirm the API returns an explanatory error rather than claiming it was indexed.
11. Sign in as a supplier and confirm document upload/delete is rejected.
12. Confirm a buyer cannot upload, list or delete documents belonging to another buyer's tender.
13. Delete a document and confirm it no longer appears and is not used in later retrieval.
14. Test oversized and unsupported file uploads.

## Known gaps before production

No OCR, semantic embeddings, vector database, malware scanner, antivirus quarantine, rate limiting, formal migration tool, or end-to-end browser tests are included. Use a test database and non-confidential sample documents.
