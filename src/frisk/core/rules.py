"""Deterministic rule engine — the auditable source of truth.

Every rule is a pure function `Dossier -> Finding | None`. The registry is just two lists.
Order of operations (non-negotiable): overrides/vetoes FIRST, then weighted sum -> 0-100, then band.
Money is Decimal; dates parse from ISO; nothing here reads the wall clock or randomness.

`score_customer` never raises: a throwing predicate degrades to a recorded RULE_ERROR finding.
Driver contributions are integers that sum EXACTLY to the score.
"""
from __future__ import annotations

from datetime import date
from decimal import Decimal
from typing import Optional

from frisk.config import CONFIG, band_for
from frisk.core.models import Dossier, Finding, RiskResult

W = CONFIG["weights"]


# --------------------------------------------------------------------------- #
# small deterministic helpers
# --------------------------------------------------------------------------- #

def _d(iso: str) -> date:
    return date.fromisoformat(iso)


def _sorted_txns(d: Dossier):
    return sorted(d.transactions, key=lambda t: t.date)


def _sum(txns) -> Decimal:
    return sum((t.amount for t in txns), Decimal(0))


# --------------------------------------------------------------------------- #
# FACTOR RULES (profile / static + screening)
# --------------------------------------------------------------------------- #

def rule_sanctions_match(d: Dossier) -> Optional[Finding]:
    for s in d.screening.get("sanctions", []):
        if float(s.get("match_score", 0)) >= 0.99:
            return Finding("SANCTIONS_MATCH", "SCREENING", 0, True,
                           f"Exact sanctions match on '{s['name']}' ({s.get('list','?')})",
                           {"name": s["name"], "match_score": s["match_score"], "list": s.get("list")})
    return None


def rule_pep_high_geo(d: Dossier) -> Optional[Finding]:
    if d.profile.get("pep") and d.profile.get("country") in CONFIG["high_risk_countries"]:
        return Finding("PEP_HIGH_GEO", "PROFILE", 0, True,
                       f"PEP resident in high-risk jurisdiction {d.profile['country']}",
                       {"country": d.profile["country"], "pep": True})
    return None


def rule_pep(d: Dossier) -> Optional[Finding]:
    if d.profile.get("pep"):
        return Finding("PEP", "PROFILE", W["PEP"], False,
                       "Politically Exposed Person", {"pep": True})
    return None


def rule_high_risk_geo(d: Dossier) -> Optional[Finding]:
    c = d.profile.get("country")
    if c in CONFIG["high_risk_countries"]:
        return Finding("HIGH_RISK_GEO", "PROFILE", W["HIGH_RISK_GEO"], False,
                       f"Customer country {c} is high-risk", {"country": c})
    return None


def rule_high_risk_occupation(d: Dossier) -> Optional[Finding]:
    occ = (d.kyc.get("occupation") or "").lower()
    if occ in CONFIG["high_risk_occupations"]:
        return Finding("HIGH_RISK_OCCUPATION", "KYC", W["HIGH_RISK_OCCUPATION"], False,
                       f"High-risk occupation: {occ}", {"occupation": occ})
    return None


def rule_kyc_incomplete(d: Dossier) -> Optional[Finding]:
    if not d.kyc.get("kyc_complete", True) or d.kyc.get("id_doc") in (None, ""):
        missing = [k for k in ("id_doc",) if d.kyc.get(k) in (None, "")]
        return Finding("KYC_INCOMPLETE", "KYC", W["KYC_INCOMPLETE"], False,
                       "KYC record incomplete (missing identity document)",
                       {"missing": missing or ["kyc_complete_flag"]})
    return None


def rule_new_account(d: Dossier) -> Optional[Finding]:
    if d.profile.get("tenure_days", 9999) < CONFIG["new_account_days"]:
        return Finding("NEW_ACCOUNT", "PROFILE", W["NEW_ACCOUNT"], False,
                       f"New account ({d.profile['tenure_days']} days old)",
                       {"tenure_days": d.profile["tenure_days"]})
    return None


def rule_adverse_media(d: Dossier) -> Optional[Finding]:
    media = d.screening.get("adverse_media", [])
    if not media:
        return None
    text = " ".join(m.get("headline", "").lower() for m in media)
    severe = len(media) >= 2 or any(k in text for k in CONFIG["adverse_severe_keywords"])
    code = "ADVERSE_MEDIA_SEVERE" if severe else "ADVERSE_MEDIA"
    return Finding(code, "SCREENING", W[code], False,
                   f"{len(media)} adverse-media item(s); "
                   + ("severe keyword/volume" if severe else "single mild mention"),
                   {"headlines": [m.get("headline") for m in media]})


def rule_cash_intensity(d: Dossier) -> Optional[Finding]:
    ins = [t for t in d.transactions if t.direction == "in"]
    total_in = _sum(ins)
    cash_in = _sum([t for t in ins if t.txn_type == "cash"])
    if total_in <= 0 or cash_in <= 0:
        return None
    ratio = cash_in / total_in
    cfg = CONFIG["cash_intensity"]
    if ratio >= cfg["min_ratio"] and cash_in >= cfg["min_sum"]:
        return Finding("CASH_INTENSITY", "TRANSACTION", W["CASH_INTENSITY"], False,
                       f"Cash inflows {cash_in} = {ratio:.0%} of credits",
                       {"cash_in": str(cash_in), "ratio": f"{ratio:.2f}"})
    return None


def rule_high_velocity(d: Dossier) -> Optional[Finding]:
    cfg = CONFIG["velocity"]
    if not d.transactions:
        return None
    txns = _sorted_txns(d)
    # any window_days span containing >= min_count txns
    dates = [_d(t.date) for t in txns]
    n = len(dates)
    for i in range(n):
        j = i
        while j < n and (dates[j] - dates[i]).days <= cfg["window_days"]:
            j += 1
        if j - i >= cfg["min_count"]:
            return Finding("HIGH_VELOCITY", "TRANSACTION", W["HIGH_VELOCITY"], False,
                           f"{j - i} transactions within {cfg['window_days']} days",
                           {"count": j - i, "window_days": cfg["window_days"]})
    return None


# --------------------------------------------------------------------------- #
# TYPOLOGY RULES (temporal transaction patterns)
# --------------------------------------------------------------------------- #

def typ_structuring(d: Dossier) -> Optional[Finding]:
    cfg = CONFIG["structuring"]
    floor = CONFIG["reporting_floor"]
    lo = cfg["low_frac"] * floor
    cash = sorted([t for t in d.transactions
                   if t.txn_type == "cash" and t.direction == "in" and lo <= t.amount < floor],
                  key=lambda t: t.date)
    n = len(cash)
    for i in range(n):
        window = [cash[i]]
        for j in range(i + 1, n):
            if (_d(cash[j].date) - _d(cash[i].date)).days <= cfg["window_days"]:
                window.append(cash[j])
        if len(window) >= cfg["min_count"] and _sum(window) > floor:
            return Finding("STRUCTURING", "TRANSACTION", W["STRUCTURING"], False,
                           f"{len(window)} sub-threshold cash deposits totalling {_sum(window)} "
                           f"within {cfg['window_days']}d (floor {floor})",
                           {"txn_ids": [t.id for t in window], "total": str(_sum(window))})
    return None


def typ_layering(d: Dossier) -> Optional[Finding]:
    cfg = CONFIG["layering"]
    outs = sorted([t for t in d.transactions if t.direction == "out" and t.txn_type == "transfer"],
                  key=lambda t: t.date)
    n = len(outs)
    for i in range(n):
        chain = [outs[i]]
        cps = {outs[i].counterparty}
        for j in range(i + 1, n):
            if (_d(outs[j].date) - _d(outs[i].date)).days <= cfg["window_days"] \
                    and outs[j].counterparty not in cps:
                chain.append(outs[j])
                cps.add(outs[j].counterparty)
        if len(chain) >= cfg["min_hops"]:
            return Finding("LAYERING", "TRANSACTION", W["LAYERING"], False,
                           f"{len(chain)} rapid onward transfers to distinct counterparties "
                           f"within {cfg['window_days']}d (layering)",
                           {"txn_ids": [t.id for t in chain], "counterparties": list(cps)})
    return None


def typ_round_trip(d: Dossier) -> Optional[Finding]:
    cfg = CONFIG["round_trip"]
    outs = [t for t in d.transactions if t.direction == "out"]
    ins = [t for t in d.transactions if t.direction == "in"]
    for o in outs:
        for it in ins:
            if it.counterparty == o.counterparty:
                continue
            days = abs((_d(it.date) - _d(o.date)).days)
            if days <= cfg["window_days"] and o.amount > 0:
                diff = abs(it.amount - o.amount) / o.amount
                if diff <= cfg["amount_tol"]:
                    return Finding("ROUND_TRIP", "TRANSACTION", W["ROUND_TRIP"], False,
                                   f"Funds out {o.amount} then back {it.amount} via a different "
                                   f"counterparty within {days}d (round-trip)",
                                   {"out": o.id, "in": it.id, "amount": str(o.amount)})
    return None


def typ_dormant_spike(d: Dossier) -> Optional[Finding]:
    cfg = CONFIG["dormant_spike"]
    txns = _sorted_txns(d)
    if len(txns) < cfg["min_burst"] + 1:
        return None
    dates = [_d(t.date) for t in txns]
    for i in range(1, len(dates)):
        gap = (dates[i] - dates[i - 1]).days
        if gap >= cfg["dormant_days"]:
            burst = [t for t in txns[i:] if t.amount >= cfg["burst_min_amount"]]
            if len(burst) >= cfg["min_burst"]:
                return Finding("DORMANT_SPIKE", "TRANSACTION", W["DORMANT_SPIKE"], False,
                               f"{gap}d dormancy then burst of {len(burst)} large transactions",
                               {"gap_days": gap, "burst_txn_ids": [t.id for t in burst]})
    return None


FACTOR_RULES = [
    rule_sanctions_match, rule_pep_high_geo, rule_pep, rule_high_risk_geo,
    rule_high_risk_occupation, rule_kyc_incomplete, rule_new_account, rule_adverse_media,
    rule_cash_intensity, rule_high_velocity,
]
TYPOLOGY_RULES = [typ_structuring, typ_layering, typ_round_trip, typ_dormant_spike]
ALL_RULES = FACTOR_RULES + TYPOLOGY_RULES


# --------------------------------------------------------------------------- #
# scoring
# --------------------------------------------------------------------------- #

def _largest_remainder(weights: dict[str, int], total: int) -> dict[str, int]:
    """Apportion `total` across codes proportional to weight, as ints summing exactly to total."""
    s = sum(weights.values())
    if s == 0:
        return {k: 0 for k in weights}
    raw = {k: total * v / s for k, v in weights.items()}
    floors = {k: int(v) for k, v in raw.items()}
    rem = total - sum(floors.values())
    # hand the leftover units to the largest fractional parts (deterministic tie-break by code)
    order = sorted(weights, key=lambda k: (-(raw[k] - floors[k]), k))
    for k in order[:rem]:
        floors[k] += 1
    return floors


def score_customer(d: Dossier) -> RiskResult:
    findings: list[Finding] = []
    for rule in ALL_RULES:
        try:
            f = rule(d)
            if f:
                findings.append(f)
        except Exception as e:  # a broken predicate must never crash the queue
            findings.append(Finding(f"{rule.__name__}_ERROR", "ENGINE", 0, False,
                                    f"rule error: {e}", {"error": str(e)}))

    overrides = [f for f in findings if f.is_override]
    flags = {f.code for f in findings if f.is_override}

    if overrides:
        top = overrides[0]
        drivers = [{"code": top.code, "contribution": 100, "rationale": top.rationale}]
        return RiskResult(d.customer_id, 100, "HIGH", findings, drivers, flags)

    scored = [f for f in findings if f.weight > 0]
    raw = sum(f.weight for f in scored)
    if raw <= 100:
        score = raw
        contribs = {f.code: f.weight for f in scored}
    else:
        score = 100
        contribs = _largest_remainder({f.code: f.weight for f in scored}, 100)
    drivers = [{"code": f.code, "contribution": contribs[f.code], "rationale": f.rationale}
               for f in scored]
    return RiskResult(d.customer_id, score, band_for(score), findings, drivers, flags)


if __name__ == "__main__":
    # quick manual view over the generated dataset
    from frisk.core.models import load_dossiers
    import os
    ds = load_dossiers()
    for d in ds:
        r = score_customer(d)
        exp = d.meta.get("expected_band")
        mark = "OK " if r.band == exp else "!! "
        codes = ",".join(f.code for f in r.findings) or "-"
        assert sum(x["contribution"] for x in r.drivers) == r.score or r.flags, \
            f"{d.customer_id}: drivers {r.drivers} != score {r.score}"
        print(f"{mark}{d.customer_id} score={r.score:3d} band={r.band:4s} exp={exp:4s} | {codes}")
