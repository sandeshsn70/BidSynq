"""Password hashing, JWT handling and role-based access dependencies.

Hashes are standard bcrypt (``$2b$...``), identical to what passlib produced in
earlier versions, so existing users keep their passwords.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from functools import lru_cache

import bcrypt
import jwt
from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.orm import Session

from app.config import settings
from app.database import get_db
from app.models import User

ALGORITHM = "HS256"
bearer_scheme = HTTPBearer(auto_error=False)


def _prepare(password: str) -> bytes:
    # bcrypt only uses the first 72 bytes; truncating explicitly keeps behaviour
    # identical to earlier versions and avoids errors with newer bcrypt releases.
    return password.encode("utf-8")[:72]


def hash_password(password: str) -> str:
    return bcrypt.hashpw(_prepare(password), bcrypt.gensalt()).decode("ascii")


def verify_password(password: str, hashed: str) -> bool:
    try:
        return bcrypt.checkpw(_prepare(password), hashed.encode("utf-8"))
    except (ValueError, TypeError, AttributeError):
        return False


@lru_cache(maxsize=1)
def _dummy_hash() -> str:
    return hash_password("bidsynq-timing-equaliser")


def burn_password_check(password: str) -> None:
    """Spend the same time as a real check so unknown emails are not detectable by timing."""
    verify_password(password, _dummy_hash())


def create_access_token(user_id: int) -> str:
    now = datetime.now(timezone.utc)
    payload = {
        "sub": str(user_id),
        "iat": int(now.timestamp()),
        "exp": int((now + timedelta(minutes=settings.access_token_minutes)).timestamp()),
    }
    return jwt.encode(payload, settings.secret_key, algorithm=ALGORITHM)


def _unauthorized(detail: str) -> HTTPException:
    return HTTPException(status.HTTP_401_UNAUTHORIZED, detail, headers={"WWW-Authenticate": "Bearer"})


def decode_access_token(token: str) -> int:
    try:
        payload = jwt.decode(
            token,
            settings.secret_key,
            algorithms=[ALGORITHM],
            options={"require": ["exp", "sub"]},
            leeway=10,
        )
    except jwt.PyJWTError:
        raise _unauthorized("Invalid or expired access token")
    subject = payload.get("sub")
    if not isinstance(subject, str) or not subject.isdigit():
        raise _unauthorized("Invalid access token")
    return int(subject)


def get_current_user(
    credentials: HTTPAuthorizationCredentials | None = Depends(bearer_scheme),
    db: Session = Depends(get_db),
) -> User:
    if credentials is None:
        raise _unauthorized("Authentication required")
    user = db.get(User, decode_access_token(credentials.credentials))
    if user is None:
        raise _unauthorized("User not found")
    return user


def require_roles(*roles: str):
    """Restrict an endpoint to users with the given roles (checked on the server, from the database)."""

    def checker(user: User = Depends(get_current_user)) -> User:
        if user.role not in roles:
            raise HTTPException(status.HTTP_403_FORBIDDEN, "Insufficient permissions")
        return user

    return checker
