"""Seeded synthetic dossier generator — 20 multi-source customer profiles.

Determinism is the whole point: same seed -> byte-identical dossiers.json. All RNGs are seeded
once; dates are anchored to a fixed REF_DATE (never datetime.now()); money is Decimal.

Run:  python data/generate.py         -> writes data/dossiers.json and runs the self-check.
"""
from __future__ import annotations

import hashlib
import os
import random
import sys
from datetime import date, timedelta
from decimal import Decimal

import numpy as np
from faker import Faker

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))
from config import CONFIG                      # noqa: E402
from models import Dossier, Txn, dumps          # noqa: E402

SEED = CONFIG["seed"]
FLOOR = CONFIG["reporting_floor"]
REF_DATE = date(2026, 7, 24)          # fixed anchor -> deterministic dates
OUT = os.path.join(os.path.dirname(__file__), "dossiers.json")

fake = Faker("en_GB")


# --------------------------------------------------------------------------- #
# The declarative 20-profile table. Each row's flags drive both the generated
# signals and the expected band. Mix: 6 low, 7 med, 5 high, 2 critical.
# --------------------------------------------------------------------------- #
PROFILES = [
    # --- 6 low: domestic, complete KYC, benign, no adverse, no firing factors ---
    {"sev": "low", "country": "GB", "occ": "teacher"},
    {"sev": "low", "country": "GB", "occ": "nurse"},
    {"sev": "low", "country": "IE", "occ": "software engineer"},
    {"sev": "low", "country": "GB", "occ": "accountant"},
    {"sev": "low", "country": "GB", "occ": "retail manager", "missing": "transactions"},  # robustness: no txns
    {"sev": "low", "country": "FR", "occ": "chef"},

    # --- 7 med: two deterministic risk factors each (36-65) ---
    {"sev": "med", "country": "RU", "occ": "consultant", "adverse": 1},                  # geo + adverse
    {"sev": "med", "country": "GB", "occ": "politician", "pep": True, "new_account": True},  # pep + new
    {"sev": "med", "country": "GB", "occ": "money exchange", "adverse": 1},              # occ + adverse
    {"sev": "med", "country": "VE", "occ": "importer", "adverse": 1, "missing": "kyc_id"},  # geo + adverse + missing id
    {"sev": "med", "country": "GB", "occ": "landlord", "pep": True, "adverse": 1},       # pep + adverse
    {"sev": "med", "country": "RU", "occ": "precious metals trader"},                    # geo + occ
    {"sev": "med", "country": "GB", "occ": "consultant", "pep": True, "new_account": True},  # pep + new

    # --- 5 high: a typology + reinforcing risk factor(s) ---
    {"sev": "high", "country": "RU", "occ": "consultant", "typology": "structuring", "cash_heavy": True},        # structuring + geo
    {"sev": "high", "country": "GB", "occ": "crypto dealer", "typology": "layering", "adverse": 2},               # layering + occ + severe adverse
    {"sev": "high", "country": "MM", "occ": "trader", "typology": "round_trip"},                                  # round_trip + geo
    {"sev": "high", "country": "GB", "occ": "precious metals trader", "typology": "dormant_spike", "adverse": 1,
     "extra": "second_passport"},                                                                                 # dormant + occ + adverse
    {"sev": "high", "country": "GB", "occ": "politician", "pep": True, "typology": "structuring", "cash_heavy": True},  # structuring + pep

    # --- 2 critical: sanctions match -> override -> forced HIGH/ESCALATE ---
    {"sev": "critical", "country": "IR", "occ": "arms dealer", "sanctioned": True, "typology": "structuring"},
    {"sev": "critical", "country": "SY", "occ": "shell company director", "sanctioned": True, "pep": True},
]

EXPECTED_BAND = {"low": "LOW", "med": "MED", "high": "HIGH", "critical": "HIGH"}


# --------------------------------------------------------------------------- #
# Transaction builders
# --------------------------------------------------------------------------- #

def _dstr(days_ago: int) -> str:
    return (REF_DATE - timedelta(days=days_ago)).isoformat()


def _amt(x: float) -> Decimal:
    return Decimal(str(round(float(x), 2)))


def benign_stream(cust: str, rng: np.random.Generator, country: str, cash_heavy: bool) -> list[Txn]:
    """~6 months of ordinary activity: salary in, direct debits out, card spend out."""
    txns: list[Txn] = []
    n = 0
    salary = float(rng.uniform(2800, 6000))
    for m in range(6):  # monthly salary credit
        txns.append(Txn(f"{cust}-T{n:03d}", _dstr(m * 30 + 3), _amt(salary * rng.uniform(0.98, 1.02)),
                        "GBP", "in", "ACME Payroll Ltd", country, "salary")); n += 1
    for m in range(6):  # rent / utilities direct debits
        txns.append(Txn(f"{cust}-T{n:03d}", _dstr(m * 30 + 5), _amt(rng.uniform(600, 1400)),
                        "GBP", "out", "Landlord DD", country, "direct_debit")); n += 1
    spends = int(rng.poisson(14))
    for _ in range(spends):  # card spend, lognormal amounts
        day = int(rng.integers(1, 180))
        amt = float(np.exp(rng.normal(3.4, 0.8)))  # ~ £30 median, long tail
        txns.append(Txn(f"{cust}-T{n:03d}", _dstr(day), _amt(min(amt, 900)),
                        "GBP", "out", fake.company(), country, "card")); n += 1
    if cash_heavy:  # extra cash deposits (raises cash intensity, but individually unremarkable)
        for _ in range(int(rng.integers(4, 8))):
            day = int(rng.integers(1, 120))
            txns.append(Txn(f"{cust}-T{n:03d}", _dstr(day), _amt(rng.uniform(1500, 4000)),
                            "GBP", "in", "Cash Deposit", country, "cash")); n += 1
    return txns


def inject_structuring(cust: str, rng: np.random.Generator, country: str, start: int) -> list[Txn]:
    """>=3 cash deposits each just under FLOOR within a 7-day window, summing > FLOOR."""
    floor = float(FLOOR)
    lo = float(CONFIG["structuring"]["low_frac"]) * floor
    txns = []
    for i in range(4):
        amt = rng.uniform(lo, floor - 150)
        txns.append(Txn(f"{cust}-S{i:02d}", _dstr(40 - i * 2), _amt(amt),
                        "GBP", "in", "Cash Deposit", country, "cash"))
    return txns  # 4 * ~9k = ~36k > 10k floor, all < floor


def inject_layering(cust: str, rng: np.random.Generator, country: str, start: int) -> list[Txn]:
    """>=3 hops, each forwarding ~80% to a distinct counterparty within a few days."""
    txns = []
    amt = 240000.0
    for i in range(3):
        amt *= float(CONFIG["layering"]["forward_ratio"])
        txns.append(Txn(f"{cust}-L{i:02d}", _dstr(30 - i * 2), _amt(amt),
                        "GBP", "out", f"Shell Co {chr(65 + i)}", "CY", "transfer"))
    return txns


def inject_round_trip(cust: str, rng: np.random.Generator, country: str, start: int) -> list[Txn]:
    """Funds out then back to origin via a different counterparty within a window."""
    amt = float(rng.uniform(50000, 120000))
    return [
        Txn(f"{cust}-R00", _dstr(20), _amt(amt), "GBP", "out", "Offshore Nominee A", "KY", "wire"),
        Txn(f"{cust}-R01", _dstr(14), _amt(amt * 0.98), "GBP", "in", "Offshore Nominee B", "KY", "wire"),
    ]


def inject_dormant_spike(cust: str, rng: np.random.Generator, country: str, start: int) -> list[Txn]:
    """Old baseline, long inactivity (>90d), then a sudden burst of large txns."""
    txns = []
    for i in range(3):  # baseline ~7-8 months ago
        txns.append(Txn(f"{cust}-D{i:02d}", _dstr(230 - i * 10), _amt(rng.uniform(50, 300)),
                        "GBP", "out", fake.company(), country, "card"))
    for i in range(4):  # burst in the last 10 days
        txns.append(Txn(f"{cust}-B{i:02d}", _dstr(9 - i * 2), _amt(rng.uniform(18000, 45000)),
                        "GBP", "in", "New Counterparty", "AE", "wire"))
    return txns


INJECTORS = {
    "structuring": inject_structuring,
    "layering": inject_layering,
    "round_trip": inject_round_trip,
    "dormant_spike": inject_dormant_spike,
}


# --------------------------------------------------------------------------- #
# Dossier assembly
# --------------------------------------------------------------------------- #

def build_dossier(idx: int, p: dict, rng: np.random.Generator) -> Dossier:
    cust = f"CUST_{idx:03d}"
    country = p["country"]
    pep = p.get("pep", False)
    sanctioned = p.get("sanctioned", False)
    adverse = p.get("adverse", 0)
    typ = p.get("typology")
    cash_heavy = p.get("cash_heavy", False)
    new_account = p.get("new_account", False)

    name = fake.name()
    tenure = int(rng.integers(10, 80)) if new_account else int(rng.integers(200, 3000))

    kyc = {
        "name": name,
        "dob": fake.date_of_birth(minimum_age=25, maximum_age=70).isoformat(),
        "nationality": country,
        "occupation": p["occ"],
        "id_doc": f"P{int(rng.integers(10**7, 10**8))}",
        "onboarded": _dstr(tenure),
        "kyc_complete": True,
    }
    profile = {
        "entity_type": "individual",
        "country": country,
        "product": "current_account",
        "pep": pep,
        "tenure_days": tenure,
    }

    # transactions: dormant_spike replaces the stream; others = benign + injected
    if typ == "dormant_spike":
        txns = INJECTORS[typ](cust, rng, country, 0)
    else:
        txns = benign_stream(cust, rng, country, cash_heavy)
        if typ:
            txns += INJECTORS[typ](cust, rng, country, len(txns))

    # screening
    sanctions = []
    if sanctioned:
        sanctions.append({"name": name, "match_score": 1.0, "list": "OFAC SDN"})
    adverse_media = []
    if adverse >= 1:
        adverse_media.append({"headline": f"{name} named in fraud investigation",
                              "sentiment": "negative", "date": _dstr(45)})
    if adverse >= 2:
        adverse_media.append({"headline": f"Regulator fines firm linked to {name} for money laundering",
                              "sentiment": "negative", "date": _dstr(20)})
    screening = {
        "sanctions": sanctions,
        "pep_confirmed": pep,
        "adverse_media": adverse_media,
    }

    meta = {"expected_band": EXPECTED_BAND[p["sev"]], "severity": p["sev"], "typology": typ,
            "missing_docs": [], "extra_docs": []}

    # robustness mutations
    if p.get("missing") == "kyc_id":
        kyc["id_doc"] = None
        kyc["kyc_complete"] = False
        meta["missing_docs"].append("kyc_id")
    if p.get("missing") == "transactions":
        txns = []
        meta["missing_docs"].append("transactions")
    if p.get("extra"):
        kyc["extra_doc"] = p["extra"]
        meta["extra_docs"].append(p["extra"])

    return Dossier(cust, kyc, profile, txns, screening, meta)


def generate() -> list[Dossier]:
    Faker.seed(SEED)
    random.seed(SEED)
    rng = np.random.default_rng(SEED)
    return [build_dossier(i, p, rng) for i, p in enumerate(PROFILES)]


def to_json(dossiers: list[Dossier]) -> str:
    return dumps([{
        "customer_id": d.customer_id, "kyc": d.kyc, "profile": d.profile,
        "transactions": [vars(t) for t in d.transactions],
        "screening": d.screening, "meta": d.meta,
    } for d in dossiers])


def write() -> str:
    payload = to_json(generate())
    with open(OUT, "w", encoding="utf-8") as f:
        f.write(payload)
    return payload


# --------------------------------------------------------------------------- #
# Self-check: determinism + band coverage + typology structural properties
# --------------------------------------------------------------------------- #

def _selfcheck():
    a = to_json(generate())
    b = to_json(generate())
    assert hashlib.sha256(a.encode()).hexdigest() == hashlib.sha256(b.encode()).hexdigest(), \
        "non-deterministic: two runs differ"

    ds = generate()
    assert len(ds) == 20, f"expected 20 dossiers, got {len(ds)}"
    bands = {d.meta["expected_band"] for d in ds}
    assert bands == {"LOW", "MED", "HIGH"}, f"band coverage incomplete: {bands}"

    floor = float(FLOOR)
    for d in ds:
        typ = d.meta.get("typology")
        if typ == "structuring":
            cash = [t for t in d.transactions if t.txn_type == "cash" and t.direction == "in"
                    and float(t.amount) < floor and float(t.amount) >= 0.8 * floor]
            assert len(cash) >= 3, f"{d.customer_id}: structuring cluster < 3 sub-floor cash txns"
        if typ == "round_trip":
            outs = [t for t in d.transactions if t.direction == "out"]
            ins = [t for t in d.transactions if t.direction == "in"]
            assert outs and ins, f"{d.customer_id}: round_trip missing out/in leg"
        if typ == "layering":
            hops = [t for t in d.transactions if t.id.startswith(f"{d.customer_id}-L")]
            assert len(hops) >= 3, f"{d.customer_id}: layering < 3 hops"
    # sanctions only on critical rows
    for d in ds:
        if d.screening["sanctions"]:
            assert d.meta["severity"] == "critical", f"{d.customer_id}: unexpected sanctions hit"
    print("self-check OK: deterministic, 20 dossiers, bands covered, typologies structurally present")


if __name__ == "__main__":
    payload = write()
    print(f"wrote {OUT} ({len(payload)} bytes)")
    _selfcheck()
