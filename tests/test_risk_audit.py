from datetime import datetime, timezone, timedelta
from types import SimpleNamespace
from app.risk import detect_bid_risks
from app.audit import append_audit, verify_chain
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from app.database import Base
from app.models import User, AuditLog

def test_near_deadline_risk_is_explained():
    now=datetime.now(timezone.utc)
    tender=SimpleNamespace(id=1, deadline=now+timedelta(seconds=60))
    bids=[SimpleNamespace(id=11,price=100.0,delivery_days=5,requirement_match=90,created_at=now)]
    alerts=detect_bid_risks(tender,bids)
    assert any(a["rule_key"]=="near_deadline_bid" for a in alerts)
    assert all(a["explanation"] for a in alerts)

def test_hash_chain_verifies():
    engine=create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    Session=sessionmaker(bind=engine)
    with Session() as db:
        user=User(name="Tester",email="test@example.com",password_hash="x",role="admin",company_name="Test")
        db.add(user); db.flush()
        append_audit(db,user.id,"test.event","test","1",{"x":1})
        append_audit(db,user.id,"test.event","test","2",{"x":2})
        db.commit()
        rows=list(db.query(AuditLog).order_by(AuditLog.id.asc()).all())
        assert verify_chain(rows)["valid"] is True
    engine.dispose()

def test_repeated_price_signal():
    now=datetime.now(timezone.utc)
    tender=SimpleNamespace(id=2,deadline=now+timedelta(days=1))
    bids=[SimpleNamespace(id=i,price=100.0,delivery_days=4,requirement_match=90,created_at=now) for i in range(1,4)]
    alerts=detect_bid_risks(tender,bids)
    assert any(a["rule_key"]=="repeated_bid_price" for a in alerts)
