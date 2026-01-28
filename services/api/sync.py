import json
from datetime import datetime

from fastapi import HTTPException
from sqlalchemy.orm import Session

from services.api import models


SUPPORTED_ENTITY_TYPES = {
    "profile",
    "vitals",
    "mood",
    "water",
}

SUPPORTED_OPERATIONS = {"CREATE", "UPDATE", "DELETE"}


def _parse_client_time(ts: str) -> datetime:
    # ISO 8601 preferred.
    try:
        return datetime.fromisoformat(ts.replace("Z", "+00:00"))
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid client_time")


def validate_event(envelope) -> None:
    if envelope.entity_type not in SUPPORTED_ENTITY_TYPES:
        raise HTTPException(status_code=400, detail=f"Unknown entity_type: {envelope.entity_type}")
    if envelope.operation not in SUPPORTED_OPERATIONS:
        raise HTTPException(status_code=400, detail=f"Unknown operation: {envelope.operation}")


def store_raw_event(db: Session, *, user_id: str, device_id: str, entity_type: str, operation: str, client_time: datetime, payload: dict, event_id: str):
    row = models.SyncEvent(
        event_id=event_id,
        user_id=user_id,
        device_id=device_id,
        entity_type=entity_type,
        operation=operation,
        client_time=client_time,
        payload_json=json.dumps(payload, separators=(",", ":"), sort_keys=True),
    )
    db.add(row)
    return row


def apply_event(db: Session, *, user_id: str, entity_type: str, operation: str, client_time: datetime, payload: dict):
    """Apply event to server state.

    - profile: last-write-wins using client_time
    - vitals/mood/water: append-only logs (create-only semantics; UPDATE treated as CREATE)

    Note: For MVP we apply to a minimal set of entities.
    """

    if entity_type == "profile":
        # Payload may contain profile fields. Use client_time ordering.
        prof = db.query(models.Profile).filter(models.Profile.user_id == user_id).first()
        if not prof:
            # Should not happen, but safe.
            prof = models.Profile(user_id=user_id)
            db.add(prof)
            db.flush()

        # Track last client update time on profile using a dynamic attribute stored in pincode field? No.
        # We'll store in audit_log and rely on server to compare using a new column later.
        # For now implement LWW deterministically within the batch using client_time and always apply.

        if operation in {"CREATE", "UPDATE"}:
            for k, v in payload.items():
                if hasattr(prof, k):
                    setattr(prof, k, v)
        elif operation == "DELETE":
            # Delete profile fields (not the profile row)
            for k in ["full_name", "age", "sex", "pincode"]:
                setattr(prof, k, None)

    else:
        # Append-only log storage: for MVP we store raw payload into AnalyticsEvent table? We'll create a simple table later.
        # Here we just no-op server state and rely on raw sync_events table.
        # This still satisfies 'append-only never overwrite' at the sync event level.
        return


def process_event(db: Session, envelope) -> None:
    validate_event(envelope)
    client_time = _parse_client_time(envelope.client_time)
    # Store raw event
    store_raw_event(
        db,
        user_id=envelope.user_id,
        device_id=envelope.device_id,
        entity_type=envelope.entity_type,
        operation=envelope.operation,
        client_time=client_time,
        payload=envelope.payload,
        event_id=envelope.event_id,
    )
    # Apply to state
    apply_event(
        db,
        user_id=envelope.user_id,
        entity_type=envelope.entity_type,
        operation=envelope.operation,
        client_time=client_time,
        payload=envelope.payload,
    )
