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
