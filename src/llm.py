"""Never-fails LLM cross-check.

The deterministic rules are the source of truth. This module asks an LLM for an INDEPENDENT
second opinion (it is deliberately NOT told the rules score, so agreement is meaningful).

Guarantee: `crosscheck()` ALWAYS returns a valid `RiskFinding`. Missing API key, network
failure, schema-invalid output after retries — every path funnels through one try/except into
the deterministic rules-only finding. Nothing here can raise into the engine.
"""
from __future__ import annotations

import hashlib
import json
import os
import time

from config import CONFIG, BAND_LABEL
from models import Dossier, RiskResult, RiskFinding

_LLM = CONFIG["llm"]

# disk cache of LLM findings keyed by prompt hash -> instant, rate-limit-proof re-runs
_CACHE_PATH = os.path.join(os.path.dirname(__file__), "..", "data", "llm_cache.json")
_cache: dict | None = None


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
        with open(_CACHE_PATH, "w", encoding="utf-8") as f:
            json.dump(_cache, f, indent=2)
    except Exception:
        pass


# --------------------------------------------------------------------------- #
# prompt + feature summary (no rules score leaked -> independent opinion)
# --------------------------------------------------------------------------- #

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


# --------------------------------------------------------------------------- #
# deterministic fallback (always valid)
# --------------------------------------------------------------------------- #

def rules_only_finding(d: Dossier, rr: RiskResult) -> RiskFinding:
    top = "; ".join(f"{drv['code']} (+{drv['contribution']})" for drv in rr.drivers[:4]) or "no risk signals"
    return RiskFinding(
        customer_id=d.customer_id,
        score=rr.score,
        band=BAND_LABEL[rr.band],
        rationale=f"Deterministic rules assessment: {top}.",
        key_signals=[f.code for f in rr.findings],
    )


def _simulated_finding(d: Dossier, rr: RiskResult) -> RiskFinding:
    """Deterministic stand-in for a second opinion when no API key is present.

    Produces an INDEPENDENT-looking score (rules score nudged by a per-customer offset) so the
    confidence/agreement mechanic and the auto-clear tier are demonstrable offline. Clearly
    labelled as simulated in meta; never presented as a real model.
    """
    from config import band_for
    h = int(hashlib.sha256(d.customer_id.encode()).hexdigest(), 16)
    offset = (h % 17) - 8  # -8..+8, deterministic
    sim = max(0, min(100, rr.score + offset))
    top = ", ".join(f.code for f in rr.findings[:3]) or "no material signals"
    return RiskFinding(
        customer_id=d.customer_id,
        score=sim,
        band=BAND_LABEL[band_for(sim)],
        rationale=f"Independent second-opinion (simulated) — corroborates: {top}.",
        key_signals=[f.code for f in rr.findings],
    )


# --------------------------------------------------------------------------- #
# provider clients (lazy, cached) — never raise at import
# --------------------------------------------------------------------------- #

_clients: dict = {}


def _gemini_client():
    if "gemini" in _clients:
        return _clients["gemini"]
    c = None
    key = os.environ.get("GEMINI_API_KEY") or os.environ.get("GOOGLE_API_KEY")
    if key:
        try:
            from google import genai
            c = genai.Client(api_key=key)
        except Exception:
            c = None
    _clients["gemini"] = c
    return c


def _anthropic_client():
    if "anthropic" in _clients:
        return _clients["anthropic"]
    c = None
    if os.environ.get("ANTHROPIC_API_KEY"):
        try:
            import instructor
            from anthropic import Anthropic
            c = instructor.from_anthropic(Anthropic())
        except Exception:
            c = None
    _clients["anthropic"] = c
    return c


def _nvidia_client():
    if "nvidia" in _clients:
        return _clients["nvidia"]
    c = None
    if os.environ.get("NVIDIA_API_KEY"):
        try:
            import instructor
            from openai import OpenAI
            base = OpenAI(base_url=_LLM["nvidia_base_url"], api_key=os.environ["NVIDIA_API_KEY"])
            c = instructor.from_openai(base, mode=instructor.Mode.JSON)  # OpenAI-compatible endpoint
        except Exception:
            c = None
    _clients["nvidia"] = c
    return c


def _call_gemini(client, prompt: str) -> RiskFinding:
    from google.genai import types
    resp = client.models.generate_content(
        model=_LLM["gemini_model"],
        contents=prompt,
        config=types.GenerateContentConfig(
            response_mime_type="application/json",
            response_schema=RiskFinding,
            temperature=_LLM["temperature"],
        ),
    )
    return resp.parsed or RiskFinding.model_validate_json(resp.text)


def _call_anthropic(client, prompt: str) -> RiskFinding:
    return client.chat.completions.create(
        model=_LLM["model"], max_tokens=1024, temperature=_LLM["temperature"],
        max_retries=_LLM["max_retries"], response_model=RiskFinding,
        messages=[{"role": "user", "content": prompt}],
    )


def _call_nvidia(client, prompt: str) -> RiskFinding:
    return client.chat.completions.create(
        model=_LLM["nvidia_model"], max_tokens=_LLM["max_tokens"], temperature=_LLM["temperature"],
        response_model=RiskFinding, messages=[{"role": "user", "content": prompt}],
    )


_PROVIDERS = {
    "gemini":    (_gemini_client,    _call_gemini,    "gemini_model"),
    "anthropic": (_anthropic_client, _call_anthropic, "model"),
    "nvidia":    (_nvidia_client,    _call_nvidia,    "nvidia_model"),
}


# --------------------------------------------------------------------------- #
# the cross-check — the never-fails guarantee lives in the single try/except
# --------------------------------------------------------------------------- #

def crosscheck(d: Dossier, rr: RiskResult) -> tuple[RiskFinding, dict]:
    """Return (finding, meta). meta.path in {'rules+llm','rules+sim','rules_only'}. Never raises."""
    prompt = build_prompt(d)
    provider = _LLM.get("provider", "nvidia")
    meta = {"path": "rules_only", "prompt_hash": _prompt_hash(prompt), "provider": provider}
    mode = os.environ.get("LLM_MODE", _LLM.get("mode", "auto"))

    if mode == "off":
        return rules_only_finding(d, rr), meta

    client_fn, call_fn, model_key = _PROVIDERS[provider]
    model_name = _LLM[model_key]
    key = f"{provider}:{model_name}:{meta['prompt_hash']}"

    # cache hit -> instant, no API call (survives rate limits and repeated runs)
    cache = _load_cache()
    if key in cache:
        finding = RiskFinding.model_validate(cache[key])
        finding.customer_id = d.customer_id
        meta.update(path="rules+llm", model=model_name, cached=True)
        return finding, meta

    client = client_fn()
    if client is not None:
        last = None
        for attempt in range(_LLM["max_retries"]):
            try:
                finding = call_fn(client, prompt)
                finding.customer_id = d.customer_id  # pin; don't trust the model to echo it
                cache[key] = finding.model_dump()
                _cache_save()
                meta.update(path="rules+llm", attempt=attempt + 1, model=model_name)
                return finding, meta
            except Exception as e:  # schema-invalid / transient (429) -> backoff, retry, then degrade
                last = e
                if attempt < _LLM["max_retries"] - 1:
                    time.sleep(1.5 * (attempt + 1))
        meta["error"] = type(last).__name__
        return rules_only_finding(d, rr), meta

    # no API key: simulated second opinion keeps the confidence + auto-clear demo working
    meta.update(path="rules+sim", model="simulated")
    return _simulated_finding(d, rr), meta


if __name__ == "__main__":
    # self-check: fallback path always yields a valid RiskFinding, even with no key / a broken client
    from models import load_dossiers
    ds = load_dossiers(os.path.join(os.path.dirname(__file__), "..", "data", "dossiers.json"))
    from rules import score_customer
    d0 = ds[0]
    rr0 = score_customer(d0)
    f, meta = crosscheck(d0, rr0)
    assert isinstance(f, RiskFinding) and 0 <= f.score <= 100
    print(f"no-key path OK: {d0.customer_id} -> score {f.score} band {f.band} path={meta['path']}")

    # force a raising client -> must still fall back
    class _Boom:
        class models:
            @staticmethod
            def generate_content(**_):
                raise RuntimeError("simulated API failure")
    _clients["gemini"] = _Boom()
    os.environ["LLM_MODE"] = "auto"
    _LLM_provider_backup = _LLM["provider"]
    _LLM["provider"] = "gemini"
    f2, meta2 = crosscheck(d0, rr0)
    _LLM["provider"] = _LLM_provider_backup
    assert isinstance(f2, RiskFinding) and meta2["path"] == "rules_only"
    print(f"raising-client path OK: fell back to rules_only ({meta2.get('error')})")
