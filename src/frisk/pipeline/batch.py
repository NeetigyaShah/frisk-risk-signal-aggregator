"""Batch scoring — the throughput layer.

Each customer runs the full agentic pipeline (parallel specialists + serial orchestrator). Those calls are
I/O-bound, so a thread pool overlaps *different customers* (a single customer stays specialists-parallel +
orchestrator-serial). Results land in the relational store, which the dashboard/API read.
"""
from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor

from frisk.config import CONFIG
from frisk.core import engine


def assess_all_scaled(dossiers, workers: int | None = None, persist: bool = True):
    workers = workers or CONFIG["scale"]["workers"]
    with ThreadPoolExecutor(max_workers=workers) as ex:
        return list(ex.map(lambda d: engine.assess(d, persist=persist), dossiers))


if __name__ == "__main__":  # throughput probe (mock provider recommended)
    import time
    from collections import Counter

    from frisk.core.models import load_dossiers
    from frisk.data import audit, store

    audit.reset(); store.reset()
    ds = load_dossiers()
    t = time.time()
    decs = assess_all_scaled(ds, persist=True)
    dt = time.time() - t
    print(f"scored {len(decs)} customers in {dt:.1f}s ({len(decs)/dt:.1f}/s) "
          f"-> {dict(Counter(d.action for d in decs))}")
    print(f"store rows: {store.count()}")
