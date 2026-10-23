from uuid import uuid4

from fastapi import APIRouter, HTTPException, Request, Response
from pydantic import ConfigDict, Field, field_validator
from sqlalchemy import func
from sqlalchemy.exc import IntegrityError

from api.workspaces import create_workspace
from models import AuthSession, RecoveryRequest, User, UserCredential, utc_now
from recovery import consume, lock_user
from security import (
    DB,
    Credentials,
    CurrentUser,
    InputModel,
    Registration,
    as_utc,
    hash_password,
    session_from_request,
    set_session,
    verify_password,
)

router = APIRouter()


def profile(user):
    return {
        "id": user.id,
        "email": user.email,
        "name": user.name,
        "role": user.role,
        "created_at": as_utc(user.created_at),
        "email_verified": user.email_verified_at is not None,
    }


@router.post("/auth/register", status_code=201)
def register(payload: Registration, request: Request, response: Response, db: DB):
    request.app.state.auth_limiter.check(request.client.host if request.client else "unknown")
    if db.query(User).filter(func.lower(User.email) == payload.email).first():
        raise HTTPException(409, "Email already registered")
    user = User(id=str(uuid4()), email=payload.email, name=payload.name, role=payload.role)
    try:
        db.add(user)
        db.flush()
        db.add(UserCredential(user_id=user.id, password_hash=hash_password(payload.password)))
        create_workspace(db, user, "Personal workspace")
        set_session(response, user.id, request.app.state.settings, db)
        db.commit()
    except IntegrityError:
        db.rollback()
        raise HTTPException(409, "Registration conflicts with an existing account") from None
    return profile(user)


@router.post("/auth/login")
def login(payload: Credentials, request: Request, response: Response, db: DB):
    request.app.state.auth_limiter.check(request.client.host if request.client else "unknown")
    # Existing mixed-case email values remain usable after migration.
    users = db.query(User).filter(func.lower(User.email) == payload.email).all()
    if len(users) != 1:
        raise HTTPException(401, "Invalid credentials")
    user = lock_user(db, users[0].id)
    credential = db.get(UserCredential, user.id)
    if not credential or not verify_password(payload.password, credential.password_hash):
        raise HTTPException(401, "Invalid credentials")
    set_session(response, user.id, request.app.state.settings, db)
    db.commit()
    return {"ok": True}


@router.post("/auth/logout")
def logout(request: Request, response: Response, db: DB):
    session = session_from_request(request, db)
    if session:
        session.revoked_at = utc_now()
        db.commit()
    response.delete_cookie("access_token", path="/")
    return {"ok": True}


@router.get("/me")
def me(user: CurrentUser):
    return profile(user)


@router.post("/auth/logout-all")
def logout_all(user: CurrentUser, response: Response, db: DB):
    db.query(AuthSession).filter(
        AuthSession.user_id == user.id, AuthSession.revoked_at.is_(None)
    ).update({"revoked_at": utc_now()})
    db.commit()
    response.delete_cookie("access_token", path="/")
    return {"ok": True}


class RecoveryEmail(InputModel):
    email: str = Field(min_length=3, max_length=254, pattern=r"^[^\s@]+@[^\s@]+\.[^\s@]+$")


class RecoveryToken(InputModel):
    token: str = Field(min_length=40, max_length=100, pattern=r"^[A-Za-z0-9_-]+$")


class ResetPassword(RecoveryToken):
    password: str = Field(min_length=8, max_length=72)

    @field_validator("password", mode="before")
    @classmethod
    def bytes_limit(cls, value):
        if not isinstance(value, str) or len(value.encode()) > 72:
            raise ValueError("Password must be at most 72 UTF-8 bytes")
        return value

    model_config = ConfigDict(extra="forbid", str_strip_whitespace=False)


def request_recovery(email, purpose, request, db):
    email = email.strip().lower()
    limiter = request.app.state.auth_limiter
    limiter.check("recovery-peer:" + (request.client.host if request.client else "unknown"))
    limiter.check("recovery-email:" + email, limit=3)
    # No filesystem delivery or password hashing occurs on the request path.
    # Unknown addresses receive the same response and queue shape.
    if request.app.state.settings.recovery_outbox_path:
        users = db.query(User).filter(func.lower(User.email) == email).all()
        user = users[0] if len(users) == 1 else None
        if user:
            lock_user(db, user.id)
        db.add(
            RecoveryRequest(
                id=str(uuid4()), user_id=user.id if user else None, purpose=purpose, state="queued"
            )
        )
        db.commit()
    return {
        "message": "If this account is eligible, recovery instructions will be delivered through the configured channel."
    }


@router.post("/auth/recovery/request", status_code=202)
def reset_request(payload: RecoveryEmail, request: Request, db: DB):
    return request_recovery(payload.email, "reset", request, db)


@router.post("/auth/verification/request", status_code=202)
def verification_request(user: CurrentUser, request: Request, db: DB):
    return request_recovery(user.email, "verify", request, db)


@router.post("/auth/recovery/complete")
def reset_complete(payload: ResetPassword, request: Request, response: Response, db: DB):
    request.app.state.auth_limiter.check(
        "token-peer:" + (request.client.host if request.client else "unknown")
    )
    consume(db, payload.token, "reset", payload.password)
    response.delete_cookie("access_token", path="/")
    return {"ok": True}


@router.post("/auth/verification/complete")
def verification_complete(payload: RecoveryToken, request: Request, db: DB):
    request.app.state.auth_limiter.check(
        "token-peer:" + (request.client.host if request.client else "unknown")
    )
    consume(db, payload.token, "verify")
    return {"ok": True}
