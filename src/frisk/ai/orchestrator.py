"""Multi-step LLM orchestration (LangGraph + LangChain).

No single LLM call decides the outcome. The dossier is analysed by THREE domain specialists in
parallel (KYC, transactions, screening), a synthesis node correlates them, a verification node
adversarially re-checks the synthesis against the evidence (chain-of-verification), and a
deterministic finalize node packages the result. Every node degrades on its own — a failed step
appends an error and the graph continues; a totally dead graph is caught by the caller and falls
back to rules-only. The rules score is still the auditable source of truth; this only sharpens the
advisory second opinion.

Graph:  START ─┬─ analyze_kyc ───────┐
               ├─ analyze_transactions├─► synthesize ─► verify ─► finalize ─► END
               └─ analyze_screening ──┘
"""
from __future__ import annotations

import operator
import os
from typing import Annotated, Any, TypedDict

from frisk.config import CONFIG
from frisk.core.models import RiskFinding, SourceFinding, Verdict, band_for, BAND_LABEL

_LLM = CONFIG["llm"]

# --------------------------------------------------------------------------- LLM runnables (lazy)

_runnables: dict = {}


def _get_runnables():
    if _runnables:
        return _runnables
    from frisk.ai.providers import get_provider
    prov = get_provider()               # the configured provider (default: openrouter)
    if not prov.available():
        return None
    try:
        llm = prov.chat_model()             # LangChain chat model from the provider boundary
        if llm is None:
            return None
        _runnables["source"] = llm.with_structured_output(SourceFinding, method="json_mode")
        _runnables["synth"] = llm.with_structured_output(RiskFinding, method="json_mode")
        _runnables["verdict"] = llm.with_structured_output(Verdict, method="json_mode")
    except Exception:
        return None
    return _runnables


def _invoke_retry(runnable, prompt, tries=3):
    """Retry structured invoke on transient API errors OR occasional bad-JSON parse failures."""
    last = None
    for _ in range(tries):
        try:
            return runnable.invoke(prompt)
        except Exception as e:
            last = e
    raise last


# --------------------------------------------------------------------------- per-domain feature text

def _docs(d, *substrings) -> str:
    """Concatenate the UNSTRUCTURED documents whose filename matches any substring (id doc, RM notes, news)."""
    picked = [x for x in getattr(d, "documents", []) if any(s in x["name"] for s in substrings)]
    if not picked:
        return ""
    return "\n\nUNSTRUCTURED DOCUMENTS:\n" + "\n---\n".join(f"[{x['name']}]\n{x['text'].strip()}" for x in picked)


def _kyc_text(d) -> str:
    p, k = d.profile, d.kyc
    return (f"nationality/country={k.get('nationality')}/{p.get('country')}; occupation={k.get('occupation')}; "
            f"PEP={p.get('pep')}; account_age_days={p.get('tenure_days')}; "
            f"kyc_complete={k.get('kyc_complete')}; id_doc_present={k.get('id_doc') is not None}"
            + _docs(d, "id_document", "rm_notes"))  # read the ID OCR + relationship-manager notes


def _txn_text(d) -> str:
    t = d.transactions
    tin = sum(float(x.amount) for x in t if x.direction == "in")
    tout = sum(float(x.amount) for x in t if x.direction == "out")
    cash = sum(float(x.amount) for x in t if x.direction == "in" and x.txn_type == "cash")
    cps = sorted({x.counterparty_country for x in t})
    return (f"{len(t)} transactions; credits={tin:.0f}; debits={tout:.0f}; cash_in={cash:.0f}; "
            f"counterparty_countries={cps}; "
            f"note: watch for structuring (many just-under-threshold cash deposits), layering "
            f"(rapid onward transfers), round-tripping, dormant-then-spike."
            + _docs(d, "correspondence"))  # read emails that might explain (or expose) transfers


def _screening_text(d) -> str:
    s = d.screening
    return (f"sanctions_hits={[h.get('name') for h in s.get('sanctions', [])]}; "
            f"pep_confirmed={s.get('pep_confirmed')}; "
            f"adverse_media={[m.get('headline') for m in s.get('adverse_media', [])]}"
            + _docs(d, "adverse_media"))  # read the full news article text, not just the headline


# --------------------------------------------------------------------------- graph state + nodes

class RiskState(TypedDict):
    dossier: Any
    rules_score: int
    rules_band: str
    source_findings: Annotated[list, operator.add]
    errors: Annotated[list, operator.add]
    synthesis: dict
    verdict: dict


def _analyst(domain: str, text_fn):
    """Build a domain-analyst node; each is one structured LLM call, degrading on error."""
    def node(state: RiskState):
        try:
            r = _invoke_retry(_get_runnables()["source"],
                f"You are an AML {domain} analyst. Assess ONLY the {domain} risk from the facts below and "
                f"respond in JSON with keys domain,risk_level(low|medium|high),signals(list),note. "
                f"Set domain='{domain}'. Be calibrated: rate LOW when no specific red flag is present. "
                f"A normal pattern (e.g. domestic salary-in / card-out with no clustering, complete KYC, "
                f"clean screening) is LOW risk — do NOT invent risk from ordinary activity.\n\n"
                f"FACTS: {text_fn(state['dossier'])}")
            return {"source_findings": [r.model_dump()]}
        except Exception as e:
            return {"source_findings": [{"domain": domain, "risk_level": "medium", "signals": [],
                                         "note": f"{domain} analysis unavailable"}],
                    "errors": [f"{domain}:{type(e).__name__}"]}
    return node


def _fewshot() -> str:
    """Recent human corrections injected as calibration examples (the closed feedback loop)."""
    try:
        from frisk.hitl.feedback import fewshot_block
        return fewshot_block()
    except Exception:
        return ""


def synthesize(state: RiskState):
    findings = state.get("source_findings", [])
    summary = "; ".join(f"[{f['domain']}={f['risk_level']}] {f['note']}" for f in findings)
    try:
        r = _invoke_retry(_get_runnables()["synth"],
            _fewshot() +
            "You are a senior AML analyst. Correlate the three domain assessments below into ONE overall "
            "money-laundering risk view. Weigh how signals REINFORCE across domains. Also report your OWN "
            "confidence 0-1 — be honest: use LOW confidence if the domains disagree or the evidence is thin "
            "(those cases go to a human reviewer). Respond in JSON with keys "
            "customer_id,score(0-100),band,rationale,key_signals(list),confidence(0-1).\n\n"
            f"DOMAIN ASSESSMENTS: {summary}")
        return {"synthesis": r.model_dump()}
    except Exception as e:
        return {"errors": [f"synthesize:{type(e).__name__}"]}


def verify(state: RiskState):
    synth = state.get("synthesis")
    if not synth:
        return {}
    findings = state.get("source_findings", [])
    summary = "; ".join(f"[{f['domain']}={f['risk_level']}] {f['note']}" for f in findings)
    try:
        r = _invoke_retry(_get_runnables()["verdict"],
            "You are a compliance QA reviewer. Adversarially check whether the SYNTHESIS is justified by the "
            "domain evidence. If the score is too high or too low given the evidence, correct it. Respond in JSON "
            "with keys consistent(bool),adjusted_score(0-100),note.\n\n"
            f"SYNTHESIS: score={synth.get('score')} rationale={synth.get('rationale')}\n"
            f"EVIDENCE: {summary}")
        return {"verdict": r.model_dump()}
    except Exception as e:
        return {"errors": [f"verify:{type(e).__name__}"]}


def finalize(state: RiskState) -> dict:
    """Deterministic packaging — no LLM. Robust to any missing upstream step."""
    synth = state.get("synthesis") or {}
    verd = state.get("verdict") or {}
    if synth:
        # the QA reviewer's corrected score wins when present, else the synthesis score
        score = int(verd["adjusted_score"]) if verd.get("adjusted_score") is not None else int(synth["score"])
        rationale = synth.get("rationale") or "multi-step assessment"
    else:  # synthesis failed entirely -> lean on rules
        score = int(state.get("rules_score", 0))
        rationale = "multi-step synthesis unavailable; using deterministic rules score"
    signals = sorted({s for f in state.get("source_findings", []) for s in f.get("signals", [])})
    finding = RiskFinding(customer_id="", score=max(0, min(100, score)),
                          band=BAND_LABEL[band_for(max(0, min(100, score)))],
                          rationale=rationale[:500], key_signals=signals[:12])
    return {"synthesis": {**synth, "_final": finding.model_dump()}}


# --------------------------------------------------------------------------- compiled graph (once)

_graph = None


def _get_graph():
    global _graph
    if _graph is not None:
        return _graph
    from langgraph.graph import StateGraph, START, END
    g = StateGraph(RiskState)
    g.add_node("analyze_kyc", _analyst("kyc", _kyc_text))
    g.add_node("analyze_transactions", _analyst("transactions", _txn_text))
    g.add_node("analyze_screening", _analyst("screening", _screening_text))
    g.add_node("synthesize", synthesize)
    g.add_node("verify", verify)
    g.add_node("finalize", finalize)
    for n in ("analyze_kyc", "analyze_transactions", "analyze_screening"):
        g.add_edge(START, n)          # fan-out (parallel)
        g.add_edge(n, "synthesize")   # fan-in
    g.add_edge("synthesize", "verify")
    g.add_edge("verify", "finalize")
    g.add_edge("finalize", END)
    _graph = g.compile()
    return _graph


def available() -> bool:
    return _get_runnables() is not None


_LVL = {"low": 17, "medium": 50, "high": 85}


def _composite_confidence(finding, out, detail) -> dict:
    """confidence = min(self-report, node agreement, verifier consistency), penalised for node errors."""
    synth = out.get("synthesis") or {}
    self_c = float(synth.get("confidence", finding.confidence) or 0.6)
    scores = [_LVL.get(sf.get("risk_level"), 50) for sf in detail["source_findings"]] + [finding.score]
    node_agreement = round(1.0 - (max(scores) - min(scores)) / 100, 2) if scores else 0.5
    verd = detail.get("verdict") or {}
    verifier = 1.0 if verd.get("consistent") else 0.5
    err_pen = 0.4 if detail["errors"] else 1.0
    composite = round(max(0.0, min(self_c, node_agreement, verifier, err_pen)), 2)
    return {"confidence": composite, "self_confidence": round(self_c, 2), "node_agreement": node_agreement}


def assess_multistep(dossier, rules_result) -> tuple[RiskFinding, dict]:
    """Run the multi-step graph. Returns (final RiskFinding, detail incl. composite confidence)."""
    init = {"dossier": dossier, "rules_score": rules_result.score, "rules_band": rules_result.band,
            "source_findings": [], "errors": []}
    out = _get_graph().invoke(init, config={"configurable": {"max_concurrency": 3}})
    final_dict = (out.get("synthesis") or {}).get("_final")
    finding = RiskFinding.model_validate(final_dict) if final_dict else RiskFinding(
        customer_id="", score=rules_result.score, band=BAND_LABEL[rules_result.band],
        rationale="graph produced no synthesis; rules score used", key_signals=[], confidence=0.3)
    finding.customer_id = dossier.customer_id
    detail = {"source_findings": out.get("source_findings", []), "verdict": out.get("verdict"),
              "errors": out.get("errors", []), "steps": 5}
    detail.update(_composite_confidence(finding, out, detail))
    return finding, detail


if __name__ == "__main__":
    from frisk.core.models import load_dossiers
    from frisk.core.rules import score_customer
    ds = load_dossiers()
    for d in (ds[18], ds[0]):  # a critical one and a clean one
        rr = score_customer(d)
        f, detail = assess_multistep(d, rr)
        print(f"\n{d.customer_id}: rules={rr.score} graph={f.score} band={f.band}")
        for sf in detail["source_findings"]:
            print(f"  - {sf['domain']}: {sf['risk_level']} :: {sf['note'][:70]}")
        print(f"  verdict: {detail['verdict']}  errors: {detail['errors']}")
