"""Seeded synthetic data generator — 20 customers, each a folder of REAL documents.

Every profile becomes ``data/customers/CUST_xxx/`` containing STRUCTURED files (kyc.json, account.json,
transactions.csv, screening.json) and UNSTRUCTURED files (id_document.txt OCR extract, rm_notes.txt
relationship-manager notes, adverse_media_*.txt news snippets, correspondence.txt emails). This mirrors
the fragmented, mixed-format inputs a real compliance analyst faces — and gives the LLM genuine
unstructured text to synthesise, not just tidy fields.

Determinism: seeded once, fixed REF_DATE, Decimal money. Run:  python -m frisk.data.generate
"""
from __future__ import annotations

import csv
import hashlib
import io
import json
import random
import shutil
from datetime import date, timedelta
from decimal import Decimal

import numpy as np
from faker import Faker

from frisk.config import CONFIG
from frisk.core.models import Dossier, Txn
from frisk.paths import CUSTOMERS_DIR, UPLOAD_SAMPLES

SEED = CONFIG["seed"]
FLOOR = CONFIG["reporting_floor"]
REF_DATE = date(2026, 7, 24)

fake = Faker("en_GB")

COUNTRY = {"GB": "United Kingdom", "IE": "Ireland", "FR": "France", "RU": "Russia",
           "VE": "Venezuela", "MM": "Myanmar", "IR": "Iran", "SY": "Syria",
           "CY": "Cyprus", "KY": "Cayman Islands", "AE": "United Arab Emirates",
           "DE": "Germany", "ES": "Spain", "NL": "Netherlands", "IT": "Italy", "US": "United States",
           "NG": "Nigeria", "AF": "Afghanistan", "YE": "Yemen", "KP": "North Korea", "PK": "Pakistan"}

PROFILES = [
    {"sev": "low", "country": "GB", "occ": "teacher"},
    {"sev": "low", "country": "GB", "occ": "nurse"},
    {"sev": "low", "country": "IE", "occ": "software engineer"},
    {"sev": "low", "country": "GB", "occ": "accountant"},
    {"sev": "low", "country": "GB", "occ": "retail manager", "missing": "transactions"},
    {"sev": "low", "country": "FR", "occ": "chef"},

    {"sev": "med", "country": "RU", "occ": "consultant", "adverse": 1},
    {"sev": "med", "country": "GB", "occ": "politician", "pep": True, "new_account": True},
    {"sev": "med", "country": "GB", "occ": "money exchange", "adverse": 1},
    {"sev": "med", "country": "VE", "occ": "importer", "adverse": 1, "missing": "kyc_id"},
    {"sev": "med", "country": "GB", "occ": "landlord", "pep": True, "adverse": 1},
    {"sev": "med", "country": "RU", "occ": "precious metals trader"},
    {"sev": "med", "country": "GB", "occ": "consultant", "pep": True, "new_account": True},

    {"sev": "high", "country": "RU", "occ": "consultant", "typology": "structuring", "cash_heavy": True},
    {"sev": "high", "country": "GB", "occ": "crypto dealer", "typology": "layering", "adverse": 2},
    {"sev": "high", "country": "MM", "occ": "trader", "typology": "round_trip"},
    {"sev": "high", "country": "GB", "occ": "precious metals trader", "typology": "dormant_spike",
     "adverse": 1, "extra": "second_passport"},
    {"sev": "high", "country": "GB", "occ": "politician", "pep": True, "typology": "structuring", "cash_heavy": True},

    {"sev": "critical", "country": "IR", "occ": "arms dealer", "sanctioned": True, "typology": "structuring"},
    {"sev": "critical", "country": "SY", "occ": "shell company director", "sanctioned": True, "pep": True},
]

EXPECTED_BAND = {"low": "LOW", "med": "MED", "high": "HIGH", "critical": "HIGH", "review": "REVIEW"}


# --------------------------------------------------------------------------- transactions (structured)

def _dstr(days_ago: int) -> str:
    return (REF_DATE - timedelta(days=days_ago)).isoformat()


def _amt(x: float) -> Decimal:
    return Decimal(str(round(float(x), 2)))


def benign_stream(cust, rng, country, cash_heavy):
    txns, n = [], 0
    salary = float(rng.uniform(2800, 6000))
    for m in range(6):
        txns.append(Txn(f"{cust}-T{n:03d}", _dstr(m * 30 + 3), _amt(salary * rng.uniform(0.98, 1.02)),
                        "GBP", "in", "ACME Payroll Ltd", country, "salary")); n += 1
    for m in range(6):
        txns.append(Txn(f"{cust}-T{n:03d}", _dstr(m * 30 + 5), _amt(rng.uniform(600, 1400)),
                        "GBP", "out", "Landlord DD", country, "direct_debit")); n += 1
    for _ in range(int(rng.poisson(14))):
        txns.append(Txn(f"{cust}-T{n:03d}", _dstr(int(rng.integers(1, 180))),
                        _amt(min(float(np.exp(rng.normal(3.4, 0.8))), 900)),
                        "GBP", "out", fake.company(), country, "card")); n += 1
    if cash_heavy:
        for _ in range(int(rng.integers(4, 8))):
            txns.append(Txn(f"{cust}-T{n:03d}", _dstr(int(rng.integers(1, 120))),
                            _amt(rng.uniform(1500, 4000)), "GBP", "in", "Cash Deposit", country, "cash")); n += 1
    return txns


def inject_structuring(cust, rng, country, s):
    floor, lo = float(FLOOR), float(CONFIG["structuring"]["low_frac"]) * float(FLOOR)
    return [Txn(f"{cust}-S{i:02d}", _dstr(40 - i * 2), _amt(rng.uniform(lo, floor - 150)),
                "GBP", "in", "Cash Deposit", country, "cash") for i in range(4)]


def inject_layering(cust, rng, country, s):
    txns, amt = [], 240000.0
    for i in range(3):
        amt *= float(CONFIG["layering"]["forward_ratio"])
        txns.append(Txn(f"{cust}-L{i:02d}", _dstr(30 - i * 2), _amt(amt), "GBP", "out",
                        f"Shell Co {chr(65 + i)}", "CY", "transfer"))
    return txns


def inject_round_trip(cust, rng, country, s):
    amt = float(rng.uniform(50000, 120000))
    return [Txn(f"{cust}-R00", _dstr(20), _amt(amt), "GBP", "out", "Offshore Nominee A", "KY", "wire"),
            Txn(f"{cust}-R01", _dstr(14), _amt(amt * 0.98), "GBP", "in", "Offshore Nominee B", "KY", "wire")]


def inject_dormant_spike(cust, rng, country, s):
    txns = [Txn(f"{cust}-D{i:02d}", _dstr(230 - i * 10), _amt(rng.uniform(50, 300)),
                "GBP", "out", fake.company(), country, "card") for i in range(3)]
    txns += [Txn(f"{cust}-B{i:02d}", _dstr(9 - i * 2), _amt(rng.uniform(18000, 45000)),
                 "GBP", "in", "New Counterparty", "AE", "wire") for i in range(4)]
    return txns


INJECTORS = {"structuring": inject_structuring, "layering": inject_layering,
             "round_trip": inject_round_trip, "dormant_spike": inject_dormant_spike}


# --------------------------------------------------------------------------- unstructured documents

def _mrz(iso, surname, given, dob, id_doc):
    a = f"P<{iso}{surname.upper()}<<{given.upper().replace(' ', '<')}".ljust(44, "<")[:44]
    b = f"{id_doc}<{iso}{dob.replace('-', '')}".ljust(44, "<")[:44]
    return f"{a}\n{b}"


def doc_id(d, iso, second=False):
    name = d.kyc["name"]
    parts = name.split()
    surname, given = parts[-1], " ".join(parts[:-1])
    nat = COUNTRY.get(iso, iso)
    idn = d.kyc.get("id_doc") or "P00000000"
    return (f"=== TRAVEL DOCUMENT — OCR EXTRACT ===\n"
            f"Type: P   Issuing country: {iso} ({nat})\n"
            f"Surname: {surname.upper()}\nGiven names: {given.upper()}\n"
            f"Nationality: {nat}\nDate of birth: {d.kyc['dob']}\n"
            f"Document no.: {idn}\nExpiry: 2031-05-01\n\nMRZ:\n{_mrz(iso, surname, given, d.kyc['dob'], idn)}\n"
            + ("\n[NOTE] Second travel document on file — different issuing state.\n" if second else ""))


def doc_rm_notes(d, p):
    occ, cn = d.kyc["occupation"], COUNTRY.get(p["country"], p["country"])
    sev, typ = p["sev"], p.get("typology")
    head = f"RELATIONSHIP MANAGER NOTES — {d.kyc['name']} ({d.customer_id})\nReviewed: {_dstr(15)}\n\n"
    conflict = p.get("conflict")
    if conflict:
        cbody = {
            "txn_borderline": ("A few cash deposits just under the £10,000 reporting threshold were noted. Client "
                               "says these are proceeds from a private house sale and provided partial documentation. "
                               "Unclear whether legitimate or structuring — recommend a second opinion."),
            "pep_benign": (f"Client is a low-profile local {occ} (PEP). Activity is limited to salary and routine "
                           f"household spending; no unusual transactions and no adverse media. EDD applied as a "
                           f"precaution — the case is genuinely borderline."),
            "adverse_unproven": ("A single negative news item surfaced during periodic review (allegations UNPROVEN, "
                                 "no charges filed). Client gave a plausible explanation; KYC and transactions are "
                                 "otherwise clean. Hard to weigh."),
            "geo_explained": (f"Client runs a legitimate import/export business in {cn}. Source of funds and wealth "
                              f"are documented and independently verified; cross-border payments match declared trade. "
                              f"{cn} is a higher-risk jurisdiction — retained for periodic review."),
            "roundtrip_explained": ("A large outbound wire returned shortly afterwards from a related entity. Client "
                                    "states this is a routine internal treasury settlement between his own companies "
                                    "(see correspondence). Plausible but not independently verified."),
        }.get(conflict)
        if cbody:
            return head + cbody + "\n"
    if sev == "critical":
        body = ("URGENT: sanctions screening returned an EXACT match (OFAC SDN). Account frozen pending "
                "MLRO review. Do NOT process any transactions. Escalated immediately.")
    elif typ == "structuring":
        body = ("CONCERN: client has made multiple cash deposits just below the £10,000 reporting threshold "
                "over recent weeks. Vague when asked about source of funds. Recommend review / possible SAR.")
    elif typ == "layering":
        body = ("CONCERN: rapid onward transfers to several distinct offshore counterparties shortly after "
                "inbound funds. Pattern consistent with layering. See correspondence on file.")
    elif typ == "round_trip":
        body = ("CONCERN: large outbound wire followed by a near-identical inbound from a related offshore "
                "entity within days. Round-tripping suspected.")
    elif typ == "dormant_spike":
        body = ("CONCERN: account largely dormant for ~8 months, then a sudden series of high-value inbound "
                "wires from a new counterparty. Source of funds unclear.")
    elif p.get("pep"):
        body = (f"Client is a {occ}; confirmed Politically Exposed Person. Enhanced due diligence applied. "
                f"Source of wealth stated as public office / family business. Ongoing monitoring in place.")
    elif p["country"] in CONFIG["high_risk_countries"]:
        body = (f"Client resident in {cn} (higher-risk jurisdiction). Cross-border activity monitored. "
                f"Source of funds: {occ} income.")
    elif p.get("adverse"):
        body = ("Negative media reference identified during periodic review (see attached article). Client "
                "denies involvement; monitoring continued.")
    else:
        body = (f"Long-standing relationship. Salary account, {occ}. Activity consistent with profile; no "
                f"concerns noted. KYC last refreshed {_dstr(120)}.")
    return head + body + "\n"


def doc_adverse(d, p, n):
    name, occ, cn = d.kyc["name"], d.kyc["occupation"], COUNTRY.get(p["country"], p["country"])
    if n == 1:
        return (f"[Financial Times — {_dstr(45)}]\n{name}, a {occ} based in {cn}, has been named in "
                f"connection with an ongoing regulatory inquiry into suspected fraud. Authorities are said "
                f"to be reviewing a series of transactions. No charges have been filed and the allegations "
                f"remain unproven.\n")
    return (f"[Reuters — {_dstr(20)}]\nRegulators have fined a company linked to {name} over alleged "
            f"money-laundering failings. Investigators are examining cross-border transfers routed through "
            f"shell entities. {name} did not respond to requests for comment.\n")


def doc_correspondence(d, p):
    typ = d.meta.get("typology")
    if p.get("conflict") == "roundtrip_explained":
        msg = ("The funds I sent out will come back this week from my other company — it's just an internal "
               "treasury settlement between my two businesses, not a third-party payment. Please log it that way.")
    elif typ == "layering":
        msg = ("Please action the three transfers to my business associates as discussed — these are "
               "consulting fees for the offshore project. Kindly expedite before month-end.")
    elif typ == "round_trip":
        msg = ("The funds sent to Nominee A will be returned shortly from our partner entity; please treat "
               "the round as an internal settlement.")
    else:
        return None
    return f"EMAIL — from {d.kyc['name']} <client@example.com>  {_dstr(18)}\nSubject: Transfers\n\n{msg}\n"


# --------------------------------------------------------------------------- dossier + documents

def build_dossier(idx, p, rng, prefix="CUST_") -> Dossier:
    cust = f"{prefix}{idx:03d}"
    country, pep, typ = p["country"], p.get("pep", False), p.get("typology")
    name = fake.name()
    tenure = int(rng.integers(10, 80)) if p.get("new_account") else int(rng.integers(200, 3000))

    kyc = {"name": name, "dob": fake.date_of_birth(minimum_age=25, maximum_age=70).isoformat(),
           "nationality": country, "occupation": p["occ"], "id_doc": f"P{int(rng.integers(10**7, 10**8))}",
           "onboarded": _dstr(tenure), "kyc_complete": True}
    profile = {"entity_type": "individual", "country": country, "product": "current_account",
               "pep": pep, "tenure_days": tenure}

    if typ == "dormant_spike":
        txns = INJECTORS[typ](cust, rng, country, 0)
    else:
        txns = benign_stream(cust, rng, country, p.get("cash_heavy", False))
        if typ:
            txns += INJECTORS[typ](cust, rng, country, len(txns))

    conflict = p.get("conflict")   # ambiguous signals -> analysts disagree -> low confidence -> human review
    if conflict == "txn_borderline":  # a few sub-threshold cash deposits, but not a clear structuring cluster
        for i in range(3):
            txns.append(Txn(f"{cust}-C{i}", _dstr(30 - i * 4), _amt(rng.uniform(9200, 9900)),
                            "GBP", "in", "Cash Deposit", country, "cash"))
    elif conflict == "roundtrip_explained":  # a round-trip pattern with an innocent explanation on file
        txns += inject_round_trip(cust, rng, country, len(txns))

    sanctions = [{"name": name, "match_score": 1.0, "list": "OFAC SDN"}] if p.get("sanctioned") else []
    adverse_media = []
    if p.get("adverse", 0) >= 1:
        adverse_media.append({"headline": f"{name} named in fraud investigation", "sentiment": "negative", "date": _dstr(45)})
    if p.get("adverse", 0) >= 2:
        adverse_media.append({"headline": f"Regulator fines firm linked to {name} for money laundering", "sentiment": "negative", "date": _dstr(20)})
    screening = {"sanctions": sanctions, "pep_confirmed": pep, "adverse_media": adverse_media}

    meta = {"expected_band": EXPECTED_BAND[p["sev"]], "severity": p["sev"], "typology": typ,
            "review": bool(conflict), "conflict": conflict, "missing_docs": [], "extra_docs": []}

    if p.get("missing") == "kyc_id":
        kyc["id_doc"] = None; kyc["kyc_complete"] = False; meta["missing_docs"].append("kyc_id")
    if p.get("missing") == "transactions":
        txns = []; meta["missing_docs"].append("transactions")
    if p.get("extra"):
        meta["extra_docs"].append(p["extra"])

    d = Dossier(cust, kyc, profile, txns, screening, meta)

    # unstructured documents
    docs = []
    if p.get("missing") != "kyc_id":
        docs.append(("id_document.txt", doc_id(d, country)))
    if p.get("extra") == "second_passport":
        docs.append(("id_document_2.txt", doc_id(d, "CY", second=True)))
    docs.append(("rm_notes.txt", doc_rm_notes(d, p)))
    for i in range(1, p.get("adverse", 0) + 1):
        docs.append((f"adverse_media_{i}.txt", doc_adverse(d, p, i)))
    corr = doc_correspondence(d, p)
    if corr:
        docs.append(("correspondence.txt", corr))
    d.documents = [{"name": n, "kind": "unstructured", "text": t} for n, t in docs]
    return d


def generate() -> list[Dossier]:
    Faker.seed(SEED); random.seed(SEED)
    rng = np.random.default_rng(SEED)
    return [build_dossier(i, p, rng) for i, p in enumerate(PROFILES)]


# --------------------------------------------------------------------------- 40-profile UPLOAD sample set
# A SEPARATE dataset (different seed → different people) for MANUAL upload. NOT auto-loaded by the app.
# The 5 "review" rows carry deliberately CONFLICTING signals so the LLM's domain analysts disagree →
# low composite confidence → routed to the human review queue.

SAMPLE_SEED = 99

SAMPLE_PROFILES = [
    # --- 5 that NEED human review (ambiguous / conflicting evidence) ---
    {"sev": "review", "country": "GB", "occ": "property developer", "conflict": "txn_borderline"},
    {"sev": "review", "country": "GB", "occ": "parish councillor", "pep": True, "cash_heavy": True, "conflict": "pep_benign"},
    {"sev": "review", "country": "IE", "occ": "restaurateur", "adverse": 1, "conflict": "adverse_unproven"},
    {"sev": "review", "country": "RU", "occ": "import/export trader", "adverse": 1, "cash_heavy": True, "conflict": "geo_explained"},
    {"sev": "review", "country": "GB", "occ": "company director", "conflict": "roundtrip_explained"},

    # --- 13 low ---
    {"sev": "low", "country": "GB", "occ": "doctor"},
    {"sev": "low", "country": "IE", "occ": "architect"},
    {"sev": "low", "country": "FR", "occ": "journalist"},
    {"sev": "low", "country": "DE", "occ": "farmer"},
    {"sev": "low", "country": "ES", "occ": "dentist"},
    {"sev": "low", "country": "NL", "occ": "pharmacist"},
    {"sev": "low", "country": "GB", "occ": "librarian"},
    {"sev": "low", "country": "GB", "occ": "plumber"},
    {"sev": "low", "country": "IT", "occ": "professor"},
    {"sev": "low", "country": "GB", "occ": "graphic designer"},
    {"sev": "low", "country": "GB", "occ": "baker", "missing": "transactions"},
    {"sev": "low", "country": "GB", "occ": "mechanic"},
    {"sev": "low", "country": "US", "occ": "software developer"},

    # --- 12 med ---
    {"sev": "med", "country": "RU", "occ": "oil trader", "adverse": 1},
    {"sev": "med", "country": "GB", "occ": "mayor", "pep": True, "new_account": True},
    {"sev": "med", "country": "GB", "occ": "money exchange", "adverse": 1},
    {"sev": "med", "country": "VE", "occ": "importer", "adverse": 1},
    {"sev": "med", "country": "MM", "occ": "gem trader", "adverse": 1},
    {"sev": "med", "country": "GB", "occ": "landlord", "pep": True},
    {"sev": "med", "country": "RU", "occ": "metals dealer"},
    {"sev": "med", "country": "GB", "occ": "consultant", "pep": True, "new_account": True},
    {"sev": "med", "country": "VE", "occ": "shipping agent", "cash_heavy": True},
    {"sev": "med", "country": "GB", "occ": "casino operator"},
    {"sev": "med", "country": "AF", "occ": "money exchange"},
    {"sev": "med", "country": "PK", "occ": "textile exporter", "adverse": 1},

    # --- 7 high (a typology + reinforcing flags) ---
    {"sev": "high", "country": "RU", "occ": "consultant", "typology": "structuring", "cash_heavy": True},
    {"sev": "high", "country": "GB", "occ": "crypto dealer", "typology": "layering", "adverse": 2},
    {"sev": "high", "country": "YE", "occ": "trader", "typology": "round_trip"},
    {"sev": "high", "country": "GB", "occ": "precious metals trader", "typology": "dormant_spike", "adverse": 1},
    {"sev": "high", "country": "KP", "occ": "broker", "typology": "layering"},
    {"sev": "high", "country": "GB", "occ": "art dealer", "typology": "structuring", "cash_heavy": True, "adverse": 1},
    {"sev": "high", "country": "RU", "occ": "arms broker", "typology": "round_trip", "adverse": 1},

    # --- 3 critical (sanctions match) ---
    {"sev": "critical", "country": "IR", "occ": "arms dealer", "sanctioned": True, "typology": "structuring"},
    {"sev": "critical", "country": "SY", "occ": "shell company director", "sanctioned": True, "pep": True},
    {"sev": "critical", "country": "KP", "occ": "procurement agent", "sanctioned": True, "typology": "layering"},
]


def write_samples(out_dir=UPLOAD_SAMPLES, seed=SAMPLE_SEED, profiles=None, prefix="SAMPLE_"):
    """Write the manual-upload sample set to a SEPARATE folder (not the app's data/customers/)."""
    profiles = profiles or SAMPLE_PROFILES
    if out_dir.exists():
        shutil.rmtree(out_dir)
    Faker.seed(seed); random.seed(seed)
    rng = np.random.default_rng(seed)
    files = 0
    review_ids = []
    for i, p in enumerate(profiles):
        d = build_dossier(i, p, rng, prefix=prefix)
        if d.meta.get("review"):
            review_ids.append(d.customer_id)
        cdir = out_dir / d.customer_id
        cdir.mkdir(parents=True, exist_ok=True)
        for name, content in render_files(d).items():
            (cdir / name).write_text(content, encoding="utf-8"); files += 1
    return len(profiles), files, review_ids


# --------------------------------------------------------------------------- render files

def _txn_csv(txns) -> str:
    buf = io.StringIO()
    w = csv.writer(buf, lineterminator="\n")
    w.writerow(["txn_id", "date", "amount", "currency", "direction", "counterparty", "counterparty_country", "txn_type"])
    for t in txns:
        w.writerow([t.id, t.date, str(t.amount), t.currency, t.direction, t.counterparty, t.counterparty_country, t.txn_type])
    return buf.getvalue()


def render_files(d: Dossier) -> dict[str, str]:
    files = {
        "kyc.json": json.dumps(d.kyc, indent=2),
        "account.json": json.dumps({"customer_id": d.customer_id, **d.profile}, indent=2),
        "screening.json": json.dumps(d.screening, indent=2),
        "_meta.json": json.dumps(d.meta, indent=2),
    }
    if "transactions" not in d.meta.get("missing_docs", []):
        files["transactions.csv"] = _txn_csv(d.transactions)
    for doc in d.documents:
        files[doc["name"]] = doc["text"]
    return files


def write() -> int:
    if CUSTOMERS_DIR.exists():
        shutil.rmtree(CUSTOMERS_DIR)
    n = 0
    for d in generate():
        cdir = CUSTOMERS_DIR / d.customer_id
        cdir.mkdir(parents=True, exist_ok=True)
        for name, content in render_files(d).items():
            (cdir / name).write_text(content, encoding="utf-8")
            n += 1
    return n


# --------------------------------------------------------------------------- self-check

def _canon(ds) -> str:
    return json.dumps([{**render_files(d)} for d in ds], sort_keys=True)


def _selfcheck():
    assert hashlib.sha256(_canon(generate()).encode()).hexdigest() == \
           hashlib.sha256(_canon(generate()).encode()).hexdigest(), "non-deterministic"
    ds = generate()
    assert len(ds) == 20
    assert {d.meta["expected_band"] for d in ds} == {"LOW", "MED", "HIGH"}
    floor = float(FLOOR)
    for d in ds:
        # every profile has structured KYC + screening + unstructured RM notes
        assert d.kyc and "rm_notes.txt" in {x["name"] for x in d.documents}
        typ = d.meta.get("typology")
        if typ == "structuring":
            cash = [t for t in d.transactions if t.txn_type == "cash" and t.direction == "in" and 0.8 * floor <= float(t.amount) < floor]
            assert len(cash) >= 3, f"{d.customer_id}: weak structuring cluster"
        if d.screening["sanctions"]:
            assert d.meta["severity"] == "critical"
    print("self-check OK: deterministic; 20 customers; structured + unstructured docs; bands covered")


if __name__ == "__main__":
    count = write()
    print(f"wrote {count} files across 20 customer folders under {CUSTOMERS_DIR}")
    _selfcheck()
