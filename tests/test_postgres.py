"""Real-PostgreSQL tests (race conditions, migrations, SQL that SQLite tolerates but PostgreSQL does not).

Skipped unless TEST_DATABASE_URL points at a DISPOSABLE database whose name contains "test", e.g.
    TEST_DATABASE_URL=postgresql://user:pw@localhost:5432/bidsynq_test pytest tests/test_postgres.py
NEVER point this at production: the fixture wipes the public schema of that database.
"""
import os
import subprocess
import sys
import threading
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest
from sqlalchemy import create_engine, select, text
from sqlalchemy.orm import sessionmaker

from app.audit import verify_chain
from app.database import Base, normalize_database_url
from app.models import AuditLog, Bid, Tender, User
from app.security import create_access_token, hash_password

URL = os.environ.get("TEST_DATABASE_URL", "")
pytestmark = pytest.mark.skipif(
    not URL or "test" not in URL.rsplit("/", 1)[-1], reason="TEST_DATABASE_URL (a *test* database) not set")
ROOT = Path(__file__).resolve().parents[1]


@pytest.fixture()
def pg():
    engine = create_engine(normalize_database_url(URL), pool_size=20, max_overflow=20)
    with engine.begin() as c:
        c.execute(text("DROP SCHEMA public CASCADE"))
        c.execute(text("CREATE SCHEMA public"))
    yield engine
    engine.dispose()


@pytest.fixture()
def pg_client(pg):
    from app.database import get_db
    from app.main import app
    from app import ratelimit

    Base.metadata.create_all(pg)
    Session = sessionmaker(bind=pg, autoflush=False, expire_on_commit=False)

    def override():
        s = Session()
        try:
            yield s
        finally:
            s.close()

    app.dependency_overrides[get_db] = override
    ratelimit.clear_all()
    yield Session
    app.dependency_overrides.clear()


def _user(Session, role, n):
    with Session() as s:
        u = User(name=f"{role}{n}", email=f"{role}{n}@example.com", password_hash=hash_password("x" * 10), role=role, company_name=f"C{n}")
        s.add(u)
        s.commit()
        return u.id, {"Authorization": f"Bearer {create_access_token(u.id)}"}


def _tender(Session, buyer_id, **kw):
    with Session() as s:
        t = Tender(buyer_id=buyer_id, title="Race tender", deadline=datetime.now(timezone.utc) + timedelta(days=2), **kw)
        s.add(t)
        s.commit()
        return t.id


def _run_parallel(fn, n):
    results, barrier = [None] * n, threading.Barrier(n)

    def worker(i):
        barrier.wait()
        results[i] = fn(i)

    threads = [threading.Thread(target=worker, args=(i,)) for i in range(n)]
    [t.start() for t in threads]
    [t.join() for t in threads]
    return results


def test_concurrent_duplicate_bids_yield_exactly_one_bid(pg_client):
    from fastapi.testclient import TestClient
    from app.main import app
    Session = pg_client
    buyer_id, _ = _user(Session, "buyer", 1)
    _, sup_headers = _user(Session, "supplier", 1)
    tid = _tender(Session, buyer_id)
    client = TestClient(app)
    codes = _run_parallel(lambda i: client.post(f"/tenders/{tid}/bids", json={"price": 100 + i, "delivery_days": 5}, headers=sup_headers).status_code, 8)
    assert sorted(codes) == [201] + [409] * 7, codes
    with Session() as s:
        assert len(s.scalars(select(Bid)).all()) == 1


def test_concurrent_writes_keep_audit_chain_linear(pg_client):
    """Each supplier bids on a DIFFERENT tender, so only the audit-chain lock serialises the writes."""
    from fastapi.testclient import TestClient
    from app.main import app
    Session = pg_client
    buyer_id, _ = _user(Session, "buyer", 1)
    tenders = [_tender(Session, buyer_id) for _ in range(12)]
    suppliers = [_user(Session, "supplier", i)[1] for i in range(12)]
    client = TestClient(app)
    codes = _run_parallel(lambda i: client.post(f"/tenders/{tenders[i]}/bids", json={"price": 100 + i, "delivery_days": 5}, headers=suppliers[i]).status_code, 12)
    assert codes == [201] * 12
    with Session() as s:
        rows = list(s.scalars(select(AuditLog).order_by(AuditLog.id)))
        assert len(rows) == 12 and len({r.previous_hash for r in rows}) == 12   # no two entries share a parent
        assert verify_chain(rows)["valid"]


def test_buyer_audit_log_query_works_on_postgresql(pg_client):
    from fastapi.testclient import TestClient
    from app.main import app
    Session = pg_client
    buyer_id, buyer_headers = _user(Session, "buyer", 1)
    client = TestClient(app)
    from tests.conftest import tender_payload
    assert client.post("/tenders", json=tender_payload(), headers=buyer_headers).status_code == 201
    r = client.get("/audit/logs", headers=buyer_headers)
    assert r.status_code == 200 and r.json()["items"]


def test_alembic_upgrade_on_existing_postgres_database_preserves_data(pg):
    Base.metadata.create_all(pg)                       # what your Render database looks like today
    Session = sessionmaker(bind=pg)
    with Session() as s:
        s.add(User(name="Old User", email="old@example.com", password_hash="$2b$12$abc", role="buyer", company_name="Old Co"))
        s.commit()
    env = {**os.environ, "DATABASE_URL": URL}
    for _ in range(2):
        r = subprocess.run([sys.executable, "-m", "alembic", "upgrade", "head"], cwd=ROOT, env=env, capture_output=True, text=True)
        assert r.returncode == 0, r.stderr
    assert subprocess.run([sys.executable, "-m", "alembic", "check"], cwd=ROOT, env=env, capture_output=True).returncode == 0
    with Session() as s:
        u = s.scalars(select(User)).one()
        assert (u.email, u.password_hash, u.company_name) == ("old@example.com", "$2b$12$abc", "Old Co")
        assert s.execute(text("SELECT version_num FROM alembic_version")).scalar() == "0001_baseline"


def test_alembic_creates_schema_on_empty_postgres(pg):
    env = {**os.environ, "DATABASE_URL": URL}
    r = subprocess.run([sys.executable, "-m", "alembic", "upgrade", "head"], cwd=ROOT, env=env, capture_output=True, text=True)
    assert r.returncode == 0, r.stderr
    with pg.connect() as c:
        tables = {row[0] for row in c.execute(text("SELECT tablename FROM pg_tables WHERE schemaname='public'"))}
    assert set(Base.metadata.tables) <= tables
