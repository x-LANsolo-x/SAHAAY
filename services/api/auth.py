import secrets
from datetime import datetime

from fastapi import Depends, HTTPException
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from passlib.context import CryptContext
from sqlalchemy.orm import Session

from services.api.db import get_db
from services.api.models import AuthToken, RoleName, User, UserRole


pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")
security = HTTPBearer(auto_error=False)


def hash_password(password: str) -> str:
    return pwd_context.hash(password)


def verify_password(password: str, password_hash: str) -> bool:
    return pwd_context.verify(password, password_hash)


def create_access_token(*, user_id: str, db: Session) -> str:
    """Creates an opaque bearer token stored in DB.

    Free/portable alternative to JWT when external deps (jose) aren't available.
    """
    token = secrets.token_urlsafe(32)
    db.add(AuthToken(token=token, user_id=user_id))
    return token


def get_current_user(
    creds: HTTPAuthorizationCredentials | None = Depends(security),
    db: Session = Depends(get_db),
) -> User:
    if creds is None:
        raise HTTPException(status_code=401, detail="Not authenticated")
    token = creds.credentials

    auth = db.get(AuthToken, token)
    if not auth or auth.revoked_at is not None:
        raise HTTPException(status_code=401, detail="Invalid token")

    user = db.get(User, auth.user_id)
    if not user or not user.is_active:
        raise HTTPException(status_code=401, detail="User not found or inactive")
    return user


def require_role(role: RoleName):
    def _dep(user: User = Depends(get_current_user), db: Session = Depends(get_db)) -> User:
        exists = (
            db.query(UserRole)
            .filter(UserRole.user_id == user.id, UserRole.role_name == role)
            .first()
        )
        if not exists:
            raise HTTPException(status_code=403, detail="Forbidden")
        return user

    return _dep
