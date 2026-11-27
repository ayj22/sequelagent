"""A small sliding-window limit, so a stuck script or a curious visitor cannot run up the model bill."""
from __future__ import annotations

import threading
import time
from collections import deque


class RateLimit:
    def __init__(self, calls: int, seconds: float, clock=time.monotonic):
        self.calls, self.seconds, self.clock = calls, seconds, clock
        self.seen: deque[float] = deque()
        self.lock = threading.Lock()

    def allow(self) -> bool:
        with self.lock:
            now = self.clock()
            while self.seen and now - self.seen[0] >= self.seconds:
                self.seen.popleft()
            if len(self.seen) >= self.calls:
                return False
            self.seen.append(now)
            return True
