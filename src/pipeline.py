"""Batch scoring pipeline — the throughput layer.

Two levers make 10k+/day cheap:
  1. Parallelism — LLM cross-checks are I/O-bound, so a thread pool overlaps them.
  2. Gating — the LLM only runs where it changes the outcome (the uncertain MED band). LOW auto-clears
     and HIGH escalates on the deterministic rules alone (microseconds each). This is the real cost lever:
     rules score 100% of the population; the LLM touches a fraction.

Results are written to the SQLite decisions store, which the dashboard/API read (no re-scoring on load).
"""
from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor

import engine
import store
from config import CONFIG
from rules import score_customer


def should_crosscheck(rr, policy: str) -> bool:
    if policy == "all":
        return True
    # "gated": LOW is rules-decisive (auto-clear), HIGH is rules-decisive (escalate);
    # only the ambiguous middle earns the LLM's latency/cost.
    return rr.band == "MED"


def assess_all_scaled(dossiers, workers: int | None = None, policy: str | None = None,
                      persist_db: bool = True):
    policy = policy or CONFIG["scale"]["crosscheck_policy"]
    workers = workers or CONFIG["scale"]["workers"]

    def one(d):
        rr = score_customer(d)  # cheap, deterministic — runs on everyone
        return engine.assess(d, persist=False, use_llm=should_crosscheck(rr, policy))

    with ThreadPoolExecutor(max_workers=workers) as ex:
        decisions = list(ex.map(one, dossiers))
    if persist_db:
        store.upsert_many(decisions)
    return decisions


if __name__ == "__main__":
    # throughput probe: prove the deterministic layer scales to millions/day on one core
    import os
    import time
    from models import load_dossiers

    base = load_dossiers(os.path.join(os.path.dirname(__file__), "..", "data", "dossiers.json"))
    N = 20000
    big = [base[i % len(base)] for i in range(N)]  # rules are pure -> safe to reuse objects

    t = time.time()
    for d in big:
        score_customer(d)
    dt = time.time() - t
    print(f"rules-only: {N:,} customers in {dt:.2f}s  ->  {N/dt:,.0f}/sec  (~{N/dt*86400/1e6:.0f}M/day/core)")

    # gated pipeline on the real 20 (LLM only on MED band, cached)
    t = time.time()
    decs = assess_all_scaled(base, policy="gated", persist_db=True)
    from collections import Counter
    print(f"gated pipeline (20): {time.time()-t:.2f}s  paths={dict(Counter(d.engine_path for d in decs))}")
    print(f"store rows: {store.count()}")
