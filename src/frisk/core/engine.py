"""Orchestrator — retrieve memory → parallel specialists → agentic orchestrator → confidence-gate → persist.

Fully LLM: no deterministic scoring, no sanctions rail. The agent's tool-call trace is the audit record.
Per customer:
  1. ``memory.retrieve`` pulls per-customer history + similar cases + lessons.
  2. specialists score their domain in parallel (memory-fed).
  3. the agent investigates with tools and emits a RiskFinding + confidence + trace.
  4. ``route_llm`` disposes by band; LOW confidence → the human review queue.
  5. write back to the relational store + episodic case-bank + append-only audit; ALWAYS evict the scratchpad.
"""
from __future__ import annotations

import hashlib
import json
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone

from frisk.ai import agent, memory
from frisk.ai.specialists import run_specialists
from frisk.config import CONFIG
from frisk.core.models import AuditRecord, Disposition, Dossier
from frisk.data import audit
from frisk.hitl import queue, scratchpad

RT = CONFIG["routing"]


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
    engine_path: str            # "agent"
    key_signals: list
    trace: list                 # ordered tool-call steps (the audit "why")
    rationale: str
    fingerprint: str
    country: str = ""
    pep: bool = False
    occupation: str = ""
    opinions: list = field(default_factory=list)         # parallel specialists' views
    injected_memory: dict = field(default_factory=dict)  # what memory was fed in (auditability)
    evidence_refs: list = field(default_factory=list)


def _fingerprint(d: Dossier) -> str:
    payload = json.dumps({
        "customer_id": d.customer_id, "kyc": d.kyc, "profile": d.profile,
        "transactions": [asdict(t) for t in d.transactions], "screening": d.screening,
    }, sort_keys=True, default=str)
    return hashlib.sha256(payload.encode()).hexdigest()


def route_llm(score: int, confidence: float) -> Disposition:
    """The LLM's score decides; LOW confidence routes the case to a human. No deterministic rails."""
    if confidence < CONFIG["confidence_threshold"]:
        return Disposition("PENDING_REVIEW", "human_queue", False)
    if score < RT["auto_clear"]:
        return Disposition("AUTO_CLEAR", "none", False)
    if score < RT["junior"]:
        return Disposition("REVIEW", "junior", False)
    if score < RT["senior"]:
        return Disposition("REVIEW", "senior", False)
    return Disposition("ESCALATE", "senior", True)


def assess(d: Dossier, actor: str | None = None, persist: bool = True) -> Decision:
    cid = d.customer_id
    mem = memory.retrieve(d)
    scratchpad.start(cid, {"pep": bool(d.profile.get("pep")), "country": d.profile.get("country")})
    try:
        # stage is what the live progress UI reads to say what is happening right now
        scratchpad.set_stage(cid, "specialists")
        opinions = run_specialists(d, mem)
        scratchpad.set_stage(cid, "agent")
        finding, detail = agent.score(d, mem, opinions)
        scratchpad.set_stage(cid, "synthesize")
        conf = detail["confidence"]
        disp = route_llm(finding.score, conf)
        ts = datetime.now(timezone.utc).isoformat()
        fp = _fingerprint(d)

        dec_dict = {
            "customer_id": cid, "name": d.kyc.get("name", cid), "entity_type": d.profile.get("entity_type"),
            "country": d.profile.get("country", ""), "occupation": d.kyc.get("occupation", ""),
            "pep": bool(d.profile.get("pep")), "ts": ts, "score": finding.score, "band": finding.band,
            "confidence": conf, "disposition": disp.action, "key_signals": finding.key_signals,
            "rationale": finding.rationale, "trace_ref": fp[:16], "human_verified": False, "corrected_score": None,
        }
        decision = Decision(
            customer_id=cid, name=dec_dict["name"], score=finding.score, band=finding.band, confidence=conf,
            action=disp.action, tier=disp.tier, requires_signoff=disp.requires_signoff, engine_path="agent",
            key_signals=finding.key_signals, trace=detail["trace"], rationale=finding.rationale, fingerprint=fp,
            country=dec_dict["country"], pep=dec_dict["pep"], occupation=dec_dict["occupation"],
            opinions=[o.model_dump() for o in opinions], injected_memory=detail.get("injected_memory", {}),
            evidence_refs=finding.evidence_refs,
        )

        if persist:
            rec = AuditRecord(
                record_id=hashlib.sha256(f"{cid}{ts}{disp.action}".encode()).hexdigest()[:16],
                customer_id=cid, ts=ts, actor=actor or f"engine:{CONFIG['policy_version']}",
                action=disp.action, score=finding.score, confidence=conf, engine_path="agent",
                band=finding.band, thresholds={"routing": RT, "bands": CONFIG["bands"]},
                trace=detail["trace"], key_signals=finding.key_signals, rationale=finding.rationale,
                ruleset_version=CONFIG["policy_version"], input_fingerprint=fp,
            )
            audit.append(rec)
            memory.write_back(dec_dict, d)
            if disp.action == "PENDING_REVIEW":
                snap = scratchpad.read(cid)
                queue.enqueue({
                    "customer_id": cid, "name": dec_dict["name"], "occupation": dec_dict["occupation"],
                    "country": dec_dict["country"], "llm_score": finding.score, "band": finding.band,
                    "confidence": conf, "reason": finding.rationale,
                    "opinions": decision.opinions, "trace": detail["trace"],
                    "scratchpad": snap.get("notes", {}), "status": "pending",
                })
        return decision
    finally:
        scratchpad.evict(cid)   # working memory is thrown away on every exit


def assess_all(dossiers: list[Dossier], persist: bool = True) -> list[Decision]:
    return [assess(d, persist=persist) for d in dossiers]


def log_analyst_action(customer_id: str, action: str, actor: str, rationale: str,
                       override_of: str | None = None, signoff_by: str | None = None) -> AuditRecord:
    """Record a human decision (approve / escalate / override) — maker-checker on ESCALATE."""
    ts = datetime.now(timezone.utc).isoformat()
    rec = AuditRecord(
        record_id=hashlib.sha256(f"{customer_id}{ts}{action}{actor}".encode()).hexdigest()[:16],
        customer_id=customer_id, ts=ts, actor=actor, action=action, score=-1, confidence=-1.0,
        engine_path="analyst", band="", thresholds={}, trace=[], key_signals=[], rationale=rationale,
        ruleset_version=CONFIG["policy_version"], input_fingerprint="",
        override_of=override_of, signoff_by=signoff_by,
    )
    audit.append(rec)
    return rec


if __name__ == "__main__":  # self-check (mock provider): python -m frisk.core.engine
    from collections import Counter

    from frisk.core.models import load_dossiers
    from frisk.data import store

    audit.reset(); store.reset()
    try:
        from frisk.data import casebank
        casebank.reset()
    except Exception:
        pass
    ds = load_dossiers()
    decisions = assess_all(ds)
    dist = Counter(dec.action for dec in decisions)
    for dec in sorted(decisions, key=lambda x: -x.score):
        print(f"{dec.customer_id} {dec.band:7s} score={dec.score:3d} conf={dec.confidence:.2f} "
              f"{dec.action:14s} steps={len(dec.trace)}")
    print("\ndisposition distribution:", dict(dist))
    assert all(0 <= d.score <= 100 and d.engine_path == "agent" for d in decisions)
    assert len(store.latest_all()) == len(ds), "every customer should have a stored assessment"
    print("engine self-check OK: agent-scored, persisted, valid decisions")
