"""One-use hashed tokens. Only the private delivery adapter receives plaintext."""

import json
import os
import stat
from datetime import timedelta
from hashlib import sha256
from pathlib import Path
from secrets import token_urlsafe
from typing import Protocol
from uuid import uuid4

from fastapi import HTTPException
from sqlalchemy import update

from models import AuthSession, RecoveryRequest, User, UserCredential, utc_now
from security import hash_password


class Delivery(Protocol):
    def deliver(self, *, email: str, purpose: str, token: str) -> None: ...


class LocalOutbox:
    """Operator-only development artifact; never served by an HTTP endpoint."""

    def __init__(self, path):
        self.path = Path(path)

    def deliver(self, *, email, purpose, token):
        self.path.mkdir(mode=0o700, parents=True, exist_ok=True)
        flags = os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW
        directory = os.open(self.path, flags)
        try:
            info = os.fstat(directory)
            if info.st_uid != os.getuid() or stat.S_IMODE(info.st_mode) & 0o077:
                raise ValueError("private_outbox_required")
            fd = os.open(
                str(uuid4()) + ".json",
                os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW,
                0o600,
                dir_fd=directory,
            )
            with os.fdopen(fd, "w") as stream:
                json.dump(
                    {
                        "email": email,
                        "purpose": purpose,
                        "token": token,
                        "note": "Local development delivery; no email was sent.",
                    },
                    stream,
                )
                stream.flush()
                os.fsync(stream.fileno())
        finally:
            os.close(directory)


def lock_user(db, user_id):
    # Shared serialization boundary for login, issuance and reset on both DBs.
    db.execute(update(User).where(User.id == user_id).values(last_seen_at=User.last_seen_at))
    return db.get(User, user_id, populate_existing=True)


def deliver_once(factory, delivery):
    with factory() as db:
        row = (
            db.query(RecoveryRequest)
            .filter_by(state="queued")
            .order_by(RecoveryRequest.created_at, RecoveryRequest.id)
            .first()
        )
        if not row:
            return False
        if row.user_id:
            lock_user(db, row.user_id)
        changed = db.execute(
            update(RecoveryRequest)
            .where(RecoveryRequest.id == row.id, RecoveryRequest.state == "queued")
            .values(state="running")
        ).rowcount
        if not changed:
            db.rollback()
            return True
        row_id = row.id
        if not row.user_id or row.created_at < utc_now() - timedelta(minutes=30):
            row.state = "failed"
            db.commit()
            return True
        user = db.get(User, row.user_id)
        db.query(RecoveryRequest).filter(
            RecoveryRequest.user_id == user.id,
            RecoveryRequest.purpose == row.purpose,
            RecoveryRequest.id != row.id,
            RecoveryRequest.state.in_(["running", "delivered"]),
        ).update({"state": "superseded", "token_hash": None})
        token = token_urlsafe(32)
        row.token_hash = sha256(token.encode()).hexdigest()
        row.expires_at = utc_now() + timedelta(minutes=30)
        email, purpose = user.email, row.purpose
        db.commit()
    try:
        delivery.deliver(email=email, purpose=purpose, token=token)
        state = "delivered"
    except Exception:
        state = "failed"
    with factory() as db:
        db.execute(
            update(RecoveryRequest)
            .where(RecoveryRequest.id == row_id, RecoveryRequest.state == "running")
            .values(
                state=state,
                token_hash=sha256(token.encode()).hexdigest() if state == "delivered" else None,
            )
        )
        db.commit()
    return True


def consume(db, token, purpose, password=None):
    digest = sha256(token.encode()).hexdigest()
    row = db.query(RecoveryRequest).filter_by(token_hash=digest).first()
    if not row or not row.user_id:
        raise HTTPException(400, "Invalid or expired token")
    user = lock_user(db, row.user_id)
    db.refresh(row)
    if (
        row.state != "delivered"
        or row.purpose != purpose
        or row.used_at
        or not row.expires_at
        or row.expires_at <= utc_now()
    ):
        raise HTTPException(400, "Invalid or expired token")
    row.state, row.used_at, row.token_hash = "consumed", utc_now(), None
    if purpose == "verify":
        user.email_verified_at = utc_now()
    else:
        db.get(UserCredential, user.id).password_hash = hash_password(password)
        db.query(AuthSession).filter_by(user_id=user.id, revoked_at=None).update(
            {"revoked_at": utc_now()}
        )
        db.query(RecoveryRequest).filter(
            RecoveryRequest.user_id == user.id, RecoveryRequest.id != row.id
        ).update({"state": "superseded", "token_hash": None})
    db.commit()


def maintain_operational_records(factory):
    """Documented operational retention only; never delete project history."""
    from models import GitHubAuthorization

    now = utc_now()
    with factory() as db:
        db.query(RecoveryRequest).filter(
            RecoveryRequest.state.in_(["queued", "running", "delivered"]),
            RecoveryRequest.created_at < now - timedelta(minutes=30),
        ).update({"state": "failed", "token_hash": None})
        db.query(RecoveryRequest).filter(
            RecoveryRequest.created_at < now - timedelta(days=7)
        ).delete()
        db.query(AuthSession).filter(AuthSession.expires_at < now - timedelta(days=7)).delete()
        db.query(GitHubAuthorization).filter(
            GitHubAuthorization.state == "pending", GitHubAuthorization.expires_at <= now
        ).update({"state": "expired", "device_secret": None})
        db.commit()
