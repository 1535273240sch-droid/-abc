"""Redis-backed distributed lock for multi-instance deployments.

When the application runs with multiple replicas (e.g., behind a
load balancer), the in-memory ``threading.RLock`` is insufficient.
This module provides a Redis SET NX EX-based distributed lock that
ensures only one instance performs state-mutating operations.

Usage:

    from app.core.distributed_lock import distributed_lock

    with distributed_lock("order_create:abc123"):
        # critical section
        store.orders[order_id] = order
"""

from __future__ import annotations

import logging
import os
import threading
import time
import uuid
from contextlib import contextmanager
from typing import Iterator

from app.core.config import settings

logger = logging.getLogger(__name__)

# Fallback: in-process reentrant lock (single-instance mode)
_local_locks: dict[str, threading.RLock] = {}
_local_registry_lock = threading.Lock()


class _LocalLock:
    """Context manager wrapper around threading.RLock."""

    def __init__(self, name: str, timeout: float = 10.0):
        with _local_registry_lock:
            lock = _local_locks.get(name)
            if lock is None:
                lock = threading.RLock()
                _local_locks[name] = lock
        self._lock = lock
        self._name = name
        self._timeout = timeout

    def __enter__(self):
        acquired = self._lock.acquire(timeout=self._timeout)
        if not acquired:
            raise TimeoutError(f"Could not acquire lock '{self._name}' within {self._timeout}s")
        return self

    def __exit__(self, *args):
        self._lock.release()


class RedisDistributedLock:
    """Redis-based distributed lock using SET NX EX + Lua release."""

    _RELEASE_SCRIPT = """
    if redis.call("get", KEYS[1]) == ARGV[1] then
        return redis.call("del", KEYS[1])
    else
        return 0
    end
    """

    _RENEW_SCRIPT = """
    if redis.call("get", KEYS[1]) == ARGV[1] then
        return redis.call("expire", KEYS[1], ARGV[2])
    else
        return 0
    end
    """

    def __init__(self, name: str, ttl: int = 10, timeout: float = 10.0):
        self.name = name
        self.ttl = ttl
        self.timeout = timeout
        self._token = str(uuid.uuid4())
        self._redis = None
        self._acquired = False

    def _get_redis(self):
        if self._redis is None:
            import redis
            self._redis = redis.from_url(settings.redis_url, socket_timeout=2)
        return self._redis

    def __enter__(self):
        deadline = time.monotonic() + self.timeout
        while time.monotonic() < deadline:
            try:
                r = self._get_redis()
                acquired = r.set(
                    f"lock:{self.name}",
                    self._token,
                    nx=True,
                    ex=self.ttl,
                )
                if acquired:
                    self._acquired = True
                    return self
            except Exception as exc:  # noqa: BLE001
                logger.debug("redis lock attempt failed: %s", exc)
            time.sleep(0.1)
        raise TimeoutError(f"Could not acquire distributed lock '{self.name}' within {self.timeout}s")

    def __exit__(self, *args):
        if self._acquired:
            try:
                r = self._get_redis()
                r.eval(self._RELEASE_SCRIPT, 1, f"lock:{self.name}", self._token)
            except Exception as exc:  # noqa: BLE001
                logger.warning("failed to release lock '%s': %s", self.name, exc)
            self._acquired = False


@contextmanager
def distributed_lock(name: str, ttl: int = 10, timeout: float = 10.0) -> Iterator[Any]:
    """Acquire a distributed lock.

    In single-instance mode (no Redis), falls back to an in-process
    ``threading.RLock``.

    Args:
        name:    Lock name (should be unique per resource)
        ttl:     Time-to-live in seconds (Redis mode only)
        timeout: Maximum time to wait for the lock

    Yields:
        The lock context.
    """
    if settings.redis_url and settings.event_backend == "redis":
        lock = RedisDistributedLock(name, ttl=ttl, timeout=timeout)
    else:
        lock = _LocalLock(name, timeout=timeout)
    with lock:
        yield lock
