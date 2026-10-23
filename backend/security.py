"""Cookie sessions, input boundaries, and membership authorization."""

from datetime import datetime, timedelta, timezone
from typing import Annotated

import bcrypt
import jwt
from fastapi import Depends, HTTPException, Request
from jwt import InvalidTokenError
from pydantic import BaseModel, ConfigDict, Field, field_validator
from sqlalchemy.orm import Session

from database import get_db
from models import Membership, User

DB = Annotated[Session, Depends(get_db)]


class InputModel(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)


class Credentials(InputModel):
    email: str = Field(min_length=3, max_length=254, pattern=r"^[^\s@]+@[^\s@]+\.[^\s@]+$")
    # Do not strip password whitespace; bcrypt counts UTF-8 bytes, not characters.
    password: str = Field(min_length=1, max_length=72)

    @field_validator("email")
    @classmethod
    def normalize_email(cls, value):
        return value.strip().lower()

    @field_validator("password", mode="before")
    @classmethod
    def password_bytes(cls, value):
        if not isinstance(value, str) or len(value.encode()) > 72:
            raise ValueError("Password must be at most 72 UTF-8 bytes")
        return value

    model_config = ConfigDict(extra="forbid", str_strip_whitespace=False)


class Registration(Credentials):
    password: str = Field(min_length=8, max_length=72)
    name: str = Field(min_length=1, max_length=100)
    role: str | None = Field(default=None, max_length=100)

    @field_validator("name")
    @classmethod
    def clean_name(cls, value):
        if not value.strip():
            raise ValueError("Name is required")
        return value.strip()


def hash_password(password):
    return bcrypt.hashpw(password.encode(), bcrypt.gensalt()).decode()


def verify_password(password, password_hash):
    try:
        return bcrypt.checkpw(password.encode(), password_hash.encode())
    except (ValueError, TypeError):
        return False


def set_session(response, user_id, settings):
    token = jwt.encode(
        {"sub": user_id, "exp": datetime.now(timezone.utc) + timedelta(hours=24)},
        settings.secret_key,
        algorithm="HS256",
    )
    response.set_cookie(
        "access_token",
        token,
        httponly=True,
        secure=settings.secure_cookies,
        samesite="lax",
        max_age=86400,
        path="/",
    )


def current_user(request: Request, db: DB):
    try:
        payload = jwt.decode(
            request.cookies.get("access_token", ""),
            request.app.state.settings.secret_key,
            algorithms=["HS256"],
            options={"require": ["exp", "sub"]},
        )
        user = db.get(User, payload["sub"])
    except (InvalidTokenError, ValueError, TypeError):
        user = None
    if user is None:
        raise HTTPException(401, "Not authenticated")
    return user


CurrentUser = Annotated[User, Depends(current_user)]


def require_member(db, user_id, workspace_id, owner=False):
    membership = db.get(Membership, (workspace_id, user_id))
    if membership is None:
        # Do not reveal whether a guessed workspace exists.
        raise HTTPException(404, "Workspace not found")
    if owner and membership.role != "owner":
        raise HTTPException(403, "Workspace owner required")
    return membership


def as_utc(value):
    """Legacy timestamps are stored as UTC without a database timezone."""
    return value.replace(tzinfo=timezone.utc) if value is not None else None
