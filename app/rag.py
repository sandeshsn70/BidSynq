"""Small, auditable RAG pipeline: extraction -> chunking -> lexical retrieval -> grounded answer."""
from __future__ import annotations
import re
import math
from pathlib import Path
from typing import Iterable

from pypdf import PdfReader
from docx import Document as DocxDocument

TOKEN_RE = re.compile(r"[a-zA-Z0-9][a-zA-Z0-9_./%-]*")

class DocumentProcessingError(ValueError):
    pass

def extract_file(path: Path, file_type: str) -> list[tuple[int | None, str]]:
    """Return (page_number, text) entries. DOCX/TXT use None as page number."""
    try:
        if file_type == "pdf":
            reader = PdfReader(str(path))
            if reader.is_encrypted:
                raise DocumentProcessingError("Password-protected PDFs are not supported.")
            pages = [(i + 1, (page.extract_text() or "").strip()) for i, page in enumerate(reader.pages)]
            if not any(text for _, text in pages):
                raise DocumentProcessingError("No selectable text found. This PDF may be scanned; OCR is not included in V3.")
            return pages
        if file_type == "docx":
            doc = DocxDocument(str(path))
            text = "\n".join(p.text.strip() for p in doc.paragraphs if p.text.strip())
            text += "\n" + "\n".join(" | ".join(cell.text.strip() for cell in row.cells) for table in doc.tables for row in table.rows)
            if not text.strip():
                raise DocumentProcessingError("No text could be extracted from this DOCX.")
            return [(None, text.strip())]
        if file_type == "txt":
            text = path.read_text(encoding="utf-8", errors="replace").strip()
            if not text:
                raise DocumentProcessingError("The text file is empty.")
            return [(None, text)]
    except DocumentProcessingError:
        raise
    except Exception as exc:
        raise DocumentProcessingError(f"Could not parse this {file_type.upper()} file: {exc}") from exc
    raise DocumentProcessingError("Supported document types are PDF, DOCX and TXT.")

def chunk_pages(pages: Iterable[tuple[int | None, str]], chunk_size: int = 1100, overlap: int = 160) -> list[dict]:
    """Split text into overlapping chunks while retaining source page references."""
    chunks: list[dict] = []
    if chunk_size <= overlap:
        raise ValueError("chunk_size must be larger than overlap")
    for page, text in pages:
        text = re.sub(r"\s+", " ", text).strip()
        if not text:
            continue
        start = 0
        while start < len(text):
            end = min(len(text), start + chunk_size)
            # Prefer ending at a sentence/word boundary without making tiny chunks.
            if end < len(text):
                boundary = max(text.rfind(". ", start + chunk_size // 2, end), text.rfind("; ", start + chunk_size // 2, end), text.rfind(" ", start + chunk_size // 2, end))
                if boundary > start:
                    end = boundary + 1
            piece = text[start:end].strip()
            if piece:
                chunks.append({"page_number": page, "content": piece, "chunk_index": len(chunks)})
            if end >= len(text):
                break
            start = max(start + 1, end - overlap)
    return chunks

def retrieve(question: str, chunks: list[dict], top_k: int = 5) -> list[dict]:
    """Dependency-light lexical retrieval with token overlap and a small exact-phrase boost."""
    q_tokens = {t.lower() for t in TOKEN_RE.findall(question) if len(t) > 1}
    if not q_tokens:
        return []
    scored = []
    q_phrase = " ".join(question.lower().split())
    for chunk in chunks:
        text = chunk.get("content", "")
        tokens = [t.lower() for t in TOKEN_RE.findall(text)]
        if not tokens:
            continue
        counts: dict[str, int] = {}
        for token in tokens:
            counts[token] = counts.get(token, 0) + 1
        # Smoothed IDF-like term weighting; penalize long chunks modestly.
        matched = q_tokens.intersection(counts)
        score = sum((1 + math.log1p(counts[t])) for t in matched) / (len(tokens) ** 0.35)
        if len(q_tokens) > 0:
            score *= len(matched) / len(q_tokens)
        if q_phrase and q_phrase in text.lower():
            score += 2.0
        if score > 0:
            scored.append(({**chunk, "score": round(score, 6)}, score))
    scored.sort(key=lambda item: item[1], reverse=True)
    return [item[0] for item in scored[:top_k]]

def extractive_answer(question: str, contexts: list[dict]) -> str:
    """Grounded fallback when no generation provider is configured."""
    if not contexts:
        return "I couldn't find relevant evidence in the uploaded tender documents. Try rephrasing the question or upload the applicable specification."
    lines = []
    for item in contexts[:3]:
        content = item["content"].strip()
        # Keep a concise evidence excerpt; citations are returned separately.
        lines.append(content[:550] + ("…" if len(content) > 550 else ""))
    return "I found the following relevant passages. This is an evidence summary, not a complete legal or procurement interpretation:\n\n" + "\n\n---\n\n".join(lines)

def generate_with_groq(question: str, contexts: list[dict], api_key: str, model: str) -> str:
    """Optional generation. Only retrieved document passages are supplied as evidence."""
    import httpx
    evidence = "\n\n".join(f"[S{i+1}] {c['content']}" for i, c in enumerate(contexts))
    prompt = (
        "Answer the user's tender-document question using ONLY the evidence passages. "
        "If the evidence does not answer it, say that the documents do not provide enough information. "
        "Do not invent requirements, dates, prices, or legal interpretations. Cite evidence labels like [S1]. "
        "Keep the answer concise.\n\nEVIDENCE:\n" + evidence + "\n\nQUESTION:\n" + question
    )
    response = httpx.post(
        "https://api.groq.com/openai/v1/chat/completions",
        headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
        json={"model": model, "temperature": 0.1, "messages": [{"role": "system", "content": "You are a cautious tender document assistant. Ground every claim in provided evidence."}, {"role": "user", "content": prompt}]},
        timeout=35.0,
    )
    response.raise_for_status()
    return response.json()["choices"][0]["message"]["content"].strip()
