"""Never-fails LLM cross-check boundary.

Deterministic rules are the source of truth. This module asks a provider (see ``ai/providers``) for an
INDEPENDENT second opinion — single call or the multi-step LangGraph graph — and GUARANTEES a valid
`RiskFinding` back. Missing key, network failure, schema-invalid output, dead graph: every path funnels
through one place into the rules-only (or simulated) finding. Nothing here raises into the engine.

Cascade: cache → multi-step graph → single provider call (retry+backoff) → rules-only / simulated.
"""
from __future__ import annotations

import hashlib
import json
import os
import threading
import time

from frisk.config import CONFIG, BAND_LABEL, band_for
from frisk.core.models import Dossier, RiskResult, RiskFinding
from frisk.paths import LLM_CACHE as _CACHE_PATH
from frisk.ai.providers import get_provider

_LLM = CONFIG["llm"]
_MODEL_KEY = {"openrouter": "openrouter_model", "nvidia": "nvidia_model", "gemini": "gemini_model",
              "anthropic": "model", "mock": "mock"}

# Opt-in LangSmith observability: real @traceable if installed + LANGSMITH_TRACING=true, else a no-op.
try:
    from langsmith import traceable as _ls_traceable

    def traceable(*a, **k):
        if a and callable(a[0]) and not k:
            return _ls_traceable(a[0])
        return _ls_traceable(*a, **k)
except Exception:
    def traceable(*a, **k):
        if a and callable(a[0]) and not k:
            return a[0]
        return lambda f: f

# --------------------------------------------------------------------------- disk cache

_cache: dict | None = None
_cache_lock = threading.Lock()


def _load_cache() -> dict:
    global _cache
    if _cache is None:
        try:
            _cache = json.loads(open(_CACHE_PATH, encoding="utf-8").read())
        except Exception:
            _cache = {}
    return _cache


def _cache_save() -> None:
    try:
        with _cache_lock, open(_CACHE_PATH, "w", encoding="utf-8") as f:
            json.dump(_cache, f, indent=2)
    except Exception:
        pass


# --------------------------------------------------------------------------- prompt (no rules score leaked)

def _features(d: Dossier) -> str:
    txns = d.transactions
    total_in = sum(float(t.amount) for t in txns if t.direction == "in")
    total_out = sum(float(t.amount) for t in txns if t.direction == "out")
    cash_in = sum(float(t.amount) for t in txns if t.direction == "in" and t.txn_type == "cash")
    countries = sorted({t.counterparty_country for t in txns})
    lines = [
        f"customer_id: {d.customer_id}",
        f"nationality/country: {d.kyc.get('nationality')}/{d.profile.get('country')}",
        f"occupation: {d.kyc.get('occupation')}",
        f"PEP: {d.profile.get('pep')}   account_age_days: {d.profile.get('tenure_days')}",
        f"KYC_complete: {d.kyc.get('kyc_complete')}   id_doc_present: {d.kyc.get('id_doc') is not None}",
        f"sanctions_hits: {[s.get('name') for s in d.screening.get('sanctions', [])]}",
        f"adverse_media: {[m.get('headline') for m in d.screening.get('adverse_media', [])]}",
        f"transactions: {len(txns)}  credits: {total_in:.0f}  debits: {total_out:.0f}  cash_in: {cash_in:.0f}",
        f"counterparty_countries: {countries}",
    ]
    if d.meta.get("missing_docs"):
        lines.append(f"MISSING DATA: {d.meta['missing_docs']} (assess with reduced confidence)")
    return "\n".join(lines)


def build_prompt(d: Dossier) -> str:
    return (
        "You are an AML compliance analyst. Assess the money-laundering / financial-crime risk of "
        "this customer from the signals below. Consider sanctions, PEP status, geography, occupation, "
        "KYC gaps, adverse media, and transaction patterns (structuring, layering, round-tripping, "
        "dormant-then-spike). Return a score 0-100 (higher = riskier), the matching band, a one-line "
        "rationale, and the key signals that drove it.\n\n"
        f"CUSTOMER SIGNALS:\n{_features(d)}"
    )


def _prompt_hash(prompt: str) -> str:
    return hashlib.sha256(prompt.encode()).hexdigest()[:12]


# --------------------------------------------------------------------------- deterministic fallbacks

def rules_only_finding(d: Dossier, rr: RiskResult) -> RiskFinding:
    top = "; ".join(f"{drv['code']} (+{drv['contribution']})" for drv in rr.drivers[:4]) or "no risk signals"
    return RiskFinding(customer_id=d.customer_id, score=rr.score, band=BAND_LABEL[rr.band],
                       rationale=f"Deterministic rules assessment: {top}.",
                       key_signals=[f.code for f in rr.findings])


def _simulated_finding(d: Dossier, rr: RiskResult) -> RiskFinding:
    """Deterministic stand-in when no provider key is present — nudges the rules score by a per-customer
    offset so the confidence/agreement mechanic and the auto-clear tier still demo offline."""
    h = int(hashlib.sha256(d.customer_id.encode()).hexdigest(), 16)
    sim = max(0, min(100, rr.score + (h % 17) - 8))
    top = ", ".join(f.code for f in rr.findings[:3]) or "no material signals"
    return RiskFinding(customer_id=d.customer_id, score=sim, band=BAND_LABEL[band_for(sim)],
                       rationale=f"Independent second-opinion (simulated) — corroborates: {top}.",
                       key_signals=[f.code for f in rr.findings])


# --------------------------------------------------------------------------- the cross-check

@traceable(
    name="risk_crosscheck",
    process_inputs=lambda inputs: {"customer_id": getattr(inputs.get("d"), "customer_id", "?"),
                                   "rules_score": getattr(inputs.get("rr"), "score", None)},
    process_outputs=lambda out: {"llm_score": out[0].score, "band": out[0].band, "path": out[1].get("path")},
)
def crosscheck(d: Dossier, rr: RiskResult) -> tuple[RiskFinding, dict]:
    """Return (finding, meta). meta.path in {rules+graph, rules+llm, rules+sim, rules_only}. Never raises."""
    prompt = build_prompt(d)
    provider_name = _LLM.get("provider", "nvidia")
    meta = {"path": "rules_only", "prompt_hash": _prompt_hash(prompt), "provider": provider_name}

    if os.environ.get("LLM_MODE", _LLM.get("mode", "auto")) == "off":
        return rules_only_finding(d, rr), meta

    provider = get_provider(provider_name)
    model_name = _LLM.get(_MODEL_KEY.get(provider_name, ""), provider_name)
    ph = meta["prompt_hash"]
    multistep = bool(_LLM.get("multi_step")) and provider_name in ("openrouter", "nvidia")
    cache = _load_cache()
    graph_key = f"{provider_name}:{model_name}:graph:{ph}"
    single_key = f"{provider_name}:{model_name}:{ph}"

    # --- cache (both entry shapes) ---
    if multistep and graph_key in cache:
        e = cache[graph_key]
        finding = RiskFinding.model_validate(e["finding"])
        finding.customer_id = d.customer_id
        meta.update(path="rules+graph", model=model_name, cached=True, detail=e.get("detail"))
        return finding, meta
    if not multistep and single_key in cache:
        finding = RiskFinding.model_validate(cache[single_key])
        finding.customer_id = d.customer_id
        meta.update(path="rules+llm", model=model_name, cached=True)
        return finding, meta

    # --- multi-step LangGraph orchestration (primary when enabled) ---
    if multistep:
        try:
            from frisk.ai import orchestrator
            if orchestrator.available():
                finding, detail = orchestrator.assess_multistep(d, rr)
                finding.customer_id = d.customer_id
                cache[graph_key] = {"finding": finding.model_dump(), "detail": detail}
                _cache_save()
                meta.update(path="rules+graph", model=model_name, detail=detail)
                return finding, meta
        except Exception as e:  # graph engine died -> cascade to single call
            meta["graph_error"] = type(e).__name__

    # --- single provider call (fallback, or when multi_step is off) ---
    if provider.available():
        last = None
        for attempt in range(_LLM["max_retries"]):
            try:
                finding = provider.complete(prompt, RiskFinding)
                finding.customer_id = d.customer_id  # pin; don't trust the model to echo it
                cache[single_key] = finding.model_dump()
                _cache_save()
                meta.update(path="rules+llm", attempt=attempt + 1, model=model_name)
                return finding, meta
            except Exception as e:  # schema-invalid / transient (429/500) -> backoff, retry, then degrade
                last = e
                if attempt < _LLM["max_retries"] - 1:
                    time.sleep(1.5 * (attempt + 1))
        meta["error"] = type(last).__name__
        return rules_only_finding(d, rr), meta

    # no key: simulated second opinion keeps confidence + auto-clear demonstrable offline
    meta.update(path="rules+sim", model="simulated")
    return _simulated_finding(d, rr), meta


if __name__ == "__main__":
    from frisk.core.models import load_dossiers
    from frisk.core.rules import score_customer
    d0 = load_dossiers()[0]
    rr0 = score_customer(d0)

    os.environ["LLM_MODE"] = "off"          # force the deterministic path for a hermetic self-check
    f, meta = crosscheck(d0, rr0)
    assert isinstance(f, RiskFinding) and 0 <= f.score <= 100 and meta["path"] == "rules_only"
    print(f"off-mode OK: {d0.customer_id} -> score {f.score} band {f.band} path={meta['path']}")

    # a provider that raises must still fall back to rules_only
    class _Boom:
        def available(self): return True
        def complete(self, *a, **k): raise RuntimeError("boom")
    globals()["get_provider"] = lambda *a, **k: _Boom()   # rebind the running module's global
    _cache = {}                                           # avoid a cache hit short-circuit
    _LLM["multi_step"] = False
    os.environ["LLM_MODE"] = "auto"
    f2, meta2 = crosscheck(d0, rr0)
    assert isinstance(f2, RiskFinding) and meta2["path"] == "rules_only"
    print(f"raising-provider OK: fell back to rules_only ({meta2.get('error')})")
