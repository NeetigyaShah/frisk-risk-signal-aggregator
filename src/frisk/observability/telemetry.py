"""LangSmith observability (opt-in).

Tracing is wired via the ``@traceable`` decorator on the cross-check and each LangGraph node. It is a
no-op unless enabled. Enable with:  LANGSMITH_TRACING=true  +  LANGSMITH_API_KEY=...  (+ LANGSMITH_PROJECT).
"""
from __future__ import annotations

import os


def enabled() -> bool:
    return os.environ.get("LANGSMITH_TRACING", "").lower() in ("1", "true", "yes")


def status() -> str:
    if not enabled():
        return "LangSmith tracing OFF (set LANGSMITH_TRACING=true + LANGSMITH_API_KEY to enable)"
    return f"LangSmith tracing ON -> project '{os.environ.get('LANGSMITH_PROJECT', 'default')}'"
