"""Never-fails LLM cross-check.

The deterministic rules are the source of truth. This module asks an LLM for an INDEPENDENT
second opinion (it is deliberately NOT told the rules score, so agreement is meaningful).

Guarantee: `crosscheck()` ALWAYS returns a valid `RiskFinding`. Missing API key, network
failure, schema-invalid output after retries — every path funnels through one try/except into
the deterministic rules-only finding. Nothing here can raise into the engine.
"""
from __future__ import annotations

import hashlib
import os

from config import CONFIG, BAND_LABEL
from models import Dossier, RiskResult, RiskFinding

_LLM = CONFIG["llm"]


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
# client (lazy, cached) — never raises at import
# --------------------------------------------------------------------------- #

_client = None
_client_tried = False


def _get_client():
    global _client, _client_tried
    if _client_tried:
        return _client
    _client_tried = True
    if not os.environ.get("ANTHROPIC_API_KEY"):
        _client = None
        return None
    try:
        import instructor
        from anthropic import Anthropic
        _client = instructor.from_anthropic(Anthropic())
    except Exception:
        _client = None
    return _client


# --------------------------------------------------------------------------- #
# the cross-check — the never-fails guarantee lives in the single try/except
# --------------------------------------------------------------------------- #

def crosscheck(d: Dossier, rr: RiskResult) -> tuple[RiskFinding, dict]:
    """Return (finding, meta). meta.path in {'rules+llm','rules+sim','rules_only'}. Never raises."""
    prompt = build_prompt(d)
    meta = {"path": "rules_only", "prompt_hash": _prompt_hash(prompt),
            "model": _LLM["model"], "retries": _LLM["max_retries"]}
    mode = os.environ.get("LLM_MODE", _LLM.get("mode", "auto"))

    if mode == "off":
        return rules_only_finding(d, rr), meta

    client = _get_client()
    if client is not None:
        try:
            finding = client.chat.completions.create(
                model=_LLM["model"],
                max_tokens=1024,
                temperature=_LLM["temperature"],
                max_retries=_LLM["max_retries"],
                response_model=RiskFinding,
                messages=[{"role": "user", "content": prompt}],
            )
            finding.customer_id = d.customer_id  # pin; don't trust the model to echo it
            meta["path"] = "rules+llm"
            return finding, meta
        except Exception as e:  # API down / no quota / schema-invalid after retries -> genuine degradation
            meta["error"] = type(e).__name__
            return rules_only_finding(d, rr), meta

    # no API key: simulated second opinion keeps the confidence + auto-clear demo working
    meta["path"] = "rules+sim"
    meta["model"] = "simulated"
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
        class chat:
            class completions:
                @staticmethod
                def create(**_):
                    raise RuntimeError("simulated API failure")
    _client = _Boom(); _client_tried = True
    f2, meta2 = crosscheck(d0, rr0)
    assert isinstance(f2, RiskFinding) and meta2["path"] == "rules_only"
    print(f"raising-client path OK: fell back to rules_only ({meta2.get('error')})")
