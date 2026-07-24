"""Domain policy — the small calibratable knob left after the full-LLM rebuild.

The deterministic scoring model is gone (the LLM scores). What remains here is the disposition policy:
band cutoffs + HITL routing thresholds + the deterministic seed. Advisory typology detection windows now
live in ``ai/tools.py``; higher-risk reference lists live in ``data/reference/``. Infra/env settings
(providers, keys, scale, agent knobs) live in ``settings.py``.
"""
from __future__ import annotations

CONFIG = {
    "seed": 42,
    "policy_version": "v2.0",

    # bands: score <= low_max -> LOW, <= med_max -> MED, else HIGH
    "bands": {"low_max": 35, "med_max": 65},

    # HITL routing thresholds (score cutoffs); low confidence overrides these to PENDING_REVIEW in the engine
    "routing": {"auto_clear": 15, "junior": 40, "senior": 70},
}


def band_for(score: int) -> str:
    """Deterministic band from a 0-100 score. Single source used by the engine and the RiskFinding validator."""
    if score <= CONFIG["bands"]["low_max"]:
        return "LOW"
    if score <= CONFIG["bands"]["med_max"]:
        return "MED"
    return "HIGH"


# band code (internal) <-> lowercase label (LLM/UI)
BAND_LABEL = {"LOW": "low", "MED": "medium", "HIGH": "high"}
LABEL_BAND = {v: k for k, v in BAND_LABEL.items()}
