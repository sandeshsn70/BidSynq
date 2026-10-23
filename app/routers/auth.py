from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app import ratelimit
from app.audit import append_audit
from app.config import settings
from app.database import get_db
from app.models import User
from app.schemas import LoginIn, RegisterIn, TokenOut, UserOut
from app.security import (
    burn_password_check,
    create_access_token,
    get_current_user,
    hash_password,
    verify_password,
)

router = APIRouter(prefix="/auth", tags=["auth"])


@router.post("/register", response_model=UserOut, status_code=201)
def register(data: RegisterIn, db: Session = Depends(get_db)):
    role = data.role.lower().strip()
    allowed_roles = {"buyer", "supplier"}
    if settings.bidsynq_allow_admin_registration:
        allowed_roles.add("admin")
    if role not in allowed_roles:
        raise HTTPException(400, f"Role must be one of: {', '.join(sorted(allowed_roles))}")

    email = str(data.email).strip().lower()
    if db.scalar(select(User.id).where(func.lower(User.email) == email)):
        raise HTTPException(409, "Email is already registered")

    user = User(
        name=data.name.strip(),
        email=email,
        password_hash=hash_password(data.password),
        role=role,
        company_name=data.company_name.strip(),
    )
    try:
        db.add(user)
        db.flush()
        append_audit(db, user.id, "user.registered", "user", user.id, {"role": role})
        db.commit()
    except IntegrityError:  # two simultaneous registrations with the same email
        db.rollback()
        raise HTTPException(409, "Email is already registered") from None
    except Exception:
        db.rollback()
        raise
    db.refresh(user)
    return user


@router.post("/login", response_model=TokenOut)
def login(data: LoginIn, db: Session = Depends(get_db)):
    email = str(data.email).strip().lower()
    limiter_key = f"login:{email}"
    if ratelimit.is_blocked(limiter_key):
        raise HTTPException(429, "Too many failed sign-in attempts. Please wait a few minutes and try again.")

    user = db.scalar(select(User).where(func.lower(User.email) == email))
    if user is None:
        burn_password_check(data.password)
    if user is None or not verify_password(data.password, user.password_hash):
        ratelimit.record_failure(limiter_key)
        raise HTTPException(401, "Incorrect email or password", headers={"WWW-Authenticate": "Bearer"})

    ratelimit.reset(limiter_key)
    return TokenOut(access_token=create_access_token(user.id))


@router.get("/me", response_model=UserOut)
def me(user: User = Depends(get_current_user)):
    return user
