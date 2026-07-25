"""One shared Redis client (with graceful in-memory fallback) reused by the review queue and scratchpad.

Opening a single connection here — instead of one per module — keeps the fallback behaviour consistent:
if Redis is unreachable, ``client()`` returns None and callers use their own in-process store, so the
app never hard-crashes on a missing broker.

The availability probe is cached but NOT permanent. Caching a `True` forever was a real outage: Redis
died mid-session, every later call raised TimeoutError instead of falling back, and the API returned
500s even though an in-memory path existed. A broker that dies after startup must degrade exactly like
one that was never there — so a failure flips back to unavailable, and we re-probe periodically to
pick it up again when it returns.
"""
from __future__ import annotations

import time

from frisk.config import CONFIG

_redis = None
_use: bool | None = None
_checked_at: float = 0.0
_RECHECK_S = 15.0


def _connect() -> bool:
    global _redis, _use, _checked_at
    _checked_at = time.time()
    try:
        import redis
        _redis = redis.Redis.from_url(CONFIG["redis_url"], decode_responses=True,
                                      socket_connect_timeout=1, socket_timeout=2)
        _redis.ping()
        _use = True
    except Exception:
        _redis, _use = None, False
    return bool(_use)


def client():
    """Return a live redis-py client, or None if Redis is unreachable.

    Availability is cached for _RECHECK_S so the hot path is not a ping per call, but an unreachable
    broker is retried rather than latched off forever.
    """
    if _use is None or (not _use and time.time() - _checked_at > _RECHECK_S):
        _connect()
    return _redis if _use else None


def mark_down() -> None:
    """Called by a caller whose operation just failed — flip to the in-memory path immediately."""
    global _use, _checked_at
    _use, _checked_at = False, time.time()


def backend() -> str:
    return "redis" if client() is not None else "in-memory (Redis unreachable)"
