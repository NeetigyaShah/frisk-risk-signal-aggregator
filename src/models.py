"""Shared schemas. Internal core = dataclasses (deterministic, frozen where it matters);
the LLM boundary = Pydantic (validation + retry feedback).

Design note: money is Decimal everywhere in the core. Dossiers persist to JSON with amounts as
strings; `load_dossiers` reparses them to Decimal so no float ever touches the scoring math.
"""
from __future__ import annotations

import json
from dataclasses import dataclass, field
from decimal import Decimal
from pathlib import Path
from typing import Literal, Optional

from pydantic import BaseModel, Field, field_validator

from config import CONFIG, band_for, BAND_LABEL

# --------------------------------------------------------------------------- #
# Internal core (deterministic)
# --------------------------------------------------------------------------- #

TxnType = Literal["cash", "wire", "card", "transfer", "salary", "direct_debit"]


@dataclass
class Txn:
    id: str
    date: str  # ISO date "YYYY-MM-DD"
    amount: Decimal
    currency: str
    direction: Literal["in", "out"]
    counterparty: str
    counterparty_country: str
    txn_type: TxnType


@dataclass
class Dossier:
    customer_id: str
    kyc: dict          # name, dob, nationality(ISO2), occupation, id_doc, onboarded, kyc_complete
    profile: dict      # entity_type, country(ISO2), product, pep(bool), tenure_days(int)
    transactions: list  # list[Txn]
    screening: dict    # sanctions[list{name,match_score,list}], pep_confirmed(bool), adverse_media[list{headline,sentiment,date}]
    meta: dict = field(default_factory=dict)  # missing_docs[list], extra_docs[list], expected_band(str) for eval


@dataclass(frozen=True)
class Finding:
    """One fired rule. `evidence` IS the audit trail + analyst rationale."""
    code: str
    category: str        # KYC | PROFILE | SCREENING | TRANSACTION
    weight: int          # points contributed if non-override
    is_override: bool     # forces band=HIGH / ESCALATE
    rationale: str
    evidence: dict


@dataclass
class RiskResult:
    customer_id: str
    score: int
    band: str            # LOW | MED | HIGH
    findings: list       # list[Finding]
    drivers: list        # list[dict]: {code, contribution, rationale} — contributions sum to score
    flags: set           # set[str]: override/kill-switch codes present


@dataclass
class Disposition:
    action: str          # AUTO_CLEAR | REVIEW | ESCALATE
    tier: str            # none | junior | senior | named_reviewer
    requires_signoff: bool = False


@dataclass
class AuditRecord:
    record_id: str
    customer_id: str
    ts: str
    actor: str           # "engine:v1.0" | "analyst:<id>"
    action: str          # AUTO_CLEAR | REVIEW | ESCALATE | OVERRIDE
    score: int
    confidence: float
    engine_path: str     # rules+llm | rules_only
    band: str
    thresholds: dict     # config snapshot (why)
    drivers: list        # sums to score
    rationale: str
    ruleset_version: str
    input_fingerprint: str
    override_of: Optional[str] = None
    signoff_by: Optional[str] = None


# --------------------------------------------------------------------------- #
# LLM boundary (Pydantic) — the only place that validates model output
# --------------------------------------------------------------------------- #

class RiskFinding(BaseModel):
    """Schema the LLM MUST fill. Constraints + validator = semantic cross-check;
    a raised ValueError becomes instructor retry feedback automatically."""
    customer_id: str
    score: int = Field(ge=0, le=100)
    band: Literal["low", "medium", "high"]
    rationale: str = Field(min_length=10)
    key_signals: list[str] = Field(default_factory=list)

    @field_validator("band")
    @classmethod
    def band_matches_score(cls, v, info):
        s = info.data.get("score")
        if s is None:
            return v  # score failed its own validation; don't mask that error
        expected = BAND_LABEL[band_for(s)]
        if v != expected:
            raise ValueError(f"band '{v}' must agree with score {s} (expected '{expected}')")
        return v


# --------------------------------------------------------------------------- #
# (De)serialisation — Decimal-safe
# --------------------------------------------------------------------------- #

def _txn_from_dict(d: dict) -> Txn:
    return Txn(
        id=d["id"], date=d["date"], amount=Decimal(str(d["amount"])),
        currency=d["currency"], direction=d["direction"],
        counterparty=d["counterparty"], counterparty_country=d["counterparty_country"],
        txn_type=d["txn_type"],
    )


def dossier_from_dict(d: dict) -> Dossier:
    return Dossier(
        customer_id=d["customer_id"], kyc=d["kyc"], profile=d["profile"],
        transactions=[_txn_from_dict(t) for t in d["transactions"]],
        screening=d["screening"], meta=d.get("meta", {}),
    )


def load_dossiers(path: str | Path) -> list[Dossier]:
    raw = json.loads(Path(path).read_text(encoding="utf-8"))
    return [dossier_from_dict(d) for d in raw]


class _DecimalEncoder(json.JSONEncoder):
    def default(self, o):
        if isinstance(o, Decimal):
            return str(o)
        return super().default(o)


def dumps(obj) -> str:
    """JSON dump that renders Decimal as string (so amounts round-trip exactly)."""
    return json.dumps(obj, cls=_DecimalEncoder, indent=2, default=str)
