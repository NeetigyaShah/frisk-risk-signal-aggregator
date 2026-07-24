"""Episodic memory — a case-bank of past assessments, retrieved by similarity.

Every finished assessment becomes a short "case-card" (text) + structured ``features``. Before scoring a
new customer we retrieve the most similar past cases and inject them as few-shot examples. Human-verified
cases are preferred (they're ground truth; self-outputs can be biased — see the echo-chamber risk).

Backend: a ``cases`` table in the same SQLite file. Similarity is a weighted feature overlap now;
the ``similar()`` signature is stable so a vector/embedding backend can drop in behind it later.
"""
from __future__ import annotations

import json
import os
import sqlite3

from frisk.paths import DECISIONS_DB

# feature -> weight in the overlap score (country/occupation dominate; band is a weak signal)
_WEIGHTS = {"country": 2, "occupation": 2, "pep": 1, "entity_type": 1, "band": 1, "top_signal": 2}


def _conn() -> sqlite3.Connection:
    os.makedirs(os.path.dirname(str(DECISIONS_DB)), exist_ok=True)
    c = sqlite3.connect(str(DECISIONS_DB))
    c.row_factory = sqlite3.Row
    return c


def migrate() -> None:
    with _conn() as c:
        c.execute(
            "CREATE TABLE IF NOT EXISTS cases ("
            "id INTEGER PRIMARY KEY AUTOINCREMENT, customer_id TEXT, card TEXT, features TEXT, "
            "band TEXT, disposition TEXT, human_verified INTEGER DEFAULT 0, created_ts TEXT)"
        )


def add(customer_id: str, card: str, features: dict, band: str, disposition: str,
        human_verified: bool = False, created_ts: str = "") -> int:
    migrate()
    with _conn() as c:
        cur = c.execute(
            "INSERT INTO cases(customer_id,card,features,band,disposition,human_verified,created_ts)"
            " VALUES(?,?,?,?,?,?,?)",
            (customer_id, card, json.dumps(features), band, disposition, int(bool(human_verified)), created_ts),
        )
        return int(cur.lastrowid)


def _score(query: dict, feats: dict) -> int:
    return sum(w for k, w in _WEIGHTS.items() if k in query and query.get(k) == feats.get(k))


def similar(features: dict, k: int = 3, prefer_verified: bool = True) -> list[dict]:
    """Top-k most similar past cases by weighted feature overlap. Verified cases get a tie-break bonus."""
    migrate()
    with _conn() as c:
        rows = c.execute("SELECT * FROM cases").fetchall()
    scored = []
    for r in rows:
        feats = json.loads(r["features"] or "{}")
        s = _score(features, feats)
        if prefer_verified and r["human_verified"]:
            s += 0.5  # break ties toward ground-truth
        if s > 0:
            scored.append({"card": r["card"], "band": r["band"], "disposition": r["disposition"],
                           "human_verified": bool(r["human_verified"]), "customer_id": r["customer_id"],
                           "score": s})
    scored.sort(key=lambda x: -x["score"])
    return scored[:k]


def count() -> int:
    migrate()
    with _conn() as c:
        return int(c.execute("SELECT COUNT(*) FROM cases").fetchone()[0])


def reset() -> None:
    with _conn() as c:
        c.execute("DROP TABLE IF EXISTS cases")
    migrate()


if __name__ == "__main__":  # self-check
    reset()
    add("A", "arms dealer, Syria, clustered cash -> HIGH escalate",
        {"country": "SY", "occupation": "director", "pep": True, "band": "HIGH"}, "HIGH", "ESCALATE", True)
    add("B", "teacher, UK, salary+card -> LOW auto-clear",
        {"country": "GB", "occupation": "teacher", "pep": False, "band": "LOW"}, "LOW", "AUTO_CLEAR", True)
    top = similar({"country": "SY", "occupation": "director", "pep": True}, k=1)
    assert top and top[0]["customer_id"] == "A", top
    assert similar({"country": "GB", "occupation": "teacher"}, k=1)[0]["customer_id"] == "B"
    print("casebank self-check OK: similarity ranks feature overlap")
