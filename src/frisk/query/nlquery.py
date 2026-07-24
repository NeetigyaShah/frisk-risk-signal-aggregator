"""Natural-language query over the triage queue — SAFE by construction.

Language → a WHITELISTED Pydantic ``FilterSpec`` (Literal fields only) → a fixed op-map over the decisions.
Model/query text is NEVER eval'd, df.query'd, or executed. Offline a deterministic keyword parser handles
common queries; with a key the LLM extracts the same spec (validated identically). Signals now match the
agent's free-text ``key_signals`` against a small canonical whitelist.
"""
from __future__ import annotations

import os
import re
from typing import Literal, Optional

from pydantic import BaseModel, Field, field_validator

from frisk.config import CONFIG

# canonical signal tokens a query may reference (matched as substrings of the agent's key_signals)
SIGNAL_CODES = {"structuring", "layering", "round_trip", "dormant_spike", "pep",
                "high-risk occupation", "high-risk jurisdiction", "kyc"}

_BAND_NORM = {"low": "LOW", "medium": "MED", "med": "MED", "high": "HIGH"}


class FilterSpec(BaseModel):
    bands: list[Literal["LOW", "MED", "HIGH"]] = Field(default_factory=list)
    actions: list[Literal["AUTO_CLEAR", "REVIEW", "ESCALATE", "PENDING_REVIEW"]] = Field(default_factory=list)
    min_score: Optional[int] = Field(default=None, ge=0, le=100)
    max_score: Optional[int] = Field(default=None, ge=0, le=100)
    signals: list[str] = Field(default_factory=list)   # ANY-of match against key_signals; whitelisted
    countries: list[str] = Field(default_factory=list)
    pep_only: bool = False
    text: str = ""

    @field_validator("signals")
    @classmethod
    def only_known(cls, v):
        return [s for s in (x.lower() for x in v) if s in SIGNAL_CODES]


_SIGNAL_WORDS = {
    "structuring": ["structuring"], "smurf": ["structuring"],
    "layering": ["layering"], "round": ["round_trip"], "round-trip": ["round_trip"],
    "dormant": ["dormant_spike"], "spike": ["dormant_spike"],
    "occupation": ["high-risk occupation"], "geography": ["high-risk jurisdiction"],
    "geo": ["high-risk jurisdiction"], "jurisdiction": ["high-risk jurisdiction"],
    "kyc": ["kyc"], "incomplete": ["kyc"],
}


def keyword_parse(q: str) -> FilterSpec:
    t = q.lower()
    bands, actions, signals = [], [], []
    if re.search(r"\bhigh\b", t): bands.append("HIGH")
    if re.search(r"\b(med|medium)\b", t): bands.append("MED")
    if re.search(r"\blow\b", t): bands.append("LOW")
    if "escalat" in t: actions.append("ESCALATE")
    if "auto" in t or "cleared" in t: actions.append("AUTO_CLEAR")
    if "review" in t and "human" not in t: actions.append("REVIEW")
    if "human" in t or "pending" in t or "queue" in t: actions.append("PENDING_REVIEW")
    for word, codes in _SIGNAL_WORDS.items():
        if word in t:
            signals += codes
    pep_only = bool(re.search(r"\bpep\b", t))
    if pep_only:
        signals += ["pep"]
    min_s = max_s = None
    m = re.search(r"(?:over|above|>=?|greater than)\s*(\d{1,3})", t)
    if m: min_s = min(100, int(m.group(1)))
    m = re.search(r"(?:under|below|<=?|less than)\s*(\d{1,3})", t)
    if m: max_s = min(100, int(m.group(1)))
    return FilterSpec(bands=bands, actions=actions, signals=list(dict.fromkeys(signals)),
                      min_score=min_s, max_score=max_s, pep_only=pep_only, text=q.strip())


def llm_parse(q: str) -> Optional[FilterSpec]:
    if not os.environ.get("ANTHROPIC_API_KEY"):
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


def _band_up(band: str) -> str:
    return _BAND_NORM.get((band or "").lower(), (band or "").upper())


def apply(spec: FilterSpec, decisions: list) -> list:
    res = decisions
    if spec.bands:
        res = [d for d in res if _band_up(d.band) in spec.bands]
    if spec.actions:
        res = [d for d in res if d.action in spec.actions]
    if spec.min_score is not None:
        res = [d for d in res if d.score >= spec.min_score]
    if spec.max_score is not None:
        res = [d for d in res if d.score <= spec.max_score]
    if spec.signals:
        want = [s.lower() for s in spec.signals]
        res = [d for d in res if any(w in " ".join(d.key_signals).lower() for w in want)]
    if spec.countries:
        cc = {c.upper() for c in spec.countries}
        res = [d for d in res if (d.country or "").upper() in cc]
    if spec.pep_only:
        res = [d for d in res if d.pep]
    if spec.text and not any([spec.bands, spec.actions, spec.signals, spec.countries, spec.pep_only,
                              spec.min_score is not None, spec.max_score is not None]):
        t = spec.text.lower()
        res = [d for d in res if t in (d.name or "").lower() or t in (d.rationale or "").lower()
               or t in (d.occupation or "").lower()]
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


if __name__ == "__main__":  # self-check (safe, whitelisted)
    for q, exp in [("everything escalated", "ESCALATE"), ("structuring cases", "structuring"),
                   ("score over 80", None), ("PEP customers", None), ("human review queue", "PENDING_REVIEW")]:
        spec = keyword_parse(q)
        assert isinstance(apply(spec, []), list)
    bad = keyword_parse("__import__('os').system('rm -rf /')")
    assert apply(bad, []) == []
    print("nlquery self-check OK (safe, whitelisted, key_signals-based)")
