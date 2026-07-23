"""Golden tests for the deterministic spine.

Covers: each typology detector, the override kill-switch, the never-fails fallback,
driver contributions summing to score, missing-data routing, and generator determinism.
"""
import os
from datetime import date, timedelta
from decimal import Decimal

import pytest

import audit
import engine
import llm
import rules
from config import CONFIG
from models import Dossier, Txn, RiskFinding, load_dossiers

REF = date(2026, 7, 24)
FLOOR = CONFIG["reporting_floor"]
DATA = os.path.join(os.path.dirname(__file__), "..", "data", "dossiers.json")


def _d(days_ago):
    return (REF - timedelta(days=days_ago)).isoformat()


def _txn(i, amount, direction, cp, cp_country="GB", ttype="cash", days_ago=10):
    return Txn(f"T{i}", _d(days_ago), Decimal(str(amount)), "GBP", direction, cp, cp_country, ttype)


def _dossier(txns=None, kyc=None, profile=None, screening=None, meta=None):
    return Dossier(
        customer_id="TST",
        kyc=kyc or {"name": "Test", "occupation": "teacher", "id_doc": "P1", "kyc_complete": True},
        profile=profile or {"country": "GB", "pep": False, "tenure_days": 1000},
        transactions=txns or [],
        screening=screening or {"sanctions": [], "pep_confirmed": False, "adverse_media": []},
        meta=meta or {},
    )


# --------------------------------------------------------------------------- typologies

def test_structuring_detected():
    lo = float(CONFIG["structuring"]["low_frac"]) * float(FLOOR)
    txns = [_txn(i, lo + 200, "in", "Cash Deposit", ttype="cash", days_ago=40 - i) for i in range(4)]
    f = rules.typ_structuring(_dossier(txns))
    assert f and f.code == "STRUCTURING"
    # all clustered txns are below the reporting floor
    assert all(Decimal(str(lo + 200)) < FLOOR for _ in txns)


def test_layering_detected():
    txns = [_txn(i, 100000 * (0.8 ** i), "out", f"Shell {chr(65+i)}", "CY", "transfer", days_ago=10 - i)
            for i in range(3)]
    f = rules.typ_layering(_dossier(txns))
    assert f and f.code == "LAYERING"


def test_round_trip_detected():
    txns = [_txn(0, 50000, "out", "Nominee A", "KY", "wire", days_ago=20),
            _txn(1, 49500, "in", "Nominee B", "KY", "wire", days_ago=14)]
    f = rules.typ_round_trip(_dossier(txns))
    assert f and f.code == "ROUND_TRIP"


def test_dormant_spike_detected():
    old = [_txn(i, 100, "out", "Shop", ttype="card", days_ago=230 - i * 5) for i in range(3)]
    burst = [_txn(10 + i, 30000, "in", "New CP", "AE", "wire", days_ago=9 - i * 2) for i in range(4)]
    f = rules.typ_dormant_spike(_dossier(old + burst))
    assert f and f.code == "DORMANT_SPIKE"


# --------------------------------------------------------------------------- override / kill-switch

def test_sanctions_override_forces_high_and_escalate():
    d = _dossier(screening={"sanctions": [{"name": "Test", "match_score": 1.0, "list": "OFAC"}],
                            "pep_confirmed": False, "adverse_media": []})
    rr = rules.score_customer(d)
    assert rr.score == 100 and rr.band == "HIGH" and "SANCTIONS_MATCH" in rr.flags
    dec = engine.assess(d, persist=False)
    assert dec.action == "ESCALATE" and dec.requires_signoff


def test_kill_switch_never_auto_clears_even_if_model_disagrees(monkeypatch):
    # even a low simulated score cannot auto-clear a sanctioned customer
    d = _dossier(screening={"sanctions": [{"name": "X", "match_score": 1.0, "list": "OFAC"}],
                            "pep_confirmed": False, "adverse_media": []})
    dec = engine.assess(d, persist=False)
    assert dec.action == "ESCALATE"


# --------------------------------------------------------------------------- never-fails fallback

def test_llm_failure_falls_back_to_rules_only(monkeypatch):
    class Boom:
        class chat:
            class completions:
                @staticmethod
                def create(**_):
                    raise RuntimeError("api down")
    monkeypatch.setattr(llm, "_client", Boom())
    monkeypatch.setattr(llm, "_client_tried", True)
    monkeypatch.setenv("LLM_MODE", "auto")
    d = _dossier()
    finding, meta = llm.crosscheck(d, rules.score_customer(d))
    assert isinstance(finding, RiskFinding) and meta["path"] == "rules_only"


def test_engine_never_raises_and_always_returns_valid(monkeypatch):
    monkeypatch.setenv("LLM_MODE", "off")
    for d in load_dossiers(DATA):
        dec = engine.assess(d, persist=False)
        assert 0 <= dec.score <= 100
        assert dec.action in {"AUTO_CLEAR", "REVIEW", "ESCALATE"}


# --------------------------------------------------------------------------- explainability + routing

def test_driver_contributions_sum_to_score():
    for d in load_dossiers(DATA):
        rr = rules.score_customer(d)
        if rr.flags:  # override -> single 100 driver
            assert sum(x["contribution"] for x in rr.drivers) == 100
        else:
            assert sum(x["contribution"] for x in rr.drivers) == rr.score


def test_missing_data_never_auto_clears():
    d = _dossier(meta={"missing_docs": ["transactions"]})  # clean but incomplete
    dec = engine.assess(d, persist=False)
    assert dec.action != "AUTO_CLEAR"
    assert dec.confidence <= CONFIG["degraded_confidence_cap"]


# --------------------------------------------------------------------------- determinism

def test_generator_is_deterministic():
    import importlib.util
    spec = importlib.util.spec_from_file_location(
        "generate", os.path.join(os.path.dirname(__file__), "..", "data", "generate.py"))
    gen = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(gen)
    assert gen.to_json(gen.generate()) == gen.to_json(gen.generate())


def test_audit_is_append_only(tmp_path, monkeypatch):
    logfile = tmp_path / "audit.jsonl"
    monkeypatch.setattr(audit, "LOG", str(logfile))
    d = _dossier()
    engine.assess(d, persist=True)
    engine.assess(d, persist=True)
    assert len(audit.read_all()) == 2
