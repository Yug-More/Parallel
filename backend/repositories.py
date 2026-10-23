"""Read-only public GitHub adapter with fixed origins and durable bounded jobs."""

import hashlib
import json
import re
import ssl
import time
import urllib.error
import urllib.request
from datetime import timedelta
from uuid import uuid4

import certifi
from fastapi import HTTPException

from collaboration import lock_workspace
from knowledge_lifecycle import advance
from models import ImportedRecord, Membership, RepositoryConnection, RepositorySync, utc_now
from provenance import iso


class SyncError(Exception):
    def __init__(self, code, retry_seconds=None):
        self.code, self.retry_seconds = code, retry_seconds


class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


def github_read(path):
    request = urllib.request.Request(
        "https://api.github.com" + path,
        headers={
            "Accept": "application/vnd.github+json",
            "User-Agent": "Parallel-workspace",
            "X-GitHub-Api-Version": "2026-03-10",
        },
        method="GET",
    )
    try:
        with urllib.request.build_opener(
            NoRedirect(),
            urllib.request.HTTPSHandler(context=ssl.create_default_context(cafile=certifi.where())),
        ).open(request, timeout=8) as response:
            raw = response.read(1_000_001)
            if len(raw) > 1_000_000:
                raise SyncError("response_limit")
            return json.loads(raw)
    except urllib.error.HTTPError as exc:
        if exc.code in {403, 429}:
            try:
                retry = int(exc.headers.get("Retry-After", "0"))
                reset = int(exc.headers.get("X-RateLimit-Reset", "0")) - int(time.time())
            except ValueError:
                retry, reset = 60, 60
            # Never retry sooner than GitHub asks. Values over one day fail visibly.
            delay = max(60, retry, reset)
            raise SyncError("rate_limited", delay if delay <= 86400 else None) from None
        raise SyncError(
            "repository_unavailable" if exc.code in {301, 302, 404, 401} else "github_http_error"
        ) from None
    except (OSError, ValueError):
        raise SyncError("github_unavailable", 60) from None


def safe_text(value, maximum):
    return re.sub(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]", "", str(value or ""))[:maximum]


def fetch_repository(repository, read=github_read, maximum=25):
    """Three GET requests, at most 50 issue/PR records, no arbitrary URLs."""
    path = f"/repos/{repository}"
    metadata = read(path)
    if not isinstance(metadata, dict) or metadata.get("private") is not False:
        raise SyncError("public_repository_required")
    records = [
        {
            "provider_id": "repository",
            "record_type": "repository",
            "title": safe_text(metadata.get("full_name", repository), 200),
            "body": safe_text(metadata.get("description"), 8000),
            "original_url": f"https://github.com/{repository}",
            "status": "public",
        }
    ]
    for category in ["issues", "pulls"]:
        items = read(f"{path}/{category}?state=all&sort=updated&direction=desc&per_page=25&page=1")
        if not isinstance(items, list):
            raise SyncError("invalid_response")
        for item in items[:maximum]:
            if category == "issues" and "pull_request" in item:
                continue
            number = item.get("number")
            if not isinstance(number, int) or number < 1:
                raise SyncError("invalid_response")
            records.append(
                {
                    "provider_id": f"{category}:{number}",
                    "record_type": category,
                    "title": safe_text(item.get("title") or "Untitled", 200),
                    "body": safe_text(item.get("body"), 8000),
                    "original_url": f"https://github.com/{repository}/{'pull' if category == 'pulls' else 'issues'}/{number}",
                    "status": "closed" if item.get("state") == "closed" else "open",
                }
            )
    return records


def external_record(db, workspace_id, record_id):
    item = (
        db.query(ImportedRecord)
        .join(RepositoryConnection, RepositoryConnection.id == ImportedRecord.connection_id)
        .filter(
            ImportedRecord.workspace_id == workspace_id,
            ImportedRecord.id == record_id,
            ImportedRecord.available.is_(True),
            RepositoryConnection.active.is_(True),
        )
        .first()
    )
    if not item:
        raise HTTPException(404, "Source not found in this workspace")
    return {
        "id": item.id,
        "kind": "external",
        "workspace_id": workspace_id,
        "title": item.title,
        "body": item.body,
        "version": item.version,
        "status": item.status,
        "archived": False,
        "authority": "untrusted_import",
        "created_at": iso(item.created_at),
        "updated_at": iso(item.updated_at),
        "original_url": item.original_url,
        "record_type": item.record_type,
        "provider": "github",
        "connection_id": item.connection_id,
    }


def connection_out(db, connection):
    jobs = (
        db.query(RepositorySync)
        .filter_by(connection_id=connection.id)
        .order_by(RepositorySync.created_at.desc(), RepositorySync.id)
        .limit(10)
        .all()
    )
    return {
        "id": connection.id,
        "repository": connection.repository,
        "active": connection.active,
        "version": connection.version,
        "auth_mode": connection.auth_mode,
        "access_verified_until": iso(connection.access_verified_until),
        "provider": "github",
        "created_at": iso(connection.created_at),
        "syncs": [
            {
                "id": job.id,
                "state": job.state,
                "attempt": job.attempt,
                "error_code": job.error_code,
                "record_count": job.record_count,
                "next_attempt_at": iso(job.next_attempt_at),
                "created_at": iso(job.created_at),
                "completed_at": iso(job.completed_at),
            }
            for job in jobs
        ],
    }


def authorized(db, job, connection):
    member = db.get(Membership, (job.workspace_id, job.initiator_id))
    return (
        connection.active
        and connection.version == job.connection_version
        and member
        and member.role == "owner"
        and (
            connection.auth_mode != "github_app_user"
            or (
                (creator := db.get(Membership, (job.workspace_id, connection.creator_id)))
                and creator.role == "owner"
            )
        )
    )


def sync_once(factory, fetch=fetch_repository, settings=None):
    with factory() as db:
        expired = (
            db.query(RepositorySync)
            .filter(RepositorySync.state == "running", RepositorySync.lease_until <= utc_now())
            .order_by(RepositorySync.created_at)
            .first()
        )
        if expired:
            lock_workspace(db, expired.workspace_id)
            db.refresh(expired)
            if expired.state == "running" and expired.lease_until <= utc_now():
                expired.state, expired.error_code = "failed", "lease_expired"
                expired.completed_at = utc_now()
                expired.lease_token = expired.lease_until = None
            db.commit()
            return True
        job = (
            db.query(RepositorySync)
            .filter(RepositorySync.state == "queued", RepositorySync.next_attempt_at <= utc_now())
            .order_by(RepositorySync.created_at, RepositorySync.id)
            .first()
        )
        if not job:
            return False
        lock_workspace(db, job.workspace_id)
        db.refresh(job)
        if job.state != "queued":
            return True
        connection = db.get(RepositoryConnection, job.connection_id)
        if not authorized(db, job, connection):
            job.state, job.completed_at = "cancelled", utc_now()
            db.commit()
            return True
        token, job_id, wid, repo = str(uuid4()), job.id, job.workspace_id, connection.repository
        job.state, job.lease_token, job.lease_until = (
            "running",
            token,
            utc_now() + timedelta(seconds=120 if connection.auth_mode == "github_app_user" else 45),
        )
        job.attempt += 1
        private = connection.auth_mode == "github_app_user"
        if private:
            member = db.get(Membership, (job.workspace_id, connection.creator_id))
            if not member or member.role != "owner":
                from github_app import revoke_connection

                revoke_connection(db, connection)
                db.commit()
                return True
        db.expunge(connection)
        db.commit()
    records, error, credential, credential_expiry = None, None, None, None
    try:
        if private:
            if not settings or not settings.github_app_enabled:
                raise SyncError("private_connector_disabled")
            from github_app import private_fetch

            def save_rotation(ciphertext, expires):
                # Refresh tokens rotate once. Persist immediately, before later
                # paginated reads can fail, while rechecking authority and lease.
                with factory() as db:
                    lock_workspace(db, wid)
                    current_job = db.get(RepositorySync, job_id)
                    current_connection = db.get(RepositoryConnection, current_job.connection_id)
                    if (
                        current_job.state != "running"
                        or current_job.lease_token != token
                        or current_job.lease_until <= utc_now()
                        or not authorized(db, current_job, current_connection)
                    ):
                        raise SyncError("refresh_authority_changed")
                    current_connection.credential, current_connection.credential_expires_at = (
                        ciphertext,
                        expires,
                    )
                    db.commit()

            records, credential, credential_expiry = private_fetch(
                settings, connection, on_refresh=save_rotation
            )
        else:
            records = fetch(repo)
    except SyncError as exc:
        error = exc
    except Exception:
        error = SyncError("sync_failed")
    with factory() as db:
        lock_workspace(db, wid)
        job = db.get(RepositorySync, job_id)
        if job.state != "running" or job.lease_token != token:
            return True
        connection = db.get(RepositoryConnection, job.connection_id)
        if not authorized(db, job, connection):
            job.state = "cancelled"
        elif job.lease_until <= utc_now():
            job.state, job.error_code = "failed", "lease_expired"
        elif error:
            if private and error.code not in {"rate_limited", "github_unavailable"}:
                from github_app import revoke_connection

                revoke_connection(db, connection)
            job.error_code = error.code
            if error.retry_seconds and job.attempt < 3:
                job.state, job.next_attempt_at = (
                    "queued",
                    utc_now() + timedelta(seconds=error.retry_seconds),
                )
            else:
                job.state = "failed"
        else:
            if private:
                connection.credential, connection.credential_expires_at = (
                    credential,
                    credential_expiry,
                )
                connection.access_verified_until = utc_now() + timedelta(minutes=10)
            changed = False
            provider_ids = {item["provider_id"] for item in records}
            existing = db.query(ImportedRecord).filter_by(connection_id=connection.id).all()
            new_count = len(provider_ids - {item.provider_id for item in existing})
            if db.query(ImportedRecord).filter_by(workspace_id=wid).count() + new_count > 2000:
                job.state, job.error_code, job.completed_at = "failed", "import_capacity", utc_now()
                job.lease_token = job.lease_until = None
                db.commit()
                return True
            for item in existing:
                if item.available and item.provider_id not in provider_ids:
                    item.available = False
                    changed = True
            for data in records:
                digest = hashlib.sha256(json.dumps(data, sort_keys=True).encode()).hexdigest()
                item = (
                    db.query(ImportedRecord)
                    .filter_by(connection_id=connection.id, provider_id=data["provider_id"])
                    .first()
                )
                if item is None:
                    changed = True
                    db.add(
                        ImportedRecord(
                            id=str(uuid4()),
                            workspace_id=wid,
                            connection_id=connection.id,
                            content_hash=digest,
                            available=True,
                            version=1,
                            **data,
                        )
                    )
                elif item.content_hash != digest or not item.available:
                    changed = True
                    for key, value in data.items():
                        setattr(item, key, value)
                    item.available = True
                    item.content_hash, item.version, item.updated_at = (
                        digest,
                        item.version + 1,
                        utc_now(),
                    )
            if changed:
                advance(db, wid)
            job.state, job.record_count, job.error_code = "completed", len(records), None
        job.lease_token = job.lease_until = None
        if job.state != "queued":
            job.completed_at = utc_now()
        db.commit()
    return True
