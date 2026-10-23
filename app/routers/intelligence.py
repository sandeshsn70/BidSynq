from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.access import bidding_closed, get_managed_tender, get_viewable_tender
from app.audit import append_audit
from app.database import get_db
from app.intelligence import estimate_price, similar_tenders, supplier_trust
from app.models import Bid, SupplierOutcome, Tender, User
from app.ranking import rank_bids
from app.schemas import (
    OutcomeOut,
    PriceOut,
    RankingOut,
    SimilarOut,
    SupplierOutcomeIn,
    TrustOut,
)
from app.security import get_current_user, require_roles

router = APIRouter(tags=["intelligence"])


def trust_scores_for(db: Session, supplier_ids: list[int]) -> dict[int, float]:
    """Advisory trust score (0-100) per supplier, computed from recorded outcomes."""
    if not supplier_ids:
        return {}
    outcomes: dict[int, list[dict]] = {sid: [] for sid in supplier_ids}
    rows = db.scalars(select(SupplierOutcome).where(SupplierOutcome.supplier_id.in_(supplier_ids))).all()
    for row in rows:
        outcomes[row.supplier_id].append(
            {"quality_score": row.quality_score, "on_time": row.on_time, "issue_count": row.issue_count}
        )
    return {sid: supplier_trust(items)["score"] for sid, items in outcomes.items()}


@router.get("/tenders/{tender_id}/ranking", response_model=RankingOut)
def get_ranking(
    tender_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(require_roles("buyer", "admin")),
):
    tender = get_managed_tender(db, tender_id, user)
    if not bidding_closed(tender):
        raise HTTPException(409, "Close the tender (or wait for its deadline) before viewing the final ranking")
    bids = list(db.scalars(select(Bid).where(Bid.tender_id == tender_id).order_by(Bid.id.asc())).all())
    trust = trust_scores_for(db, sorted({b.supplier_id for b in bids}))
    ranking = rank_bids(tender, bids, trust)
    companies = {u.id: (u.company_name or u.name) for u in
                 db.scalars(select(User).where(User.id.in_({b.supplier_id for b in bids}))).all()} if bids else {}
    for row in ranking:
        row["supplier_company"] = companies.get(row["supplier_id"])
    return RankingOut(
        tender_id=tender_id,
        weights={"price": tender.w_price, "delivery": tender.w_delivery, "trust": tender.w_trust,
                 "match": tender.w_match},
        method=("Weighted score: price and delivery are min-max scaled across eligible bids (lowest = 100); "
                "trust comes from buyer-recorded supplier outcomes (neutral 70 when there is no history); "
                "requirement match is self-declared by the supplier. Bids that fail mandatory requirements score 0."),
        ranking=ranking,
        note="Ranking is advisory, explainable, and not an automatic award decision.",
    )


# ------------------------------------------------------------------ supplier outcomes


@router.post("/tenders/{tender_id}/supplier-outcomes", response_model=OutcomeOut, status_code=201)
def record_supplier_outcome(
    tender_id: int,
    data: SupplierOutcomeIn,
    db: Session = Depends(get_db),
    user: User = Depends(require_roles("buyer", "admin")),
):
    """Record a buyer-reviewed outcome after a tender has closed. One record per supplier/tender."""
    tender = get_managed_tender(db, tender_id, user)
    if tender.status not in ("closed", "awarded"):
        raise HTTPException(409, "Tender must be closed or awarded before recording supplier performance")
    if not db.scalar(select(Bid.id).where(Bid.tender_id == tender_id, Bid.supplier_id == data.supplier_id)):
        raise HTTPException(404, "Supplier has no bid for this tender")
    supplier = db.get(User, data.supplier_id)
    if not supplier or supplier.role != "supplier":
        raise HTTPException(422, "supplier_id must identify a supplier account")
    if db.scalar(select(SupplierOutcome.id).where(
            SupplierOutcome.tender_id == tender_id, SupplierOutcome.supplier_id == data.supplier_id)):
        raise HTTPException(409, "An outcome is already recorded for this supplier and tender")

    row = SupplierOutcome(
        tender_id=tender_id, supplier_id=data.supplier_id, quality_score=data.quality_score,
        on_time=data.on_time, issue_count=data.issue_count, notes=data.notes, recorded_by=user.id,
    )
    try:
        db.add(row)
        db.flush()
        append_audit(db, user.id, "supplier.outcome_recorded", "supplier_outcome", row.id,
                     {"tender_id": tender_id, "supplier_id": data.supplier_id, "quality_score": data.quality_score,
                      "on_time": data.on_time, "issue_count": data.issue_count})
        db.commit()
    except IntegrityError:
        db.rollback()
        raise HTTPException(409, "An outcome is already recorded for this supplier and tender") from None
    except Exception:
        db.rollback()
        raise
    db.refresh(row)
    return OutcomeOut(
        id=row.id, tender_id=row.tender_id, supplier_id=row.supplier_id, quality_score=row.quality_score,
        on_time=row.on_time, issue_count=row.issue_count, created_at=row.created_at,
        message="Outcome recorded; it will contribute to the supplier's advisory trust score.",
    )


def _trust_payload(db: Session, supplier: User) -> dict:
    rows = db.scalars(
        select(SupplierOutcome).where(SupplierOutcome.supplier_id == supplier.id)
        .order_by(SupplierOutcome.created_at.desc(), SupplierOutcome.id.desc())
    ).all()
    scored = supplier_trust(
        [{"quality_score": r.quality_score, "on_time": r.on_time, "issue_count": r.issue_count} for r in rows]
    )
    return {
        "supplier_id": supplier.id,
        "company_name": supplier.company_name,
        **scored,
        "recent_outcomes": [
            {"tender_id": r.tender_id, "quality_score": r.quality_score, "on_time": r.on_time,
             "issue_count": r.issue_count, "created_at": r.created_at}
            for r in rows[:10]
        ],
    }


# NOTE: "/suppliers/me/trust" must be declared before "/suppliers/{supplier_id}/trust".
@router.get("/suppliers/me/trust", response_model=TrustOut)
def my_supplier_trust(db: Session = Depends(get_db), user: User = Depends(require_roles("supplier"))):
    return _trust_payload(db, user)


@router.get("/suppliers/{supplier_id}/trust", response_model=TrustOut)
def get_supplier_trust(supplier_id: int, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    supplier = db.get(User, supplier_id)
    if not supplier or supplier.role != "supplier":
        raise HTTPException(404, "Supplier not found")
    if user.role == "supplier" and user.id != supplier_id:
        raise HTTPException(403, "Suppliers can only view their own trust profile")
    return _trust_payload(db, supplier)


# ------------------------------------------------------------------ price intelligence


def _intel_tender(db: Session, tender_id: int, user: User) -> Tender:
    """Visibility check shared by the similar-tender and price endpoints."""
    return get_viewable_tender(db, tender_id, user)


@router.get("/tenders/{tender_id}/similar", response_model=SimilarOut)
def get_similar_tenders(
    tender_id: int,
    limit: int = Query(default=5, ge=1, le=10),
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    target = _intel_tender(db, tender_id, user)
    candidates = db.scalars(
        select(Tender).where(Tender.status.in_(["closed", "awarded"]), Tender.id != tender_id)
        .order_by(Tender.created_at.desc()).limit(500)
    ).all()
    target_dict = {"id": target.id, "title": target.title, "description": target.description,
                   "category": target.category, "quantity": target.quantity}
    candidate_dicts = [
        {"id": t.id, "title": t.title, "description": t.description, "category": t.category,
         "quantity": t.quantity, "status": t.status, "created_at": t.created_at.isoformat() if t.created_at else None}
        for t in candidates
    ]
    return SimilarOut(
        tender_id=tender_id,
        matches=similar_tenders(target_dict, candidate_dicts, limit),
        method="category + lexical overlap + quantity similarity",
        note="Similarity is heuristic, not a semantic embedding score.",
    )


@router.get("/tenders/{tender_id}/price-intelligence", response_model=PriceOut)
def get_price_intelligence(tender_id: int, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    target = _intel_tender(db, tender_id, user)
    historical = db.execute(
        select(Bid, Tender).join(Tender, Bid.tender_id == Tender.id)
        .where(Tender.status.in_(["closed", "awarded"]), Bid.tender_id != tender_id)
        .order_by(Bid.created_at.desc(), Bid.id.desc()).limit(5000)
    ).all()
    history = [{"price": b.price, "quantity": t.quantity, "category": t.category, "created_at": b.created_at}
               for b, t in historical]
    result = estimate_price({"id": target.id, "category": target.category, "quantity": target.quantity}, history)
    return PriceOut(
        tender_id=tender_id, category=target.category, quantity=target.quantity, **result,
        human_review_required=True,
        disclaimer=("Advisory estimate only, derived from past bids on this platform (not market prices). "
                    "It is not a quote, valuation guarantee, or automatic award recommendation. "
                    "Historical prices may be sparse or non-comparable."),
    )
