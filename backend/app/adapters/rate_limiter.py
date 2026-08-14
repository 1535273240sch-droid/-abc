"""Token-bucket rate limiter for adapter simulation."""

import threading
import time


class RateLimiter:
    def __init__(self, max_requests_per_second: float = 10.0):
        self._max_rate = max_requests_per_second
        self._tokens = max_requests_per_second
        self._last_refill = time.monotonic()
        self._lock = threading.Lock()

    def acquire(self, timeout: float = 0.0) -> bool:
        with self._lock:
            self._refill()
            if self._tokens >= 1.0:
                self._tokens -= 1.0
                return True
            if timeout > 0:
                wait = (1.0 - self._tokens) / self._max_rate if self._max_rate > 0 else 0.1
                self._lock.release()
                time.sleep(min(wait, timeout))
                self._lock.acquire()
                self._refill()
                if self._tokens >= 1.0:
                    self._tokens -= 1.0
                    return True
            return False

    def _refill(self) -> None:
        now = time.monotonic()
        elapsed = now - self._last_refill
        self._tokens = min(self._max_rate, self._tokens + elapsed * self._max_rate)
        self._last_refill = now

    @property
    def is_rate_limited(self) -> bool:
        with self._lock:
            self._refill()
            return self._tokens < 1.0

    def reset(self) -> None:
        with self._lock:
            self._tokens = self._max_rate
            self._last_refill = time.monotonic()