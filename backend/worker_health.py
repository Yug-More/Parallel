"""A heartbeat proves process liveness, not successful job execution."""

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
        "status": "recently_alive" if active else "not_recently_seen",
        "note": "Recent process liveness does not prove a job succeeded; inspect its durable state.",
    }


class HeartbeatSupervisor:
    """Independent liveness pulse; deliberately says nothing about job success."""

    def __init__(self, factory, worker_id, interval=10):
        from threading import Event, Thread

        self.factory, self.worker_id, self.interval = factory, worker_id, interval
        self.stop = Event()
        self.thread = Thread(target=self.pulse, name="worker-heartbeat", daemon=True)

    def pulse(self):
        import logging

        while not self.stop.wait(self.interval):
            try:
                heartbeat(self.factory, self.worker_id)
            except Exception:
                # Do not print database URLs or provider exception bodies.
                logging.getLogger(__name__).warning("worker_heartbeat_failed")

    def __enter__(self):
        heartbeat(self.factory, self.worker_id)
        self.thread.start()
        return self

    def __exit__(self, *_):
        if self.thread.ident is None:
            return
        self.stop.set()
        self.thread.join(timeout=5)
        if not self.thread.is_alive():
            heartbeat(self.factory, self.worker_id, "stopped")
