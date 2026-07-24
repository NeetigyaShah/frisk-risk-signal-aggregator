"""Append-only decision store (JSONL).

Regulators inspect whether *closures* are defensible, so we log every decision — auto-clears and
escalates alike — plus every analyst override. The file is only ever appended to; `reset()` exists
solely to seed a clean demo run.

ponytail: JSONL append is enough for a POC audit trail; sqlite adds nothing here.
"""
from __future__ import annotations

import json
import os
from dataclasses import asdict

from frisk.core.models import AuditRecord

from frisk.paths import AUDIT_LOG as LOG


def append(rec: AuditRecord) -> None:
    with open(LOG, "a", encoding="utf-8") as f:
        f.write(json.dumps(asdict(rec), default=str) + "\n")


def read_all() -> list[dict]:
    if not os.path.exists(LOG):
        return []
    with open(LOG, encoding="utf-8") as f:
        return [json.loads(line) for line in f if line.strip()]


def for_customer(customer_id: str) -> list[dict]:
    return [r for r in read_all() if r.get("customer_id") == customer_id]


def reset() -> None:
    if os.path.exists(LOG):
        os.remove(LOG)
