"""Session-bound GitHub App device authorization; no browser credential input."""

import re
from datetime import timedelta
from uuid import uuid4

from fastapi import APIRouter, HTTPException, Request
from pydantic import Field

import github_app
from api.repositories import queue
from collaboration import lock_workspace, record_activity
from models import GitHubAuthorization, RepositoryConnection, utc_now
from repositories import connection_out
from security import DB, CurrentUser, InputModel

router = APIRouter()


class Start(InputModel):
    repository: str = Field(min_length=3, max_length=150)
    installation_id: int = Field(ge=1, le=9223372036854775807)


def configured(request):
    if not request.app.state.settings.github_app_enabled:
        raise HTTPException(503, "GitHub App authorization is disabled")
    return request.app.state.settings


@router.post("/workspaces/{workspace_id}/github-authorizations", status_code=202)
def start(workspace_id: str, payload: Start, user: CurrentUser, db: DB, request: Request):
    settings = configured(request)
    lock_workspace(db, workspace_id, user.id, owner=True)
    if not re.fullmatch(
        r"[A-Za-z0-9][A-Za-z0-9-]{0,38}/[A-Za-z0-9_.-]{1,100}", payload.repository
    ) or payload.repository.split("/")[1] in {".", ".."}:
        raise HTTPException(422, "Use owner/repository")
    if db.query(RepositoryConnection).filter_by(workspace_id=workspace_id).count() >= 20:
        raise HTTPException(409, "Workspace connection limit reached")
    if (
        db.query(GitHubAuthorization)
        .filter(
            GitHubAuthorization.workspace_id == workspace_id,
            GitHubAuthorization.created_at > utc_now() - timedelta(hours=1),
        )
        .count()
        >= 5
    ):
        raise HTTPException(429, "At most five authorization starts per workspace per hour")
    row = GitHubAuthorization(
        id=str(uuid4()),
        workspace_id=workspace_id,
        creator_id=user.id,
        repository=payload.repository,
        installation_id=payload.installation_id,
        state="pending",
        interval=5,
        next_poll_at=utc_now() + timedelta(minutes=15),
        expires_at=utc_now() + timedelta(minutes=15),
    )
    db.add(row)
    db.commit()
    try:
        value = github_app.request_json(
            "/login/device/code", data={"client_id": settings.github_app_client_id}
        )
        device, code = value["device_code"], value["user_code"]
        if (
            not isinstance(device, str)
            or not 1 <= len(device) <= 2048
            or not isinstance(code, str)
            or not re.fullmatch(r"[A-Z0-9-]{4,20}", code)
        ):
            raise ValueError
        expires = min(900, max(30, int(value["expires_in"])))
        interval = min(60, max(5, int(value["interval"])))
    except Exception:
        lock_workspace(db, workspace_id, user.id, owner=True)
        row.state, row.error_code = "failed", "authorization_start_failed"
        db.commit()
        raise HTTPException(502, "GitHub authorization could not start") from None
    lock_workspace(db, workspace_id, user.id, owner=True)
    row.device_secret = github_app.seal(settings, {"device_code": device, "user_code": code})
    row.expires_at, row.interval = utc_now() + timedelta(seconds=expires), interval
    row.next_poll_at = utc_now() + timedelta(seconds=interval)
    db.commit()
    return {
        "id": row.id,
        "state": "pending",
        "user_code": code,
        "verification_uri": "https://github.com/login/device",
        "interval": interval,
        "expires_in": expires,
    }


@router.post("/workspaces/{workspace_id}/github-authorizations/{authorization_id}/complete")
def complete(workspace_id: str, authorization_id: str, user: CurrentUser, db: DB, request: Request):
    settings = configured(request)
    lock_workspace(db, workspace_id, user.id, owner=True)
    row = (
        db.query(GitHubAuthorization)
        .filter_by(id=authorization_id, workspace_id=workspace_id, creator_id=user.id)
        .first()
    )
    if not row:
        raise HTTPException(404, "Authorization not found")
    if row.state != "pending":
        return {"state": row.state, "error_code": row.error_code}
    if row.expires_at <= utc_now():
        row.state, row.device_secret = "expired", None
        db.commit()
        return {"state": "expired"}
    if row.next_poll_at > utc_now():
        raise HTTPException(429, "Wait for the device polling interval")
    secret = github_app.unseal(settings, row.device_secret)
    row.next_poll_at = (
        row.expires_at
    )  # exclude competing exchanges; interrupted requests expire visibly
    db.commit()
    try:
        value = github_app.request_json(
            "/login/oauth/access_token",
            data={
                "client_id": settings.github_app_client_id,
                "device_code": secret["device_code"],
                "grant_type": "urn:ietf:params:oauth:grant-type:device_code",
            },
        )
        pending = value.get("error") in {"authorization_pending", "slow_down"}
        if pending:
            credentials = None
        else:
            credentials, expires = github_app.token_payload(value)
            rid = github_app.verified_repository(
                settings, credentials["access_token"], row.installation_id, row.repository
            )
    except Exception:
        lock_workspace(db, workspace_id, user.id, owner=True)
        row.state, row.device_secret, row.error_code = "failed", None, "authorization_failed"
        db.commit()
        return {"state": "failed", "error_code": "authorization_failed"}
    lock_workspace(db, workspace_id, user.id, owner=True)
    db.refresh(row)
    if row.state != "pending" or row.expires_at <= utc_now():
        row.state, row.device_secret = "expired", None
        db.commit()
        return {"state": "expired"}
    if pending:
        row.interval = min(60, row.interval + (5 if value["error"] == "slow_down" else 0))
        row.next_poll_at = utc_now() + timedelta(seconds=row.interval)
        db.commit()
        return {"state": "pending", "interval": row.interval}
    if db.query(RepositoryConnection).filter_by(workspace_id=workspace_id).count() >= 20:
        row.state, row.device_secret, row.error_code = "failed", None, "connection_capacity"
        db.commit()
        return {"state": "failed", "error_code": "connection_capacity"}
    existing = (
        db.query(RepositoryConnection)
        .filter_by(workspace_id=workspace_id, repository=row.repository, active=True)
        .first()
    )
    if existing:
        from github_app import revoke_connection

        revoke_connection(db, existing)
    connection = RepositoryConnection(
        id=str(uuid4()),
        workspace_id=workspace_id,
        creator_id=user.id,
        repository=row.repository,
        auth_mode="github_app_user",
        installation_id=row.installation_id,
        repository_id=rid,
        credential=github_app.seal(settings, credentials),
        credential_expires_at=expires,
        access_verified_until=utc_now() + timedelta(minutes=10),
        active=True,
        version=1,
    )
    db.add(connection)
    db.flush()
    queue(db, connection, user)
    row.state, row.device_secret = "completed", None
    record_activity(
        db, workspace_id, user, "Authorized selected read-only GitHub App repository access"
    )
    db.commit()
    return {"state": "completed", "connection": connection_out(db, connection)}


@router.get("/workspaces/{workspace_id}/github-authorizations")
def pending(workspace_id: str, user: CurrentUser, db: DB, request: Request):
    settings = configured(request)
    lock_workspace(db, workspace_id, user.id, owner=True)
    rows = (
        db.query(GitHubAuthorization)
        .filter_by(workspace_id=workspace_id, creator_id=user.id, state="pending")
        .order_by(GitHubAuthorization.created_at.desc())
        .limit(5)
        .all()
    )
    result = []
    for row in rows:
        if row.expires_at <= utc_now():
            row.state, row.device_secret = "expired", None
        elif row.device_secret:
            try:
                code = github_app.unseal(settings, row.device_secret)["user_code"]
                result.append(
                    {
                        "id": row.id,
                        "repository": row.repository,
                        "state": "pending",
                        "user_code": code,
                        "verification_uri": "https://github.com/login/device",
                        "interval": row.interval,
                    }
                )
            except Exception:
                row.state, row.device_secret, row.error_code = (
                    "failed",
                    None,
                    "credential_unavailable",
                )
    db.commit()
    return {"items": result}


class VerifyAccess(InputModel):
    version: int = Field(ge=1)


@router.post("/workspaces/{workspace_id}/connections/{connection_id}/verify")
def verify_access(
    workspace_id: str,
    connection_id: str,
    payload: VerifyAccess,
    user: CurrentUser,
    db: DB,
    request: Request,
):
    settings = configured(request)
    lock_workspace(db, workspace_id, user.id, owner=True)
    row = (
        db.query(RepositoryConnection)
        .filter_by(id=connection_id, workspace_id=workspace_id)
        .first()
    )
    if not row:
        raise HTTPException(404, "Connection not found")
    if (
        row.version != payload.version
        or not row.active
        or row.auth_mode != "github_app_user"
        or row.creator_id != user.id
    ):
        raise HTTPException(409, "Connection changed or requires renewed owner authorization")
    if not row.credential_expires_at or row.credential_expires_at <= utc_now() + timedelta(
        seconds=60
    ):
        raise HTTPException(409, "Sync the connection to renew its grant first")
    credentials = github_app.unseal(settings, row.credential)
    expected_id, installation_id, repository = (
        row.repository_id,
        row.installation_id,
        row.repository,
    )
    db.commit()
    request.app.state.auth_limiter.check("github-permission-budget", limit=20)
    try:
        verified = github_app.verified_repository(
            settings, credentials["access_token"], installation_id, repository
        )
        valid = verified == expected_id
    except Exception:
        valid = False
    lock_workspace(db, workspace_id, user.id, owner=True)
    db.refresh(row)
    if row.version != payload.version or not row.active or row.creator_id != user.id:
        raise HTTPException(409, "Connection changed during verification")
    if not valid:
        github_app.revoke_connection(db, row)
        db.commit()
        raise HTTPException(409, "Private access could not be verified; connection revoked")
    row.access_verified_until = utc_now() + timedelta(minutes=10)
    record_activity(db, workspace_id, user, "Revalidated selected read-only GitHub App permission")
    db.commit()
    return connection_out(db, row)
