"""Parallel domain specialists — the fast, memory-fed first pass.

Three single-call analysts (kyc | transactions | documents) run concurrently. Each gets ONLY its domain's
facts plus injected memory (semantic cheat-sheet + episodic few-shot + per-customer history summary) and
returns a ``SpecialistOpinion``. Their opinions feed the agentic orchestrator, which holds the full context.
A failing specialist degrades to a neutral opinion — never crashes the scoring.
"""
from __future__ import annotations

import json
from concurrent.futures import ThreadPoolExecutor

from frisk.ai import memory
from frisk.ai.providers.factory import get_provider
from frisk.ai.tools import dossier_summary
from frisk.core.models import SpecialistOpinion

DOMAINS = ["kyc", "transactions", "documents"]


def _facts(d, domain: str) -> str:
    if domain == "kyc":
        return f"KYC: {json.dumps(d.kyc)}\nPROFILE: {json.dumps(d.profile)}\nSCREENING: {json.dumps(d.screening)}"
    if domain == "transactions":
        return dossier_summary(d)
    return "\n---\n".join(f"[{x['name']}]\n{x['text'][:1500]}" for x in getattr(d, "documents", [])) \
        or "No unstructured documents on file."


def _prompt(d, domain: str, mem: dict) -> str:
    cheat = memory.txn_cheatsheet() if domain == "transactions" else memory.kyc_cheatsheet()
    fewshot = memory.fewshot_for(domain, d)
    hist = (mem.get("injected") or {}).get("history_summary", "")
    return (
        f"You are an AML {domain} analyst. Assess ONLY the {domain} risk from the facts below and respond "
        f"in JSON with keys domain,risk_level(low|medium|high),signals(list),note,tentative_score(0-100). "
        f"Set domain='{domain}'. Be calibrated: rate LOW when no specific red flag is present; do NOT invent "
        f"risk from ordinary activity. This system has NO sanctions or adverse-media screening — never claim a "
        f"customer is sanctioned, watchlisted, or in the news; judge only the facts below.\n\n"
        f"REFERENCE (context, not rules):\n{cheat}\n\n{fewshot}\n\n{hist}\n\nFACTS:\n{_facts(d, domain)}"
    )


def run_specialists(d, mem: dict) -> list[SpecialistOpinion]:
    prov = get_provider()

    def one(domain: str) -> SpecialistOpinion:
        try:
            op = prov.complete(_prompt(d, domain, mem), SpecialistOpinion)
            op.domain = domain
            return op
        except Exception:
            return SpecialistOpinion(domain=domain, risk_level="medium", note=f"{domain} analysis unavailable")

    with ThreadPoolExecutor(max_workers=3) as ex:
        return list(ex.map(one, DOMAINS))


if __name__ == "__main__":  # self-check (mock provider)
    import os
    os.environ["FRISK_PROVIDER"] = "mock"
    from frisk.core.models import Dossier, Txn
    from decimal import Decimal
    d = Dossier("T1", {"name": "T", "occupation": "arms dealer", "kyc_complete": True},
                {"country": "IR", "entity_type": "individual", "pep": False},
                [Txn("A", "2026-07-01", Decimal("9500"), "GBP", "in", "Cash", "IR", "cash")],
                {"pep_confirmed": False}, {}, [{"name": "rm_notes.txt", "kind": "unstructured", "text": "high risk"}])
    ops = run_specialists(d, {"injected": {}})
    assert len(ops) == 3 and {o.domain for o in ops} == {"kyc", "transactions", "documents"}
    assert all(isinstance(o, SpecialistOpinion) for o in ops)
    print("specialists self-check OK:", [(o.domain, o.risk_level, o.tentative_score) for o in ops])
