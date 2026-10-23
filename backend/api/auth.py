from uuid import uuid4

from fastapi import APIRouter, HTTPException, Request, Response
from sqlalchemy import func
from sqlalchemy.exc import IntegrityError

from api.workspaces import create_workspace
from models import AuthSession, User, UserCredential, utc_now
from security import (
    DB,
    Credentials,
    CurrentUser,
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
    user = users[0]
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
