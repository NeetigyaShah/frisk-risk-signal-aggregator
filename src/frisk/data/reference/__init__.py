"""Semantic memory — static reference cheat-sheets injected into specialist prompts.

General domain knowledge (typology definitions, higher-risk lists) that rarely changes and is the same
for every customer. `load(name)` reads the matching `.md`; missing files return "" so a specialist
degrades gracefully rather than crashing.
"""
from __future__ import annotations

from pathlib import Path

_DIR = Path(__file__).resolve().parent


def load(name: str) -> str:
    p = _DIR / f"{name}.md"
    return p.read_text(encoding="utf-8") if p.exists() else ""
