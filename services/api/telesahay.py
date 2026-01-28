from services.api import models


def render_sms_summary(items: list[dict], advice: str | None) -> str:
    """Generate SMS-friendly prescription summary (160-300 chars)."""
    parts = []

    if items:
        drugs = ", ".join([f"{i.get('drug', 'med')} {i.get('dose', '')}" for i in items[:3]])
        parts.append(f"Rx: {drugs}")

    if advice:
        parts.append(f"Advice: {advice[:80]}")

    summary = ". ".join(parts)

    # Ensure length constraint 160-300 chars
    if len(summary) < 160:
        # Pad with generic message
        padding = ". Follow instructions as prescribed. Contact your doctor if symptoms persist. Take medication regularly."
        summary += padding
        # If still short, add more filler
        while len(summary) < 160:
            summary += " Please consult if symptoms worsen."
            if len(summary) >= 160:
                break

    if len(summary) > 300:
        summary = summary[:297] + "..."

    return summary


def enqueue_message(*, db, user_id: str, channel: str, payload: str):
    """Enqueue a message in the message_queue table."""
    msg = models.MessageQueue(user_id=user_id, channel=channel, payload=payload)
    db.add(msg)
    return msg


VALID_TRANSITIONS = {
    models.TeleRequestStatus.requested: [models.TeleRequestStatus.scheduled],
    models.TeleRequestStatus.scheduled: [models.TeleRequestStatus.in_progress],
    models.TeleRequestStatus.in_progress: [models.TeleRequestStatus.completed],
    models.TeleRequestStatus.completed: [],
}


def validate_status_transition(current: models.TeleRequestStatus, new: models.TeleRequestStatus) -> bool:
    """Returns True if transition is valid."""
    return new in VALID_TRANSITIONS.get(current, [])
