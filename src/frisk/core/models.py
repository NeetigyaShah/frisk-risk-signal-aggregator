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

from pydantic import BaseModel, Field, model_validator

from frisk.config import CONFIG, band_for, BAND_LABEL

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
    documents: list = field(default_factory=list)  # unstructured docs: [{name, kind, text}] (id doc, RM notes, news, email)


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
    """Schema the model MUST fill. `score` range is hard-enforced; `band` is DERIVED from the score
    (coerced deterministically) so the band can never contradict the number, whatever the model says.
    `customer_id` is pinned by us after the call, so it is optional here."""
    customer_id: str = ""
    score: int = Field(ge=0, le=100, description="AML risk 0-100, higher = riskier")
    # accept ANY band vocabulary the model uses ("Critical", "severe", …) then normalise from the score
    band: str = "low"
    rationale: str = Field(min_length=1, description="one-line justification")
    key_signals: list[str] = Field(default_factory=list, description="signal names that drove the score")
    evidence_refs: list[str] = Field(default_factory=list, description="txn ids / document names you actually saw")
    confidence: float = Field(default=0.6, ge=0.0, le=1.0, description="your own confidence 0-1 (low = unsure, send to human)")

    @model_validator(mode="after")
    def _coerce_band(self):
        object.__setattr__(self, "band", BAND_LABEL[band_for(self.score)])  # deterministic band always wins
        return self


class SpecialistOpinion(BaseModel):
    """One parallel domain specialist's memory-fed opinion (kyc | transactions | documents)."""
    domain: str = "kyc"
    risk_level: Literal["low", "medium", "high"] = "low"
    signals: list[str] = Field(default_factory=list, description="specific red flags found in this domain")
    note: str = Field(default="", description="one-line domain assessment")
    tentative_score: int = Field(default=0, ge=0, le=100, description="this domain's tentative 0-100 risk")


@dataclass
class AgentStep:
    """One turn of the orchestrator's tool-calling loop — the audit trace is a list of these."""
    step: int
    tool: str
    args: dict
    result_digest: str


class SourceFinding(BaseModel):
    """Output of one domain-analyst node in the multi-step graph."""
    domain: Literal["kyc", "transactions", "screening"]
    risk_level: Literal["low", "medium", "high"]
    signals: list[str] = Field(default_factory=list, description="specific red flags found in this domain")
    note: str = Field(min_length=1, description="one-line domain assessment")


class Verdict(BaseModel):
    """Output of the verification / critic node (chain-of-verification)."""
    consistent: bool = Field(description="does the synthesis follow from the evidence?")
    adjusted_score: int = Field(ge=0, le=100, description="score after adversarial re-check")
    note: str = Field(min_length=1, description="what the check found")


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
        screening=d["screening"], meta=d.get("meta", {}), documents=d.get("documents", []),
    )


def load_dossiers(path=None) -> list[Dossier]:
    """Load dossiers from the per-customer folders (or a legacy dossiers.json path)."""
    from frisk.data.loaders import load_all
    return load_all(path)


class _DecimalEncoder(json.JSONEncoder):
    def default(self, o):
        if isinstance(o, Decimal):
            return str(o)
        return super().default(o)


def dumps(obj) -> str:
    """JSON dump that renders Decimal as string (so amounts round-trip exactly)."""
    return json.dumps(obj, cls=_DecimalEncoder, indent=2, default=str)
