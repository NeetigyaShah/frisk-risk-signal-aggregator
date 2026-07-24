"""Working memory — the orchestrator's per-customer scratchpad (Redis, ephemeral).

One hash per run at ``frisk:scratch:{customer_id}``: the agent writes evolving notes/observations while it
investigates, reads them back across tool-calling turns, and the engine EVICTS the key on every terminal
path (scored / routed-to-human / exception). A sliding TTL is only a crash reaper — DEL is the normal path.
Falls back to an in-process dict when Redis is down so the loop still runs (stateless-ish).
"""
from __future__ import annotations

import json
import uuid

from frisk.config import CONFIG
from frisk.hitl.redis_conn import client

KEY = "frisk:scratch:"
_mem: dict[str, dict] = {}   # in-process fallback: cid -> {field: str}


def _k(cid: str) -> str:
    return KEY + cid


def _hset(cid: str, field: str, value: str) -> None:
    r = client()
    if r:
        r.hset(_k(cid), field, value)
        r.expire(_k(cid), CONFIG["scratchpad_ttl_s"])
    else:
        _mem.setdefault(cid, {})[field] = value


def start(cid: str, facts: dict | None = None) -> str:
    """Begin a run: clear any stale key, stamp run_id + facts, set the TTL backstop. Returns run_id."""
    run_id = uuid.uuid4().hex[:12]
    data = {"run_id": run_id, "facts": json.dumps(facts or {}), "notes": "{}",
            "scratch": "", "stage": "init", "working_score": "", "confidence": ""}
    r = client()
    if r:
        r.delete(_k(cid))
        r.hset(_k(cid), mapping=data)
        r.expire(_k(cid), CONFIG["scratchpad_ttl_s"])
    else:
        _mem[cid] = data
    return run_id


def read(cid: str) -> dict:
    r = client()
    raw = r.hgetall(_k(cid)) if r else _mem.get(cid)
    if not raw:
        return {}
    out = dict(raw)
    out["facts"] = json.loads(out.get("facts") or "{}")
    out["notes"] = json.loads(out.get("notes") or "{}")
    return out


def note(cid: str, key: str, value: str) -> None:
    cur = read(cid)
    if not cur:
        start(cid, {})
        cur = read(cid)
    notes = cur.get("notes", {})
    notes[key] = value
    _hset(cid, "notes", json.dumps(notes))
    # also append to a free-text scratch log for the reviewer
    _hset(cid, "scratch", (cur.get("scratch", "") + f"\n[{key}] {value}").strip())


def set_stage(cid: str, stage: str, working_score: int | None = None, confidence: float | None = None) -> None:
    _hset(cid, "stage", stage)
    if working_score is not None:
        _hset(cid, "working_score", str(working_score))
    if confidence is not None:
        _hset(cid, "confidence", str(confidence))


def evict(cid: str) -> dict:
    """Snapshot then DELETE the scratchpad — called on every terminal path. Returns the snapshot."""
    snap = read(cid)
    r = client()
    if r:
        r.delete(_k(cid))
    else:
        _mem.pop(cid, None)
    return snap


if __name__ == "__main__":  # self-check
    start("C9", {"pep": True})
    note("C9", "cash", "clustered just under 10k")
    set_stage("C9", "synthesize", working_score=55, confidence=0.4)
    r = read("C9")
    assert r["facts"]["pep"] is True and r["notes"]["cash"].startswith("clustered")
    assert r["stage"] == "synthesize" and r["working_score"] == "55"
    snap = evict("C9")
    assert snap["notes"]["cash"].startswith("clustered")
    assert read("C9") == {}
    print("scratchpad self-check OK: start/note/stage/read/evict")
