"""Server-side validation of uploaded tender documents.

The filename and extension are never trusted on their own: the bytes themselves must
look like the claimed format.
"""
from __future__ import annotations

import io
import zipfile
from pathlib import Path

from app.rag import DocumentProcessingError, decode_text_bytes

ALLOWED_EXTENSIONS = {"pdf", "docx", "txt"}
MAX_DOCX_ENTRIES = 5000
MAX_DOCX_UNCOMPRESSED = 150 * 1024 * 1024  # zip-bomb guard


def safe_display_name(filename: str | None) -> str:
    """Strip any path components and control characters from the client-supplied name."""
    name = Path((filename or "document").replace("\\", "/")).name
    name = "".join(ch for ch in name if ch.isprintable()).strip()
    return (name or "document")[:255]


def extension_of(name: str) -> str:
    return Path(name).suffix.lower().lstrip(".")


def validate_document_bytes(raw: bytes, extension: str) -> None:
    """Raise DocumentProcessingError unless ``raw`` genuinely is a PDF, DOCX or text file."""
    if extension not in ALLOWED_EXTENSIONS:
        raise DocumentProcessingError("Supported file types are PDF, DOCX and TXT.")
    if not raw:
        raise DocumentProcessingError("The uploaded file is empty.")

    looks_pdf = raw[:1024].find(b"%PDF-") != -1
    looks_zip = raw[:4] == b"PK\x03\x04"

    if extension == "pdf":
        if not looks_pdf:
            raise DocumentProcessingError("This file is not a valid PDF.")
    elif extension == "docx":
        if not looks_zip:
            raise DocumentProcessingError("This file is not a valid DOCX document.")
        try:
            with zipfile.ZipFile(io.BytesIO(raw)) as archive:
                infos = archive.infolist()
                names = {info.filename for info in infos}
                if len(infos) > MAX_DOCX_ENTRIES or sum(i.file_size for i in infos) > MAX_DOCX_UNCOMPRESSED:
                    raise DocumentProcessingError("This DOCX file is too large to process safely.")
                if "[Content_Types].xml" not in names or "word/document.xml" not in names:
                    raise DocumentProcessingError("This file is not a valid DOCX document.")
        except zipfile.BadZipFile:
            raise DocumentProcessingError("This file is not a valid DOCX document.") from None
    else:  # txt
        if looks_pdf or looks_zip:
            raise DocumentProcessingError("The file content does not match the .txt extension.")
        decode_text_bytes(raw)  # rejects NUL bytes / undecodable data
