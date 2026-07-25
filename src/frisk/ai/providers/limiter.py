"""Global LLM call concurrency limiter.

Diagnosed: two customers scored concurrently both started at t=0 (genuinely parallel at the code
level — no serialization bug), but each took 76-90s wall-clock versus ~15-30s solo. Each customer
fires up to ~18 LLM calls (3 specialists + up to 16 agent turns); batching customers stacks that on
top of itself, so 2-6 concurrent customers can burst 30-100+ simultaneous requests at the provider.
That trips per-key rate limiting, and the SDK's automatic retry+backoff then silently eats tens of
seconds per throttled call — the slowdown is provider-side throttling, not our own threading.

Fix: every LLM call site (specialists, the agent loop, SAR drafting, reflection) acquires one shared
semaphore first. This bounds total simultaneous in-flight requests app-wide, regardless of how many
ThreadPoolExecutors are stacked on top of each other (per-customer specialists x cross-customer batch),
so concurrent runs get real overlap without bursting past whatever limit is triggering the backoff.
"""
from __future__ import annotations

import threading

from frisk.config import CONFIG

_sem = threading.Semaphore(CONFIG["llm_concurrency"])


class llm_slot:
    """``with llm_slot(): provider.complete(...)`` — waits for a free concurrency slot."""

    def __enter__(self):
        _sem.acquire()
        return self

    def __exit__(self, *exc):
        _sem.release()
        return False
