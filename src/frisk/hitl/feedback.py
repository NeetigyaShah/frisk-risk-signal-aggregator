"""Human corrections → few-shot examples that teach the LLM (the closed feedback loop).

When a reviewer fixes a low-confidence case, the correction is appended here. Future synthesis prompts
inject the most recent corrections so the model calibrates toward expert human judgement over time.
"""
from __future__ import annotations

import json

from frisk.paths import FEEDBACK_LOG


def record(customer_id: str, features: str, human_score: int, band: str, action: str,
           note: str, reviewer: str) -> None:
    entry = {"customer_id": customer_id, "features": (features or "")[:1200],
             "human_score": human_score, "band": band, "action": action,
             "note": note, "reviewer": reviewer}
    with open(FEEDBACK_LOG, "a", encoding="utf-8") as f:
        f.write(json.dumps(entry) + "\n")


def all_corrections() -> list[dict]:
    if not FEEDBACK_LOG.exists():
        return []
    return [json.loads(line) for line in FEEDBACK_LOG.read_text(encoding="utf-8").splitlines() if line.strip()]


def fewshot_block(k: int = 3) -> str:
    corr = all_corrections()[-k:]
    if not corr:
        return ""
    lines = ["HUMAN REVIEWER CORRECTIONS — a senior analyst set these scores; calibrate to match this judgement:"]
    for c in corr:
        lines.append(f"- corrected to {c['human_score']}/100 ({c['band']}): {c['note']}")
    return "\n".join(lines) + "\n\n"
