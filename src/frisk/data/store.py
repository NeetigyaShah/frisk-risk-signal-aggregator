"""SQLite decisions store — the scalable read path.

At scale the dashboard must NOT re-score thousands of customers on every page load. Workers write
scored decisions here; the UI (and any API) query this indexed table. Swap sqlite3 for Postgres in
production by changing only this module — the interface (upsert_many / query / get / count) is stable.
"""
from __future__ import annotations

import json
import os
import sqlite3
from datetime import datetime, timezone

from frisk.config import CONFIG

from frisk.paths import DECISIONS_DB as DB

SCHEMA = """
CREATE TABLE IF NOT EXISTS decisions(
  customer_id TEXT PRIMARY KEY, name TEXT, score INTEGER, band TEXT, action TEXT, tier TEXT,
  confidence REAL, engine_path TEXT, country TEXT, pep INTEGER, llm_score INTEGER,
  drivers TEXT, findings TEXT, flags TEXT, rationale TEXT, ts TEXT
);
CREATE INDEX IF NOT EXISTS idx_band   ON decisions(band);
CREATE INDEX IF NOT EXISTS idx_action ON decisions(action);
CREATE INDEX IF NOT EXISTS idx_score  ON decisions(score DESC);
"""


def _conn():
    os.makedirs(os.path.dirname(DB), exist_ok=True)
    c = sqlite3.connect(DB)
    c.row_factory = sqlite3.Row
    return c


def init():
    with _conn() as c:
        c.executescript(SCHEMA)


def upsert_many(decisions) -> int:
    init()
    now = datetime.now(timezone.utc).isoformat()
    rows = [(d.customer_id, d.name, d.score, d.band, d.action, d.tier, d.confidence, d.engine_path,
             d.country, int(d.pep), d.llm_score, json.dumps(d.drivers), json.dumps(d.findings),
             json.dumps(d.flags), d.rationale, now) for d in decisions]
    with _conn() as c:
        c.executemany(
            "INSERT INTO decisions VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?) "
            "ON CONFLICT(customer_id) DO UPDATE SET "
            "score=excluded.score, band=excluded.band, action=excluded.action, tier=excluded.tier, "
            "confidence=excluded.confidence, engine_path=excluded.engine_path, llm_score=excluded.llm_score, "
            "drivers=excluded.drivers, findings=excluded.findings, flags=excluded.flags, "
            "rationale=excluded.rationale, ts=excluded.ts", rows)
    return len(rows)


def _row(r: sqlite3.Row) -> dict:
    d = dict(r)
    for k in ("drivers", "findings", "flags"):
        d[k] = json.loads(d[k]) if d[k] else []
    return d


def query(band: str | None = None, action: str | None = None, limit: int | None = None) -> list[dict]:
    init()
    q, conds, args = "SELECT * FROM decisions", [], []
    if band:
        conds.append("band = ?"); args.append(band)
    if action:
        conds.append("action = ?"); args.append(action)
    if conds:
        q += " WHERE " + " AND ".join(conds)
    q += " ORDER BY score DESC"
    if limit:
        q += f" LIMIT {int(limit)}"
    with _conn() as c:
        return [_row(r) for r in c.execute(q, args)]


def get(customer_id: str) -> dict | None:
    init()
    with _conn() as c:
        r = c.execute("SELECT * FROM decisions WHERE customer_id = ?", (customer_id,)).fetchone()
        return _row(r) if r else None


def count() -> int:
    init()
    with _conn() as c:
        return c.execute("SELECT COUNT(*) FROM decisions").fetchone()[0]
