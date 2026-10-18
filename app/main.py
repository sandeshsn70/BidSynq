from datetime import datetime, timezone, timedelta
from pathlib import Path
from uuid import uuid4
import re
from fastapi import FastAPI, Depends, HTTPException, Query, UploadFile, File, Form
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy.orm import Session
from sqlalchemy import select, func, delete
from app.database import Base, engine, get_db
from app.models import User, Tender, Bid, TenderDocument, DocumentChunk, SupplierOutcome, AuditLog, RiskAlert
from app.schemas import RegisterIn, LoginIn, TokenOut, UserOut, TenderCreate, TenderOut, BidCreate, BidOut, TenderStatusUpdate, SupplierOutcomeIn
from app.security import hash_password, verify_password, create_access_token, get_current_user, require_roles
from app.config import settings
from app.ranking import rank_bids
from app.rag import extract_file, chunk_pages, retrieve, extractive_answer, generate_with_groq, DocumentProcessingError
from app.intelligence import supplier_trust, similar_tenders, estimate_price
from app.audit import append_audit, verify_chain
from app.risk import detect_bid_risks
import json

Base.metadata.create_all(bind=engine)
app = FastAPI(title="BidSynq API", version="5.0.0", description="B2B procurement with RAG, supplier intelligence, risk review and tamper-evident audit trails")
app.add_middleware(CORSMiddleware, allow_origins=[origin.strip().rstrip("/") for origin in settings.cors_origins.split(",") if origin.strip()], allow_credentials=True, allow_methods=["*"], allow_headers=["*"])

@app.get("/health")
def health():
    return {"status": "ok", "version": "5.0.0", "rag": "enabled", "supplier_intelligence": "enabled", "price_intelligence": "advisory", "risk_monitoring": "human_review_only", "audit_chain": "enabled"}


@app.post("/auth/register", response_model=UserOut, status_code=201)
def register(data: RegisterIn, db: Session = Depends(get_db)):
    role = data.role.lower().strip()
    allowed_roles = {"buyer", "supplier"}

    if settings.bidsynq_allow_admin_registration:
        allowed_roles.add("admin")

    if role not in allowed_roles:
        raise HTTPException(
            status_code=400,
            detail=f"Role must be one of: {', '.join(sorted(allowed_roles))}",
        )

    email = str(data.email).strip().lower()

    existing_user = db.scalar(
        select(User).where(User.email == email)
    )

    if existing_user:
        raise HTTPException(
            status_code=409,
            detail="Email is already registered",
        )

    user = User(
        name=data.name.strip(),
        email=email,
        password_hash=hash_password(data.password),
        role=role,
        company_name=data.company_name.strip(),
    )

    try:
        db.add(user)
        db.flush()

        append_audit(
            db,
            user.id,
            "user.registered",
            "user",
            user.id,
            {"role": role},
        )

        db.commit()
        db.refresh(user)
        return user

    except Exception:
        db.rollback()
        raise


@app.post("/auth/login", response_model=TokenOut)
def login(data: LoginIn, db: Session = Depends(get_db)):
    email = str(data.email).strip().lower()

    user = db.scalar(
        select(User).where(User.email == email)
    )

    if user is None or not verify_password(
        data.password,
        user.password_hash,
    ):
        raise HTTPException(
            status_code=401,
            detail="Incorrect email or password",
            headers={"WWW-Authenticate": "Bearer"},
        )

    token = create_access_token(user.id)

    return TokenOut(access_token=token)


@app.get("/dashboard/summary")
def dashboard_summary(db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    if user.role in ("buyer", "admin"):
        own = select(Tender.id).where(Tender.buyer_id == user.id) if user.role == "buyer" else select(Tender.id)
        tender_count = db.scalar(select(func.count()).select_from(Tender).where(Tender.buyer_id == user.id)) if user.role == "buyer" else db.scalar(select(func.count()).select_from(Tender))
        open_count = db.scalar(select(func.count()).select_from(Tender).where(Tender.buyer_id == user.id, Tender.status == "open")) if user.role == "buyer" else db.scalar(select(func.count()).select_from(Tender).where(Tender.status == "open"))
        bids_count = db.scalar(select(func.count()).select_from(Bid).where(Bid.tender_id.in_(own))) or 0
        return {"role": user.role, "tenders": tender_count or 0, "open_tenders": open_count or 0, "bids_received": bids_count}
    bid_count = db.scalar(select(func.count()).select_from(Bid).where(Bid.supplier_id == user.id)) or 0
    open_count = db.scalar(select(func.count()).select_from(Tender).where(Tender.status == "open", Tender.deadline > datetime.now(timezone.utc))) or 0
    return {"role": user.role, "submitted_bids": bid_count, "open_tenders": open_count}

@app.post("/tenders", response_model=TenderOut, status_code=201)
def create_tender(data: TenderCreate, db: Session = Depends(get_db), user: User = Depends(require_roles("buyer", "admin"))):
    weights = [data.w_price, data.w_delivery, data.w_trust, data.w_match]
    if abs(sum(weights) - 1.0) > 0.001:
        raise HTTPException(400, "Evaluation weights must sum to 1.0")
    deadline = data.deadline
    if deadline.tzinfo is None: deadline = deadline.replace(tzinfo=timezone.utc)
    if deadline <= datetime.now(timezone.utc): raise HTTPException(400, "Deadline must be in the future")
    tender = Tender(buyer_id=user.id, **data.model_dump(exclude={"deadline"}), deadline=deadline, status="open")
    db.add(tender); db.flush(); append_audit(db, user.id, "tender.created", "tender", tender.id, {"title": tender.title, "category": tender.category, "tender_type": tender.tender_type}); db.commit(); db.refresh(tender)
    return tender

@app.get("/tenders", response_model=list[TenderOut])
def list_tenders(status: str = Query(default="open", pattern="^(open|closed|awarded|cancelled|all)$"), db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    stmt = select(Tender)
    if status != "all": stmt = stmt.where(Tender.status == status)
    if user.role == "buyer": stmt = stmt.where(Tender.buyer_id == user.id) if status != "open" else stmt.where(Tender.buyer_id == user.id)
    return list(db.scalars(stmt.order_by(Tender.created_at.desc())).all())

@app.get("/tenders/{tender_id}", response_model=TenderOut)
def get_tender(tender_id: int, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    tender = db.get(Tender, tender_id)
    if not tender: raise HTTPException(404, "Tender not found")
    return tender

@app.patch("/tenders/{tender_id}/status", response_model=TenderOut)
def update_tender_status(tender_id: int, data: TenderStatusUpdate, db: Session = Depends(get_db), user: User = Depends(require_roles("buyer", "admin"))):
    tender = db.get(Tender, tender_id)
    if not tender: raise HTTPException(404, "Tender not found")
    if user.role == "buyer" and tender.buyer_id != user.id: raise HTTPException(403, "You can only manage your own tenders")
    if tender.status != "open": raise HTTPException(409, "Only open tenders can be closed or cancelled")
    old_status = tender.status
    tender.status = data.status
    append_audit(db, user.id, "tender.status_changed", "tender", tender.id, {"from": old_status, "to": data.status})
    db.commit(); db.refresh(tender)
    return tender

@app.post("/tenders/{tender_id}/bids", response_model=BidOut, status_code=201)
def submit_bid(tender_id: int, data: BidCreate, db: Session = Depends(get_db), user: User = Depends(require_roles("supplier"))):
    tender = db.get(Tender, tender_id)
    if not tender: raise HTTPException(404, "Tender not found")
    now = datetime.now(timezone.utc)
    deadline = tender.deadline if tender.deadline.tzinfo else tender.deadline.replace(tzinfo=timezone.utc)
    if tender.status != "open" or deadline <= now: raise HTTPException(400, "Tender is not open for bidding")
    existing = db.scalar(select(Bid).where(Bid.tender_id == tender_id, Bid.supplier_id == user.id))
    if existing:
        raise HTTPException(409, "You already submitted a bid. Use PUT to revise it where revisions are allowed.")
    bid = Bid(tender_id=tender_id, supplier_id=user.id, **data.model_dump())
    db.add(bid)
    if tender.tender_type == "reverse_auction" and tender.anti_sniping and deadline - now <= timedelta(minutes=2):
        tender.deadline = now + timedelta(minutes=2)
    db.flush(); append_audit(db, user.id, "bid.submitted", "bid", bid.id, {"tender_id": tender_id, "price": bid.price, "delivery_days": bid.delivery_days})
    db.commit(); db.refresh(bid)
    return bid

@app.put("/tenders/{tender_id}/bids/me", response_model=BidOut)
def revise_my_bid(tender_id: int, data: BidCreate, db: Session = Depends(get_db), user: User = Depends(require_roles("supplier"))):
    tender = db.get(Tender, tender_id)
    if not tender: raise HTTPException(404, "Tender not found")
    now = datetime.now(timezone.utc)
    deadline = tender.deadline if tender.deadline.tzinfo else tender.deadline.replace(tzinfo=timezone.utc)
    if tender.status != "open" or deadline <= now: raise HTTPException(400, "Tender is not open for bidding")
    if tender.tender_type != "reverse_auction": raise HTTPException(400, "Bid revisions are enabled only for reverse auctions in V2")
    bid = db.scalar(select(Bid).where(Bid.tender_id == tender_id, Bid.supplier_id == user.id))
    if not bid: raise HTTPException(404, "Submit an initial bid before revising it")
    if data.price >= bid.price: raise HTTPException(400, "A reverse-auction revision must be lower than your current price")
    old_price = bid.price
    for field, value in data.model_dump().items(): setattr(bid, field, value)
    bid.updated_at = now
    if tender.anti_sniping and deadline - now <= timedelta(minutes=2): tender.deadline = now + timedelta(minutes=2)
    append_audit(db, user.id, "bid.revised", "bid", bid.id, {"tender_id": tender_id, "old_price": old_price, "new_price": bid.price})
    db.commit(); db.refresh(bid)
    return bid

@app.get("/tenders/{tender_id}/bids", response_model=list[BidOut])
def list_bids(tender_id: int, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    tender = db.get(Tender, tender_id)
    if not tender: raise HTTPException(404, "Tender not found")
    if user.role == "buyer" and tender.buyer_id != user.id: raise HTTPException(403, "You can only view bids for your own tenders")
    if user.role == "supplier": return list(db.scalars(select(Bid).where(Bid.tender_id == tender_id, Bid.supplier_id == user.id)).all())
    if tender.tender_type == "sealed" and tender.status == "open": raise HTTPException(403, "Sealed bids are hidden until the tender closes")
    return list(db.scalars(select(Bid).where(Bid.tender_id == tender_id)).all())

@app.get("/tenders/{tender_id}/ranking")
def get_ranking(tender_id: int, db: Session = Depends(get_db), user: User = Depends(require_roles("buyer", "admin"))):
    tender = db.get(Tender, tender_id)
    if not tender: raise HTTPException(404, "Tender not found")
    if user.role == "buyer" and tender.buyer_id != user.id: raise HTTPException(403, "You can only rank bids for your own tenders")
    if tender.status == "open": raise HTTPException(409, "Close the tender before viewing the final ranking")
    bids = list(db.scalars(select(Bid).where(Bid.tender_id == tender_id)).all())
    return {"tender_id": tender_id, "ranking": rank_bids(tender, bids), "note": "Ranking is advisory, explainable, and not an automatic award decision."}


# ---------------- Tender document intelligence (V3) ----------------
DOCUMENT_ROOT = Path("storage") / "tender_documents"
DOCUMENT_ROOT.mkdir(parents=True, exist_ok=True)
ALLOWED_DOCUMENT_TYPES = {"pdf", "docx", "txt"}


def _tender_for_user(tender_id: int, db: Session, user: User) -> Tender:
    tender = db.get(Tender, tender_id)
    if not tender:
        raise HTTPException(404, "Tender not found")
    if user.role == "buyer" and tender.buyer_id != user.id:
        raise HTTPException(403, "You can only access documents for your own tenders")
    if user.role == "supplier" and tender.status not in ("open", "closed", "awarded"):
        raise HTTPException(404, "Tender documents are not available")
    return tender


@app.post("/tenders/{tender_id}/documents", status_code=201)
def upload_tender_document(
    tender_id: int,
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
    user: User = Depends(require_roles("buyer", "admin")),
):
    """Upload and index one tender PDF, DOCX or TXT document."""
    tender = _tender_for_user(tender_id, db, user)
    if user.role == "buyer" and tender.buyer_id != user.id:
        raise HTTPException(403, "You can only upload documents to your own tenders")
    original_name = Path(file.filename or "document").name
    extension = Path(original_name).suffix.lower().lstrip(".")
    if extension not in ALLOWED_DOCUMENT_TYPES:
        raise HTTPException(415, "Supported file types are PDF, DOCX and TXT")
    raw = file.file.read(settings.max_document_mb * 1024 * 1024 + 1)
    if not raw:
        raise HTTPException(400, "The uploaded file is empty")
    if len(raw) > settings.max_document_mb * 1024 * 1024:
        raise HTTPException(413, f"Maximum document size is {settings.max_document_mb} MB")
    stored_name = f"{uuid4().hex}.{extension}"
    target = DOCUMENT_ROOT / stored_name
    target.write_bytes(raw)
    try:
        pages = extract_file(target, extension)
        chunks = chunk_pages(pages)
        if not chunks:
            raise DocumentProcessingError("No indexable text was found in the document")
        document = TenderDocument(
            tender_id=tender_id, uploaded_by=user.id, filename=original_name,
            stored_filename=stored_name, file_type=extension, file_size=len(raw), status="processed",
        )
        db.add(document)
        db.flush()
        for item in chunks:
            db.add(DocumentChunk(
                document_id=document.id, tender_id=tender_id,
                chunk_index=item["chunk_index"], page_number=item["page_number"],
                section=f"Page {item['page_number']}" if item["page_number"] else f"Text chunk {item['chunk_index'] + 1}",
                content=item["content"],
            ))
        db.flush(); append_audit(db, user.id, "tender.document_uploaded", "tender_document", document.id, {"tender_id": tender_id, "filename": original_name, "chunks_indexed": len(chunks), "file_size": len(raw)})
        db.commit()
        db.refresh(document)
        return {"id": document.id, "tender_id": tender_id, "filename": document.filename,
                "file_type": document.file_type, "file_size": document.file_size,
                "status": document.status, "chunks_indexed": len(chunks), "created_at": document.created_at}
    except DocumentProcessingError as exc:
        db.rollback()
        target.unlink(missing_ok=True)
        raise HTTPException(422, str(exc))
    except Exception:
        db.rollback()
        target.unlink(missing_ok=True)
        raise
    finally:
        file.file.close()


@app.get("/tenders/{tender_id}/documents")
def list_tender_documents(tender_id: int, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    _tender_for_user(tender_id, db, user)
    docs = db.scalars(select(TenderDocument).where(TenderDocument.tender_id == tender_id).order_by(TenderDocument.created_at.desc())).all()
    return [{"id": d.id, "tender_id": d.tender_id, "filename": d.filename, "file_type": d.file_type,
             "file_size": d.file_size, "status": d.status, "created_at": d.created_at} for d in docs]


@app.delete("/tenders/{tender_id}/documents/{document_id}")
def delete_tender_document(tender_id: int, document_id: int, db: Session = Depends(get_db), user: User = Depends(require_roles("buyer", "admin"))):
    tender = _tender_for_user(tender_id, db, user)
    document = db.get(TenderDocument, document_id)
    if not document or document.tender_id != tender_id:
        raise HTTPException(404, "Document not found")
    if user.role == "buyer" and tender.buyer_id != user.id:
        raise HTTPException(403, "You can only delete documents for your own tenders")
    path = DOCUMENT_ROOT / document.stored_filename
    db.execute(delete(DocumentChunk).where(DocumentChunk.document_id == document_id))
    db.delete(document)
    append_audit(db, user.id, "tender.document_deleted", "tender_document", document_id, {"tender_id": tender_id, "filename": document.filename})
    db.commit()
    path.unlink(missing_ok=True)
    return {"status": "deleted", "document_id": document_id}


@app.post("/tenders/{tender_id}/assistant/ask")
def ask_tender_assistant(
    tender_id: int,
    payload: dict,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """Answer from indexed tender sources and return traceable citations."""
    _tender_for_user(tender_id, db, user)
    question = str(payload.get("question", "")).strip()
    if len(question) < 3:
        raise HTTPException(422, "Question must contain at least 3 characters")
    if len(question) > 1200:
        raise HTTPException(422, "Question must be at most 1200 characters")
    rows = db.execute(
        select(DocumentChunk, TenderDocument)
        .join(TenderDocument, DocumentChunk.document_id == TenderDocument.id)
        .where(DocumentChunk.tender_id == tender_id)
    ).all()
    chunks = []
    for chunk, document in rows:
        chunks.append({"chunk_id": chunk.id, "document_id": document.id, "filename": document.filename,
                       "page_number": chunk.page_number, "section": chunk.section, "content": chunk.content})
    retrieved = retrieve(question, chunks, top_k=5)
    if not retrieved:
        return {"answer": "I could not find relevant evidence in the indexed documents. Upload the relevant tender specification or try a more specific question.",
                "mode": "retrieval_only", "citations": [], "disclaimer": "Answers are limited to the uploaded and successfully extracted text."}
    try:
        if settings.groq_api_key:
            answer = generate_with_groq(question, retrieved, settings.groq_api_key, settings.groq_model)
            mode = "groq_grounded_rag"
        else:
            answer = extractive_answer(question, retrieved)
            mode = "extractive_rag_no_api_key"
    except Exception:
        # Fail closed to evidence excerpts; never fabricate a generated answer on provider failure.
        answer = extractive_answer(question, retrieved)
        mode = "extractive_fallback_provider_unavailable"
    citations = []
    for i, item in enumerate(retrieved, start=1):
        citations.append({"source_id": f"S{i}", "document_id": item["document_id"], "filename": item["filename"],
                          "page_number": item["page_number"], "section": item["section"],
                          "excerpt": item["content"][:700], "relevance_score": item["score"]})
    return {"answer": answer, "mode": mode, "citations": citations,
            "disclaimer": "AI output is decision support, not a legal interpretation. Verify cited passages in the original tender document."}


@app.get("/tenders/{tender_id}/assistant/requirements")
def tender_requirement_checklist(tender_id: int, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    """Return an evidence-linked starter checklist from the tender's mandatory requirements."""
    tender = _tender_for_user(tender_id, db, user)
    requirements = [line.strip(" •-*	") for line in re.split(r"[\n;]+", tender.mandatory_requirements or "") if line.strip(" •-*	")]
    rows = db.execute(select(DocumentChunk, TenderDocument).join(TenderDocument, DocumentChunk.document_id == TenderDocument.id).where(DocumentChunk.tender_id == tender_id)).all()
    chunks = [{"chunk_id": c.id, "document_id": d.id, "filename": d.filename, "page_number": c.page_number, "section": c.section, "content": c.content} for c, d in rows]
    checklist = []
    for requirement in requirements:
        matches = retrieve(requirement, chunks, top_k=1)
        best = matches[0] if matches else None
        checklist.append({"requirement": requirement, "evidence_found": bool(best),
                          "evidence": ({"filename": best["filename"], "page_number": best["page_number"], "excerpt": best["content"][:400]} if best else None),
                          "review_status": "needs_human_review"})
    return {"tender_id": tender_id, "checklist": checklist,
            "note": "Evidence matching is a retrieval aid, not proof of supplier compliance. Every item requires human review."}


# ---------------- Supplier and price intelligence (V4) ----------------
@app.post("/tenders/{tender_id}/supplier-outcomes", status_code=201)
def record_supplier_outcome(tender_id: int, data: SupplierOutcomeIn, db: Session = Depends(get_db), user: User = Depends(require_roles("buyer", "admin"))):
    """Record a buyer-reviewed outcome after a tender has closed. One record per supplier/tender."""
    tender = db.get(Tender, tender_id)
    if not tender:
        raise HTTPException(404, "Tender not found")
    if user.role == "buyer" and tender.buyer_id != user.id:
        raise HTTPException(403, "You can only record outcomes for your own tenders")
    if tender.status not in ("closed", "awarded"):
        raise HTTPException(409, "Tender must be closed or awarded before recording supplier performance")
    bid = db.scalar(select(Bid).where(Bid.tender_id == tender_id, Bid.supplier_id == data.supplier_id))
    if not bid:
        raise HTTPException(404, "Supplier has no bid for this tender")
    supplier = db.get(User, data.supplier_id)
    if not supplier or supplier.role != "supplier":
        raise HTTPException(422, "supplier_id must identify a supplier account")
    existing = db.scalar(select(SupplierOutcome).where(SupplierOutcome.tender_id == tender_id, SupplierOutcome.supplier_id == data.supplier_id))
    if existing:
        raise HTTPException(409, "An outcome is already recorded for this supplier and tender")
    row = SupplierOutcome(tender_id=tender_id, supplier_id=data.supplier_id, quality_score=data.quality_score, on_time=data.on_time, issue_count=data.issue_count, notes=data.notes, recorded_by=user.id)
    db.add(row); db.flush(); append_audit(db, user.id, "supplier.outcome_recorded", "supplier_outcome", row.id, {"tender_id": tender_id, "supplier_id": data.supplier_id, "quality_score": data.quality_score, "on_time": data.on_time, "issue_count": data.issue_count}); db.commit(); db.refresh(row)
    return {"id": row.id, "tender_id": row.tender_id, "supplier_id": row.supplier_id, "quality_score": row.quality_score, "on_time": row.on_time, "issue_count": row.issue_count, "created_at": row.created_at, "message": "Outcome recorded; it will contribute to the supplier's advisory trust score."}

@app.get("/suppliers/{supplier_id}/trust")
def get_supplier_trust(supplier_id: int, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    supplier = db.get(User, supplier_id)
    if not supplier or supplier.role != "supplier":
        raise HTTPException(404, "Supplier not found")
    # Buyers/admins can inspect supplier trust; suppliers can inspect only their own.
    if user.role == "supplier" and user.id != supplier_id:
        raise HTTPException(403, "Suppliers can only view their own trust profile")
    rows = db.scalars(select(SupplierOutcome).where(SupplierOutcome.supplier_id == supplier_id).order_by(SupplierOutcome.created_at.desc())).all()
    payload = [{"quality_score": r.quality_score, "on_time": r.on_time, "issue_count": r.issue_count} for r in rows]
    return {"supplier_id": supplier_id, "company_name": supplier.company_name, **supplier_trust(payload), "recent_outcomes": [{"tender_id": r.tender_id, "quality_score": r.quality_score, "on_time": r.on_time, "issue_count": r.issue_count, "created_at": r.created_at} for r in rows[:10]]}

@app.get("/tenders/{tender_id}/similar")
def get_similar_tenders(tender_id: int, limit: int = Query(default=5, ge=1, le=10), db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    target = db.get(Tender, tender_id)
    if not target:
        raise HTTPException(404, "Tender not found")
    _tender_for_user(tender_id, db, user)
    candidates = db.scalars(select(Tender).where(Tender.status.in_(["closed", "awarded"])).order_by(Tender.created_at.desc()).limit(500)).all()
    target_dict = {"id": target.id, "title": target.title, "description": target.description, "category": target.category, "quantity": target.quantity}
    candidate_dicts = [{"id": t.id, "title": t.title, "description": t.description, "category": t.category, "quantity": t.quantity, "status": t.status, "created_at": t.created_at.isoformat() if t.created_at else None} for t in candidates]
    return {"tender_id": tender_id, "matches": similar_tenders(target_dict, candidate_dicts, limit), "method": "category + lexical overlap + quantity similarity", "note": "Similarity is heuristic, not a semantic embedding score."}

@app.get("/tenders/{tender_id}/price-intelligence")
def get_price_intelligence(tender_id: int, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    target = db.get(Tender, tender_id)
    if not target:
        raise HTTPException(404, "Tender not found")
    _tender_for_user(tender_id, db, user)
    historical = db.execute(select(Bid, Tender).join(Tender, Bid.tender_id == Tender.id).where(Tender.status.in_(["closed", "awarded"]), Bid.tender_id != tender_id).order_by(Bid.created_at.asc()).limit(5000)).all()
    history = [{"price": b.price, "quantity": t.quantity, "category": t.category, "created_at": b.created_at} for b, t in historical]
    target_dict = {"id": target.id, "category": target.category, "quantity": target.quantity}
    result = estimate_price(target_dict, history)
    # Include comparable historical sample counts and avoid exposing supplier identities or individual bid values.
    return {"tender_id": tender_id, "category": target.category, "quantity": target.quantity, **result, "human_review_required": True, "disclaimer": "Advisory estimate only. It is not a quote, valuation guarantee, or automatic award recommendation. Historical prices may be sparse or non-comparable."}

@app.get("/suppliers/me/trust")
def my_supplier_trust(db: Session = Depends(get_db), user: User = Depends(require_roles("supplier"))):
    rows = db.scalars(select(SupplierOutcome).where(SupplierOutcome.supplier_id == user.id).order_by(SupplierOutcome.created_at.desc())).all()
    payload = [{"quality_score": r.quality_score, "on_time": r.on_time, "issue_count": r.issue_count} for r in rows]
    return {"supplier_id": user.id, "company_name": user.company_name, **supplier_trust(payload), "recent_outcomes": [{"tender_id": r.tender_id, "quality_score": r.quality_score, "on_time": r.on_time, "issue_count": r.issue_count, "created_at": r.created_at} for r in rows[:10]]}


# ---------------- V5 risk review and tamper-evident audit ----------------
def _can_access_tender(tender_id: int, db: Session, user: User):
    tender = db.get(Tender, tender_id)
    if not tender:
        raise HTTPException(404, "Tender not found")
    if user.role == "buyer" and tender.buyer_id != user.id:
        raise HTTPException(403, "You can only access your own tenders")
    if user.role == "supplier":
        raise HTTPException(403, "This endpoint is restricted to buyers and administrators")
    return tender

@app.post("/tenders/{tender_id}/risk/scan")
def scan_tender_risks(tender_id: int, db: Session = Depends(get_db), user: User = Depends(require_roles("buyer", "admin"))):
    """Run explainable risk checks. Alerts are review leads, never automated findings."""
    tender = _can_access_tender(tender_id, db, user)
    bids = list(db.scalars(select(Bid).where(Bid.tender_id == tender_id).order_by(Bid.created_at.asc())).all())
    findings = detect_bid_risks(tender, bids)
    inserted = 0
    for finding in findings:
        if db.scalar(select(RiskAlert.id).where(RiskAlert.fingerprint == finding["fingerprint"])):
            continue
        row = RiskAlert(fingerprint=finding["fingerprint"], tender_id=tender_id, bid_id=finding.get("bid_id"),
                        rule_key=finding["rule_key"], severity=finding["severity"], title=finding["title"],
                        explanation=finding["explanation"], evidence_json=json.dumps(finding["evidence"], sort_keys=True), status="open")
        db.add(row); inserted += 1
    append_audit(db, user.id, "risk.scan_completed", "tender", tender_id, {"bids_checked": len(bids), "new_alerts": inserted})
    db.commit()
    return {"tender_id": tender_id, "bids_checked": len(bids), "signals_detected": len(findings), "new_alerts_saved": inserted,
            "alerts": list_risk_alerts_payload(db, tender_id),
            "disclaimer": "Risk signals are not proof of fraud, collusion or misconduct. Review source evidence and apply consistent due process."}

def list_risk_alerts_payload(db: Session, tender_id: int | None = None):
    query = select(RiskAlert)
    if tender_id is not None: query = query.where(RiskAlert.tender_id == tender_id)
    rows = db.scalars(query.order_by(RiskAlert.created_at.desc()).limit(500)).all()
    return [{"id": r.id, "tender_id": r.tender_id, "bid_id": r.bid_id, "rule_key": r.rule_key, "severity": r.severity,
             "title": r.title, "explanation": r.explanation, "evidence": json.loads(r.evidence_json or "{}"),
             "status": r.status, "review_note": r.review_note, "created_at": r.created_at} for r in rows]

@app.get("/risk/alerts")
def get_risk_alerts(tender_id: int | None = Query(default=None, ge=1), status: str = Query(default="all", pattern="^(open|reviewed|dismissed|all)$"),
                    db: Session = Depends(get_db), user: User = Depends(require_roles("buyer", "admin"))):
    if tender_id is not None: _can_access_tender(tender_id, db, user)
    query = select(RiskAlert)
    if tender_id is not None: query = query.where(RiskAlert.tender_id == tender_id)
    if status != "all": query = query.where(RiskAlert.status == status)
    if user.role == "buyer": query = query.join(Tender, RiskAlert.tender_id == Tender.id).where(Tender.buyer_id == user.id)
    rows = db.scalars(query.order_by(RiskAlert.created_at.desc()).limit(500)).all()
    return [{"id": r.id, "tender_id": r.tender_id, "bid_id": r.bid_id, "rule_key": r.rule_key, "severity": r.severity,
             "title": r.title, "explanation": r.explanation, "evidence": json.loads(r.evidence_json or "{}"),
             "status": r.status, "review_note": r.review_note, "created_at": r.created_at} for r in rows]

@app.patch("/risk/alerts/{alert_id}/review")
def review_risk_alert(alert_id: int, payload: dict, db: Session = Depends(get_db), user: User = Depends(require_roles("buyer", "admin"))):
    row = db.get(RiskAlert, alert_id)
    if not row: raise HTTPException(404, "Risk alert not found")
    _can_access_tender(row.tender_id, db, user)
    status = str(payload.get("status", ""))
    note = str(payload.get("note", "")).strip()
    if status not in ("reviewed", "dismissed"): raise HTTPException(422, "status must be reviewed or dismissed")
    if len(note) > 2000: raise HTTPException(422, "note must be at most 2000 characters")
    row.status = status; row.review_note = note; row.reviewed_by = user.id; row.reviewed_at = datetime.now(timezone.utc)
    append_audit(db, user.id, "risk.alert_reviewed", "risk_alert", row.id, {"tender_id": row.tender_id, "status": status, "note": note})
    db.commit()
    return {"id": row.id, "status": row.status, "review_note": row.review_note, "reviewed_at": row.reviewed_at}

@app.get("/audit/verify")
def verify_audit_log(db: Session = Depends(get_db), user: User = Depends(require_roles("admin"))):
    rows = list(db.scalars(select(AuditLog).order_by(AuditLog.id.asc())).all())
    result = verify_chain(rows)
    result["note"] = "Hash chaining makes unauthorized edits detectable if the chain head is independently preserved. This database is not an immutable/WORM store."
    return result

@app.get("/audit/logs")
def get_audit_logs(limit: int = Query(default=100, ge=1, le=500), offset: int = Query(default=0, ge=0),
                   db: Session = Depends(get_db), user: User = Depends(require_roles("buyer", "admin"))):
    query = select(AuditLog)
    if user.role == "buyer":
        owned_tender_ids = select(Tender.id).where(Tender.buyer_id == user.id)
        query = query.where((AuditLog.entity_type == "tender") & AuditLog.entity_id.in_(owned_tender_ids) |
                            (AuditLog.entity_type == "bid") & AuditLog.details_json.contains('"tender_id"'))
    rows = db.scalars(query.order_by(AuditLog.id.desc()).offset(offset).limit(limit)).all()
    result=[]
    for r in rows:
        details=json.loads(r.details_json or "{}")
        if user.role == "buyer" and details.get("tender_id") is not None:
            tender=db.get(Tender, int(details["tender_id"]))
            if not tender or tender.buyer_id != user.id: continue
        result.append({"id":r.id,"actor_id":r.actor_id,"action":r.action,"entity_type":r.entity_type,"entity_id":r.entity_id,
                       "details":details,"previous_hash":r.previous_hash,"entry_hash":r.entry_hash,"created_at":r.created_at})
    return {"items":result,"limit":limit,"offset":offset}
