from app.intelligence import MIN_COMPARABLES, estimate_price, similar_tenders, supplier_trust
from tests.conftest import bid_payload


def test_trust_without_history_is_neutral_not_negative():
    r = supplier_trust([])
    assert r["score"] == 70.0 and r["confidence"] == "no_history" and r["observations"] == 0
    assert "neutral prior" in r["explanation"]


def test_trust_score_rewards_good_outcomes_and_is_bounded():
    good = [{"quality_score": 5, "on_time": True, "issue_count": 0}] * 5
    bad = [{"quality_score": 1, "on_time": False, "issue_count": 3}] * 5
    assert supplier_trust(good)["score"] > 70 > supplier_trust(bad)["score"]
    assert 0 <= supplier_trust(bad)["score"] <= supplier_trust(good)["score"] <= 100


def test_trust_tolerates_garbage_and_more_history_means_more_confidence():
    r = supplier_trust([{"quality_score": "x", "on_time": None, "issue_count": "y"}, "junk", None])
    assert r["observations"] == 1 and 0 <= r["score"] <= 100
    one = supplier_trust([{"quality_score": 5, "on_time": True, "issue_count": 0}])
    many = supplier_trust([{"quality_score": 5, "on_time": True, "issue_count": 0}] * 12)
    assert one["confidence"] == "low" and many["confidence"] == "higher" and many["score"] > one["score"]


def test_similar_tenders_prefers_same_category():
    target = {"id": 1, "title": "Safety gloves", "description": "industrial safety gloves", "category": "PPE", "quantity": 100}
    cands = [{"id": 2, "title": "Industrial gloves", "description": "safety gloves", "category": "PPE", "quantity": 90, "status": "closed"},
             {"id": 3, "title": "Office chairs", "description": "furniture", "category": "Furniture", "quantity": 100, "status": "closed"},
             {"id": 1, "title": "itself", "category": "PPE"}, "junk", None]
    results = similar_tenders(target, cands)
    assert [r["tender_id"] for r in results] == [2]
    assert similar_tenders(target, [], 5) == [] and similar_tenders(None, None) == []


def test_price_estimate_reports_insufficient_data_without_history():
    r = estimate_price({"category": "PPE", "quantity": 10}, [])
    assert r["source"] == "insufficient_data" and r["predicted_total_price"] is None and r["suggested_range"] is None


def test_price_estimate_never_reveals_individual_bids():
    # 2 comparable bids: below the privacy minimum -> no estimate that would echo them back
    hist = [{"price": 1234.0, "quantity": 10, "category": "PPE"}, {"price": 4321.0, "quantity": 12, "category": "PPE"}]
    r = estimate_price({"category": "PPE", "quantity": 10}, hist)
    assert r["source"] == "insufficient_data" and r["same_category_samples"] == 2
    hist += [{"price": 2000.0, "quantity": 11, "category": "ppe"}]
    r = estimate_price({"category": "PPE", "quantity": 10}, hist)
    assert r["source"] == "historical_comparables" and r["model"] == "category_median_baseline"
    assert r["predicted_total_price"] == 2000.0 and r["suggested_range"]["low"] <= 2000 <= r["suggested_range"]["high"]


def test_price_estimate_ignores_invalid_history_rows():
    hist = [{"price": float("nan"), "quantity": 5, "category": "A"}, {"price": -1, "quantity": 5, "category": "A"},
            {"price": 10, "quantity": 0, "category": "A"}, "x", None, {"price": "abc"}]
    assert estimate_price({"category": "A", "quantity": 5}, hist)["training_samples"] == 0


def test_price_model_path_with_enough_history():
    hist = [{"price": 1000 + i * 10, "quantity": 10 + i, "category": "PPE" if i % 2 else "IT"} for i in range(MIN_COMPARABLES * 6)]
    r = estimate_price({"category": "PPE", "quantity": 12}, hist)
    assert r["predicted_total_price"] and r["predicted_total_price"] > 0 and r["training_samples"] == len(hist)
    assert r["suggested_range"]["low"] <= r["predicted_total_price"] <= r["suggested_range"]["high"]


# -------------------------------------------------------------------------------- API


def _closed_tender_with_bid(client, buyer, supplier, create_tender, title, price, category="PPE"):
    t = create_tender(title=title, category=category)
    client.post(f"/tenders/{t['id']}/bids", json=bid_payload(price=price), headers=supplier.headers)
    client.patch(f"/tenders/{t['id']}/status", json={"status": "closed"}, headers=buyer.headers)
    return t


def test_price_and_similar_endpoints(client, buyer, supplier, make_user, create_tender):
    others = [make_user("supplier") for _ in range(3)]
    for i, s in enumerate(others):
        _closed_tender_with_bid(client, buyer, s, create_tender, f"Safety gloves batch {i}", 1000 + i * 100)
    target = create_tender(title="Safety gloves batch new")
    body = client.get(f"/tenders/{target['id']}/price-intelligence", headers=buyer.headers).json()
    assert body["human_review_required"] and body["source"] == "historical_comparables" and body["currency"] == "INR"
    assert "not market prices" in body["disclaimer"]
    # suppliers get the same advisory output but never see per-bid data
    supplier_view = client.get(f"/tenders/{target['id']}/price-intelligence", headers=supplier.headers).json()
    assert not {"bids", "supplier_id", "history"} & supplier_view.keys()
    sim = client.get(f"/tenders/{target['id']}/similar?limit=2", headers=buyer.headers).json()
    assert len(sim["matches"]) == 2 and sim["matches"][0]["similarity"] >= sim["matches"][1]["similarity"]


def test_intelligence_respects_tender_ownership(client, buyer, buyer2, create_tender):
    t = create_tender()
    assert client.get(f"/tenders/{t['id']}/price-intelligence", headers=buyer2.headers).status_code == 403
    assert client.get(f"/tenders/{t['id']}/similar", headers=buyer2.headers).status_code == 403
    assert client.get("/tenders/99999/similar", headers=buyer.headers).status_code == 404


# -------------------------------------------------------------------- supplier outcomes


def test_outcome_rules(client, buyer, buyer2, supplier, supplier2, create_tender):
    t = create_tender()
    client.post(f"/tenders/{t['id']}/bids", json=bid_payload(), headers=supplier.headers)
    url = f"/tenders/{t['id']}/supplier-outcomes"
    good = {"supplier_id": supplier.id, "quality_score": 4.5, "on_time": True, "issue_count": 1}
    assert client.post(url, json=good, headers=buyer.headers).status_code == 409       # tender still open
    client.patch(f"/tenders/{t['id']}/status", json={"status": "closed"}, headers=buyer.headers)
    assert client.post(url, json=good, headers=supplier.headers).status_code == 403    # suppliers cannot self-rate
    assert client.post(url, json=good, headers=buyer2.headers).status_code == 403      # not the owner
    for bad in ({"quality_score": 0}, {"quality_score": 6}, {"quality_score": "nan"}, {"issue_count": -1}, {"issue_count": 101}):
        assert client.post(url, json={**good, **bad}, headers=buyer.headers).status_code == 422, bad
    assert client.post(url, json={**good, "supplier_id": supplier2.id}, headers=buyer.headers).status_code == 404   # never bid
    assert client.post(url, json=good, headers=buyer.headers).status_code == 201
    assert client.post(url, json=good, headers=buyer.headers).status_code == 409                                    # duplicate


def test_trust_endpoints_and_visibility(client, buyer, supplier, supplier2, create_tender):
    t = create_tender()
    client.post(f"/tenders/{t['id']}/bids", json=bid_payload(), headers=supplier.headers)
    client.patch(f"/tenders/{t['id']}/status", json={"status": "closed"}, headers=buyer.headers)
    client.post(f"/tenders/{t['id']}/supplier-outcomes", headers=buyer.headers,
                json={"supplier_id": supplier.id, "quality_score": 5, "on_time": True, "issue_count": 0, "notes": "private note"})
    mine = client.get("/suppliers/me/trust", headers=supplier.headers).json()
    assert mine["observations"] == 1 and mine["score"] > 70 and "advisory" in mine["explanation"]
    assert "private note" not in client.get("/suppliers/me/trust", headers=supplier.headers).text
    assert client.get(f"/suppliers/{supplier.id}/trust", headers=buyer.headers).status_code == 200
    assert client.get(f"/suppliers/{supplier.id}/trust", headers=supplier2.headers).status_code == 403
    assert client.get(f"/suppliers/{buyer.id}/trust", headers=buyer.headers).status_code == 404
    fresh = client.get("/suppliers/me/trust", headers=supplier2.headers).json()
    assert fresh["observations"] == 0 and fresh["confidence"] == "no_history" and fresh["score"] == 70.0
