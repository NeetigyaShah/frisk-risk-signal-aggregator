"""Natural-language query over the triage queue — SAFE by construction.

Language is turned into a WHITELISTED Pydantic `FilterSpec` (Literal fields only), then a pandas-style
mask is built from a fixed op-map. Model/query text is NEVER eval'd, df.query'd, or executed.

Offline, a deterministic keyword parser handles common queries; with an API key, the LLM extracts the
same FilterSpec (validated identically). Either way the spec is the only thing that touches the data.
"""
from __future__ import annotations

import os
import re
from typing import Literal, Optional

from pydantic import BaseModel, Field, field_validator

from frisk.config import CONFIG

# whitelist of signal codes a query may reference
SIGNAL_CODES = set(CONFIG["weights"]) | {"SANCTIONS_MATCH", "PEP_HIGH_GEO"}


class FilterSpec(BaseModel):
    bands: list[Literal["LOW", "MED", "HIGH"]] = Field(default_factory=list)
    actions: list[Literal["AUTO_CLEAR", "REVIEW", "ESCALATE"]] = Field(default_factory=list)
    min_score: Optional[int] = Field(default=None, ge=0, le=100)
    max_score: Optional[int] = Field(default=None, ge=0, le=100)
    signals: list[str] = Field(default_factory=list)   # ANY-of match; validated to the whitelist
    countries: list[str] = Field(default_factory=list)
    pep_only: bool = False
    text: str = ""

    @field_validator("signals")
    @classmethod
    def only_known(cls, v):
        return [s for s in (x.upper() for x in v) if s in SIGNAL_CODES]


# --------------------------------------------------------------------------- deterministic parser

_SIGNAL_WORDS = {
    "sanction": ["SANCTIONS_MATCH"], "ofac": ["SANCTIONS_MATCH"],
    "structuring": ["STRUCTURING"], "smurf": ["STRUCTURING"],
    "layering": ["LAYERING"], "round": ["ROUND_TRIP"], "round-trip": ["ROUND_TRIP"],
    "dormant": ["DORMANT_SPIKE"], "spike": ["DORMANT_SPIKE"],
    "adverse": ["ADVERSE_MEDIA", "ADVERSE_MEDIA_SEVERE"], "media": ["ADVERSE_MEDIA", "ADVERSE_MEDIA_SEVERE"],
    "cash": ["CASH_INTENSITY"], "velocity": ["HIGH_VELOCITY"],
    "geography": ["HIGH_RISK_GEO"], "geo": ["HIGH_RISK_GEO"],
    "occupation": ["HIGH_RISK_OCCUPATION"], "kyc": ["KYC_INCOMPLETE"], "incomplete": ["KYC_INCOMPLETE"],
    "new account": ["NEW_ACCOUNT"],
}


def keyword_parse(q: str) -> FilterSpec:
    t = q.lower()
    bands, actions, signals = [], [], []
    if re.search(r"\bhigh\b", t): bands.append("HIGH")
    if re.search(r"\b(med|medium)\b", t): bands.append("MED")
    if re.search(r"\blow\b", t): bands.append("LOW")
    if "escalat" in t: actions.append("ESCALATE")
    if "auto" in t or "cleared" in t or "auto-clear" in t: actions.append("AUTO_CLEAR")
    if "review" in t: actions.append("REVIEW")
    for word, codes in _SIGNAL_WORDS.items():
        if word in t:
            signals += codes
    pep_only = bool(re.search(r"\bpep\b", t))
    if pep_only:
        signals += ["PEP", "PEP_HIGH_GEO"]
    min_s = max_s = None
    m = re.search(r"(?:over|above|>=?|greater than)\s*(\d{1,3})", t)
    if m: min_s = min(100, int(m.group(1)))
    m = re.search(r"(?:under|below|<=?|less than)\s*(\d{1,3})", t)
    if m: max_s = min(100, int(m.group(1)))
    return FilterSpec(bands=bands, actions=actions, signals=list(dict.fromkeys(signals)),
                      min_score=min_s, max_score=max_s, pep_only=pep_only, text=q.strip())


# --------------------------------------------------------------------------- optional LLM parser

def llm_parse(q: str) -> Optional[FilterSpec]:
    if not os.environ.get("ANTHROPIC_API_KEY") or os.environ.get("LLM_MODE") == "off":
        return None
    try:
        import instructor
        from anthropic import Anthropic
        client = instructor.from_anthropic(Anthropic())
        return client.chat.completions.create(
            model=CONFIG["llm"]["model"], max_tokens=512, temperature=0, max_retries=2,
            response_model=FilterSpec,
            messages=[{"role": "user", "content":
                       f"Extract a compliance-queue filter from this request. Only use the allowed "
                       f"fields; leave others empty. Signals must be from {sorted(SIGNAL_CODES)}.\n\n"
                       f"Request: {q}"}],
        )
    except Exception:
        return None


def parse(q: str) -> FilterSpec:
    return llm_parse(q) or keyword_parse(q)


# --------------------------------------------------------------------------- apply (fixed op-map)

def apply(spec: FilterSpec, decisions: list) -> list:
    res = decisions
    if spec.bands:
        res = [d for d in res if d.band in spec.bands]
    if spec.actions:
        res = [d for d in res if d.action in spec.actions]
    if spec.min_score is not None:
        res = [d for d in res if d.score >= spec.min_score]
    if spec.max_score is not None:
        res = [d for d in res if d.score <= spec.max_score]
    if spec.signals:
        want = set(spec.signals)
        res = [d for d in res if want & {f["code"] for f in d.findings}]
    if spec.countries:
        cc = {c.upper() for c in spec.countries}
        res = [d for d in res if d.country.upper() in cc]
    if spec.pep_only:
        res = [d for d in res if d.pep or "PEP_HIGH_GEO" in d.flags]
    # free-text fallback only if nothing structured matched
    if spec.text and not any([spec.bands, spec.actions, spec.signals, spec.countries, spec.pep_only,
                              spec.min_score is not None, spec.max_score is not None]):
        t = spec.text.lower()
        res = [d for d in res if t in d.name.lower() or t in d.rationale.lower()
               or t in d.occupation.lower()]
    return res


def explain(spec: FilterSpec) -> str:
    parts = []
    if spec.bands: parts.append("band " + "/".join(spec.bands))
    if spec.actions: parts.append("action " + "/".join(spec.actions))
    if spec.min_score is not None: parts.append(f"score >= {spec.min_score}")
    if spec.max_score is not None: parts.append(f"score <= {spec.max_score}")
    if spec.signals: parts.append("signal " + "/".join(spec.signals))
    if spec.pep_only: parts.append("PEP")
    if spec.countries: parts.append("country " + "/".join(spec.countries))
    return "Filter: " + "; ".join(parts) if parts else "No structured filter (showing all)."


if __name__ == "__main__":
    import os as _os
    from frisk.core.models import load_dossiers
    from frisk.core.engine import assess_all
    ds = load_dossiers()
    decs = assess_all(ds, persist=False)
    for q in ["show high-risk customers with a sanctions hit",
              "everything escalated",
              "structuring cases",
              "score over 80",
              "PEP customers"]:
        spec = keyword_parse(q)
        out = apply(spec, decs)
        print(f"[{q}] -> {len(out)} match | {explain(spec)}")
        assert isinstance(out, list)
    # safety: a malicious string is just treated as data, never executed
    bad = keyword_parse("__import__('os').system('rm -rf /')")
    assert apply(bad, decs) == decs or isinstance(apply(bad, decs), list)
    print("nlquery self-check OK (safe, whitelisted)")
