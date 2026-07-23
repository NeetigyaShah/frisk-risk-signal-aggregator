"""Orchestrator: rules (source of truth) -> LLM cross-check -> reconcile(confidence) -> route() -> audit.

Routing invariants (all enforced here, tested in tests/):
  - kill-switch (sanctions / PEP-in-high-risk-geo) escalates FIRST, regardless of score.
  - the rules-only / degraded path never auto-clears.
  - low confidence (rules<->LLM disagreement) never auto-clears.
"""
from __future__ import annotations

import hashlib
import json
from dataclasses import asdict, dataclass
from datetime import datetime, timezone

import audit
from config import CONFIG
from llm import crosscheck
from models import AuditRecord, Disposition, Dossier
from rules import score_customer

HARD = set(CONFIG["hard_escalate"])
RT = CONFIG["routing"]
LOW_CONF = 0.60  # below this, an otherwise-clear case is held for review


@dataclass
class Decision:
    customer_id: str
    name: str
    score: int
    band: str
    confidence: float
    action: str
    tier: str
    requires_signoff: bool
    engine_path: str
    flags: list
    drivers: list
    findings: list        # list[dict] for UI/audit
    rationale: str        # LLM (or rules-only) rationale
    llm_score: int
    fingerprint: str
    country: str = ""
    pep: bool = False
    occupation: str = ""


def _fingerprint(d: Dossier) -> str:
    payload = json.dumps({
        "customer_id": d.customer_id, "kyc": d.kyc, "profile": d.profile,
        "transactions": [asdict(t) for t in d.transactions],
        "screening": d.screening,
    }, sort_keys=True, default=str)
    return hashlib.sha256(payload.encode()).hexdigest()


def reconcile(rules_score: int, llm_score: int, path: str) -> float:
    if path == "rules_only":
        return round(CONFIG["degraded_confidence_cap"], 2)  # degraded -> capped low
    return round(1 - abs(rules_score - llm_score) / 100, 2)


def route(score: int, flags: set, degraded: bool, confidence: float) -> Disposition:
    if flags & HARD:                                   # kill-switch first
        return Disposition("ESCALATE", "named_reviewer", True)
    if score < RT["auto_clear"]:
        disp = Disposition("AUTO_CLEAR", "none", False)
    elif score < RT["junior"]:
        disp = Disposition("REVIEW", "junior", False)
    elif score < RT["senior"]:
        disp = Disposition("REVIEW", "senior", False)
    else:
        disp = Disposition("ESCALATE", "senior", True)
    # degraded (rules-only / missing data) or low-confidence results never silently auto-clear
    if disp.action == "AUTO_CLEAR" and (degraded or confidence < LOW_CONF):
        disp = Disposition("REVIEW", "junior", False)
    return disp


def _incomplete(d: Dossier) -> bool:
    return bool(d.meta.get("missing_docs")) or not d.transactions or not d.kyc.get("kyc_complete", True)


def assess(d: Dossier, actor: str | None = None, persist: bool = True) -> Decision:
    rr = score_customer(d)
    lf, meta = crosscheck(d, rr)
    incomplete = _incomplete(d)
    conf = reconcile(rr.score, lf.score, meta["path"])
    if incomplete:                                     # missing data -> cap confidence
        conf = min(conf, round(CONFIG["degraded_confidence_cap"], 2))
    degraded = meta["path"] == "rules_only" or incomplete
    disp = route(rr.score, rr.flags, degraded, conf)

    ts = datetime.now(timezone.utc).isoformat()
    fp = _fingerprint(d)
    rec = AuditRecord(
        record_id=hashlib.sha256(f"{d.customer_id}{ts}{disp.action}".encode()).hexdigest()[:16],
        customer_id=d.customer_id, ts=ts,
        actor=actor or f"engine:{CONFIG['ruleset_version']}",
        action=disp.action, score=rr.score, confidence=conf, engine_path=meta["path"],
        band=rr.band, thresholds={"routing": RT, "bands": CONFIG["bands"]},
        drivers=rr.drivers, rationale=lf.rationale,
        ruleset_version=CONFIG["ruleset_version"], input_fingerprint=fp,
    )
    if persist:
        audit.append(rec)

    return Decision(
        customer_id=d.customer_id, name=d.kyc.get("name", d.customer_id),
        score=rr.score, band=rr.band, confidence=conf,
        action=disp.action, tier=disp.tier, requires_signoff=disp.requires_signoff,
        engine_path=meta["path"], flags=sorted(rr.flags), drivers=rr.drivers,
        findings=[asdict(f) for f in rr.findings], rationale=lf.rationale,
        llm_score=lf.score, fingerprint=fp,
        country=d.profile.get("country", ""), pep=bool(d.profile.get("pep")),
        occupation=d.kyc.get("occupation", ""),
    )


def assess_all(dossiers: list[Dossier], persist: bool = True) -> list[Decision]:
    return [assess(d, persist=persist) for d in dossiers]


def log_analyst_action(customer_id: str, action: str, actor: str, rationale: str,
                       override_of: str | None = None, signoff_by: str | None = None) -> AuditRecord:
    """Record a human decision (approve / escalate / override) — maker-checker on ESCALATE."""
    ts = datetime.now(timezone.utc).isoformat()
    rec = AuditRecord(
        record_id=hashlib.sha256(f"{customer_id}{ts}{action}{actor}".encode()).hexdigest()[:16],
        customer_id=customer_id, ts=ts, actor=actor, action=action, score=-1, confidence=-1.0,
        engine_path="analyst", band="", thresholds={}, drivers=[], rationale=rationale,
        ruleset_version=CONFIG["ruleset_version"], input_fingerprint="",
        override_of=override_of, signoff_by=signoff_by,
    )
    audit.append(rec)
    return rec


if __name__ == "__main__":
    import os
    from collections import Counter
    from models import load_dossiers

    audit.reset()
    ds = load_dossiers(os.path.join(os.path.dirname(__file__), "..", "data", "dossiers.json"))
    decisions = assess_all(ds)
    dist = Counter(dec.action for dec in decisions)
    for dec in sorted(decisions, key=lambda x: -x.score):
        sign = "*" if dec.requires_signoff else " "
        print(f"{dec.customer_id} {dec.band:4s} score={dec.score:3d} conf={dec.confidence:.2f} "
              f"{dec.action:10s}{sign} [{dec.tier}] path={dec.engine_path}")
    print("\ndisposition distribution:", dict(dist))
    assert len(audit.read_all()) == 20, "audit log should have one record per customer"
    # invariant checks
    by_id = {d.customer_id: d for d in ds}
    for dec in decisions:
        if dec.flags:
            assert dec.action == "ESCALATE", f"{dec.customer_id} has kill-switch flag but was {dec.action}"
        d = by_id[dec.customer_id]
        if d.meta.get("missing_docs") or not d.transactions:
            assert dec.action != "AUTO_CLEAR", f"{dec.customer_id} has missing data but was auto-cleared"
    print("engine self-check OK: 20 audit records, no kill-switch auto-clear, no missing-data auto-clear")
