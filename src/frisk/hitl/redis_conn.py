"""One shared Redis client (with graceful in-memory fallback) reused by the review queue and scratchpad.

Opening a single connection here — instead of one per module — keeps the fallback behaviour consistent:
if Redis is unreachable, ``client()`` returns None and callers use their own in-process store, so the
app never hard-crashes on a missing broker.
"""
from __future__ import annotations

from frisk.config import CONFIG

_redis = None
_use: bool | None = None


def client():
    """Return a live redis-py client, or None if Redis is unreachable (probe once, then cache)."""
    global _redis, _use
    if _use is None:
        try:
            import redis
            _redis = redis.Redis.from_url(CONFIG["redis_url"], decode_responses=True, socket_connect_timeout=1)
            _redis.ping()
            _use = True
        except Exception:
            _use = False
    return _redis if _use else None


def backend() -> str:
    return "redis" if client() is not None else "in-memory (Redis unreachable)"
