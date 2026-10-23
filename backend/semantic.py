"""Optional provider interface and bounded durable index with lexical fallback.

The shipped local character-ngram adapter is deterministic lexical similarity,
NOT a trained semantic model. Tests may inject an adapter with the same protocol.
No network, automatic model downloads, or external embedding calls occur here.
"""

import hashlib
import json
import math
import re
import time
from datetime import timedelta
from typing import Protocol
from uuid import uuid4

from collaboration import lock_workspace
from knowledge_sources import fingerprint, resolve
from models import Membership, RetrievalIndex, Workspace, utc_now
from retrieval import retrieve
from security import require_member


class EmbeddingProvider(Protocol):
    name: str
    model: str

    def embed(self, texts: list[str]) -> list[list[float]]: ...


class LocalNgrams:
    name = "local-ngram"
    model = "char3-sha256-128-v1"

    def embed(self, texts):
        result = []
        for text in texts:
            vector = [0.0] * 128
            normalized = " ".join(re.findall(r"\w+", text.casefold()))[:3000]
            for i in range(max(0, len(normalized) - 2)):
                bucket = (
                    int.from_bytes(hashlib.sha256(normalized[i : i + 3].encode()).digest()[:2])
                    % 128
                )
                vector[bucket] += 1
            norm = math.sqrt(sum(v * v for v in vector)) or 1
            result.append([v / norm for v in vector])
        return result


def validate_vectors(vectors, count):
    if len(vectors) != count:
        raise ValueError("invalid_embedding")
    dimensions = len(vectors[0]) if vectors else 0
    if not 1 <= dimensions <= 1536:
        raise ValueError("invalid_embedding")
    for vector in vectors:
        if len(vector) != dimensions or any(
            not isinstance(v, (int, float)) or not math.isfinite(v) for v in vector
        ):
            raise ValueError("invalid_embedding")
    return vectors


def index_snapshot(db, workspace_id, trained, include_historical=False):
    kinds = ("decision", "task", "document", "external") if trained else ("document",)
    if trained and include_historical:
        kinds += ("decision_revision",)
    rows, total = [], 0
    for kind in kinds:
        result = retrieve(
            db,
            workspace_id,
            kind=kind,
            include_historical=include_historical if trained else False,
            limit=201,
        )
        total += result["total"]
        rows.extend(result["items"])
    if total > (64 if trained else 200):
        raise ValueError("index_capacity")
    sources = [resolve(db, workspace_id, row["kind"], row["id"]) for row in rows]
    stamps = sorted((s["kind"], s["id"], fingerprint(s)) for s in sources)
    return sources, hashlib.sha256(json.dumps(stamps).encode()).hexdigest()


def require_member_if_present(db, user_id, workspace_id):
    if db.get(Membership, (workspace_id, user_id)):
        require_member(db, user_id, workspace_id)


def index_once(factory, provider=None, settings=None):
    from embedding_providers import configured_provider

    supplied_provider = provider
    with factory() as db:
        job = (
            db.query(RetrievalIndex)
            .filter(
                (RetrievalIndex.state == "queued")
                | ((RetrievalIndex.state == "running") & (RetrievalIndex.lease_until <= utc_now()))
            )
            .order_by(RetrievalIndex.created_at, RetrievalIndex.id)
            .first()
        )
        if not job:
            return False
        lock_workspace(db, job.workspace_id)
        db.refresh(job)
        if job.state == "running":
            if job.lease_until <= utc_now():
                job.state, job.error_code = "failed", "lease_expired"
                job.entries, job.lease_token, job.lease_until = [], None, None
                db.commit()
            return True
        if job.state != "queued":
            return True
        workspace = db.get(Workspace, job.workspace_id)
        if workspace.knowledge_epoch != job.epoch or not db.get(
            Membership, (job.workspace_id, job.creator_id)
        ):
            job.state = "cancelled"
            db.commit()
            return True
        require_member(db, job.creator_id, job.workspace_id)
        trained = job.provider.startswith("trained-")
        if trained and db.get(Membership, (job.workspace_id, job.creator_id)).role != "owner":
            job.state = "cancelled"
            db.commit()
            return True
        provider = supplied_provider or (
            configured_provider(settings) if trained else LocalNgrams()
        )
        if provider is None:
            job.state, job.error_code = "failed", "provider_disabled"
            db.commit()
            return True
        if getattr(provider, "external", False) and not (job.options or {}).get("external_consent"):
            job.state, job.error_code = "failed", "consent_required"
            db.commit()
            return True
        if (provider.name, provider.model) != (job.provider, job.model):
            job.state, job.error_code = "failed", "provider_changed"
            db.commit()
            return True
        try:
            sources, snapshot = index_snapshot(
                db, job.workspace_id, trained, bool((job.options or {}).get("include_historical"))
            )
        except ValueError:
            job.state, job.error_code = "failed", "index_capacity"
            db.commit()
            return True
        if trained and (job.options or {}).get("source_fingerprint") != snapshot:
            job.state, job.error_code = "cancelled", "source_changed"
            db.commit()
            return True
        texts = [(s["title"] + "\n" + s["body"])[:3000] for s in sources]
        if trained:
            texts = [text.encode()[:2000].decode("utf8", errors="ignore") for text in texts]
            if sum(len(text.encode()) for text in texts) > 64000:
                job.state, job.error_code = "failed", "input_budget"
                db.commit()
                return True
        job.input_characters = sum(map(len, texts))
        job_id, wid, token = job.id, job.workspace_id, str(uuid4())
        job.state, job.lease_token, job.lease_until = (
            "running",
            token,
            utc_now() + timedelta(seconds=150 if trained else 20),
        )
        db.commit()
    started = time.monotonic()
    error, entries = None, []
    try:
        if sources:
            vectors = []
            for start in range(0, len(texts), 16):
                # Recheck authority and all source snapshots immediately before each
                # bounded call; do not hold a transaction across provider latency.
                with factory() as db:
                    lock_workspace(db, wid)
                    current = db.get(RetrievalIndex, job_id)
                    require_member(db, current.creator_id, wid, owner=trained)
                    if (
                        current.state != "running"
                        or current.lease_token != token
                        or current.epoch != db.get(Workspace, wid).knowledge_epoch
                    ):
                        raise ValueError("source_changed")
                    if any(
                        fingerprint(resolve(db, wid, source["kind"], source["id"]))
                        != fingerprint(source)
                        for source in sources
                    ):
                        raise ValueError("source_changed")
                    db.commit()
                if getattr(provider, "external", False):
                    with factory() as db:
                        from github_app import require_fresh_private_access

                        require_fresh_private_access(db, wid)
                    if settings is None:
                        raise ValueError("budget_unavailable")
                    from rate_limit import SharedRateLimiter

                    SharedRateLimiter(factory, settings.secret_key).check(
                        "embedding-global-budget", limit=12
                    )
                batch = texts[start : start + 16]
                vectors.extend(validate_vectors(provider.embed(batch), len(batch)))
            entries = [
                {"id": s["id"], "kind": s["kind"], "fingerprint": fingerprint(s), "vector": v}
                for s, v in zip(sources, vectors, strict=True)
            ]
    except Exception:
        error = "embedding_failed"
    with factory() as db:
        lock_workspace(db, wid)
        job = db.get(RetrievalIndex, job_id)
        if job.state != "running" or job.lease_token != token:
            return True
        require_member_if_present(db, job.creator_id, wid)
        if job.epoch != db.get(Workspace, wid).knowledge_epoch or not db.get(
            Membership, (wid, job.creator_id)
        ):
            job.state = "cancelled"
        elif trained and db.get(Membership, (wid, job.creator_id)).role != "owner":
            job.state = "cancelled"
        elif job.lease_until <= utc_now():
            job.state, job.error_code = "failed", "lease_expired"
        else:
            try:
                if any(
                    fingerprint(resolve(db, wid, s["kind"], s["id"])) != fingerprint(s)
                    for s in sources
                ):
                    error = "source_changed"
            except Exception:
                error = "source_changed"
            job.duration_ms = int((time.monotonic() - started) * 1000)
            job.dimensions = len(entries[0]["vector"]) if entries else None
            job.usage_tokens = getattr(provider, "usage_tokens", 0)
            job.state, job.error_code, job.entries = (
                ("failed" if error else "ready"),
                error,
                ([] if error else entries),
            )
        job.completed_at, job.lease_token, job.lease_until = utc_now(), None, None
        db.commit()
    return True


def hybrid(
    db,
    workspace_id,
    *,
    q,
    limit=20,
    offset=0,
    provider=None,
    user_id=None,
    semantic_only=False,
    **filters,
):
    baseline = retrieve(db, workspace_id, q=q, limit=limit, offset=offset, **filters)
    baseline["index_status"] = "lexical_fallback"

    def fresh_fallback():
        db.expire_all()
        if user_id:
            require_member(db, user_id, workspace_id)
        result = retrieve(db, workspace_id, q=q, limit=limit, offset=offset, **filters)
        return {**result, "index_status": "lexical_fallback"}

    provider = provider or LocalNgrams()
    trained = getattr(provider, "trained", False)
    # Character ranking preserves the original fallback behavior. Trained ranking
    # intersects a fresh SQL eligibility set for every requested filter.
    if (
        not q.strip()
        or offset
        or (not trained and any(v for k, v in filters.items() if k != "kind"))
        or (not trained and filters.get("kind") not in {None, "document"})
    ):
        return baseline
    job = (
        db.query(RetrievalIndex)
        .filter_by(
            workspace_id=workspace_id,
            state="ready",
            epoch=db.get(Workspace, workspace_id).knowledge_epoch,
            provider=provider.name,
            model=provider.model,
        )
        .order_by(RetrievalIndex.created_at.desc())
        .first()
    )
    if not job or not job.entries:
        return baseline
    try:
        if getattr(provider, "external", False) and not (job.options or {}).get("external_consent"):
            return baseline
        # Commit expiry invalidations and release DB locks before provider latency.
        epoch, job_id = job.epoch, job.id
        if trained:
            _, current_snapshot = index_snapshot(
                db, workspace_id, True, bool((job.options or {}).get("include_historical"))
            )
            if current_snapshot != (job.options or {}).get("source_fingerprint"):
                return fresh_fallback()
        db.commit()
        query = validate_vectors(provider.embed([q]), 1)[0]
        if user_id:
            lock_workspace(db, workspace_id, user_id, owner=getattr(provider, "external", False))
        else:
            db.expire_all()
        if db.get(Workspace, workspace_id, populate_existing=True).knowledge_epoch != epoch:
            return fresh_fallback()
        job = db.get(RetrievalIndex, job_id, populate_existing=True)
        eligible = None
        if trained:
            _, current_snapshot = index_snapshot(
                db, workspace_id, True, bool((job.options or {}).get("include_historical"))
            )
            if current_snapshot != (job.options or {}).get("source_fingerprint"):
                return fresh_fallback()
            live = retrieve(db, workspace_id, q="", limit=1001, **filters)
            if live["total"] > 1000:
                return fresh_fallback()
            eligible = {row["ref"] for row in live["items"]}
        candidates = []
        for entry in job.entries:
            kind = entry.get("kind", "document")
            if eligible is not None and f"{kind}:{entry['id']}" not in eligible:
                continue
            source = resolve(db, workspace_id, kind, entry["id"])
            if fingerprint(source) != entry["fingerprint"] or len(query) != len(entry["vector"]):
                return fresh_fallback()
            score = sum(a * b for a, b in zip(query, entry["vector"], strict=True))
            if score >= 0.25:
                candidates.append((score, source))
        baseline = fresh_fallback()
        candidates.sort(key=lambda x: (-x[0], x[1]["id"]))
        ranks = (
            {}
            if semantic_only
            else {r["ref"]: (1 / (60 + i), r) for i, r in enumerate(baseline["items"], 1)}
        )
        for i, (_, source) in enumerate(candidates, 1):
            ref = f"{source['kind']}:{source['id']}"
            weight, row = ranks.get(
                ref,
                (
                    0,
                    {
                        "id": source["id"],
                        "kind": source["kind"],
                        "ref": ref,
                        "title": source["title"],
                        "excerpt": source["body"],
                        "version": source["version"],
                        "status": source["status"],
                        "authority": source["authority"],
                        "event_at": source["created_at"],
                        "score": 0,
                    },
                ),
            )
            ranks[ref] = (weight + 1 / (60 + i), row)
        rows = sorted(ranks.values(), key=lambda x: (-x[0], x[1]["ref"]))
        return {
            **baseline,
            "items": [r for _, r in rows[:limit]],
            "total": len(rows),
            "method": ("trained_semantic_v1" if semantic_only else "trained_hybrid_rrf_v1")
            if trained
            else "hybrid_rrf_v1",
            "index_status": "ready",
            "embedding_provider": provider.name,
            "embedding_model": provider.model,
            "evidence": "matching_sources" if rows else "no_matching_evidence",
        }
    except Exception:
        return fresh_fallback()
