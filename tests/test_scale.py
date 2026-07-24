"""Scale-layer tests — parallel batch scoring across customers + the relational store roundtrip."""
from frisk.core.models import load_dossiers
from frisk.data import store
from frisk.pipeline.batch import assess_all_scaled


def test_batch_scores_all_and_persists():
    store.reset()
    ds = load_dossiers()
    decs = assess_all_scaled(ds, workers=4, persist=True)
    assert len(decs) == 20
    assert store.count() == 20
    assert len(store.latest_all()) == 20
    assert all(0 <= d.score <= 100 and d.engine_path == "agent" for d in decs)


def test_store_roundtrip_and_latest():
    store.reset()
    store.record_assessment({"customer_id": "Z", "name": "Z", "entity_type": "individual", "country": "GB",
                             "occupation": "x", "pep": False, "ts": "2026-01-01T00:00:00Z", "score": 30,
                             "band": "low", "confidence": 0.8, "disposition": "REVIEW", "key_signals": ["k"],
                             "rationale": "r", "trace_ref": "t", "human_verified": False, "corrected_score": None})
    store.record_assessment({"customer_id": "Z", "name": "Z", "entity_type": "individual", "country": "GB",
                             "occupation": "x", "pep": False, "ts": "2026-02-01T00:00:00Z", "score": 70,
                             "band": "high", "confidence": 0.9, "disposition": "ESCALATE", "key_signals": ["k2"],
                             "rationale": "r", "trace_ref": "t", "human_verified": True, "corrected_score": 70})
    assert store.get("Z")["score"] == 70                 # latest wins
    assert [r["score"] for r in store.history("Z", 5)] == [70, 30]
