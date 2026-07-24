"""Single source of truth for all tunable knobs.

Everything calibratable — weights, floors, windows, band cutoffs, routing thresholds —
lives in CONFIG. No magic numbers anywhere else. This is what a real compliance team
recalibrates; keeping it in one auditable place is the whole point.
"""
from __future__ import annotations

import os
from decimal import Decimal

try:  # load .env (API keys) so any entrypoint — scripts, streamlit, tests — sees them
    from dotenv import load_dotenv
    load_dotenv(os.path.join(os.path.dirname(__file__), "..", ".env"))
except Exception:
    pass

CONFIG = {
    "seed": 42,
    "ruleset_version": "v1.0",

    # --- money / typology thresholds ---
    "reporting_floor": Decimal("10000"),  # cash-transaction reporting floor (structuring clusters just under this)
    "structuring": {"window_days": 7, "min_count": 3, "low_frac": Decimal("0.8")},
    "layering": {"min_hops": 3, "forward_ratio": Decimal("0.80"), "window_days": 5},
    "round_trip": {"window_days": 10, "amount_tol": Decimal("0.15")},
    "dormant_spike": {"dormant_days": 90, "spike_mult": Decimal("5"), "baseline_days": 90, "min_burst": 3, "burst_min_amount": Decimal("15000")},
    "cash_intensity": {"min_ratio": Decimal("0.30"), "min_sum": Decimal("5000")},
    "velocity": {"window_days": 30, "min_count": 25},
    "adverse_severe_keywords": ["money laundering", "laundering", "terrorist", "sanction", "fraud ring"],

    # --- profile risk reference lists ---
    "high_risk_countries": ["IR", "KP", "SY", "RU", "AF", "MM", "YE", "VE"],  # ISO-2
    "high_risk_occupations": [
        "casino operator", "crypto dealer", "arms dealer",
        "money exchange", "shell company director", "precious metals trader",
    ],
    "new_account_days": 90,

    # --- factor weights: points added when a (non-override) rule fires; additive, capped at 100 ---
    "weights": {
        "HIGH_RISK_GEO": 22,
        "PEP": 30,
        "HIGH_RISK_OCCUPATION": 22,
        "KYC_INCOMPLETE": 15,
        "NEW_ACCOUNT": 12,
        "ADVERSE_MEDIA": 20,
        "ADVERSE_MEDIA_SEVERE": 30,
        "CASH_INTENSITY": 18,
        "HIGH_VELOCITY": 15,
        # typologies: one alone -> MED; a typology + a risk factor -> HIGH
        "STRUCTURING": 45,
        "LAYERING": 42,
        "ROUND_TRIP": 45,
        "DORMANT_SPIKE": 45,
    },

    # --- bands: score <= low_max -> LOW, <= med_max -> MED, else HIGH ---
    "bands": {"low_max": 35, "med_max": 65},

    # --- HITL routing thresholds (score cutoffs) ---
    "routing": {"auto_clear": 15, "junior": 40, "senior": 70},
    # override codes that force ESCALATE regardless of arithmetic (kill-switch)
    "hard_escalate": ["SANCTIONS_MATCH", "PEP_HIGH_GEO"],

    # rules<->llm agreement tolerance (score points) used for confidence-gated routing
    "agreement_tolerance": 20,
    # rules-only / degraded path can never exceed this confidence and never auto-clears
    "degraded_confidence_cap": 0.49,

    # --- LLM cross-check ---
    "llm": {
        # mode: "auto" -> real model if a provider key is set, else deterministic simulated
        #       second opinion (so the demo shows confidence + auto-clear offline);
        #       "off" -> pure rules-only (degraded, never auto-clears).
        "mode": "auto",
        "provider": "nvidia",                       # nvidia | gemini | anthropic
        "nvidia_model": "nvidia/nemotron-3-ultra-550b-a55b",
        "nvidia_base_url": "https://integrate.api.nvidia.com/v1",
        "gemini_model": "gemini-2.5-flash-lite",    # fast, high free-tier quota
        "model": "claude-haiku-4-5-20251001",       # anthropic model
        "temperature": 0,
        "max_tokens": 8192,
        "max_retries": 3,
        "timeout_s": 60,
    },
}


def band_for(score: int) -> str:
    """Deterministic band from a 0-100 score. Single source used by rules, engine, and the LLM validator."""
    if score <= CONFIG["bands"]["low_max"]:
        return "LOW"
    if score <= CONFIG["bands"]["med_max"]:
        return "MED"
    return "HIGH"


# band code (internal) <-> lowercase label (LLM/UI)
BAND_LABEL = {"LOW": "low", "MED": "medium", "HIGH": "high"}
LABEL_BAND = {v: k for k, v in BAND_LABEL.items()}
