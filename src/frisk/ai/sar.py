"""SAR drafting — turn a scored case into a filing-ready Suspicious Activity Report narrative.

A SAR (Suspicious Activity Report) is the document a compliance team actually files with the FIU
(FinCEN in the US, the NCA in the UK) when a case can't be explained away. The hard part for an analyst
is the NARRATIVE: who, what, when, where, why it is suspicious, and what evidence supports it.

We already hold everything that narrative needs — the agent's rationale, its key signals, the cited
evidence, the specialist opinions and the raw transactions — so the LLM composes them into the standard
5-part structure. Draft only: it is explicitly marked for human review and sign-off before filing.
"""
from __future__ import annotations

from pydantic import BaseModel, Field

from frisk.ai.providers.factory import get_provider


class SARDraft(BaseModel):
    subject_summary: str = Field(default="", description="who the subject is: identity, occupation, jurisdiction, account profile")
    suspicious_activity: str = Field(default="", description="WHAT is suspicious: the pattern, amounts, dates, counterparties")
    supporting_evidence: str = Field(default="", description="the specific transactions and documents that evidence it")
    analysis: str = Field(default="", description="WHY this indicates possible money laundering; typology named")
    recommended_action: str = Field(default="", description="file / continue monitoring / exit relationship, and any next steps")
    priority: str = Field(default="MEDIUM", description="LOW | MEDIUM | HIGH filing priority")


def _txn_lines(dossier, refs: list[str], limit: int = 12) -> str:
    """The cited transactions first (they are the evidence), then the largest others for context."""
    if dossier is None or not dossier.transactions:
        return "No transaction records on file."
    cited = [t for t in dossier.transactions if t.id in set(refs)]
    rest = sorted([t for t in dossier.transactions if t.id not in set(refs)],
                  key=lambda t: -float(t.amount))
    rows = (cited + rest)[:limit]
    return "\n".join(
        f"  {t.id} | {t.date} | {t.direction:3s} | {t.amount} {t.currency} | {t.txn_type} | "
        f"{t.counterparty} ({t.counterparty_country})" for t in rows)


def build_prompt(dec, dossier) -> str:
    kyc = dossier.kyc if dossier else {}
    prof = dossier.profile if dossier else {}
    docs = "; ".join(d["name"] for d in (getattr(dossier, "documents", []) or [])) or "none"
    ops = "\n".join(f"  [{o.get('domain')}={o.get('risk_level')}] {o.get('note','')}" for o in (dec.opinions or []))
    return (
        "You are a senior AML compliance officer drafting a Suspicious Activity Report (SAR) narrative for "
        "filing with the financial intelligence unit. Write in formal, factual, third-person regulatory prose. "
        "Cite specific transaction ids, amounts and dates — never invent facts that are not in the evidence below. "
        "If the evidence is weak, say so plainly in the analysis rather than overstating.\n\n"
        "Respond in JSON with keys: subject_summary, suspicious_activity, supporting_evidence, analysis, "
        "recommended_action, priority(LOW|MEDIUM|HIGH).\n\n"
        f"SUBJECT\n  id={dec.customer_id}; name={kyc.get('name')}; dob={kyc.get('dob')}; "
        f"nationality={kyc.get('nationality')}; occupation={kyc.get('occupation')}; "
        f"country={prof.get('country')}; PEP={bool(prof.get('pep'))}; "
        f"account_age_days={prof.get('tenure_days')}; kyc_complete={kyc.get('kyc_complete')}\n\n"
        f"AI RISK ASSESSMENT\n  score={dec.score}/100 band={dec.band} disposition={dec.action} "
        f"confidence={dec.confidence}\n  rationale: {dec.rationale}\n"
        f"  key signals: {'; '.join(dec.key_signals or []) or 'none'}\n"
        f"  cited evidence: {', '.join(dec.evidence_refs or []) or 'none'}\n\n"
        f"SPECIALIST OPINIONS\n{ops or '  none'}\n\n"
        f"TRANSACTIONS (cited first)\n{_txn_lines(dossier, dec.evidence_refs or [])}\n\n"
        f"DOCUMENTS ON FILE: {docs}"
    )


def draft(dec, dossier) -> dict:
    """Compose a SAR draft for one decision. Never raises — returns a degraded draft on failure."""
    try:
        d = get_provider().complete(build_prompt(dec, dossier), SARDraft)
        out = d.model_dump()
    except Exception as e:
        out = SARDraft(
            subject_summary=f"{(dossier.kyc.get('name') if dossier else dec.customer_id)} ({dec.customer_id})",
            suspicious_activity=dec.rationale or "",
            supporting_evidence=", ".join(dec.evidence_refs or []) or "see case file",
            analysis=f"Automated narrative unavailable ({type(e).__name__}); the risk assessment above stands.",
            recommended_action="Manual review required before filing.",
            priority="HIGH" if dec.score >= 70 else "MEDIUM",
        ).model_dump()
    out["customer_id"] = dec.customer_id
    out["subject_name"] = (dossier.kyc.get("name") if dossier else dec.customer_id)
    out["score"] = dec.score
    out["band"] = dec.band
    out["evidence_refs"] = dec.evidence_refs or []
    out["key_signals"] = dec.key_signals or []
    return out


if __name__ == "__main__":  # self-check (mock provider)
    import os
    os.environ["FRISK_PROVIDER"] = "mock"
    from decimal import Decimal
    from types import SimpleNamespace
    from frisk.core.models import Dossier, Txn
    d = Dossier("T1", {"name": "Test Person", "occupation": "arms dealer", "kyc_complete": True},
                {"country": "IR", "pep": False, "tenure_days": 900},
                [Txn("S0", "2026-07-01", Decimal("9500"), "GBP", "in", "Cash Deposit", "IR", "cash")],
                {"pep_confirmed": False}, {}, [{"name": "rm_notes.txt", "kind": "unstructured", "text": "x"}])
    dec = SimpleNamespace(customer_id="T1", score=83, band="high", action="ESCALATE", confidence=0.85,
                          rationale="Structuring pattern detected.", key_signals=["structuring"],
                          evidence_refs=["S0"], opinions=[{"domain": "kyc", "risk_level": "high", "note": "n"}])
    s = draft(dec, d)
    assert s["customer_id"] == "T1" and s["priority"] in ("LOW", "MEDIUM", "HIGH")
    assert "S0" in _txn_lines(d, ["S0"])
    print("sar self-check OK:", {k: str(v)[:48] for k, v in s.items() if k in ("priority", "subject_summary")})
