"""Bounded per-process authentication throttling; no application-level proxy-header parsing."""

from collections import OrderedDict, deque
from threading import Lock
from time import monotonic

from fastapi import HTTPException


class AuthRateLimiter:
    def __init__(self, limit=20, window=60, clock=monotonic):
        self.limit, self.window, self.clock = limit, window, clock
        self.clients = OrderedDict()
        self.lock = Lock()

    def check(self, key):
        with self.lock:
            now = self.clock()
            recent = self.clients.pop(key, deque())
            while recent and recent[0] <= now - self.window:
                recent.popleft()
            self.clients[key] = recent
            if len(self.clients) > 10000:
                self.clients.popitem(last=False)
            if len(recent) >= self.limit:
                raise HTTPException(
                    429,
                    "Too many authentication attempts. Try again shortly.",
                    headers={"Retry-After": str(self.window)},
                )
            recent.append(now)


class SharedRateLimiter:
    """Database-atomic fixed windows across HTTP processes. No raw IP storage."""

    def __init__(self, factory, secret, limit=20, clock=None):
        import time

        self.factory, self.secret, self.limit = factory, secret.encode(), limit
        self.clock = clock or time.time

    def check(self, key, limit=None):
        import hashlib
        import hmac

        from sqlalchemy import text

        digest = hmac.new(self.secret, key.encode(), hashlib.sha256).hexdigest()
        window = int(self.clock() // 60)
        with self.factory() as db:
            # Supported by SQLite >=3.35 and PostgreSQL. One atomic statement,
            # including the first request race and rollover. Rejections also count.
            count = db.execute(
                text("""
                INSERT INTO abuse_counters (key, "window", count) VALUES (:key, :window, 1)
                ON CONFLICT (key) DO UPDATE SET
                    count = CASE WHEN abuse_counters."window" = :window THEN abuse_counters.count + 1 ELSE 1 END,
                    "window" = :window
                RETURNING count
            """),
                {"key": digest, "window": window},
            ).scalar_one()
            db.execute(
                text('DELETE FROM abuse_counters WHERE "window" < :old'), {"old": window - 1440}
            )
            db.commit()
        if count > (limit or self.limit):
            raise HTTPException(
                429,
                "Shared request limit reached; try again next minute",
                headers={"Retry-After": str(60 - int(self.clock()) % 60)},
            )
