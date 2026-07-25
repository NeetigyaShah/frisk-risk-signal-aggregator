"""Procedural memory — distil "lessons learned" from human corrections.

Periodically (``frisk reflect``) an LLM reads the most recent reviewer corrections and writes 1-3 short
rules-of-thumb into the ``lessons`` table. The orchestrator injects the top lessons into its system prompt,
so the system nudges its own behaviour toward expert judgement over time.
"""
from __future__ import annotations

from pydantic import BaseModel, Field

from frisk.ai.providers.factory import get_provider
from frisk.ai.providers.limiter import llm_slot
from frisk.data import store
from frisk.hitl.feedback import all_corrections


class Lessons(BaseModel):
    lessons: list[str] = Field(default_factory=list, description="1-3 short general rules-of-thumb")


def reflect(k: int = 20, created_ts: str = "") -> int:
    corr = all_corrections()[-k:]
    if not corr:
        return 0
    summary = "\n".join(
        f"- {c['customer_id']}: reviewer set {c['human_score']}/100 ({c['band']}) — {c.get('note', '')}"
        for c in corr
    )
    prompt = ("You are an AML QA lead. From these recent human corrections to the AI's risk scores, distil "
              "1-3 SHORT, general rules-of-thumb (one sentence each) the AI should apply next time to avoid "
              "repeating the same mistakes. Respond in JSON with key lessons (a list of strings).\n\n" + summary)
    try:
        with llm_slot():
            lessons = get_provider().complete(prompt, Lessons).lessons[:3]
    except Exception:
        lessons = []
    ids = [c["customer_id"] for c in corr]
    for text in lessons:
        if text.strip():
            store.add_lesson(text.strip(), ids, created_ts)
    return len([x for x in lessons if x.strip()])


if __name__ == "__main__":  # self-check (mock)
    import os
    os.environ["FRISK_PROVIDER"] = "mock"
    from frisk.hitl import feedback
    store.reset()
    feedback.record("C1", "salary + card spend", 15, "LOW", "AUTO_CLEAR", "ordinary domestic activity", "rev")
    feedback.record("C2", "pep but benign", 30, "LOW", "REVIEW", "PEP alone is not high risk", "rev")
    n = reflect(created_ts="2026-07-24T00:00:00Z")
    assert n >= 1 and store.top_lessons(5), "reflection should add at least one lesson"
    print(f"reflection self-check OK: {n} lesson(s) — e.g. {store.top_lessons(1)[0]['text'][:60]}")
