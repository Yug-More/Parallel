"""GitHub App user authorization; fixed hosts, encrypted expiring grants, GET data.

Only authentication endpoints accept POST. Imported content never chooses a URL.
This module does not create/install apps, change permissions, or write repository data.
"""

import json
import ssl
import urllib.error
import urllib.parse
import urllib.request
from datetime import timedelta

import certifi
from cryptography.fernet import Fernet

from knowledge_lifecycle import advance
from models import Membership, RepositoryConnection, RepositorySync, utc_now
from repositories import NoRedirect, SyncError, fetch_repository


def seal(settings, payload):
    return (
        Fernet(settings.credential_encryption_key.encode())
        .encrypt(json.dumps(payload).encode())
        .decode()
    )


def unseal(settings, ciphertext):
    try:
        return json.loads(
            Fernet(settings.credential_encryption_key.encode()).decrypt(ciphertext.encode())
        )
    except Exception:
        raise SyncError("credential_unavailable") from None


def request_json(path, *, token=None, data=None):
    if data is not None and path not in {"/login/device/code", "/login/oauth/access_token"}:
        raise SyncError("endpoint_forbidden")
    host = "https://github.com" if data is not None else "https://api.github.com"
    if not path.startswith("/") or path.startswith("//") or "\\" in path:
        raise SyncError("endpoint_forbidden")
    headers = {
        "Accept": "application/json" if data is not None else "application/vnd.github+json",
        "User-Agent": "Parallel-workspace",
        "X-GitHub-Api-Version": "2026-03-10",
    }
    if token:
        headers["Authorization"] = "Bearer " + token
    body = urllib.parse.urlencode(data).encode() if data is not None else None
    req = urllib.request.Request(
        host + path, data=body, headers=headers, method="POST" if data is not None else "GET"
    )
    try:
        opener = urllib.request.build_opener(
            NoRedirect(),
            urllib.request.HTTPSHandler(context=ssl.create_default_context(cafile=certifi.where())),
        )
        with opener.open(req, timeout=8) as response:
            raw = response.read(1_000_001)
            if len(raw) > 1_000_000:
                raise SyncError("response_limit")
            return json.loads(raw)
    except urllib.error.HTTPError as exc:
        if exc.code in {401, 404}:
            raise SyncError("repository_access_lost") from None
        if exc.code in {403, 429}:
            try:
                delay = max(60, int(exc.headers.get("Retry-After", "60")))
            except ValueError:
                delay = 60
            raise SyncError("rate_limited", delay if delay <= 86400 else None) from None
        raise SyncError("github_http_error") from None
    except (OSError, ValueError):
        raise SyncError("github_unavailable", 60) from None


def verified_repository(settings, token, installation_id, repository, read=None):
    read = read or request_json
    found = None
    for page in range(1, 6):
        data = read(f"/user/installations?per_page=100&page={page}", token=token)
        installations = data.get("installations", [])
        found = next((i for i in installations if i.get("id") == installation_id), None)
        if found or len(installations) < 100:
            break
    if (
        not found
        or found.get("app_id") != settings.github_app_id
        or found.get("suspended_at")
        or found.get("repository_selection") != "selected"
    ):
        raise SyncError("selected_installation_required")
    permissions = found.get("permissions", {})
    if (
        not permissions
        or any(
            k not in {"metadata", "issues", "pull_requests"} or v != "read"
            for k, v in permissions.items()
        )
        or permissions.get("issues") != "read"
        or permissions.get("pull_requests") != "read"
    ):
        raise SyncError("read_only_permissions_required")
    for page in range(1, 6):
        data = read(
            f"/user/installations/{installation_id}/repositories?per_page=100&page={page}",
            token=token,
        )
        repos = data.get("repositories", [])
        for repo in repos:
            if repo.get("full_name", "").casefold() == repository.casefold():
                if not isinstance(repo.get("id"), int) or repo["id"] <= 0:
                    raise SyncError("invalid_response")
                return repo["id"]
        if len(repos) < 100:
            break
    raise SyncError("repository_access_lost")


def token_payload(value):
    if (
        value.get("token_type", "").lower() != "bearer"
        or not isinstance(value.get("access_token"), str)
        or not 1 <= len(value["access_token"]) <= 2048
        or not isinstance(value.get("refresh_token"), str)
        or not 1 <= len(value["refresh_token"]) <= 2048
    ):
        raise SyncError("expiring_token_required")
    expires = value.get("expires_in")
    if not isinstance(expires, int) or not 60 <= expires <= 28800:
        raise SyncError("expiring_token_required")
    return {
        "access_token": value["access_token"],
        "refresh_token": value["refresh_token"],
    }, utc_now() + timedelta(seconds=expires)


def revoke_connection(db, row):
    if row.active:
        advance(db, row.workspace_id)
        row.active, row.version = False, row.version + 1
    row.credential = row.credential_expires_at = row.access_verified_until = None
    db.query(RepositorySync).filter(
        RepositorySync.connection_id == row.id, RepositorySync.state.in_(["queued", "running"])
    ).update(
        {"state": "cancelled", "lease_token": None, "lease_until": None, "completed_at": utc_now()}
    )


def expire_workspace(db, wid):
    """Read-time fail closed; caller transaction owns workspace serialization.

    A read rollback does not restore visibility: every later request checks again.
    The worker persists expiry independently. No provider request occurs here.
    """
    rows = (
        db.query(RepositoryConnection)
        .filter_by(workspace_id=wid, active=True, auth_mode="github_app_user")
        .all()
    )
    invalid = [
        r
        for r in rows
        if not r.access_verified_until
        or r.access_verified_until <= utc_now()
        or not (m := db.get(Membership, (wid, r.creator_id)))
        or m.role != "owner"
    ]
    if invalid:
        from collaboration import lock_workspace

        lock_workspace(db, wid)
        for row in invalid:
            db.refresh(row)
            member = db.get(Membership, (wid, row.creator_id), populate_existing=True)
            if row.active and (
                not row.access_verified_until
                or row.access_verified_until <= utc_now()
                or not member
                or member.role != "owner"
            ):
                revoke_connection(db, row)
        db.flush()


def private_fetch(settings, connection, read=None):
    read = read or request_json
    credentials = unseal(settings, connection.credential)
    expires = connection.credential_expires_at
    if not expires or expires <= utc_now() + timedelta(seconds=60):
        value = read(
            "/login/oauth/access_token",
            data={
                "client_id": settings.github_app_client_id,
                "client_secret": settings.github_app_client_secret,
                "grant_type": "refresh_token",
                "refresh_token": credentials["refresh_token"],
            },
        )
        credentials, expires = token_payload(value)
    token = credentials["access_token"]
    rid = verified_repository(
        settings, token, connection.installation_id, connection.repository, read
    )
    if rid != connection.repository_id:
        raise SyncError("repository_identity_changed")

    # Full bounded pagination, stable upserts and removal invalidation. Each sync
    # revalidates permission; no partially paginated response is committed.
    def paginated(path):
        if "?" not in path:
            metadata = read(path, token=token)
            if metadata.get("id") != rid:
                raise SyncError("repository_identity_changed")
            return {
                **metadata,
                "private": False,
            }  # reuse sanitizer after explicit private authorization
        base = path.split("?", 1)[0]
        items = []
        for page in range(1, 5):
            values = read(
                f"{base}?state=all&sort=updated&direction=desc&per_page=25&page={page}", token=token
            )
            if not isinstance(values, list):
                raise SyncError("invalid_response")
            items.extend(values)
            if len(values) < 25:
                return items
        raise SyncError("pagination_capacity")

    records = fetch_repository(connection.repository, read=paginated, maximum=100)
    records[0]["status"] = "private"  # distinguish imported repository visibility
    return records, seal(settings, credentials), expires


def maintain_private(factory):
    """Renew explicit connections via bounded sync every five minutes."""
    from uuid import uuid4

    from collaboration import lock_workspace

    with factory() as db:
        rows = (
            db.query(RepositoryConnection)
            .filter_by(active=True, auth_mode="github_app_user")
            .order_by(RepositoryConnection.created_at)
            .limit(100)
            .all()
        )
        for row in rows:
            lock_workspace(db, row.workspace_id)
            expire_workspace(db, row.workspace_id)
            db.refresh(row)
            if not row.active:
                continue
            recent = (
                db.query(RepositorySync)
                .filter(
                    RepositorySync.connection_id == row.id,
                    (RepositorySync.state.in_(["queued", "running"]))
                    | (RepositorySync.created_at > utc_now() - timedelta(minutes=5)),
                )
                .first()
            )
            if not recent:
                db.add(
                    RepositorySync(
                        id=str(uuid4()),
                        workspace_id=row.workspace_id,
                        connection_id=row.id,
                        initiator_id=row.creator_id,
                        connection_version=row.version,
                        state="queued",
                        attempt=0,
                        record_count=0,
                    )
                )
        db.commit()
