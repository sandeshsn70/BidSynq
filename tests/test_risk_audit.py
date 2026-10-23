import math
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace as NS

import pytest
from sqlalchemy import select

from app.audit import GENESIS_HASH, append_audit, canonical_json, verify_chain
from app.models import AuditLog, RiskAlert, Tender, User
from app.risk import detect_bid_risks
from tests.conftest import bid_payload

NOW = datetime.now(timezone.utc)


def bid(i, price=100.0, days=5, match=90, created=None):
    return NS(id=i, price=price, delivery_days=days, requirement_match=match, created_at=created or NOW - timedelta(days=1))


TENDER = NS(id=1, deadline=NOW + timedelta(days=1))


# ------------------------------------------------------------------------- detectors


def test_empty_and_missing_inputs():
    assert detect_bid_risks(None, [bid(1)]) == [] and detect_bid_risks(TENDER, []) == [] and detect_bid_risks(TENDER, None) == []


def test_malformed_values_never_crash():
    bids = [bid(1, price=float("nan")), bid(2, price=float("inf")), bid(3, price=None), bid(4, price="abc"),
            bid(5, price=-5), bid(6, days=float("nan")), bid(7, match=None, created="yesterday")]
    assert isinstance(detect_bid_risks(TENDER, bids), list)
    assert isinstance(detect_bid_risks(NS(id=1, deadline="soon"), [bid(1)]), list)


def test_mad_outlier_detected_with_evidence():
    bids = [bid(1, 100), bid(2, 101), bid(3, 99), bid(4, 102), bid(5, 5000)]
    alerts = [a for a in detect_bid_risks(TENDER, bids) if a["rule_key"] == "price_outlier_mad"]
    assert [a["bid_id"] for a in alerts] == [5]
    assert alerts[0]["evidence"]["median_price"] == 101 and alerts[0]["evidence"]["robust_deviation"] >= 4


def test_mad_needs_three_bids_and_spread():
    assert not detect_bid_risks(TENDER, [bid(1, 100), bid(2, 5000)])
    assert not [a for a in detect_bid_risks(TENDER, [bid(1, 100), bid(2, 100), bid(3, 100)]) if a["rule_key"] == "price_outlier_mad"]


def test_repeated_price_signal():
    alerts = detect_bid_risks(TENDER, [bid(i, 100.004) for i in (1, 2, 3)])
    rep = [a for a in alerts if a["rule_key"] == "repeated_bid_price"]
    assert len(rep) == 1 and rep[0]["evidence"]["bid_ids"] == [1, 2, 3] and "not evidence of collusion" in rep[0]["explanation"]


def test_near_deadline_signal_and_boundaries():
    t = NS(id=2, deadline=NOW + timedelta(seconds=60))
    near = [a for a in detect_bid_risks(t, [bid(1, created=NOW)]) if a["rule_key"] == "near_deadline_bid"]
    assert near and near[0]["evidence"]["seconds_before_deadline"] == 60
    assert not [a for a in detect_bid_risks(t, [bid(1, created=NOW - timedelta(minutes=10))]) if a["rule_key"] == "near_deadline_bid"]
    assert not [a for a in detect_bid_risks(t, [bid(1, created=NOW + timedelta(minutes=10))]) if a["rule_key"] == "near_deadline_bid"]


def test_isolation_forest_needs_enough_valid_observations():
    few = [bid(i, 100 + i) for i in range(1, 7)]
    assert not [a for a in detect_bid_risks(TENDER, few) if a["rule_key"] == "multivariate_outlier_iforest"]
    many = [bid(i, 100 + i, days=5 + i % 3, match=90) for i in range(1, 12)] + [bid(99, 100, days=400, match=5)]
    flagged = [a for a in detect_bid_risks(TENDER, many) if a["rule_key"] == "multivariate_outlier_iforest"]
    assert flagged and all(a["evidence"]["detector"] == "IsolationForest" for a in flagged)


def test_alerts_are_never_called_fraud_and_have_stable_fingerprints():
    bids = [bid(1, 100), bid(2, 101), bid(3, 99), bid(4, 102), bid(5, 5000)]
    first, second = detect_bid_risks(TENDER, bids), detect_bid_risks(TENDER, list(reversed(bids)))
    assert first and {a["fingerprint"] for a in first} == {a["fingerprint"] for a in second}
    for a in first:
        assert len(a["fingerprint"]) == 64 and a["evidence"] and a["rule_key"] and a["explanation"]
        text = (a["title"] + a["explanation"]).lower()
        assert "confirmed" not in text and "fraud" not in text.replace("not evidence of fraud", "")


# ------------------------------------------------------------------------ risk API


def _tender_with_bids(client, create_tender, suppliers, prices, **kw):
    t = create_tender(**kw)
    for s, p in zip(suppliers, prices):
        assert client.post(f"/tenders/{t['id']}/bids", json=bid_payload(price=p), headers=s.headers).status_code == 201
    return t


def test_scan_saves_alerts_once_and_is_idempotent(client, buyer, make_user, create_tender):
    sup = [make_user("supplier") for _ in range(5)]
    t = _tender_with_bids(client, create_tender, sup, [100, 101, 99, 102, 9000])
    first = client.post(f"/tenders/{t['id']}/risk/scan", headers=buyer.headers).json()
    assert first["new_alerts_saved"] >= 1 and first["bids_checked"] == 5 and "not proof of fraud" in first["disclaimer"]
    second = client.post(f"/tenders/{t['id']}/risk/scan", headers=buyer.headers).json()
    assert second["new_alerts_saved"] == 0 and second["signals_detected"] == first["signals_detected"]
    alerts = client.get(f"/risk/alerts?tender_id={t['id']}", headers=buyer.headers).json()
    assert len(alerts) == first["new_alerts_saved"] and all(a["status"] == "open" for a in alerts)
    assert client.get("/dashboard/summary", headers=buyer.headers).json()["open_risk_alerts"] == len(alerts)


def test_unique_fingerprint_constraint_backstops_duplicates(client, buyer, make_user, create_tender, Session):
    from sqlalchemy.exc import IntegrityError
    sup = [make_user("supplier") for _ in range(5)]
    t = _tender_with_bids(client, create_tender, sup, [100, 101, 99, 102, 9000])
    client.post(f"/tenders/{t['id']}/risk/scan", headers=buyer.headers)
    with Session() as s:
        existing = s.scalars(select(RiskAlert)).first()
        s.add(RiskAlert(fingerprint=existing.fingerprint, tender_id=t["id"], rule_key="x", title="x", explanation="x"))
        with pytest.raises(IntegrityError):
            s.commit()


def test_sealed_tender_cannot_be_scanned_while_open(client, buyer, supplier, create_tender):
    t = create_tender(tender_type="sealed")
    client.post(f"/tenders/{t['id']}/bids", json=bid_payload(), headers=supplier.headers)
    assert client.post(f"/tenders/{t['id']}/risk/scan", headers=buyer.headers).status_code == 409
    client.patch(f"/tenders/{t['id']}/status", json={"status": "closed"}, headers=buyer.headers)
    assert client.post(f"/tenders/{t['id']}/risk/scan", headers=buyer.headers).status_code == 200


def test_risk_endpoints_restricted_by_role_and_ownership(client, buyer, buyer2, supplier, create_tender):
    t = create_tender()
    assert client.post(f"/tenders/{t['id']}/risk/scan", headers=supplier.headers).status_code == 403
    assert client.get("/risk/alerts", headers=supplier.headers).status_code == 403
    assert client.get(f"/risk/alerts?tender_id={t['id']}", headers=buyer2.headers).status_code == 403
    assert client.get("/risk/alerts", headers=buyer2.headers).json() == []


def test_only_admins_can_review_alerts_and_review_is_audited(client, buyer, admin, make_user, create_tender):
    sup = [make_user("supplier") for _ in range(5)]
    t = _tender_with_bids(client, create_tender, sup, [100, 101, 99, 102, 9000])
    client.post(f"/tenders/{t['id']}/risk/scan", headers=buyer.headers)
    alert = client.get("/risk/alerts", headers=buyer.headers).json()[0]
    url = f"/risk/alerts/{alert['id']}/review"
    assert client.patch(url, json={"status": "dismissed"}, headers=buyer.headers).status_code == 403
    assert client.patch(url, json={"status": "confirmed_fraud"}, headers=admin.headers).status_code == 422
    assert client.patch(url, json={"status": "dismissed", "note": "x" * 2001}, headers=admin.headers).status_code == 422
    ok = client.patch(url, json={"status": "reviewed", "note": "Price explained by scope"}, headers=admin.headers)
    assert ok.status_code == 200 and ok.json()["status"] == "reviewed" and ok.json()["reviewed_at"]
    assert client.patch("/risk/alerts/99999/review", json={"status": "reviewed"}, headers=admin.headers).status_code == 404
    actions = [i["action"] for i in client.get("/audit/logs", headers=admin.headers).json()["items"]]
    assert "risk.alert_reviewed" in actions and "risk.scan_completed" in actions


# ------------------------------------------------------------------------ audit chain


def _chain(db, n=4):
    user = User(name="T", email="t@example.com", password_hash="x", role="admin", company_name="")
    db.add(user)
    db.flush()
    for i in range(n):
        append_audit(db, user.id, "test.event", "test", str(i), {"i": i, "msg": "héllo ✓"})
    db.commit()
    return list(db.scalars(select(AuditLog).order_by(AuditLog.id)).all())


def test_chain_links_to_genesis_and_verifies(db):
    rows = _chain(db)
    assert rows[0].previous_hash == GENESIS_HASH
    assert all(rows[i].previous_hash == rows[i - 1].entry_hash for i in range(1, len(rows)))
    result = verify_chain(rows)
    assert result["valid"] and result["checked_entries"] == 4 and result["head_hash"] == rows[-1].entry_hash


def test_empty_chain_is_valid():
    assert verify_chain([]) == {"valid": True, "checked_entries": 0, "head_hash": GENESIS_HASH, "last_entry_id": None}


def test_tampered_details_detected(db):
    rows = _chain(db)
    rows[1].details_json = canonical_json({"i": 1, "msg": "changed"})
    r = verify_chain(rows)
    assert not r["valid"] and r["reason"] == "entry_hash_mismatch" and r["broken_at_id"] == rows[1].id


@pytest.mark.parametrize("field,value,reason", [
    ("action", "test.other", "entry_hash_mismatch"),
    ("actor_id", 999, "entry_hash_mismatch"),
    ("entity_id", "other", "entry_hash_mismatch"),
    ("entry_hash", "f" * 64, "entry_hash_mismatch"),
    ("previous_hash", "a" * 64, "previous_hash_mismatch"),
    ("details_json", "{not json", "malformed_entry"),
    ("details_json", '{"x": NaN}', "malformed_entry"),
])
def test_other_tampering_detected(db, field, value, reason):
    rows = _chain(db)
    setattr(rows[2], field, value)
    r = verify_chain(rows)
    assert not r["valid"] and r["reason"] == reason and r["broken_at_id"] == rows[2].id


def test_deleted_or_reordered_entries_detected(db):
    rows = _chain(db, 5)
    assert not verify_chain(rows[:2] + rows[3:])["valid"]
    assert not verify_chain([rows[1], rows[0]] + rows[2:])["valid"]
    assert not verify_chain(rows[1:])["valid"]                      # genesis removed


def test_audit_rejects_invalid_input(db):
    with pytest.raises(ValueError):
        append_audit(db, None, " ", "x", "1", {})
    with pytest.raises(TypeError):
        append_audit(db, None, "a", "x", "1", ["not", "a", "dict"])
    with pytest.raises(ValueError):
        append_audit(db, None, "a", "x", "1", {"bad": math.nan})


def test_verify_endpoint_detects_tampering_in_database(client, admin, buyer, create_tender, Session):
    create_tender()
    ok = client.get("/audit/verify", headers=admin.headers).json()
    assert ok["valid"] and ok["checked_entries"] >= 1 and "WORM" in ok["note"]
    with Session() as s:
        row = s.scalars(select(AuditLog).order_by(AuditLog.id)).first()
        row.details_json = '{"tampered": true}'
        s.commit()
    bad = client.get("/audit/verify", headers=admin.headers).json()
    assert bad["valid"] is False and bad["broken_at_id"] == row.id


def test_audit_log_visibility(client, buyer, buyer2, supplier, admin, create_tender):
    mine = create_tender()
    theirs = create_tender(owner=buyer2, title="Other buyer tender")
    client.post(f"/tenders/{mine['id']}/bids", json=bid_payload(), headers=supplier.headers)
    client.post(f"/tenders/{theirs['id']}/bids", json=bid_payload(), headers=supplier.headers)

    def refs(actor):
        items = client.get("/audit/logs?limit=500", headers=actor.headers).json()["items"]
        return {(i["details"].get("tender_id") or int(i["entity_id"])) for i in items if i["entity_type"] in ("tender", "bid")}

    assert refs(buyer) == {mine["id"]} and refs(buyer2) == {theirs["id"]} and refs(admin) == {mine["id"], theirs["id"]}
    assert client.get("/audit/logs", headers=supplier.headers).status_code == 403


def test_audit_logs_pagination(client, buyer, admin, create_tender):
    for i in range(3):
        create_tender(title=f"Tender number {i}")
    page1 = client.get("/audit/logs?limit=2", headers=buyer.headers).json()
    page2 = client.get("/audit/logs?limit=2&offset=2", headers=buyer.headers).json()
    ids = [i["id"] for i in page1["items"] + page2["items"]]
    assert len(ids) == len(set(ids)) and ids == sorted(ids, reverse=True)
    assert len(client.get("/audit/logs?limit=2", headers=admin.headers).json()["items"]) == 2


def test_business_change_and_audit_entry_commit_together(client, buyer, monkeypatch, Session):
    import app.routers.tenders as module

    def boom(*a, **k):
        raise RuntimeError("audit store failed")

    monkeypatch.setattr(module, "append_audit", boom)
    from tests.conftest import tender_payload
    with pytest.raises(RuntimeError):
        client.post("/tenders", json=tender_payload(), headers=buyer.headers)
    with Session() as s:
        assert s.scalars(select(Tender)).all() == []          # rolled back: no tender without its audit record
