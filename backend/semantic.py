"""Optional provider interface and bounded durable index with lexical fallback.

The shipped local character-ngram adapter is deterministic lexical similarity,
NOT a trained semantic model. Tests may inject an adapter with the same protocol.
No network, automatic model downloads, or external embedding calls occur here.
"""

import hashlib
import math
import re
from datetime import timedelta
from typing import Protocol
from uuid import uuid4

from collaboration import lock_workspace
from knowledge_sources import fingerprint, resolve
from models import Membership, RetrievalIndex, Workspace, utc_now
from retrieval import retrieve


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


def index_once(factory, provider=None):
    provider = provider or LocalNgrams()
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
        if (provider.name, provider.model) != (job.provider, job.model):
            job.state, job.error_code = "failed", "provider_changed"
            db.commit()
            return True
        # Index only uploaded passages; native mutable state still uses live SQL.
        result = retrieve(db, job.workspace_id, kind="document", limit=201)
        if result["total"] > 200:
            job.state, job.error_code = "failed", "index_capacity"
            db.commit()
            return True
        sources = [resolve(db, job.workspace_id, r["kind"], r["id"]) for r in result["items"]]
        job_id, wid, token = job.id, job.workspace_id, str(uuid4())
        job.state, job.lease_token, job.lease_until = (
            "running",
            token,
            utc_now() + timedelta(seconds=20),
        )
        db.commit()
    error, entries = None, []
    try:
        if sources:
            vectors = validate_vectors(
                provider.embed([s["title"] + "\n" + s["body"] for s in sources]), len(sources)
            )
            entries = [
                {"id": s["id"], "fingerprint": fingerprint(s), "vector": v}
                for s, v in zip(sources, vectors, strict=True)
            ]
    except Exception:
        error = "embedding_failed"
    with factory() as db:
        lock_workspace(db, wid)
        job = db.get(RetrievalIndex, job_id)
        if job.state != "running" or job.lease_token != token:
            return True
        if job.epoch != db.get(Workspace, wid).knowledge_epoch or not db.get(
            Membership, (wid, job.creator_id)
        ):
            job.state = "cancelled"
        elif job.lease_until <= utc_now():
            job.state, job.error_code = "failed", "lease_expired"
        else:
            job.state, job.error_code, job.entries = (
                ("failed" if error else "ready"),
                error,
                ([] if error else entries),
            )
        job.completed_at, job.lease_token, job.lease_until = utc_now(), None, None
        db.commit()
    return True


def hybrid(db, workspace_id, *, q, limit=20, offset=0, provider=None, **filters):
    baseline = retrieve(db, workspace_id, q=q, limit=limit, offset=offset, **filters)
    baseline["index_status"] = "lexical_fallback"
    # Filter semantics must never be widened by the auxiliary index.
    if (
        not q.strip()
        or offset
        or any(v for k, v in filters.items() if k != "kind")
        or filters.get("kind") not in {None, "document"}
    ):
        return baseline
    provider = provider or LocalNgrams()
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
        query = validate_vectors(provider.embed([q]), 1)[0]
        candidates = []
        for entry in job.entries:
            source = resolve(db, workspace_id, "document", entry["id"])
            if fingerprint(source) != entry["fingerprint"] or len(query) != len(entry["vector"]):
                return baseline
            score = sum(a * b for a, b in zip(query, entry["vector"], strict=True))
            if score >= 0.25:
                candidates.append((score, source))
        candidates.sort(key=lambda x: (-x[0], x[1]["id"]))
        ranks = {r["ref"]: (1 / (60 + i), r) for i, r in enumerate(baseline["items"], 1)}
        for i, (_, source) in enumerate(candidates, 1):
            ref = f"document:{source['id']}"
            weight, row = ranks.get(
                ref,
                (
                    0,
                    {
                        "id": source["id"],
                        "kind": "document",
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
            "method": "hybrid_rrf_v1",
            "index_status": "ready",
            "embedding_provider": provider.name,
            "embedding_model": provider.model,
            "evidence": "matching_sources" if rows else "no_matching_evidence",
        }
    except Exception:
        return baseline
