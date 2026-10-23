"""Database constraints, migrations (data preservation!) and configuration safety."""
import os
import subprocess
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest
from sqlalchemy import create_engine, inspect, select, text
from sqlalchemy.exc import IntegrityError

from app.audit import append_audit, verify_chain
from app.config import DEFAULT_SECRET, Settings, validate_production_settings
from app.database import Base, normalize_database_url
from app.models import AuditLog, Bid, SupplierOutcome, Tender, User

ROOT = Path(__file__).resolve().parents[1]
FUTURE = datetime.now(timezone.utc) + timedelta(days=3)


def user(email, role="supplier"):
    return User(name="N", email=email, password_hash="h", role=role, company_name="")


# --------------------------------------------------------------------------- constraints


def test_unique_email(db):
    db.add(user("a@x.com"))
    db.commit()
    db.add(user("a@x.com"))
    with pytest.raises(IntegrityError):
        db.commit()


def test_unique_bid_and_outcome_per_supplier_and_tender(db):
    buyer, sup = user("b@x.com", "buyer"), user("s@x.com")
    db.add_all([buyer, sup])
    db.flush()
    tender = Tender(buyer_id=buyer.id, title="T", deadline=FUTURE)
    db.add(tender)
    db.flush()
    db.add(Bid(tender_id=tender.id, supplier_id=sup.id, price=1, delivery_days=1))
    db.commit()
    db.add(Bid(tender_id=tender.id, supplier_id=sup.id, price=2, delivery_days=1))
    with pytest.raises(IntegrityError):
        db.commit()
    db.rollback()
    db.add(SupplierOutcome(tender_id=tender.id, supplier_id=sup.id, recorded_by=buyer.id))
    db.commit()
    db.add(SupplierOutcome(tender_id=tender.id, supplier_id=sup.id, recorded_by=buyer.id))
    with pytest.raises(IntegrityError):
        db.commit()


def test_audit_entry_hash_is_unique_and_rollback_discards_entries(db):
    append_audit(db, None, "a.b", "x", "1", {})
    db.rollback()
    assert db.scalars(select(AuditLog)).all() == []        # transaction semantics: nothing half-written
    append_audit(db, None, "a.b", "x", "1", {})
    db.commit()
    row = db.scalars(select(AuditLog)).one()
    db.add(AuditLog(action="a", entity_type="x", entity_id="1", previous_hash=row.previous_hash, entry_hash=row.entry_hash))
    with pytest.raises(IntegrityError):
        db.commit()


# ----------------------------------------------------------------------------- migrations


def _alembic(url: str, *args: str):
    env = {**os.environ, "DATABASE_URL": url}
    return subprocess.run([sys.executable, "-m", "alembic", *args], cwd=ROOT, env=env, capture_output=True, text=True)


def test_baseline_migration_creates_everything_on_empty_database(tmp_path):
    url = f"sqlite:///{tmp_path}/fresh.db"
    result = _alembic(url, "upgrade", "head")
    assert result.returncode == 0, result.stderr
    names = set(inspect(create_engine(url)).get_table_names())
    assert set(Base.metadata.tables) | {"alembic_version"} == names
    assert _alembic(url, "check").returncode == 0, "migration and models have drifted apart"


def test_migration_preserves_existing_production_like_data(tmp_path):
    """Simulates your Render database: created by create_all(), already full of data, never seen Alembic."""
    url = f"sqlite:///{tmp_path}/prod.db"
    engine = create_engine(url)
    Base.metadata.create_all(engine)
    from sqlalchemy.orm import Session
    with Session(engine) as s:
        buyer, sup = user("buyer@x.com", "buyer"), user("sup@x.com")
        s.add_all([buyer, sup])
        s.flush()
        tender = Tender(buyer_id=buyer.id, title="Existing tender", deadline=FUTURE, status="closed")
        s.add(tender)
        s.flush()
        s.add(Bid(tender_id=tender.id, supplier_id=sup.id, price=123.45, delivery_days=7))
        append_audit(s, buyer.id, "tender.created", "tender", tender.id, {"title": "Existing tender"})
        s.commit()
    before = {t: engine.connect().execute(text(f"SELECT COUNT(*) FROM {t}")).scalar() for t in Base.metadata.tables}
    schema_before = {t: [c["name"] for c in inspect(engine).get_columns(t)] for t in Base.metadata.tables}

    for _ in range(2):                                           # running it twice must also be harmless
        assert _alembic(url, "upgrade", "head").returncode == 0

    engine2 = create_engine(url)
    after = {t: engine2.connect().execute(text(f"SELECT COUNT(*) FROM {t}")).scalar() for t in Base.metadata.tables}
    assert before == after and before["users"] == 2 and before["bids"] == 1
    assert schema_before == {t: [c["name"] for c in inspect(engine2).get_columns(t)] for t in Base.metadata.tables}
    with Session(engine2) as s:
        assert s.scalars(select(Bid)).one().price == 123.45
        assert verify_chain(s.scalars(select(AuditLog).order_by(AuditLog.id)))["valid"]
    assert engine2.connect().execute(text("SELECT version_num FROM alembic_version")).scalar() == "0001_baseline"


def test_application_code_never_drops_or_creates_tables():
    banned = ("drop_all", "create_all", "DROP TABLE", "TRUNCATE")
    for path in list((ROOT / "app").rglob("*.py")):
        source = path.read_text()
        for word in banned:
            assert word not in source.replace("# create_all", ""), f"{path.name} uses {word}"
    for path in (ROOT / "alembic" / "versions").glob("*.py"):
        text_ = path.read_text().lower()
        assert "drop_table" not in text_.replace("never drops", "") or "drop_table(" not in text_


# ------------------------------------------------------------------------------ settings


@pytest.mark.parametrize("raw,expected", [
    ("postgres://u:p@h/db", "postgresql+psycopg://u:p@h/db"),
    ("postgresql://u:p@h/db", "postgresql+psycopg://u:p@h/db"),
    ("postgresql+psycopg://u:p@h/db", "postgresql+psycopg://u:p@h/db"),
    ("  postgres://u:p@h/db\n", "postgresql+psycopg://u:p@h/db"),
    ("sqlite:///x.db", "sqlite:///x.db"),
])
def test_database_url_normalisation(raw, expected):
    assert normalize_database_url(raw) == expected


def _prod(**kw):
    base = dict(secret_key="x" * 40, database_url="postgresql://u:p@h/db", bidsynq_allow_admin_registration=False)
    return Settings(**{**base, **kw}, _env_file=None)


def test_production_validation(monkeypatch):
    monkeypatch.setenv("RENDER", "true")
    validate_production_settings(_prod())                                         # good config passes
    for bad in ({"secret_key": DEFAULT_SECRET}, {"secret_key": "short"}, {"database_url": "sqlite:///x.db"},
                {"bidsynq_allow_admin_registration": True}, {"cors_origins": "*"}):
        with pytest.raises(RuntimeError):
            validate_production_settings(_prod(**bad))


def test_dev_mode_does_not_enforce_production_rules(monkeypatch):
    monkeypatch.delenv("RENDER", raising=False)
    monkeypatch.delenv("BIDSYNQ_ENV", raising=False)
    validate_production_settings(Settings(secret_key=DEFAULT_SECRET, database_url="sqlite:///x.db", _env_file=None))


def test_settings_strip_whitespace_and_default_cors():
    s = Settings(secret_key=" abc \n", groq_api_key=" key ", _env_file=None)
    assert s.secret_key == "abc" and s.groq_api_key == "key"
    assert "https://bidsynq-frontend.onrender.com" in s.cors_origin_list
    assert Settings(cors_origins="https://a.com/, https://b.com", _env_file=None).cors_origin_list == ["https://a.com", "https://b.com"]


def test_cors_only_allows_configured_origins(client):
    good = client.options("/tenders", headers={"Origin": "https://bidsynq-frontend.onrender.com",
                                               "Access-Control-Request-Method": "GET"})
    bad = client.options("/tenders", headers={"Origin": "https://evil.example", "Access-Control-Request-Method": "GET"})
    assert good.headers.get("access-control-allow-origin") == "https://bidsynq-frontend.onrender.com"
    assert "access-control-allow-origin" not in bad.headers


def test_health_endpoint_reports_state_without_secrets(client):
    body = client.get("/health").json()
    assert body["status"] == "ok" and body["database"] == "ok" and body["groq_configured"] is False
    assert "test-secret" not in str(body)


def test_security_headers_present(client):
    h = client.get("/health").headers
    assert h["x-content-type-options"] == "nosniff" and h["cache-control"] == "no-store"
