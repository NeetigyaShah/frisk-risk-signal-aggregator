"""Review message queue — low-confidence LLM cases are produced here for an independent human reviewer.

Real broker: **Redis** (redis-py). The engine/pipeline is the producer (`enqueue_decision`); the human
review panel is the consumer (`pending` / `resolve`). If Redis is unreachable the queue falls back to an
in-process store so the app never hard-crashes — `backend()` reports which is active.
"""
from __future__ import annotations

import json

from frisk.hitl.redis_conn import backend, client as _r  # shared connection + fallback

PENDING = "frisk:review:pending"     # Redis list of customer_ids awaiting review
CASE = "frisk:review:case:"          # Redis hash per case

_mem = {"pending": [], "cases": {}}  # in-process fallback


def enqueue(case: dict) -> None:
    cid = case["customer_id"]
    r = _r()
    if r:
        r.hset(CASE + cid, mapping={"data": json.dumps(case)})
        if cid not in r.lrange(PENDING, 0, -1):
            r.rpush(PENDING, cid)
    else:
        _mem["cases"][cid] = case
        if cid not in _mem["pending"]:
            _mem["pending"].append(cid)


def enqueue_decision(dec) -> None:
    """Produce a review case from a low-confidence engine Decision."""
    detail = dec.llm_detail or {}
    enqueue({
        "customer_id": dec.customer_id, "name": dec.name, "occupation": dec.occupation,
        "country": dec.country, "llm_score": dec.score, "band": dec.band,
        "confidence": dec.confidence, "reason": dec.rationale,
        "source_findings": detail.get("source_findings", []), "verdict": detail.get("verdict"),
        "flags": dec.flags, "status": "pending",
    })


def pending() -> list[dict]:
    r = _r()
    if r:
        out = []
        for cid in r.lrange(PENDING, 0, -1):
            raw = r.hget(CASE + cid, "data")
            if raw:
                out.append(json.loads(raw))
        return out
    return [_mem["cases"][cid] for cid in _mem["pending"] if cid in _mem["cases"]]


def resolve(customer_id: str, resolution: dict) -> None:
    r = _r()
    if r:
        r.lrem(PENDING, 0, customer_id)
        raw = r.hget(CASE + customer_id, "data")
        case = json.loads(raw) if raw else {"customer_id": customer_id}
        case.update(status="resolved", resolution=resolution)
        r.hset(CASE + customer_id, mapping={"data": json.dumps(case)})
    else:
        if customer_id in _mem["pending"]:
            _mem["pending"].remove(customer_id)
        _mem["cases"].setdefault(customer_id, {"customer_id": customer_id}).update(
            status="resolved", resolution=resolution)


def count() -> int:
    return len(pending())


def reset() -> None:
    r = _r()
    if r:
        for cid in r.lrange(PENDING, 0, -1):
            r.delete(CASE + cid)
        r.delete(PENDING)
    _mem["pending"].clear()
    _mem["cases"].clear()


if __name__ == "__main__":
    print("queue backend:", backend())
    reset()
    enqueue({"customer_id": "CUST_TEST", "name": "Test", "llm_score": 55, "band": "MED",
             "confidence": 0.4, "reason": "analysts disagree", "status": "pending"})
    print("pending:", [c["customer_id"] for c in pending()])
    resolve("CUST_TEST", {"human_score": 62, "band": "MED", "action": "REVIEW", "note": "ok", "reviewer": "demo"})
    print("after resolve, pending:", [c["customer_id"] for c in pending()])
