from fastapi import HTTPException
from sqlalchemy.orm import Session

from services.api import models


def _parse_category(category: str) -> models.ConsentCategory:
    try:
        return models.ConsentCategory(category)
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid consent category")


def _parse_scope(scope: str) -> models.ConsentScope:
    try:
        return models.ConsentScope(scope)
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid consent scope")


def upsert_consent(*, db: Session, user_id: str, category: str, scope: str, granted: bool) -> models.Consent:
    cat = _parse_category(category)
    sc = _parse_scope(scope)

    latest = (
        db.query(models.Consent)
        .filter(models.Consent.user_id == user_id, models.Consent.category == cat, models.Consent.scope == sc)
        .order_by(models.Consent.version.desc())
        .first()
    )
    next_version = 1 if not latest else latest.version + 1
    c = models.Consent(user_id=user_id, category=cat, scope=sc, version=next_version, granted=granted)
    db.add(c)
    return c


def has_active_consent(*, db: Session, user_id: str, category: models.ConsentCategory, scope: models.ConsentScope) -> bool:
    latest = (
        db.query(models.Consent)
        .filter(models.Consent.user_id == user_id, models.Consent.category == category, models.Consent.scope == scope)
        .order_by(models.Consent.version.desc())
        .first()
    )
    return bool(latest and latest.granted)
