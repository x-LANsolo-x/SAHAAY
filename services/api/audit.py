import hashlib
import json
from datetime import datetime

from fastapi import Request
from sqlalchemy.orm import Session

from services.api import models


def _canonical(obj) -> str:
    return json.dumps(obj, separators=(",", ":"), sort_keys=True, ensure_ascii=False)


def compute_entry_hash(
    *,
    prev_hash: str | None,
    actor_user_id: str | None,
    action: str,
    entity_type: str,
    entity_id: str | None,
    ip: str | None,
    device_id: str | None,
    ts: datetime,
) -> str:
    payload = {
        "prev_hash": prev_hash,
        "actor_user_id": actor_user_id,
        "action": action,
        "entity_type": entity_type,
        "entity_id": entity_id,
        "ip": ip,
        "device_id": device_id,
        "ts": ts.isoformat(),
    }
    return hashlib.sha256(_canonical(payload).encode("utf-8")).hexdigest()


def write_audit(
    *,
    db: Session,
    request: Request | None,
    actor_user_id: str | None,
    action: str,
    entity_type: str,
    entity_id: str | None,
    device_id: str | None = None,
):
    # Append-only: always insert a new row.
    last = db.query(models.AuditLog).order_by(models.AuditLog.ts.desc()).first()
    prev_hash = last.entry_hash if last else None
    ip = None
    if request is not None and request.client is not None:
        ip = request.client.host
    if device_id is None and request is not None:
        device_id = request.headers.get("X-Device-Id")

    ts = datetime.utcnow()
    entry_hash = compute_entry_hash(
        prev_hash=prev_hash,
        actor_user_id=actor_user_id,
        action=action,
        entity_type=entity_type,
        entity_id=entity_id,
        ip=ip,
        device_id=device_id,
        ts=ts,
    )

    row = models.AuditLog(
        actor_user_id=actor_user_id,
        action=action,
        entity_type=entity_type,
        entity_id=entity_id,
        ip=ip,
        device_id=device_id,
        ts=ts,
        prev_hash=prev_hash,
        entry_hash=entry_hash,
    )
    db.add(row)
    return row


def verify_audit_chain(db: Session) -> bool:
    rows = db.query(models.AuditLog).order_by(models.AuditLog.ts.asc()).all()
    prev = None
    for r in rows:
        expected = compute_entry_hash(
            prev_hash=prev,
            actor_user_id=r.actor_user_id,
            action=r.action,
            entity_type=r.entity_type,
            entity_id=r.entity_id,
            ip=r.ip,
            device_id=r.device_id,
            ts=r.ts,
        )
        if expected != r.entry_hash:
            return False
        prev = r.entry_hash
    return True
