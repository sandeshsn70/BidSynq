from app.rag import chunk_pages, retrieve, extractive_answer


def test_chunking_preserves_pdf_page_numbers():
    chunks = chunk_pages([(3, "Delivery must occur within 30 days. " * 80)], chunk_size=180, overlap=30)
    assert len(chunks) > 1
    assert all(item["page_number"] == 3 for item in chunks)
    assert all(item["content"] for item in chunks)


def test_retrieval_ranks_relevant_passage_first():
    chunks = [
        {"filename": "scope.pdf", "page_number": 2, "section": "Page 2", "content": "The supplier must provide ISO 9001 certification and proof of quality management."},
        {"filename": "schedule.pdf", "page_number": 4, "section": "Page 4", "content": "The bid submission deadline is 30 November."},
    ]
    result = retrieve("What certification must the supplier provide?", chunks)
    assert result
    assert "ISO 9001" in result[0]["content"]
    assert result[0]["score"] > 0


def test_extractive_fallback_does_not_claim_no_evidence():
    answer = extractive_answer("deadline?", [{"content": "The deadline is 30 November."}])
    assert "30 November" in answer


def test_no_match_returns_empty_list():
    assert retrieve("zzzz qqqqq", [{"content": "The supplier must provide quality certificates."}]) == []
