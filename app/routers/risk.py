import json
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.access import get_managed_tender, sealed_bids_hidden
from app.audit import append_audit
from app.database import get_db
from app.models import Bid, RiskAlert, Tender, User
from app.risk import detect_bid_risks
from app.schemas import ReviewIn, ReviewOut, RiskAlertOut, ScanOut
from app.security import require_roles

router = APIRouter(tags=["risk"])

DISCLAIMER = ("Risk signals are not proof of fraud, collusion or misconduct. "
              "Review source evidence and apply consistent due process.")


def _alert_out(row: RiskAlert) -> RiskAlertOut:
    try:
        evidence = json.loads(row.evidence_json or "{}")
        if not isinstance(evidence, dict):
            evidence = {"value": evidence}
    except ValueError:
        evidence = {}
    return RiskAlertOut(
        id=row.id, tender_id=row.tender_id, bid_id=row.bid_id, rule_key=row.rule_key, severity=row.severity,
        title=row.title, explanation=row.explanation, evidence=evidence, status=row.status,
        review_note=row.review_note or "", created_at=row.created_at, reviewed_at=row.reviewed_at,
    )


@router.post("/tenders/{tender_id}/risk/scan", response_model=ScanOut)
def scan_tender_risks(
    tender_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(require_roles("buyer", "admin")),
):
    """Run explainable risk checks. Alerts are review leads, never automated findings."""
    tender = get_managed_tender(db, tender_id, user)
    if sealed_bids_hidden(tender):
        # Alert evidence contains bid prices, which would disclose sealed bids early.
        raise HTTPException(409, "Risk scans for sealed tenders are available after bidding closes")
    bids = list(db.scalars(select(Bid).where(Bid.tender_id == tender_id).order_by(Bid.created_at.asc(), Bid.id.asc())).all())
    findings = detect_bid_risks(tender, bids)

    inserted = 0
    for finding in findings:
        if db.scalar(select(RiskAlert.id).where(RiskAlert.fingerprint == finding["fingerprint"])):
            continue
        try:
            with db.begin_nested():  # savepoint: a duplicate from a concurrent scan only rolls back this row
                db.add(RiskAlert(
                    fingerprint=finding["fingerprint"], tender_id=tender_id, bid_id=finding.get("bid_id"),
                    rule_key=finding["rule_key"], severity=finding["severity"], title=finding["title"],
                    explanation=finding["explanation"],
                    evidence_json=json.dumps(finding["evidence"], sort_keys=True), status="open",
                ))
            inserted += 1
        except IntegrityError:
            continue
    try:
        append_audit(db, user.id, "risk.scan_completed", "tender", tender_id,
                     {"tender_id": tender_id, "bids_checked": len(bids), "new_alerts": inserted})
        db.commit()
    except Exception:
        db.rollback()
        raise
    rows = db.scalars(select(RiskAlert).where(RiskAlert.tender_id == tender_id)
                      .order_by(RiskAlert.created_at.desc(), RiskAlert.id.desc()).limit(500)).all()
    return ScanOut(tender_id=tender_id, bids_checked=len(bids), signals_detected=len(findings),
                   new_alerts_saved=inserted, alerts=[_alert_out(r) for r in rows], disclaimer=DISCLAIMER)


@router.get("/risk/alerts", response_model=list[RiskAlertOut])
def get_risk_alerts(
    tender_id: int | None = Query(default=None, ge=1),
    status: str = Query(default="all", pattern="^(open|reviewed|dismissed|all)$"),
    db: Session = Depends(get_db),
    user: User = Depends(require_roles("buyer", "admin")),
):
    if tender_id is not None:
        get_managed_tender(db, tender_id, user)
    query = select(RiskAlert)
    if tender_id is not None:
        query = query.where(RiskAlert.tender_id == tender_id)
    if status != "all":
        query = query.where(RiskAlert.status == status)
    if user.role == "buyer":
        query = query.join(Tender, RiskAlert.tender_id == Tender.id).where(Tender.buyer_id == user.id)
    rows = db.scalars(query.order_by(RiskAlert.created_at.desc(), RiskAlert.id.desc()).limit(500)).all()
    return [_alert_out(r) for r in rows]


@router.patch("/risk/alerts/{alert_id}/review", response_model=ReviewOut)
def review_risk_alert(
    alert_id: int,
    payload: ReviewIn,
    db: Session = Depends(get_db),
    user: User = Depends(require_roles("admin")),
):
    """Only administrators can record a review decision (independent of the buyer who runs the tender)."""
    row = db.get(RiskAlert, alert_id)
    if not row:
        raise HTTPException(404, "Risk alert not found")
    previous = {"status": row.status, "note": row.review_note}
    row.status = payload.status
    row.review_note = payload.note
    row.reviewed_by = user.id
    row.reviewed_at = datetime.now(timezone.utc)
    try:
        append_audit(db, user.id, "risk.alert_reviewed", "risk_alert", row.id,
                     {"tender_id": row.tender_id, "status": payload.status, "note": payload.note, "previous": previous})
        db.commit()
    except Exception:
        db.rollback()
        raise
    return ReviewOut(id=row.id, status=row.status, review_note=row.review_note, reviewed_at=row.reviewed_at)
