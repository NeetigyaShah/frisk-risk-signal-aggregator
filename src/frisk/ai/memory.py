"""Layered-memory orchestration — retrieve, assemble, and write back the five memory tiers.

Ties the stores together into the one loop the engine runs per customer:
  RETRIEVE  per-customer history (store) + similar cases (casebank) + lessons (store) + cheat-sheets (reference)
  ASSEMBLE  format each tier into specialist/orchestrator prompt text (and log WHAT was injected — auditability)
  WRITE-BACK  append the assessment (store) + add a case-card (casebank); human-verified cases weigh highest

Working memory (the Redis scratchpad) is handled separately by ``hitl/scratchpad.py``.
"""
from __future__ import annotations

from frisk.config import CONFIG
from frisk.data import casebank, reference, store


def features(d) -> dict:
    """Structured retrieval key from a Dossier (pre-score, so no band)."""
    return {"entity_type": (d.profile or {}).get("entity_type"),
            "country": (d.profile or {}).get("country"),
            "occupation": (d.kyc or {}).get("occupation"),
            "pep": bool((d.profile or {}).get("pep"))}


def kyc_cheatsheet() -> str:
    return reference.load("high_risk")


def txn_cheatsheet() -> str:
    return reference.load("typologies")


def history_summary(history: list[dict]) -> str:
    if not history:
        return "No prior assessments on file for this customer."
    parts = [f"{h.get('ts', '?')[:10]} {h.get('band')}({h.get('score')})" for h in history]
    return "Prior assessments (newest first): " + "; ".join(parts)


def _fewshot_text(sims: list[dict]) -> str:
    if not sims:
        return ""
    lines = [f"- {s['card']}  => {s['band']}/{s['disposition']}"
             + ("  [reviewer-verified]" if s.get("human_verified") else "") for s in sims]
    return "Similar past cases (for calibration, not rules):\n" + "\n".join(lines)


def fewshot_for(domain: str, d, k: int | None = None) -> str:
    """Episodic few-shot for a specialist: similar past cases + recent human corrections."""
    k = k or CONFIG["memory_topk"]
    sims = casebank.similar(features(d), k=k, prefer_verified=True)
    text = _fewshot_text(sims)
    try:
        from frisk.hitl.feedback import fewshot_block
        corr = fewshot_block()
        if corr:
            text = (text + "\n\n" if text else "") + "Recent reviewer corrections:\n" + corr
    except Exception:
        pass
    return text


def retrieve(d) -> dict:
    """Pull every retrievable tier for one customer and log what was injected."""
    k = CONFIG["memory_topk"]
    hist = store.history(d.customer_id, k=k)
    sims = casebank.similar(features(d), k=k, prefer_verified=True)
    lessons = store.top_lessons(k=k)
    injected = {"history_n": len(hist), "similar_n": len(sims), "lessons_n": len(lessons),
                "similar_ids": [s["customer_id"] for s in sims],
                "history_summary": history_summary(hist)}
    return {"history": hist, "similar": sims, "lessons": lessons, "injected": injected}


def make_card(dec: dict) -> str:
    """A one-line case-card summarising a finished assessment for episodic recall."""
    sig = ", ".join(dec.get("key_signals", [])[:4])
    return (f"{dec.get('occupation','?')}, {dec.get('country','?')}"
            + (", PEP" if dec.get("pep") else "")
            + (f"; signals: {sig}" if sig else "")
            + f" => {dec.get('band')}/{dec.get('disposition')} (score {dec.get('score')})")


def write_back(dec: dict, d) -> None:
    """Persist the assessment (per-customer history) and add an episodic case-card."""
    store.record_assessment(dec)
    feats = features(d)
    feats["band"] = dec.get("band")
    if dec.get("key_signals"):
        feats["top_signal"] = dec["key_signals"][0]
    casebank.add(dec["customer_id"], make_card(dec), feats, dec.get("band", ""),
                 dec.get("disposition", ""), human_verified=bool(dec.get("human_verified")),
                 created_ts=dec.get("ts", ""))


if __name__ == "__main__":  # self-check
    import types
    store.reset(); casebank.reset()

    def dossier(cid, country, occ, pep):
        return types.SimpleNamespace(customer_id=cid, profile={"country": country, "entity_type": "individual", "pep": pep},
                                     kyc={"occupation": occ})

    d = dossier("C1", "SY", "shell company director", True)
    dec = {"customer_id": "C1", "name": "X", "entity_type": "individual", "country": "SY",
           "occupation": "shell company director", "pep": True, "ts": "2026-01-01T00:00:00Z",
           "score": 88, "band": "HIGH", "confidence": 0.9, "disposition": "ESCALATE",
           "key_signals": ["high-risk jurisdiction", "opaque ownership"], "rationale": "r",
           "trace_ref": "t", "human_verified": True, "corrected_score": None}
    write_back(dec, d)
    # a second, similar customer should retrieve C1 as an episodic neighbour
    d2 = dossier("C2", "SY", "shell company director", True)
    mem = retrieve(d2)
    assert mem["injected"]["similar_n"] == 1, mem["injected"]
    assert "shell company director" in mem["similar"][0]["card"]
    # C1's own history is retrievable
    assert retrieve(d)["injected"]["history_n"] == 1
    assert "typolog" in txn_cheatsheet().lower() or "structuring" in txn_cheatsheet().lower()
    print("memory self-check OK: retrieve + write-back across tiers")
