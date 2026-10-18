from types import SimpleNamespace
from app.ranking import rank_bids

def test_mandatory_failure_is_ineligible():
    tender = SimpleNamespace(w_price=.35, w_delivery=.2, w_trust=.25, w_match=.2)
    bids = [
        SimpleNamespace(id=1, supplier_id=10, price=100, delivery_days=5, mandatory_met=True, requirement_match=100),
        SimpleNamespace(id=2, supplier_id=11, price=1, delivery_days=1, mandatory_met=False, requirement_match=100),
    ]
    ranked = rank_bids(tender, bids)
    assert ranked[0]["bid_id"] == 1
    assert ranked[1]["eligible"] is False
