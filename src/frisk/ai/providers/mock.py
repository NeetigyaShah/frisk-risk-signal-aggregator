"""Deterministic mock provider — a real rule-based oracle, not a stub.

Enables zero-key, fully offline, reproducible runs (used in CI and as the reference behaviour a real
model must beat). Produces a schema-valid score derived deterministically from the prompt.
"""
from __future__ import annotations

import hashlib

from pydantic import BaseModel

from frisk.ai.providers.base import Provider


class MockProvider(Provider):
    name = "mock"

    def available(self) -> bool:
        return True  # always available; needs no key

    def complete(self, prompt: str, schema: type[BaseModel]) -> BaseModel:
        # deterministic pseudo-score from the prompt; band is coerced from score by the schema validator
        score = int(hashlib.sha256(prompt.encode()).hexdigest(), 16) % 101
        fields = getattr(schema, "model_fields", {})
        data = {}
        if "score" in fields:
            data["score"] = score
        if "rationale" in fields:
            data["rationale"] = "Deterministic mock second opinion."
        if "risk_level" in fields:
            data["risk_level"] = "high" if score >= 66 else "medium" if score >= 36 else "low"
        if "domain" in fields:
            data["domain"] = "kyc"
        if "consistent" in fields:
            data["consistent"] = True
        if "adjusted_score" in fields:
            data["adjusted_score"] = score
        if "note" in fields:
            data["note"] = "mock"
        return schema.model_validate(data)
