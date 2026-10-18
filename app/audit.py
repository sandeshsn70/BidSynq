
"""Tamper-evident, hash-chained audit log helpers.

This is not an immutable/WORM store. Audit entries require appropriate
database access controls and independent backups for stronger protection.
"""
from __future__ import annotations

import hashlib
import hmac
import json
from datetime import datetime, timezone
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import AuditLog


GENESIS_HASH = "0" * 64


def canonical_json(value: Any) -> str:
    """Serialize values consistently for hashing."""
    return json.dumps(
        value,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
        default=str,
        allow_nan=False,
    )


def normalized_timestamp(value: datetime) -> str:
    """Normalize a datetime to an ISO-8601 UTC timestamp."""
    if not isinstance(value, datetime):
        raise TypeError("Audit timestamp must be a datetime")

    if value.tzinfo is None:
        value = value.replace(tzinfo=timezone.utc)
    else:
        value = value.astimezone(timezone.utc)

    return value.isoformat()


def _entry_payload(
    actor_id: int | None,
    action: str,
    entity_type: str,
    entity_id: str | int,
    details: Any,
    previous_hash: str,
    created_at: datetime,
) -> dict:
    """Build the exact payload used to calculate an entry hash."""
    return {
        "actor_id": actor_id,
        "action": action,
        "entity_type": entity_type,
        "entity_id": str(entity_id),
        "details": details,
        "previous_hash": previous_hash,
        "created_at": normalized_timestamp(created_at),
    }


def _calculate_hash(payload: dict) -> str:
    """Return the SHA-256 digest of a canonical audit payload."""
    serialized = canonical_json(payload).encode("utf-8")
    return hashlib.sha256(serialized).hexdigest()


def append_audit(
    db: Session,
    actor_id: int | None,
    action: str,
    entity_type: str,
    entity_id: str | int,
    details: dict | None = None,
) -> AuditLog:
    """Append an audit entry linked to the preceding entry.

    The caller is responsible for committing or rolling back the
    surrounding database transaction.
    """
    if not action or not action.strip():
        raise ValueError("Audit action cannot be empty")

    if not entity_type or not entity_type.strip():
        raise ValueError("Audit entity type cannot be empty")

    audit_details = details if details is not None else {}

    if not isinstance(audit_details, dict):
        raise TypeError("Audit details must be a dictionary")

    # Validate serialization before adding the database row.
    details_json = canonical_json(audit_details)

    previous = db.scalar(
        select(AuditLog)
        .order_by(AuditLog.id.desc())
        .limit(1)
    )

    previous_hash = previous.entry_hash if previous else GENESIS_HASH

    created_at = datetime.now(timezone.utc)

    payload = _entry_payload(
        actor_id=actor_id,
        action=action,
        entity_type=entity_type,
        entity_id=entity_id,
        details=audit_details,
        previous_hash=previous_hash,
        created_at=created_at,
    )

    entry_hash = _calculate_hash(payload)

    row = AuditLog(
        actor_id=actor_id,
        action=action,
        entity_type=entity_type,
        entity_id=str(entity_id),
        details_json=details_json,
        previous_hash=previous_hash,
        entry_hash=entry_hash,
        created_at=created_at,
    )

    db.add(row)
    db.flush()

    return row


def verify_chain(rows) -> dict:
    """Verify audit entries in chronological order.

    Pass the complete chain starting with its genesis entry, ordered
    by ascending ID. A filtered subset is not independently verifiable
    as a complete chain.
    """
    previous_hash = GENESIS_HASH
    checked = 0
    last_id = None

    for row in rows:
        last_id = getattr(row, "id", None)

        stored_previous_hash = getattr(row, "previous_hash", None)
        stored_entry_hash = getattr(row, "entry_hash", None)

        if stored_previous_hash != previous_hash:
            return {
                "valid": False,
                "checked_entries": checked,
                "broken_at_id": last_id,
                "reason": "previous_hash_mismatch",
            }

        try:
            details = json.loads(row.details_json or "{}")

            payload = _entry_payload(
                actor_id=row.actor_id,
                action=row.action,
                entity_type=row.entity_type,
                entity_id=row.entity_id,
                details=details,
                previous_hash=stored_previous_hash,
                created_at=row.created_at,
            )

            expected_hash = _calculate_hash(payload)

        except (TypeError, ValueError, AttributeError, OverflowError):
            return {
                "valid": False,
                "checked_entries": checked,
                "broken_at_id": last_id,
                "reason": "malformed_entry",
            }

        if not isinstance(stored_entry_hash, str) or not hmac.compare_digest(
            expected_hash, stored_entry_hash
        ):
            return {
                "valid": False,
                "checked_entries": checked,
                "broken_at_id": last_id,
                "reason": "entry_hash_mismatch",
            }

        previous_hash = stored_entry_hash
        checked += 1

    return {
        "valid": True,
        "checked_entries": checked,
        "head_hash": previous_hash,
        "last_entry_id": last_id,
    }
