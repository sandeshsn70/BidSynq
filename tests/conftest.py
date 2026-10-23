"""Shared fixtures. Tests never touch the production database and never call the real Groq API."""
import os
import tempfile
from datetime import datetime, timedelta, timezone

# Must be set before the app is imported so the module-level engine never points at real data.
_TMP = tempfile.mkdtemp(prefix="bidsynq-tests-")
os.environ["DATABASE_URL"] = f"sqlite:///{_TMP}/import-time.db"
os.environ["SECRET_KEY"] = "test-secret-key-that-is-long-enough-123456"
os.environ["GROQ_API_KEY"] = ""
os.environ["DOCUMENT_STORAGE_DIR"] = f"{_TMP}/documents"
os.environ.pop("RENDER", None)
os.environ.pop("BIDSYNQ_ENV", None)

import pytest  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402
from sqlalchemy import create_engine  # noqa: E402
from sqlalchemy.orm import sessionmaker  # noqa: E402
from sqlalchemy.pool import StaticPool  # noqa: E402

import app.main as main_module  # noqa: E402
from app import ratelimit  # noqa: E402
from app.config import settings  # noqa: E402
from app.database import Base, get_db  # noqa: E402
from app.main import app  # noqa: E402
from app.models import User  # noqa: E402
from app.security import create_access_token, hash_password  # noqa: E402

PASSWORD = "CorrectHorse9!"


@pytest.fixture()
def engine():
    eng = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    Base.metadata.create_all(eng)
    yield eng
    eng.dispose()


@pytest.fixture()
def Session(engine):
    return sessionmaker(bind=engine, autoflush=False, autocommit=False, expire_on_commit=False)


@pytest.fixture()
def db(Session):
    with Session() as session:
        yield session


@pytest.fixture()
def client(Session, monkeypatch):
    def override():
        session = Session()
        try:
            yield session
        finally:
            session.close()

    app.dependency_overrides[get_db] = override
    monkeypatch.setattr(main_module, "SessionLocal", Session)
    ratelimit.clear_all()
    monkeypatch.setattr(settings, "groq_api_key", "")
    monkeypatch.setattr(settings, "bidsynq_allow_admin_registration", False)
    with TestClient(app) as test_client:
        yield test_client
    app.dependency_overrides.clear()


class Actor:
    """A signed-in user: holds the id and ready-made auth headers."""

    def __init__(self, user: User):
        self.id = user.id
        self.email = user.email
        self.role = user.role
        self.headers = {"Authorization": f"Bearer {create_access_token(user.id)}"}


@pytest.fixture()
def make_user(Session):
    counter = {"n": 0}

    def _make(role: str, company: str = "") -> Actor:
        counter["n"] += 1
        with Session() as session:
            user = User(
                name=f"{role.title()} {counter['n']}",
                email=f"{role}{counter['n']}@example.com",
                password_hash=hash_password(PASSWORD),
                role=role,
                company_name=company or f"{role.title()} Co {counter['n']}",
            )
            session.add(user)
            session.commit()
            session.refresh(user)
            return Actor(user)

    return _make


@pytest.fixture()
def buyer(make_user):
    return make_user("buyer")


@pytest.fixture()
def buyer2(make_user):
    return make_user("buyer")


@pytest.fixture()
def supplier(make_user):
    return make_user("supplier")


@pytest.fixture()
def supplier2(make_user):
    return make_user("supplier")


@pytest.fixture()
def admin(make_user):
    return make_user("admin")


def tender_payload(**overrides):
    payload = {
        "title": "Industrial safety gloves",
        "description": "Supply of cut-resistant gloves",
        "category": "PPE",
        "quantity": 100,
        "tender_type": "rfq",
        "deadline": (datetime.now(timezone.utc) + timedelta(days=7)).isoformat(),
        "mandatory_requirements": "ISO 9001 certification\nDelivery within 30 days",
    }
    payload.update(overrides)
    return payload


def bid_payload(**overrides):
    payload = {"price": 1000.0, "delivery_days": 10, "validity_days": 30, "requirement_match": 95.0,
               "mandatory_met": True, "compliance_notes": "ok"}
    payload.update(overrides)
    return payload


@pytest.fixture()
def create_tender(client, buyer):
    def _create(owner=None, **overrides):
        owner = owner or buyer
        response = client.post("/tenders", json=tender_payload(**overrides), headers=owner.headers)
        assert response.status_code == 201, response.text
        return response.json()

    return _create


@pytest.fixture()
def set_deadline(Session):
    """Directly move a tender's deadline (to simulate time passing)."""
    from app.models import Tender

    def _set(tender_id: int, when: datetime):
        with Session() as session:
            tender = session.get(Tender, tender_id)
            tender.deadline = when
            session.commit()

    return _set


@pytest.fixture()
def set_status(Session):
    from app.models import Tender

    def _set(tender_id: int, status: str):
        with Session() as session:
            session.get(Tender, tender_id).status = status
            session.commit()

    return _set


def minimal_pdf(text: str) -> bytes:
    """Build a tiny valid one-page PDF containing ``text`` (no third-party PDF writer needed)."""
    safe = text.replace("\\", "\\\\").replace("(", "\\(").replace(")", "\\)")
    stream = f"BT /F1 12 Tf 72 720 Td ({safe}) Tj ET".encode("latin-1")
    objects = [
        b"<< /Type /Catalog /Pages 2 0 R >>",
        b"<< /Type /Pages /Kids [3 0 R] /Count 1 >>",
        b"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] /Contents 4 0 R "
        b"/Resources << /Font << /F1 5 0 R >> >> >>",
        b"<< /Length " + str(len(stream)).encode() + b" >>\nstream\n" + stream + b"\nendstream",
        b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>",
    ]
    out = bytearray(b"%PDF-1.4\n")
    offsets = []
    for number, body in enumerate(objects, start=1):
        offsets.append(len(out))
        out += f"{number} 0 obj\n".encode() + body + b"\nendobj\n"
    xref = len(out)
    out += f"xref\n0 {len(objects) + 1}\n".encode() + b"0000000000 65535 f \n"
    for offset in offsets:
        out += f"{offset:010d} 00000 n \n".encode()
    out += f"trailer\n<< /Size {len(objects) + 1} /Root 1 0 R >>\nstartxref\n{xref}\n%%EOF\n".encode()
    return bytes(out)


def minimal_docx(paragraphs: list[str]) -> bytes:
    import io

    from docx import Document

    document = Document()
    for paragraph in paragraphs:
        document.add_paragraph(paragraph)
    buffer = io.BytesIO()
    document.save(buffer)
    return buffer.getvalue()
