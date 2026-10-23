"""Shared authorization and tender-state helpers used by every router."""
from __future__ import annotations

from datetime import datetime, timezone

from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import Bid, Tender, User


def as_utc(value: datetime) -> datetime:
    return value if value.tzinfo else value.replace(tzinfo=timezone.utc)


def now_utc() -> datetime:
    return datetime.now(timezone.utc)


def bidding_closed(tender: Tender, now: datetime | None = None) -> bool:
    """True once the tender is no longer open OR its deadline has passed."""
    return tender.status != "open" or as_utc(tender.deadline) <= (now or now_utc())


def sealed_bids_hidden(tender: Tender, now: datetime | None = None) -> bool:
    """Sealed-bid contents stay hidden from everyone but the submitting supplier until bidding closes."""
    return tender.tender_type == "sealed" and not bidding_closed(tender, now)


def get_tender(db: Session, tender_id: int, *, lock: bool = False) -> Tender:
    """Load a tender or raise 404. ``lock=True`` takes a row lock (PostgreSQL) for race-free updates."""
    stmt = select(Tender).where(Tender.id == tender_id)
    if lock:
        stmt = stmt.with_for_update().execution_options(populate_existing=True)
    tender = db.scalar(stmt)
    if tender is None:
        raise HTTPException(404, "Tender not found")
    return tender


def supplier_has_bid(db: Session, tender_id: int, supplier_id: int) -> bool:
    return db.scalar(select(Bid.id).where(Bid.tender_id == tender_id, Bid.supplier_id == supplier_id)) is not None


def can_view_tender(db: Session, tender: Tender, user: User) -> bool:
    if user.role == "admin":
        return True
    if user.role == "buyer":
        return tender.buyer_id == user.id
    if tender.status in ("open", "closed", "awarded"):
        return True
    return supplier_has_bid(db, tender.id, user.id)


def get_viewable_tender(db: Session, tender_id: int, user: User) -> Tender:
    tender = get_tender(db, tender_id)
    if not can_view_tender(db, tender, user):
        if user.role == "buyer":
            raise HTTPException(403, "You can only access your own tenders")
        raise HTTPException(404, "Tender not found")
    return tender


def get_managed_tender(db: Session, tender_id: int, user: User, *, lock: bool = False) -> Tender:
    """Tender that the user may manage: its owning buyer or an admin."""
    tender = get_tender(db, tender_id, lock=lock)
    if user.role == "buyer" and tender.buyer_id != user.id:
        raise HTTPException(403, "You can only manage your own tenders")
    if user.role not in ("buyer", "admin"):
        raise HTTPException(403, "Insufficient permissions")
    return tender


def get_document_tender(db: Session, tender_id: int, user: User) -> Tender:
    """Tender whose documents the user may read. Suppliers: open tenders, or ones they bid on."""
    tender = get_viewable_tender(db, tender_id, user)
    if user.role == "supplier" and tender.status != "open" and not supplier_has_bid(db, tender.id, user.id):
        raise HTTPException(404, "Tender documents are not available")
    return tender
