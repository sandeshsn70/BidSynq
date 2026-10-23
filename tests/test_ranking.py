import math
from types import SimpleNamespace as NS

from app.ranking import rank_bids
from tests.conftest import bid_payload

T = NS(w_price=.35, w_delivery=.2, w_trust=.25, w_match=.2)


def bid(i, price, days, match=100, met=True, supplier=None):
    return NS(id=i, supplier_id=supplier or i * 10, price=price, delivery_days=days, requirement_match=match, mandatory_met=met)


def test_mandatory_failure_is_ineligible_and_ranked_last():
    ranked = rank_bids(T, [bid(1, 100, 5), bid(2, 1, 1, met=False)])
    assert [r["bid_id"] for r in ranked] == [1, 2]
    assert ranked[1]["eligible"] is False and ranked[1]["score"] == 0.0
    assert ranked[1]["reason_codes"] == ["MANDATORY_REQUIREMENTS_NOT_MET"]


def test_score_is_weighted_and_hand_checkable():
    # bid 1 is cheapest and fastest (100/100); bid 2 is dearest and slowest (0/0). trust defaults to 50.
    ranked = rank_bids(T, [bid(1, 100, 5, 80), bid(2, 200, 15, 60)])
    first, second = ranked
    assert first["bid_id"] == 1 and first["price_score"] == 100 and first["delivery_score"] == 100
    assert first["score"] == round(.35 * 100 + .2 * 100 + .25 * 50 + .2 * 80, 2)      # 83.5
    assert second["score"] == round(.25 * 50 + .2 * 60, 2)                              # 24.5


def test_real_trust_scores_change_ranking():
    bids = [bid(1, 100, 5, supplier=7), bid(2, 100, 5, supplier=8)]
    ranked = rank_bids(T, bids, {7: 20.0, 8: 95.0})
    assert [r["bid_id"] for r in ranked] == [2, 1]
    assert ranked[0]["trust_score"] == 95.0


def test_weights_are_normalised_and_zero_weights_handled():
    t100 = NS(w_price=35, w_delivery=20, w_trust=25, w_match=20)
    bids = [bid(1, 100, 5), bid(2, 150, 9)]
    assert [r["score"] for r in rank_bids(t100, bids)] == [r["score"] for r in rank_bids(T, bids)]
    zero = rank_bids(NS(w_price=0, w_delivery=0, w_trust=0, w_match=0), bids)
    assert all(math.isfinite(r["score"]) for r in zero) and zero[0]["score"] > 0
    negative = rank_bids(NS(w_price=-1, w_delivery=0, w_trust=1, w_match=0), bids)
    assert all(0 <= r["score"] <= 100 for r in negative)


def test_invalid_numbers_do_not_crash():
    bids = [bid(1, float("nan"), float("inf")), bid(2, None, "x", match="bad"), bid(3, 100, 5, match=1e9)]
    ranked = rank_bids(T, bids)
    assert len(ranked) == 3
    assert all(math.isfinite(r["score"]) and 0 <= r["score"] <= 100 for r in ranked)


def test_empty_and_single_bid():
    assert rank_bids(T, []) == []
    only = rank_bids(T, [bid(1, 100, 5)])
    assert only[0]["price_score"] == 100 and only[0]["eligible"]


def test_equal_scores_are_ordered_deterministically_by_bid_id():
    bids = [bid(5, 100, 5), bid(2, 100, 5), bid(9, 100, 5)]
    order = [r["bid_id"] for r in rank_bids(T, bids)]
    assert order == [2, 5, 9] and order == [r["bid_id"] for r in rank_bids(T, list(reversed(bids)))]


def test_explanations_present_for_every_result():
    ranked = rank_bids(T, [bid(1, 100, 5), bid(2, 100, 5, met=False)])
    assert all(r["explanation"] for r in ranked)


# ------------------------------------------------------------------------------ API


def test_ranking_endpoint_requires_closed_bidding(client, buyer, supplier, create_tender):
    t = create_tender()
    client.post(f"/tenders/{t['id']}/bids", json=bid_payload(), headers=supplier.headers)
    assert client.get(f"/tenders/{t['id']}/ranking", headers=buyer.headers).status_code == 409
    assert client.get(f"/tenders/{t['id']}/ranking", headers=supplier.headers).status_code == 403


def test_ranking_endpoint_uses_recorded_supplier_outcomes(client, buyer, supplier, supplier2, create_tender):
    # Past tender: supplier2 delivered badly, supplier delivered well.
    old = create_tender(title="Previous purchase")
    for s in (supplier, supplier2):
        client.post(f"/tenders/{old['id']}/bids", json=bid_payload(), headers=s.headers)
    client.patch(f"/tenders/{old['id']}/status", json={"status": "closed"}, headers=buyer.headers)
    good = {"supplier_id": supplier.id, "quality_score": 5, "on_time": True, "issue_count": 0}
    bad = {"supplier_id": supplier2.id, "quality_score": 1, "on_time": False, "issue_count": 5}
    for payload in (good, bad):
        assert client.post(f"/tenders/{old['id']}/supplier-outcomes", json=payload, headers=buyer.headers).status_code == 201

    new = create_tender(title="New purchase")
    for s in (supplier, supplier2):
        client.post(f"/tenders/{new['id']}/bids", json=bid_payload(price=1000), headers=s.headers)
    client.patch(f"/tenders/{new['id']}/status", json={"status": "closed"}, headers=buyer.headers)
    body = client.get(f"/tenders/{new['id']}/ranking", headers=buyer.headers).json()
    assert [r["supplier_id"] for r in body["ranking"]] == [supplier.id, supplier2.id]
    assert body["ranking"][0]["trust_score"] > body["ranking"][1]["trust_score"]
    assert body["weights"]["price"] == 0.35 and "advisory" in body["note"]
    assert body["ranking"][0]["supplier_company"]
