import json

from fastapi import APIRouter, Depends, Query
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.audit import verify_chain
from app.database import get_db
from app.models import AuditLog, Tender, User
from app.schemas import AuditItemOut, AuditPageOut, VerifyOut
from app.security import require_roles

router = APIRouter(prefix="/audit", tags=["audit"])

MAX_BUYER_SCAN = 20_000  # upper bound on rows examined when filtering a buyer's view


@router.get("/verify", response_model=VerifyOut)
def verify_audit_log(db: Session = Depends(get_db), user: User = Depends(require_roles("admin"))):
    rows = db.scalars(select(AuditLog).order_by(AuditLog.id.asc()))
    result = verify_chain(rows)
    result["note"] = (
        "Hash chaining makes unauthorized edits detectable if the chain head is independently preserved. "
        "This database is not an immutable/WORM store: someone with full database access could rewrite "
        "the whole chain, so keep a copy of head_hash elsewhere."
    )
    return result


def _item(row: AuditLog) -> AuditItemOut:
    try:
        details = json.loads(row.details_json or "{}")
        if not isinstance(details, dict):
            details = {"value": details}
    except ValueError:
        details = {"error": "malformed details"}
    return AuditItemOut(
        id=row.id, actor_id=row.actor_id, action=row.action, entity_type=row.entity_type,
        entity_id=row.entity_id, details=details, previous_hash=row.previous_hash,
        entry_hash=row.entry_hash, created_at=row.created_at,
    )


@router.get("/logs", response_model=AuditPageOut)
def get_audit_logs(
    limit: int = Query(default=100, ge=1, le=500),
    offset: int = Query(default=0, ge=0),
    db: Session = Depends(get_db),
    user: User = Depends(require_roles("buyer", "admin")),
):
    """Admins see everything. Buyers see only entries about their own tenders (and their own actions)."""
    if user.role == "admin":
        rows = db.scalars(select(AuditLog).order_by(AuditLog.id.desc()).offset(offset).limit(limit)).all()
        return AuditPageOut(items=[_item(r) for r in rows], limit=limit, offset=offset)

    owned = {str(t) for t in db.scalars(select(Tender.id).where(Tender.buyer_id == user.id)).all()}
    visible: list[AuditItemOut] = []
    skipped = scanned = 0
    stream = db.scalars(select(AuditLog).order_by(AuditLog.id.desc()).execution_options(yield_per=500))
    for row in stream:
        scanned += 1
        if scanned > MAX_BUYER_SCAN:
            break
        item = _item(row)
        tender_ref = item.details.get("tender_id")
        mine = (
            row.actor_id == user.id
            or (row.entity_type == "tender" and row.entity_id in owned)
            or (tender_ref is not None and str(tender_ref) in owned)
        )
        if not mine:
            continue
        if skipped < offset:
            skipped += 1
            continue
        visible.append(item)
        if len(visible) >= limit:
            break
    return AuditPageOut(items=visible, limit=limit, offset=offset)
