"""Ingestion — read a customer's folder of mixed documents into a typed Dossier.

Structured files (kyc.json, account.json, transactions.csv, screening.json) map to the Dossier fields;
every ``*.txt`` becomes an unstructured document the LLM analysts read. This is the ingestion seam a
production system would extend to accept uploaded CSV/JSON or pasted text (see ``parse_pasted``).
"""
from __future__ import annotations

import csv
import io
import json
from decimal import Decimal
from pathlib import Path

from frisk.core.models import Dossier, Txn
from frisk.paths import CUSTOMERS_DIR


def _txns_from_csv(text: str) -> list[Txn]:
    out = []
    for r in csv.DictReader(io.StringIO(text)):
        out.append(Txn(r["txn_id"], r["date"], Decimal(str(r["amount"])), r["currency"], r["direction"],
                       r["counterparty"], r["counterparty_country"], r["txn_type"]))
    return out


def load_customer(cdir: Path) -> Dossier:
    def j(name, default):
        p = cdir / name
        return json.loads(p.read_text(encoding="utf-8")) if p.exists() else default

    kyc = j("kyc.json", {})
    account = j("account.json", {})
    screening = j("screening.json", {"pep_confirmed": False})
    meta = j("_meta.json", {})
    tx_path = cdir / "transactions.csv"
    txns = _txns_from_csv(tx_path.read_text(encoding="utf-8")) if tx_path.exists() else []
    documents = [{"name": p.name, "kind": "unstructured", "text": p.read_text(encoding="utf-8")}
                 for p in sorted(cdir.glob("*.txt"))]
    cid = account.get("customer_id") or cdir.name
    profile = {k: v for k, v in account.items() if k != "customer_id"}
    return Dossier(cid, kyc, profile, txns, screening, meta, documents)


def load_all(path=None) -> list[Dossier]:
    """Load every customer folder under `path` (or the default customers dir). Legacy `.json` also accepted."""
    if path and str(path).endswith(".json"):  # back-compat with the old single dossiers.json
        from frisk.core.models import dossier_from_dict
        raw = json.loads(Path(path).read_text(encoding="utf-8"))
        return [dossier_from_dict(d) for d in raw]
    root = Path(path) if path else CUSTOMERS_DIR
    return [load_customer(d) for d in sorted(p for p in root.iterdir() if p.is_dir())]


def dossier_from_files(files: dict[str, str], customer_id: str = "UPLOAD_001") -> Dossier:
    """Build a Dossier from in-memory uploaded files (name -> text). Same mapping as a folder."""
    def j(name, default):
        return json.loads(files[name]) if name in files else default

    kyc = j("kyc.json", {})
    account = j("account.json", {})
    screening = j("screening.json", {"pep_confirmed": False})
    meta = j("_meta.json", {})
    txns = _txns_from_csv(files["transactions.csv"]) if "transactions.csv" in files else []
    documents = [{"name": n, "kind": "unstructured", "text": t} for n, t in files.items() if n.endswith(".txt")]
    cid = account.get("customer_id") or customer_id
    profile = {k: v for k, v in account.items() if k != "customer_id"}
    return Dossier(cid, kyc, profile, txns, screening, meta, documents)


def parse_pasted(text: str, customer_id: str = "PASTED_001") -> Dossier:
    """Best-effort ingestion of pasted JSON (a single dossier-shaped object) — for the upload/paste UI."""
    try:
        obj = json.loads(text)
        from frisk.core.models import dossier_from_dict
        obj.setdefault("customer_id", customer_id)
        return dossier_from_dict(obj)
    except Exception:
        # treat as free-text: one unstructured document, minimal structured shell
        return Dossier(customer_id, {}, {}, [], {"pep_confirmed": False},
                       {}, [{"name": "pasted.txt", "kind": "unstructured", "text": text}])
