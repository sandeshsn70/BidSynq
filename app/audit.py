"""Tamper-evident, hash-chained audit log helpers. Not an immutable/WORM store."""
from datetime import datetime, timezone
import hashlib, json
from sqlalchemy import select
from sqlalchemy.orm import Session
from app.models import AuditLog

GENESIS_HASH = "0" * 64

def canonical_json(value):
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False, default=str)

def normalized_timestamp(value):
    if value.tzinfo is None:
        value = value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc).isoformat()

def append_audit(db: Session, actor_id: int | None, action: str, entity_type: str, entity_id: str | int, details: dict | None = None):
    previous = db.scalar(select(AuditLog).order_by(AuditLog.id.desc()).limit(1))
    previous_hash = previous.entry_hash if previous else GENESIS_HASH
    created_at = datetime.now(timezone.utc)
    payload = {"actor_id": actor_id, "action": action, "entity_type": entity_type, "entity_id": str(entity_id),
               "details": details or {}, "previous_hash": previous_hash, "created_at": normalized_timestamp(created_at)}
    digest = hashlib.sha256(canonical_json(payload).encode("utf-8")).hexdigest()
    row = AuditLog(actor_id=actor_id, action=action, entity_type=entity_type, entity_id=str(entity_id),
                   details_json=canonical_json(details or {}), previous_hash=previous_hash, entry_hash=digest, created_at=created_at)
    db.add(row)
    db.flush()
    return row

def verify_chain(rows):
    previous_hash = GENESIS_HASH
    checked = 0
    for row in rows:
        if row.previous_hash != previous_hash:
            return {"valid": False, "checked_entries": checked, "broken_at_id": row.id, "reason": "previous_hash_mismatch"}
        payload = {"actor_id": row.actor_id, "action": row.action, "entity_type": row.entity_type, "entity_id": row.entity_id,
                   "details": json.loads(row.details_json or "{}"), "previous_hash": row.previous_hash, "created_at": normalized_timestamp(row.created_at)}
        expected = hashlib.sha256(canonical_json(payload).encode("utf-8")).hexdigest()
        if expected != row.entry_hash:
            return {"valid": False, "checked_entries": checked, "broken_at_id": row.id, "reason": "entry_hash_mismatch"}
        previous_hash = row.entry_hash
        checked += 1
    return {"valid": True, "checked_entries": checked, "head_hash": previous_hash}
