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
from frisk.hitl.redis_conn import client, mark_down

KEY = "frisk:scratch:"
_mem: dict[str, dict] = {}   # in-process fallback: cid -> {field: str}


def _k(cid: str) -> str:
    return KEY + cid


def _hset(cid: str, field: str, value: str) -> None:
    # Working memory must never be able to fail a scoring run. If Redis drops mid-run, degrade to the
    # in-process store instead of raising — a lost scratchpad costs nothing, a 500 costs the decision.
    r = client()
    if r:
        try:
            r.hset(_k(cid), field, value)
            r.expire(_k(cid), CONFIG["scratchpad_ttl_s"])
            return
        except Exception:
            mark_down()
    _mem.setdefault(cid, {})[field] = value


def start(cid: str, facts: dict | None = None) -> str:
    """Begin a run: clear any stale key, stamp run_id + facts, set the TTL backstop. Returns run_id."""
    run_id = uuid.uuid4().hex[:12]
    data = {"run_id": run_id, "facts": json.dumps(facts or {}), "notes": "{}", "steps": "[]",
            "scratch": "", "stage": "init", "working_score": "", "confidence": ""}
    r = client()
    if r:
        try:
            r.delete(_k(cid))
            r.hset(_k(cid), mapping=data)
            r.expire(_k(cid), CONFIG["scratchpad_ttl_s"])
            return run_id
        except Exception:
            mark_down()
    _mem[cid] = data
    return run_id


def read(cid: str) -> dict:
    r = client()
    raw = None
    if r:
        try:
            raw = r.hgetall(_k(cid))
        except Exception:
            mark_down()
    if raw is None:
        raw = _mem.get(cid)
    if not raw:
        return {}
    out = dict(raw)
    # the in-process fallback hands back the same objects it was given, so a field may already be
    # decoded — only json.loads what is still a string.
    def _dec(v, default):
        if v in (None, ""):
            return default
        return json.loads(v) if isinstance(v, (str, bytes, bytearray)) else v

    out["facts"] = _dec(out.get("facts"), {})
    out["notes"] = _dec(out.get("notes"), {})
    out["steps"] = _dec(out.get("steps"), [])
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


def step(cid: str, tool: str, detail: str) -> None:
    """Append one tool call to an ordered progress log.

    Distinct from note(): notes are a keyed hash the agent reads back, so two `read_document` calls
    overwrite each other. The UI needs the ordered sequence, including repeats, so it gets its own
    append-only list. Bounded to the last 40 entries — this is a progress feed, not the audit trail.
    """
    cur = read(cid)
    if not cur:
        start(cid, {})
        cur = read(cid)
    log = list(cur.get("steps") or [])   # read() already decoded this
    log.append({"tool": tool, "detail": detail})
    _hset(cid, "steps", json.dumps(log[-40:]))


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
        try:
            r.delete(_k(cid))
        except Exception:
            mark_down()
    _mem.pop(cid, None)   # always clear the fallback too — eviction must be unconditional
    return snap


if __name__ == "__main__":  # self-check
    start("C9", {"pep": True})
    note("C9", "cash", "clustered just under 10k")
    set_stage("C9", "synthesize", working_score=55, confidence=0.4)
    # the ordered feed must keep repeats — note() would collapse these two into one
    step("C9", "read_document", "id_document.txt")
    step("C9", "read_document", "rm_notes.txt")
    step("C9", "query_transactions", "35 rows")
    r = read("C9")
    assert r["facts"]["pep"] is True and r["notes"]["cash"].startswith("clustered")
    assert r["stage"] == "synthesize" and r["working_score"] == "55"
    assert [s["tool"] for s in r["steps"]] == ["read_document", "read_document", "query_transactions"]
    assert r["steps"][1]["detail"] == "rm_notes.txt"
    snap = evict("C9")
    assert snap["notes"]["cash"].startswith("clustered")
    assert read("C9") == {}
    print("scratchpad self-check OK: start/note/stage/read/evict")
