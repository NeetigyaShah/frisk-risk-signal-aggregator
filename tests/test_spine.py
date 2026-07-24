"""Golden tests for the full-LLM agentic spine (mock provider drives the tool loop).

Covers: generator determinism (no sanctions/adverse), engine always returns a valid Decision through the
agent, low-confidence routing to the human queue, scratchpad eviction, per-customer history, episodic
recall, injected-memory logging, append-only audit, parallel specialists, band coercion, and NL-query safety.
"""
from frisk.ai import memory
from frisk.ai.specialists import run_specialists
from frisk.core import engine
from frisk.core.models import Dossier, RiskFinding, load_dossiers
from frisk.data import audit, casebank, store
from frisk.hitl import scratchpad
from frisk.query import nlquery


def _dossier(cid="TST", occ="teacher", country="GB", pep=False, txns=None, docs=None,
             kyc_complete=True, missing=None):
    return Dossier(
        cid, {"name": "Test", "occupation": occ, "id_doc": "P1", "kyc_complete": kyc_complete},
        {"country": country, "entity_type": "individual", "pep": pep, "tenure_days": 1000},
        txns or [], {"pep_confirmed": pep}, {"missing_docs": missing or []},
        docs or [{"name": "rm_notes.txt", "kind": "unstructured", "text": "routine relationship"}],
    )


def test_generator_deterministic_and_no_sanctions():
    import hashlib
    from frisk.data.generate import _canon, generate
    ds = generate()
    assert len(ds) == 20
    assert hashlib.sha256(_canon(generate()).encode()).hexdigest() == \
           hashlib.sha256(_canon(generate()).encode()).hexdigest()
    for d in ds:
        assert set(d.screening) == {"pep_confirmed"}
        assert not any(x["name"].startswith("adverse_media") for x in d.documents)


def test_engine_returns_valid_decision_for_every_customer():
    decs = engine.assess_all(load_dossiers(), persist=False)
    assert len(decs) == 20
    for d in decs:
        assert 0 <= d.score <= 100
        assert d.band in ("low", "medium", "high")
        assert d.action in ("AUTO_CLEAR", "REVIEW", "ESCALATE", "PENDING_REVIEW")
        assert d.engine_path == "agent"
        assert d.trace and d.trace[-1]["tool"] == "finalize"


def test_low_confidence_routes_to_human():
    d = _dossier(cid="REVIEWME", docs=[{"name": "rm_notes.txt", "kind": "unstructured",
                 "text": "This case is genuinely borderline; recommend a second opinion."}])
    dec = engine.assess(d, persist=False)
    assert dec.confidence < 0.6
    assert dec.action == "PENDING_REVIEW"


def test_scratchpad_evicted_after_assess():
    engine.assess(_dossier(cid="EVICT"), persist=False)
    assert scratchpad.read("EVICT") == {}


def test_per_customer_history_appends():
    store.reset()
    engine.assess(_dossier(cid="HIST"), persist=True)
    engine.assess(_dossier(cid="HIST"), persist=True)
    assert len(store.history("HIST", k=5)) == 2


def test_episodic_casebank_recall():
    casebank.reset()
    casebank.add("A", "arms dealer syria", {"country": "SY", "occupation": "director", "pep": True,
                 "band": "HIGH"}, "HIGH", "ESCALATE", True)
    top = casebank.similar({"country": "SY", "occupation": "director", "pep": True}, k=1)
    assert top and top[0]["customer_id"] == "A"


def test_injected_memory_recorded_on_decision():
    dec = engine.assess(_dossier(cid="MEMLOG"), persist=False)
    assert "history_n" in dec.injected_memory


def test_audit_append_only_and_analyst_action():
    audit.reset()
    engine.assess(_dossier(cid="AUD"), persist=True)
    n = len(audit.read_all())
    engine.log_analyst_action("AUD", "ESCALATE", actor="analyst:test", rationale="manual")
    assert len(audit.read_all()) == n + 1


def test_specialists_run_parallel_three_domains():
    ops = run_specialists(_dossier(occ="arms dealer", country="IR"), {"injected": {}})
    assert len(ops) == 3 and {o.domain for o in ops} == {"kyc", "transactions", "documents"}


def test_riskfinding_band_coerced_from_score():
    assert RiskFinding(score=90, rationale="x").band == "high"
    assert RiskFinding(score=10, rationale="x").band == "low"


def test_memory_writeback_and_retrieve_roundtrip():
    store.reset(); casebank.reset()
    d = _dossier(cid="RT", occ="crypto dealer", country="RU")
    engine.assess(d, persist=True)
    mem = memory.retrieve(d)
    assert mem["injected"]["history_n"] >= 1   # its own prior assessment is retrievable


def test_nlquery_is_safe_and_whitelisted():
    spec = nlquery.keyword_parse("__import__('os').system('rm -rf /')")
    assert nlquery.apply(spec, []) == []
    spec2 = nlquery.keyword_parse("structuring cases escalated")
    assert "structuring" in spec2.signals and "ESCALATE" in spec2.actions
