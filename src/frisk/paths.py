"""Central filesystem paths — resolved once, overridable via FRISK_DATA_DIR.

Every module reads data/cache/db locations from here instead of navigating `../..` relative to its
own file, so moving a module between sub-packages never breaks a path.
"""
from __future__ import annotations

import os
from pathlib import Path

PKG_ROOT = Path(__file__).resolve().parent      # src/frisk
SRC_ROOT = PKG_ROOT.parent                       # src
PROJECT_ROOT = SRC_ROOT.parent                   # repo root

DATA_DIR = Path(os.environ.get("FRISK_DATA_DIR", str(PROJECT_ROOT / "data")))
DATA_DIR.mkdir(parents=True, exist_ok=True)

DOSSIERS = DATA_DIR / "dossiers.json"
CUSTOMERS_DIR = DATA_DIR / "customers"          # per-customer folders of structured + unstructured docs
LLM_CACHE = DATA_DIR / "llm_cache.json"
AUDIT_LOG = DATA_DIR / "audit_log.jsonl"
DECISIONS_DB = DATA_DIR / "decisions.db"
FEEDBACK_LOG = DATA_DIR / "feedback.jsonl"       # human corrections (few-shot loop)
ENV_FILE = PROJECT_ROOT / ".env"
