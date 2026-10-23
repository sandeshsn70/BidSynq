import logging
import re
from pathlib import Path
from uuid import uuid4

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile
from sqlalchemy import delete, func, select
from sqlalchemy.orm import Session

from app.access import get_document_tender, get_managed_tender
from app.audit import append_audit
from app.config import settings
from app.database import get_db
from app.models import DocumentChunk, TenderDocument, User
from app.rag import DocumentProcessingError, chunk_pages, extract_file, retrieve, extractive_answer
from app.rag import GroqError, generate_with_groq
from app.schemas import AskIn, AskOut, ChecklistOut, DeleteOut, DocumentOut, UploadOut
from app.security import get_current_user, require_roles
from app.uploads import extension_of, safe_display_name, validate_document_bytes

logger = logging.getLogger("bidsynq.documents")
router = APIRouter(tags=["documents"])


def _storage_dir() -> Path:
    path = Path(settings.document_storage_dir)
    path.mkdir(parents=True, exist_ok=True)
    return path


def _chunks_for(db: Session, tender_id: int) -> list[dict]:
    rows = db.execute(
        select(DocumentChunk, TenderDocument)
        .join(TenderDocument, DocumentChunk.document_id == TenderDocument.id)
        .where(DocumentChunk.tender_id == tender_id)
        .order_by(DocumentChunk.id.asc())
    ).all()
    return [
        {"chunk_id": c.id, "document_id": d.id, "filename": d.filename, "page_number": c.page_number,
         "section": c.section, "content": c.content}
        for c, d in rows
    ]


@router.post("/tenders/{tender_id}/documents", response_model=UploadOut, status_code=201)
def upload_tender_document(
    tender_id: int,
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
    user: User = Depends(require_roles("buyer", "admin")),
):
    """Upload and index one tender PDF, DOCX or TXT document (owner buyer or admin only)."""
    tender = get_managed_tender(db, tender_id, user)
    original_name = safe_display_name(file.filename)
    extension = extension_of(original_name)
    if extension not in ("pdf", "docx", "txt"):
        raise HTTPException(415, "Supported file types are PDF, DOCX and TXT")

    limit = settings.max_document_mb * 1024 * 1024
    try:
        raw = file.file.read(limit + 1)
    finally:
        file.file.close()
    if not raw:
        raise HTTPException(400, "The uploaded file is empty")
    if len(raw) > limit:
        raise HTTPException(413, f"Maximum document size is {settings.max_document_mb} MB")

    existing = db.scalar(select(func.count()).select_from(TenderDocument).where(TenderDocument.tender_id == tender.id)) or 0
    if existing >= settings.max_documents_per_tender:
        raise HTTPException(409, f"A tender can have at most {settings.max_documents_per_tender} documents")

    target: Path | None = None
    try:
        validate_document_bytes(raw, extension)
        stored_name = f"{uuid4().hex}.{extension}"
        target = _storage_dir() / stored_name
        target.write_bytes(raw)
        chunks = chunk_pages(extract_file(target, extension))
        if not chunks:
            raise DocumentProcessingError("No indexable text was found in the document")

        document = TenderDocument(
            tender_id=tender.id, uploaded_by=user.id, filename=original_name,
            stored_filename=stored_name, file_type=extension, file_size=len(raw), status="processed",
        )
        db.add(document)
        db.flush()
        for item in chunks:
            db.add(DocumentChunk(
                document_id=document.id, tender_id=tender.id,
                chunk_index=item["chunk_index"], page_number=item["page_number"],
                section=f"Page {item['page_number']}" if item["page_number"] else f"Text chunk {item['chunk_index'] + 1}",
                content=item["content"],
            ))
        db.flush()
        append_audit(db, user.id, "tender.document_uploaded", "tender_document", document.id,
                     {"tender_id": tender.id, "filename": original_name, "chunks_indexed": len(chunks),
                      "file_size": len(raw)})
        db.commit()
        db.refresh(document)
        return UploadOut(
            id=document.id, tender_id=tender.id, filename=document.filename, file_type=document.file_type,
            file_size=document.file_size, status=document.status, created_at=document.created_at,
            chunks_indexed=len(chunks),
        )
    except DocumentProcessingError as exc:
        db.rollback()
        if target:
            target.unlink(missing_ok=True)
        raise HTTPException(422, str(exc)) from None
    except Exception:
        db.rollback()
        if target:
            target.unlink(missing_ok=True)
        raise


@router.get("/tenders/{tender_id}/documents", response_model=list[DocumentOut])
def list_tender_documents(tender_id: int, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    get_document_tender(db, tender_id, user)
    docs = db.scalars(
        select(TenderDocument).where(TenderDocument.tender_id == tender_id)
        .order_by(TenderDocument.created_at.desc(), TenderDocument.id.desc())
    ).all()
    return list(docs)


@router.delete("/tenders/{tender_id}/documents/{document_id}", response_model=DeleteOut)
def delete_tender_document(
    tender_id: int,
    document_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(require_roles("buyer", "admin")),
):
    get_managed_tender(db, tender_id, user)
    document = db.get(TenderDocument, document_id)
    if not document or document.tender_id != tender_id:
        raise HTTPException(404, "Document not found")
    stored = Path(document.stored_filename).name  # never follow a stored path outside the storage dir
    filename = document.filename
    try:
        db.execute(delete(DocumentChunk).where(DocumentChunk.document_id == document_id))
        db.delete(document)
        append_audit(db, user.id, "tender.document_deleted", "tender_document", document_id,
                     {"tender_id": tender_id, "filename": filename})
        db.commit()
    except Exception:
        db.rollback()
        raise
    (_storage_dir() / stored).unlink(missing_ok=True)
    return DeleteOut(status="deleted", document_id=document_id)


@router.post("/tenders/{tender_id}/assistant/ask", response_model=AskOut, response_model_exclude_none=True)
def ask_tender_assistant(
    tender_id: int,
    payload: AskIn,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """Answer from indexed tender sources and return traceable citations."""
    get_document_tender(db, tender_id, user)
    retrieved = retrieve(payload.question, _chunks_for(db, tender_id), top_k=5)
    disclaimer = ("AI output is decision support, not a legal interpretation. "
                  "Verify cited passages in the original tender document.")
    if not retrieved:
        return AskOut(
            answer=("I could not find relevant evidence in the indexed documents. Upload the relevant tender "
                    "specification or try a more specific question."),
            mode="retrieval_only", citations=[],
            disclaimer="Answers are limited to the uploaded and successfully extracted text.",
        )

    notice = None
    try:
        if settings.groq_api_key:
            answer = generate_with_groq(payload.question, retrieved, settings.groq_api_key, settings.groq_model,
                                        timeout=settings.groq_timeout_seconds)
            mode = "groq_grounded_rag"
        else:
            answer = extractive_answer(payload.question, retrieved)
            mode = "extractive_rag_no_api_key"
    except GroqError as exc:
        logger.warning("Groq unavailable, using extractive fallback: %s", exc)
        answer = extractive_answer(payload.question, retrieved)
        mode = "extractive_fallback_provider_unavailable"
        notice = str(exc)
    except Exception:
        logger.exception("Unexpected assistant error; using extractive fallback")
        answer = extractive_answer(payload.question, retrieved)
        mode = "extractive_fallback_provider_unavailable"
        notice = "The AI provider is currently unavailable."

    citations = [
        {"source_id": f"S{i}", "document_id": item["document_id"], "filename": item["filename"],
         "page_number": item["page_number"], "section": item["section"], "excerpt": item["content"][:700],
         "relevance_score": item["score"]}
        for i, item in enumerate(retrieved, start=1)
    ]
    return AskOut(answer=answer, mode=mode, citations=citations, disclaimer=disclaimer, notice=notice)


@router.get("/tenders/{tender_id}/assistant/requirements", response_model=ChecklistOut)
def tender_requirement_checklist(tender_id: int, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    """Evidence-linked starter checklist built from the tender's mandatory requirements."""
    tender = get_document_tender(db, tender_id, user)
    lines = [re.sub(r"^[\s•*\-]+", "", part).strip() for part in re.split(r"[\n;]+", tender.mandatory_requirements or "")]
    requirements = [line for line in lines if line]
    chunks = _chunks_for(db, tender_id)
    checklist = []
    for requirement in requirements:
        matches = retrieve(requirement, chunks, top_k=1)
        best = matches[0] if matches else None
        checklist.append({
            "requirement": requirement,
            "evidence_found": bool(best),
            "evidence": ({"filename": best["filename"], "page_number": best["page_number"],
                          "excerpt": best["content"][:400]} if best else None),
            "review_status": "needs_human_review",
        })
    return ChecklistOut(
        tender_id=tender_id, checklist=checklist,
        note="Evidence matching is a retrieval aid, not proof of supplier compliance. Every item requires human review.",
    )
