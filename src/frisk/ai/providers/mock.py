"""Deterministic mock provider — a real offline oracle that DRIVES the agent, not a stub.

Two jobs:
  * ``complete(prompt, schema)`` — fills any of our Pydantic schemas (incl. SpecialistOpinion) with a
    deterministic keyword-derived score, so parallel specialists run offline.
  * ``chat_model()`` — a fake tool-calling chat model that emits a fixed tool sequence
    (read_kyc → query_transactions → find_txn_patterns → read_document → finalize) so the orchestrator
    loop runs end-to-end with zero key. Score is keyword-derived; confidence drops on "borderline"
    language so the ambiguous review cases deterministically route to the human queue.
"""
from __future__ import annotations

from pydantic import BaseModel

from frisk.ai.providers.base import Provider

_OCC = ["arms dealer", "arms broker", "shell company", "crypto dealer", "money exchange",
        "procurement agent", "precious metals", "gem trader", "casino"]
_TYP = ["structuring", "layering", "round_trip", "round-trip", "dormant"]
_GEO = ["iran", "syria", "north korea", "russia", "venezuela", "myanmar", "yemen", "afghanistan", "pakistan"]
_PEP = ["pep=true", "politically exposed", "'pep': true", "pep': true", "pep: true", "\"pep\": true"]
_BORDERLINE = ["borderline", "second opinion", "conflicting information", "unclear whether", "not independently verified"]


def _score(text: str) -> int:
    t = text.lower()
    s = 10
    if any(k in t for k in _OCC):
        s += 25
    if any(k in t for k in _TYP):
        s += 30
    if any(k in t for k in _GEO):
        s += 18
    if any(k in t for k in _PEP):
        s += 12
    return min(s, 100)


def _signals(text: str) -> list[str]:
    t = text.lower()
    out = []
    if any(k in t for k in _OCC):
        out.append("high-risk occupation")
    for k in _TYP:
        if k in t:
            out.append(k.replace("-", "_")); break
    if any(k in t for k in _GEO):
        out.append("high-risk jurisdiction")
    if any(k in t for k in _PEP):
        out.append("PEP")
    return out or ["no material signal"]


class MockProvider(Provider):
    name = "mock"

    def available(self) -> bool:
        return True

    def complete(self, prompt: str, schema: type[BaseModel]) -> BaseModel:
        score = _score(prompt)
        fields = getattr(schema, "model_fields", {})
        data: dict = {}
        if "score" in fields:
            data["score"] = score
        if "tentative_score" in fields:
            data["tentative_score"] = score
        if "risk_level" in fields:
            data["risk_level"] = "high" if score >= 66 else "medium" if score >= 36 else "low"
        if "domain" in fields:
            data["domain"] = ("transactions" if "transaction" in prompt.lower()
                              else "documents" if "document" in prompt.lower() else "kyc")
        if "signals" in fields:
            data["signals"] = _signals(prompt)
        if "key_signals" in fields:
            data["key_signals"] = _signals(prompt)
        if "rationale" in fields:
            data["rationale"] = "Deterministic mock assessment from the facts."
        if "note" in fields:
            data["note"] = "mock domain note"
        if "confidence" in fields:
            data["confidence"] = 0.4 if any(k in prompt.lower() for k in _BORDERLINE) else 0.9
        if "consistent" in fields:
            data["consistent"] = True
        if "adjusted_score" in fields:
            data["adjusted_score"] = score
        return schema.model_validate(data)

    def chat_model(self):
        return _MockChat()


class _MockChat:
    """A fake tool-calling chat model: emits a fixed tool sequence, then finalize."""

    def bind_tools(self, tools, **kwargs):
        return self

    def invoke(self, messages):
        from langchain_core.messages import AIMessage, ToolMessage
        n = sum(1 for m in messages if isinstance(m, ToolMessage))
        text = " ".join(str(getattr(m, "content", "")) for m in messages)
        script = [
            ("read_kyc", {}),
            ("query_transactions", {"direction": "in"}),
            ("find_txn_patterns", {"hint": "free"}),
            ("read_document", {"name": "rm_notes"}),
        ]
        if n < len(script):
            name, args = script[n]
            return AIMessage(content="", tool_calls=[{"name": name, "args": args, "id": f"call_{n}"}])
        score = _score(text)
        conf = 0.4 if any(k in text.lower() for k in _BORDERLINE) else 0.9
        args = {"score": score, "confidence": conf, "rationale": "Mock agent decision from the gathered facts.",
                "key_signals": _signals(text), "evidence_refs": ["rm_notes.txt"]}
        return AIMessage(content="", tool_calls=[{"name": "finalize", "args": args, "id": "call_final"}])
