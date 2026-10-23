from datetime import datetime, timedelta

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.access import (
    as_utc,
    get_managed_tender,
    get_viewable_tender,
    now_utc,
)
from app.audit import append_audit
from app.database import get_db
from app.models import Bid, RiskAlert, Tender, User
from app.schemas import (
    BidCreate,
    BidDetailOut,
    BidOut,
    DashboardOut,
    MyBidOut,
    TenderCreate,
    TenderOut,
    TenderStatusUpdate,
    TenderUpdate,
)
from app.security import get_current_user, require_roles
from app.access import bidding_closed, get_tender, sealed_bids_hidden

router = APIRouter(tags=["tenders"])

WEIGHT_FIELDS = ("w_price", "w_delivery", "w_trust", "w_match")
ANTI_SNIPING_WINDOW = timedelta(minutes=2)


def _check_weights(values: list[float]) -> None:
    if abs(sum(values) - 1.0) > 0.001:
        raise HTTPException(400, "Evaluation weights must sum to 1.0")


@router.get("/dashboard/summary", response_model=DashboardOut, response_model_exclude_none=True)
def dashboard_summary(db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    if user.role in ("buyer", "admin"):
        scope = [Tender.buyer_id == user.id] if user.role == "buyer" else []
        tenders = db.scalar(select(func.count()).select_from(Tender).where(*scope)) or 0
        open_tenders = db.scalar(select(func.count()).select_from(Tender).where(*scope, Tender.status == "open")) or 0
        own_ids = select(Tender.id).where(*scope)
        bids_received = db.scalar(select(func.count()).select_from(Bid).where(Bid.tender_id.in_(own_ids))) or 0
        open_alerts = (
            db.scalar(
                select(func.count()).select_from(RiskAlert).where(
                    RiskAlert.status == "open", RiskAlert.tender_id.in_(own_ids)
                )
            )
            or 0
        )
        return DashboardOut(
            role=user.role,
            tenders=tenders,
            open_tenders=open_tenders,
            bids_received=bids_received,
            open_risk_alerts=open_alerts,
        )
    submitted = db.scalar(select(func.count()).select_from(Bid).where(Bid.supplier_id == user.id)) or 0
    open_tenders = (
        db.scalar(
            select(func.count()).select_from(Tender).where(Tender.status == "open", Tender.deadline > now_utc())
        )
        or 0
    )
    return DashboardOut(role=user.role, submitted_bids=submitted, open_tenders=open_tenders)


# ----------------------------------------------------------------------------- tenders


@router.post("/tenders", response_model=TenderOut, status_code=201)
def create_tender(
    data: TenderCreate,
    db: Session = Depends(get_db),
    user: User = Depends(require_roles("buyer", "admin")),
):
    _check_weights([data.w_price, data.w_delivery, data.w_trust, data.w_match])
    if data.deadline <= now_utc():
        raise HTTPException(400, "Deadline must be in the future")
    tender = Tender(buyer_id=user.id, **data.model_dump(exclude={"deadline"}), deadline=data.deadline, status="open")
    try:
        db.add(tender)
        db.flush()
        append_audit(
            db, user.id, "tender.created", "tender", tender.id,
            {"title": tender.title, "category": tender.category, "tender_type": tender.tender_type},
        )
        db.commit()
    except Exception:
        db.rollback()
        raise
    db.refresh(tender)
    return tender


@router.get("/tenders", response_model=list[TenderOut])
def list_tenders(
    status: str = Query(default="open", pattern="^(open|closed|awarded|cancelled|all)$"),
    limit: int = Query(default=200, ge=1, le=500),
    offset: int = Query(default=0, ge=0),
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    stmt = select(Tender)
    if status != "all":
        stmt = stmt.where(Tender.status == status)
    if user.role == "buyer":
        stmt = stmt.where(Tender.buyer_id == user.id)
    elif user.role == "supplier":
        has_bid = select(Bid.tender_id).where(Bid.supplier_id == user.id)
        stmt = stmt.where((Tender.status != "cancelled") | Tender.id.in_(has_bid))
    stmt = stmt.order_by(Tender.created_at.desc(), Tender.id.desc()).offset(offset).limit(limit)
    return list(db.scalars(stmt).all())


@router.get("/tenders/{tender_id}", response_model=TenderOut)
def get_tender_detail(tender_id: int, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    return get_viewable_tender(db, tender_id, user)


@router.patch("/tenders/{tender_id}", response_model=TenderOut)
def update_tender(
    tender_id: int,
    data: TenderUpdate,
    db: Session = Depends(get_db),
    user: User = Depends(require_roles("buyer", "admin")),
):
    """Edit an open tender. Once bids exist, scoring weights, quantity and requirements are frozen
    (suppliers priced against them) and the deadline may only be extended."""
    tender = get_managed_tender(db, tender_id, user, lock=True)
    if tender.status != "open":
        raise HTTPException(409, "Only open tenders can be edited")
    changes = data.model_dump(exclude_unset=True)
    if not changes:
        raise HTTPException(400, "No changes supplied")

    bid_count = db.scalar(select(func.count()).select_from(Bid).where(Bid.tender_id == tender.id)) or 0
    frozen = {"quantity", "mandatory_requirements", *WEIGHT_FIELDS}
    if bid_count and frozen & changes.keys():
        raise HTTPException(409, "Quantity, requirements and scoring weights cannot change after bids are submitted")

    if "deadline" in changes:
        new_deadline = changes["deadline"]
        if new_deadline is None or new_deadline <= now_utc():
            raise HTTPException(400, "Deadline must be in the future")
        if bid_count and new_deadline <= as_utc(tender.deadline):
            raise HTTPException(409, "After bids are submitted the deadline can only be extended")
    for field in ("title", "category") + tuple(WEIGHT_FIELDS) + ("quantity", "deadline", "anti_sniping"):
        if field in changes and changes[field] is None:
            raise HTTPException(400, f"{field} cannot be null")

    if any(w in changes for w in WEIGHT_FIELDS):
        _check_weights([changes.get(w, getattr(tender, w)) for w in WEIGHT_FIELDS])

    before = {k: (v.isoformat() if isinstance(v, datetime) else v) for k, v in
              ((k, getattr(tender, k)) for k in changes)}
    for field, value in changes.items():
        setattr(tender, field, value)
    after = {k: (v.isoformat() if isinstance(v, datetime) else v) for k, v in changes.items()}
    try:
        append_audit(db, user.id, "tender.updated", "tender", tender.id,
                     {"tender_id": tender.id, "fields": sorted(changes), "before": before, "after": after})
        db.commit()
    except Exception:
        db.rollback()
        raise
    db.refresh(tender)
    return tender


@router.patch("/tenders/{tender_id}/status", response_model=TenderOut)
def update_tender_status(
    tender_id: int,
    data: TenderStatusUpdate,
    db: Session = Depends(get_db),
    user: User = Depends(require_roles("buyer", "admin")),
):
    tender = get_managed_tender(db, tender_id, user, lock=True)
    if tender.status != "open":
        raise HTTPException(409, "Only open tenders can be closed or cancelled")
    old_status = tender.status
    tender.status = data.status
    try:
        append_audit(db, user.id, "tender.status_changed", "tender", tender.id,
                     {"tender_id": tender.id, "from": old_status, "to": data.status})
        db.commit()
    except Exception:
        db.rollback()
        raise
    db.refresh(tender)
    return tender


# ------------------------------------------------------------------------------- bids


def _bid_details(db: Session, bids: list[Bid]) -> list[BidDetailOut]:
    supplier_ids = {b.supplier_id for b in bids}
    suppliers = {}
    if supplier_ids:
        suppliers = {u.id: u for u in db.scalars(select(User).where(User.id.in_(supplier_ids))).all()}
    result = []
    for bid in bids:
        supplier = suppliers.get(bid.supplier_id)
        item = BidDetailOut.model_validate(bid)
        item.supplier_name = supplier.name if supplier else None
        item.supplier_company = (supplier.company_name or None) if supplier else None
        result.append(item)
    return result


@router.post("/tenders/{tender_id}/bids", response_model=BidOut, status_code=201)
def submit_bid(
    tender_id: int,
    data: BidCreate,
    db: Session = Depends(get_db),
    user: User = Depends(require_roles("supplier")),
):
    # The row lock makes the deadline/status check and the insert atomic with respect to
    # a buyer closing the tender or another request extending the deadline.
    tender = get_tender(db, tender_id, lock=True)
    now = now_utc()
    if bidding_closed(tender, now) or tender.status == "cancelled":
        raise HTTPException(400, "Tender is not open for bidding")
    if db.scalar(select(Bid.id).where(Bid.tender_id == tender_id, Bid.supplier_id == user.id)):
        raise HTTPException(409, "You already submitted a bid. Use PUT to revise it where revisions are allowed.")

    bid = Bid(tender_id=tender_id, supplier_id=user.id, **data.model_dump())
    try:
        db.add(bid)
        deadline = as_utc(tender.deadline)
        if tender.tender_type == "reverse_auction" and tender.anti_sniping and deadline - now <= ANTI_SNIPING_WINDOW:
            tender.deadline = now + ANTI_SNIPING_WINDOW
        db.flush()
        append_audit(db, user.id, "bid.submitted", "bid", bid.id,
                     {"tender_id": tender_id, "price": bid.price, "delivery_days": bid.delivery_days})
        db.commit()
    except IntegrityError:
        db.rollback()
        raise HTTPException(409, "You already submitted a bid for this tender.") from None
    except Exception:
        db.rollback()
        raise
    db.refresh(bid)
    return bid


@router.put("/tenders/{tender_id}/bids/me", response_model=BidOut)
def revise_my_bid(
    tender_id: int,
    data: BidCreate,
    db: Session = Depends(get_db),
    user: User = Depends(require_roles("supplier")),
):
    tender = get_tender(db, tender_id, lock=True)
    now = now_utc()
    if bidding_closed(tender, now):
        raise HTTPException(400, "Tender is not open for bidding")
    if tender.tender_type != "reverse_auction":
        raise HTTPException(400, "Bid revisions are enabled only for reverse auctions")
    bid = db.scalar(select(Bid).where(Bid.tender_id == tender_id, Bid.supplier_id == user.id).with_for_update())
    if not bid:
        raise HTTPException(404, "Submit an initial bid before revising it")
    if data.price >= bid.price:
        raise HTTPException(400, "A reverse-auction revision must be lower than your current price")

    old_price = bid.price
    try:
        for field, value in data.model_dump().items():
            setattr(bid, field, value)
        bid.updated_at = now
        deadline = as_utc(tender.deadline)
        if tender.anti_sniping and deadline - now <= ANTI_SNIPING_WINDOW:
            tender.deadline = now + ANTI_SNIPING_WINDOW
        append_audit(db, user.id, "bid.revised", "bid", bid.id,
                     {"tender_id": tender_id, "old_price": old_price, "new_price": bid.price})
        db.commit()
    except Exception:
        db.rollback()
        raise
    db.refresh(bid)
    return bid


@router.get("/tenders/{tender_id}/bids", response_model=list[BidDetailOut])
def list_bids(tender_id: int, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    tender = get_tender(db, tender_id)
    if user.role == "supplier":
        own = db.scalars(select(Bid).where(Bid.tender_id == tender_id, Bid.supplier_id == user.id)).all()
        return _bid_details(db, list(own))
    if user.role == "buyer" and tender.buyer_id != user.id:
        raise HTTPException(403, "You can only view bids for your own tenders")
    if sealed_bids_hidden(tender):
        raise HTTPException(403, "Sealed bids are hidden until the tender closes")
    bids = db.scalars(select(Bid).where(Bid.tender_id == tender_id).order_by(Bid.price.asc(), Bid.id.asc())).all()
    return _bid_details(db, list(bids))


@router.get("/bids/me", response_model=list[MyBidOut])
def my_bids(db: Session = Depends(get_db), user: User = Depends(require_roles("supplier"))):
    rows = db.execute(
        select(Bid, Tender).join(Tender, Bid.tender_id == Tender.id)
        .where(Bid.supplier_id == user.id).order_by(Bid.created_at.desc(), Bid.id.desc())
    ).all()
    now = now_utc()
    result = []
    for bid, tender in rows:
        base = BidOut.model_validate(bid).model_dump()
        result.append(MyBidOut(
            **base,
            tender_title=tender.title,
            tender_status=tender.status,
            tender_type=tender.tender_type,
            tender_deadline=tender.deadline,
            bidding_open=not bidding_closed(tender, now),
        ))
    return result
