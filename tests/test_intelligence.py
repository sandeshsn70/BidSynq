from app.intelligence import supplier_trust, similar_tenders, estimate_price

def test_trust_without_history_is_neutral_not_negative():
    result = supplier_trust([])
    assert result["score"] == 70.0
    assert result["confidence"] == "no_history"

def test_trust_score_rewards_good_outcomes():
    good = [{"quality_score": 5, "on_time": True, "issue_count": 0} for _ in range(5)]
    bad = [{"quality_score": 1, "on_time": False, "issue_count": 3} for _ in range(5)]
    assert supplier_trust(good)["score"] > supplier_trust(bad)["score"]

def test_similar_tenders_prefers_same_category():
    target = {"id": 1, "title": "Safety gloves", "description": "industrial safety gloves", "category": "PPE", "quantity": 100}
    candidates = [{"id": 2, "title": "Industrial gloves", "description": "safety gloves", "category": "PPE", "quantity": 90, "status": "closed"}, {"id": 3, "title": "Office chairs", "description": "furniture", "category": "Furniture", "quantity": 100, "status": "closed"}]
    results = similar_tenders(target, candidates)
    assert results[0]["tender_id"] == 2

def test_price_estimate_reports_insufficient_data_without_history():
    result = estimate_price({"category": "PPE", "quantity": 10}, [])
    assert result["source"] == "insufficient_data"
    assert result["predicted_total_price"] is None
