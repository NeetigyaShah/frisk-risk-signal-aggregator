"""Relational store — the durable, queryable record (per-customer history + procedural lessons).

SQLite now (→ Postgres at scale), one file at ``paths.DECISIONS_DB``. Three tables:
  * ``customers``   — stable attributes, one row per customer (upserted).
  * ``assessments`` — APPEND-ONLY history, one row per scoring event (this is the per-customer memory tier).
  * ``lessons``     — procedural "lessons learned" distilled from human corrections.

The dashboard queue reads ``latest_all()``; the agent's per-customer memory reads ``history(cid)``.
JSON columns (key_signals) are encoded/decoded here so callers pass/receive plain Python.
"""
from __future__ import annotations

import json
import os
import sqlite3
from typing import Any

from frisk.paths import DECISIONS_DB

_JSON_COLS = ("key_signals",)


def _conn() -> sqlite3.Connection:
    os.makedirs(os.path.dirname(str(DECISIONS_DB)), exist_ok=True)
    c = sqlite3.connect(str(DECISIONS_DB), timeout=10)
    c.execute("PRAGMA busy_timeout=10000")   # tolerate concurrent batch writers
    c.row_factory = sqlite3.Row
    return c


def migrate() -> None:
    with _conn() as c:
        c.executescript(
            """
            CREATE TABLE IF NOT EXISTS customers (
                customer_id TEXT PRIMARY KEY, name TEXT, entity_type TEXT, country TEXT,
                occupation TEXT, pep INTEGER, first_seen TEXT
            );
            CREATE TABLE IF NOT EXISTS assessments (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                customer_id TEXT, ts TEXT, score INTEGER, band TEXT, confidence REAL,
                disposition TEXT, key_signals TEXT, rationale TEXT, trace_ref TEXT,
                human_verified INTEGER DEFAULT 0, corrected_score INTEGER
            );
            CREATE INDEX IF NOT EXISTS ix_assess_cust ON assessments(customer_id, id);
            CREATE TABLE IF NOT EXISTS lessons (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                text TEXT, from_corrections TEXT, created_ts TEXT, weight REAL DEFAULT 1.0
            );
            """
        )


init = migrate  # back-compat alias


def _row(r: sqlite3.Row) -> dict[str, Any]:
    d = dict(r)
    for col in _JSON_COLS:
        if col in d and isinstance(d[col], str):
            try:
                d[col] = json.loads(d[col])
            except (json.JSONDecodeError, TypeError):
                d[col] = []
    for b in ("pep", "human_verified"):
        if d.get(b) is not None:
            d[b] = bool(d[b])
    return d


def record_assessment(dec: dict) -> int:
    """Append one assessment (per-customer history) and upsert the customer. Returns the assessment id."""
    with _conn() as c:
        c.execute(
            "INSERT OR IGNORE INTO customers(customer_id,name,entity_type,country,occupation,pep,first_seen)"
            " VALUES(?,?,?,?,?,?,?)",
            (dec["customer_id"], dec.get("name"), dec.get("entity_type"), dec.get("country"),
             dec.get("occupation"), int(bool(dec.get("pep"))), dec.get("ts")),
        )
        c.execute(
            "UPDATE customers SET name=?,entity_type=?,country=?,occupation=?,pep=? WHERE customer_id=?",
            (dec.get("name"), dec.get("entity_type"), dec.get("country"), dec.get("occupation"),
             int(bool(dec.get("pep"))), dec["customer_id"]),
        )
        cur = c.execute(
            "INSERT INTO assessments(customer_id,ts,score,band,confidence,disposition,key_signals,"
            "rationale,trace_ref,human_verified,corrected_score) VALUES(?,?,?,?,?,?,?,?,?,?,?)",
            (dec["customer_id"], dec.get("ts"), int(dec.get("score", 0)), dec.get("band"),
             float(dec.get("confidence", 0.0)), dec.get("disposition"),
             json.dumps(dec.get("key_signals", [])), dec.get("rationale"), dec.get("trace_ref"),
             int(bool(dec.get("human_verified"))), dec.get("corrected_score")),
        )
        return int(cur.lastrowid)


def record_many(decisions: list[dict]) -> int:
    for d in decisions:
        record_assessment(d)
    return len(decisions)


def history(customer_id: str, k: int = 5) -> list[dict]:
    """Newest-first prior assessments for one customer — the per-customer memory tier."""
    migrate()
    with _conn() as c:
        rows = c.execute(
            "SELECT * FROM assessments WHERE customer_id=? ORDER BY id DESC LIMIT ?", (customer_id, k)
        ).fetchall()
    return [_row(r) for r in rows]


def latest_all() -> list[dict]:
    """The most-recent assessment per customer — the dashboard queue read path."""
    migrate()
    with _conn() as c:
        rows = c.execute(
            "SELECT a.* FROM assessments a JOIN (SELECT customer_id, MAX(id) mid FROM assessments "
            "GROUP BY customer_id) m ON a.id=m.mid ORDER BY a.score DESC"
        ).fetchall()
    return [_row(r) for r in rows]


def get(customer_id: str) -> dict | None:
    h = history(customer_id, k=1)
    return h[0] if h else None


def add_lesson(text: str, from_corrections: list | None = None, created_ts: str = "", weight: float = 1.0) -> int:
    with _conn() as c:
        cur = c.execute(
            "INSERT INTO lessons(text,from_corrections,created_ts,weight) VALUES(?,?,?,?)",
            (text, json.dumps(from_corrections or []), created_ts, weight),
        )
        return int(cur.lastrowid)


def top_lessons(k: int = 5) -> list[dict]:
    migrate()
    with _conn() as c:
        rows = c.execute(
            "SELECT * FROM lessons ORDER BY weight DESC, id DESC LIMIT ?", (k,)
        ).fetchall()
    return [dict(r) for r in rows]


def count() -> int:
    with _conn() as c:
        return int(c.execute("SELECT COUNT(*) FROM assessments").fetchone()[0])


def reset() -> None:
    with _conn() as c:
        c.executescript("DROP TABLE IF EXISTS customers; DROP TABLE IF EXISTS assessments; "
                        "DROP TABLE IF EXISTS lessons;")
    migrate()


if __name__ == "__main__":  # self-check
    reset()
    base = dict(customer_id="C1", name="A", entity_type="individual", country="GB", occupation="x",
                pep=False, band="LOW", confidence=0.9, disposition="AUTO_CLEAR", key_signals=["k"],
                rationale="r", trace_ref="t", human_verified=False, corrected_score=None)
    record_assessment({**base, "ts": "2026-01-01T00:00:00Z", "score": 10})
    record_assessment({**base, "ts": "2026-02-01T00:00:00Z", "score": 40})
    h = history("C1", k=5)
    assert [r["score"] for r in h] == [40, 10], h
    la = latest_all()
    assert len(la) == 1 and la[0]["score"] == 40, la
    assert la[0]["key_signals"] == ["k"]
    add_lesson("don't over-flag domestic salary+card spend", ["corr1"], "2026-02-02T00:00:00Z", 2.0)
    assert top_lessons(1)[0]["text"].startswith("don't over-flag")
    print("store self-check OK: history newest-first, latest-per-customer, lessons")
