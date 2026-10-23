"""A heartbeat proves recent worker polling, not successful job execution."""

from datetime import timedelta

from models import WorkerHeartbeat, utc_now
from security import as_utc


def heartbeat(factory, worker_id, state="running"):
    with factory() as db:
        row = db.get(WorkerHeartbeat, worker_id)
        if row is None:
            row = WorkerHeartbeat(id=worker_id)
            db.add(row)
        row.state, row.last_seen_at = state, utc_now()
        db.query(WorkerHeartbeat).filter(
            WorkerHeartbeat.last_seen_at < utc_now() - timedelta(days=7)
        ).delete()
        db.commit()


def status(db):
    latest = db.query(WorkerHeartbeat).order_by(WorkerHeartbeat.last_seen_at.desc()).first()
    active = (
        db.query(WorkerHeartbeat)
        .filter(
            WorkerHeartbeat.state == "running",
            WorkerHeartbeat.last_seen_at > utc_now() - timedelta(seconds=60),
        )
        .count()
    )
    return {
        "active_workers": active,
        "last_seen_at": as_utc(latest.last_seen_at) if latest else None,
        "status": "recently_polling" if active else "not_recently_seen",
        "note": "Recent polling does not prove a job succeeded; inspect its durable state.",
    }
