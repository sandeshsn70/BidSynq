from datetime import datetime, timedelta, timezone

from tests.conftest import bid_payload, tender_payload


# ------------------------------------------------------------------ tender creation


def test_buyer_creates_and_reads_tender(client, buyer, create_tender):
    tender = create_tender()
    assert tender["buyer_id"] == buyer.id and tender["status"] == "open" and tender["bidding_open"] is True
    assert client.get(f"/tenders/{tender['id']}", headers=buyer.headers).json()["title"] == tender["title"]


def test_tender_validation(client, buyer):
    def post(**o):
        return client.post("/tenders", json=tender_payload(**o), headers=buyer.headers)

    assert post(w_price=0.5, w_delivery=0.5, w_trust=0.5, w_match=0.5).status_code == 400   # sum != 1
    assert post(deadline=(datetime.now(timezone.utc) - timedelta(hours=1)).isoformat()).status_code == 400
    assert post(deadline="2030-01-01T10:00:00").status_code == 422                          # no timezone
    assert post(quantity=0).status_code == 422
    assert post(title="abc").status_code == 422
    assert post(tender_type="auction").status_code == 422
    assert post(w_price=-0.1, w_delivery=0.45, w_trust=0.35, w_match=0.3).status_code == 422
    assert post(w_price="nan").status_code == 422


def test_supplier_cannot_create_tender(client, supplier):
    assert client.post("/tenders", json=tender_payload(), headers=supplier.headers).status_code == 403


# ------------------------------------------------------------------ ownership (BOLA)


def test_buyers_cannot_see_or_change_each_others_tenders(client, buyer, buyer2, create_tender):
    tender = create_tender()
    tid = tender["id"]
    assert client.get(f"/tenders/{tid}", headers=buyer2.headers).status_code == 403
    assert client.patch(f"/tenders/{tid}", json={"title": "Hijacked title"}, headers=buyer2.headers).status_code == 403
    assert client.patch(f"/tenders/{tid}/status", json={"status": "closed"}, headers=buyer2.headers).status_code == 403
    assert client.get(f"/tenders/{tid}/bids", headers=buyer2.headers).status_code == 403
    assert client.get(f"/tenders/{tid}/ranking", headers=buyer2.headers).status_code == 403
    assert client.post(f"/tenders/{tid}/risk/scan", headers=buyer2.headers).status_code == 403
    assert client.get("/tenders?status=all", headers=buyer2.headers).json() == []


def test_admin_can_view_and_manage_any_tender(client, admin, create_tender):
    tender = create_tender()
    assert client.get(f"/tenders/{tender['id']}", headers=admin.headers).status_code == 200
    assert client.patch(f"/tenders/{tender['id']}/status", json={"status": "closed"}, headers=admin.headers).status_code == 200


def test_supplier_listing_hides_cancelled_unless_they_bid(client, buyer, supplier, supplier2, create_tender):
    t = create_tender()
    client.post(f"/tenders/{t['id']}/bids", json=bid_payload(), headers=supplier.headers)
    client.patch(f"/tenders/{t['id']}/status", json={"status": "cancelled"}, headers=buyer.headers)
    assert [x["id"] for x in client.get("/tenders?status=cancelled", headers=supplier.headers).json()] == [t["id"]]
    assert client.get("/tenders?status=cancelled", headers=supplier2.headers).json() == []
    assert client.get(f"/tenders/{t['id']}", headers=supplier2.headers).status_code == 404


# ----------------------------------------------------------------------- update/status


def test_update_tender_and_audit(client, buyer, create_tender):
    t = create_tender()
    r = client.patch(f"/tenders/{t['id']}", json={"title": "Updated title", "quantity": 250}, headers=buyer.headers)
    assert r.status_code == 200 and r.json()["title"] == "Updated title" and r.json()["quantity"] == 250
    logs = client.get("/audit/logs", headers=buyer.headers).json()["items"]
    assert any(i["action"] == "tender.updated" for i in logs)


def test_update_rules_after_bids(client, buyer, supplier, create_tender):
    t = create_tender()
    client.post(f"/tenders/{t['id']}/bids", json=bid_payload(), headers=supplier.headers)
    url = f"/tenders/{t['id']}"
    assert client.patch(url, json={"w_price": 0.4, "w_delivery": 0.15}, headers=buyer.headers).status_code == 409
    assert client.patch(url, json={"quantity": 5}, headers=buyer.headers).status_code == 409
    earlier = (datetime.now(timezone.utc) + timedelta(days=1)).isoformat()
    later = (datetime.now(timezone.utc) + timedelta(days=30)).isoformat()
    assert client.patch(url, json={"deadline": earlier}, headers=buyer.headers).status_code == 409
    assert client.patch(url, json={"deadline": later}, headers=buyer.headers).status_code == 200
    assert client.patch(url, json={"description": "Clarified scope"}, headers=buyer.headers).status_code == 200


def test_update_validation(client, buyer, create_tender):
    t = create_tender()
    url = f"/tenders/{t['id']}"
    assert client.patch(url, json={}, headers=buyer.headers).status_code == 400
    assert client.patch(url, json={"tender_type": "sealed"}, headers=buyer.headers).status_code == 422  # immutable
    assert client.patch(url, json={"w_price": 0.9}, headers=buyer.headers).status_code == 400            # weights != 1
    assert client.patch(url, json={"deadline": "2020-01-01T00:00:00Z"}, headers=buyer.headers).status_code == 400
    assert client.patch(url, json={"title": None}, headers=buyer.headers).status_code == 400


def test_status_transitions(client, buyer, create_tender):
    t = create_tender()
    url = f"/tenders/{t['id']}/status"
    assert client.patch(url, json={"status": "awarded"}, headers=buyer.headers).status_code == 422
    assert client.patch(url, json={"status": "closed"}, headers=buyer.headers).json()["status"] == "closed"
    assert client.patch(url, json={"status": "cancelled"}, headers=buyer.headers).status_code == 409
    assert client.patch(f"/tenders/{t['id']}", json={"title": "Too late now"}, headers=buyer.headers).status_code == 409


# ----------------------------------------------------------------------------- bidding


def test_bid_submission_and_duplicate_rejected(client, supplier, create_tender):
    t = create_tender()
    first = client.post(f"/tenders/{t['id']}/bids", json=bid_payload(), headers=supplier.headers)
    assert first.status_code == 201 and first.json()["supplier_id"] == supplier.id
    second = client.post(f"/tenders/{t['id']}/bids", json=bid_payload(price=900), headers=supplier.headers)
    assert second.status_code == 409


def test_only_suppliers_can_bid(client, buyer, admin, create_tender):
    t = create_tender()
    for actor in (buyer, admin):
        assert client.post(f"/tenders/{t['id']}/bids", json=bid_payload(), headers=actor.headers).status_code == 403


def test_bid_validation(client, supplier, create_tender):
    t = create_tender()
    url = f"/tenders/{t['id']}/bids"
    for bad in ({"price": 0}, {"price": -5}, {"price": "nan"}, {"price": "inf"}, {"delivery_days": 0},
                {"validity_days": 0}, {"requirement_match": 101}, {"requirement_match": -1}, {"price": 1e20}):
        assert client.post(url, json=bid_payload(**bad), headers=supplier.headers).status_code == 422, bad
    assert client.post("/tenders/999999/bids", json=bid_payload(), headers=supplier.headers).status_code == 404


def test_deadline_enforced_even_if_status_still_open(client, supplier, create_tender, set_deadline):
    t = create_tender()
    set_deadline(t["id"], datetime.now(timezone.utc) - timedelta(minutes=1))
    r = client.post(f"/tenders/{t['id']}/bids", json=bid_payload(), headers=supplier.headers)
    assert r.status_code == 400
    assert client.get(f"/tenders/{t['id']}", headers=supplier.headers).json()["bidding_open"] is False


def test_closed_and_cancelled_tenders_reject_bids(client, buyer, supplier, supplier2, create_tender):
    a, b = create_tender(), create_tender(title="Another tender")
    client.patch(f"/tenders/{a['id']}/status", json={"status": "closed"}, headers=buyer.headers)
    client.patch(f"/tenders/{b['id']}/status", json={"status": "cancelled"}, headers=buyer.headers)
    assert client.post(f"/tenders/{a['id']}/bids", json=bid_payload(), headers=supplier.headers).status_code == 400
    assert client.post(f"/tenders/{b['id']}/bids", json=bid_payload(), headers=supplier2.headers).status_code == 400


def test_suppliers_only_see_their_own_bids(client, buyer, supplier, supplier2, create_tender):
    t = create_tender()
    client.post(f"/tenders/{t['id']}/bids", json=bid_payload(price=500), headers=supplier.headers)
    client.post(f"/tenders/{t['id']}/bids", json=bid_payload(price=400), headers=supplier2.headers)
    mine = client.get(f"/tenders/{t['id']}/bids", headers=supplier.headers).json()
    assert [b["supplier_id"] for b in mine] == [supplier.id]
    assert len(client.get(f"/tenders/{t['id']}/bids", headers=buyer.headers).json()) == 2
    listing = client.get("/bids/me", headers=supplier.headers).json()
    assert len(listing) == 1 and listing[0]["tender_title"] == t["title"] and listing[0]["bidding_open"] is True


# ------------------------------------------------------------------------- sealed bids


def test_sealed_bids_hidden_until_closed(client, buyer, admin, supplier, create_tender):
    t = create_tender(tender_type="sealed")
    client.post(f"/tenders/{t['id']}/bids", json=bid_payload(), headers=supplier.headers)
    url = f"/tenders/{t['id']}/bids"
    assert client.get(url, headers=buyer.headers).status_code == 403
    assert client.get(url, headers=admin.headers).status_code == 403
    assert client.get(url, headers=supplier.headers).status_code == 200      # own bid is still visible
    client.patch(f"/tenders/{t['id']}/status", json={"status": "closed"}, headers=buyer.headers)
    assert len(client.get(url, headers=buyer.headers).json()) == 1


def test_sealed_bids_open_after_deadline_without_manual_close(client, buyer, supplier, create_tender, set_deadline):
    t = create_tender(tender_type="sealed")
    client.post(f"/tenders/{t['id']}/bids", json=bid_payload(), headers=supplier.headers)
    set_deadline(t["id"], datetime.now(timezone.utc) - timedelta(seconds=5))
    assert client.get(f"/tenders/{t['id']}/bids", headers=buyer.headers).status_code == 200


def test_rfq_bids_visible_to_owner_while_open(client, buyer, supplier, create_tender):
    t = create_tender()
    client.post(f"/tenders/{t['id']}/bids", json=bid_payload(), headers=supplier.headers)
    assert client.get(f"/tenders/{t['id']}/bids", headers=buyer.headers).status_code == 200


# ---------------------------------------------------------------------- reverse auctions


def test_reverse_auction_revision_rules(client, supplier, create_tender):
    t = create_tender(tender_type="reverse_auction")
    url = f"/tenders/{t['id']}/bids/me"
    client.post(f"/tenders/{t['id']}/bids", json=bid_payload(price=1000), headers=supplier.headers)
    assert client.put(url, json=bid_payload(price=1000), headers=supplier.headers).status_code == 400   # not lower
    assert client.put(url, json=bid_payload(price=1200), headers=supplier.headers).status_code == 400
    ok = client.put(url, json=bid_payload(price=900), headers=supplier.headers)
    assert ok.status_code == 200 and ok.json()["price"] == 900


def test_revision_not_allowed_for_rfq(client, supplier, create_tender):
    t = create_tender()
    client.post(f"/tenders/{t['id']}/bids", json=bid_payload(), headers=supplier.headers)
    assert client.put(f"/tenders/{t['id']}/bids/me", json=bid_payload(price=1), headers=supplier.headers).status_code == 400


def test_anti_sniping_extends_deadline(client, supplier, create_tender, set_deadline):
    t = create_tender(tender_type="reverse_auction")
    set_deadline(t["id"], datetime.now(timezone.utc) + timedelta(seconds=60))
    client.post(f"/tenders/{t['id']}/bids", json=bid_payload(), headers=supplier.headers)
    new_deadline = datetime.fromisoformat(client.get(f"/tenders/{t['id']}", headers=supplier.headers).json()["deadline"])
    if new_deadline.tzinfo is None:
        new_deadline = new_deadline.replace(tzinfo=timezone.utc)
    assert new_deadline - datetime.now(timezone.utc) > timedelta(seconds=90)


# --------------------------------------------------------------------------- dashboard


def test_dashboard_is_role_specific_and_real(client, buyer, supplier, admin, create_tender):
    t = create_tender()
    client.post(f"/tenders/{t['id']}/bids", json=bid_payload(), headers=supplier.headers)
    b = client.get("/dashboard/summary", headers=buyer.headers).json()
    assert (b["tenders"], b["open_tenders"], b["bids_received"]) == (1, 1, 1)
    s = client.get("/dashboard/summary", headers=supplier.headers).json()
    assert s["submitted_bids"] == 1 and s["open_tenders"] == 1 and "bids_received" not in s
    assert client.get("/dashboard/summary", headers=admin.headers).json()["tenders"] == 1


def test_dashboard_empty_state(client, buyer):
    assert client.get("/dashboard/summary", headers=buyer.headers).json() == {
        "role": "buyer", "tenders": 0, "open_tenders": 0, "bids_received": 0, "open_risk_alerts": 0}
