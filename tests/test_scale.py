"""Tests for the scale layer: gating policy, store round-trip, and gated auto-clear."""
import os

from frisk.core import engine
from frisk.pipeline import batch as pipeline
from frisk.core import rules
from frisk.data import store
from frisk.core.models import load_dossiers

from frisk.paths import CUSTOMERS_DIR as DATA


def test_gating_skips_llm_on_decisive_bands():
    ds = load_dossiers(DATA)
    decs = pipeline.assess_all_scaled(ds, policy="gated", persist_db=False)
    for d, dec in zip(ds, decs):  # ThreadPoolExecutor.map preserves order
        rr = rules.score_customer(d)
        if rr.band in ("LOW", "HIGH") and not rr.flags:
            assert dec.engine_path == "rules_gated", f"{d.customer_id} should be gated (no LLM)"


def test_gated_low_risk_auto_clears():
    # a clean low-risk customer, gated, still auto-clears on rules alone (policy-authoritative, not degraded)
    low = load_dossiers(DATA)[0]  # CUST_000, benign teacher
    dec = engine.assess(low, persist=False, use_llm=False)
    assert dec.engine_path == "rules_gated"
    assert dec.action == "AUTO_CLEAR"
    assert dec.confidence > 0.5  # not the degraded cap


def test_store_roundtrip(tmp_path, monkeypatch):
    monkeypatch.setattr(store, "DB", str(tmp_path / "decisions.db"))
    ds = load_dossiers(DATA)[:6]
    decs = [engine.assess(d, persist=False, use_llm=False) for d in ds]
    assert store.upsert_many(decs) == 6
    assert store.count() == 6
    top = store.query(limit=3)
    assert len(top) == 3 and top[0]["score"] >= top[-1]["score"]  # ranked
    # idempotent upsert (no duplicate rows)
    store.upsert_many(decs)
    assert store.count() == 6


def test_throughput_smoke():
    # rules score a big batch fast (no LLM) — guards the scale claim
    import time
    base = load_dossiers(DATA)
    big = [base[i % len(base)] for i in range(2000)]
    t = time.time()
    for d in big:
        rules.score_customer(d)
    rate = 2000 / (time.time() - t)
    assert rate > 200, f"rules throughput too low: {rate:.0f}/sec"
