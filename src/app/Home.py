"""Financial Risk Signal Aggregator — analyst triage UI.

Three views wired with st.navigation: Triage Queue -> Case Detail -> Audit Trail.
Run:  streamlit run src/app/Home.py
"""
from __future__ import annotations

import json
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))  # src/ on path

import pandas as pd
import streamlit as st

import audit
import nlquery
from config import CONFIG
from engine import assess_all, log_analyst_action
from models import load_dossiers

st.set_page_config(page_title="Risk Signal Aggregator", page_icon="🛡️", layout="wide")

DATA = os.path.join(os.path.dirname(__file__), "..", "..", "data", "dossiers.json")

BAND_EMOJI = {"LOW": "🟢", "MED": "🟡", "HIGH": "🔴"}
ACTION_EMOJI = {"AUTO_CLEAR": "🟢 Auto-clear", "REVIEW": "🟡 Review", "ESCALATE": "🔴 Escalate"}
TIER_LABEL = {"none": "—", "junior": "Junior", "senior": "Senior", "named_reviewer": "MLRO"}


@st.cache_resource(show_spinner="Scoring customers…")
def bootstrap():
    """Score all customers once per session and seed the audit log."""
    audit.reset()
    ds = load_dossiers(DATA)
    decs = assess_all(ds, persist=True)  # one engine AuditRecord per customer
    return decs, {d.customer_id: d for d in ds}


DECISIONS, DOSSIERS = bootstrap()
BY_ID = {d.customer_id: d for d in DECISIONS}
st.session_state.setdefault("case_id", None)
st.session_state.setdefault("actions_taken", {})


# --------------------------------------------------------------------------- helpers

def _queue_df(decisions) -> pd.DataFrame:
    rows = []
    for d in decisions:
        top = d.drivers[0]["code"] if d.drivers else ("SANCTIONS_MATCH" if d.flags else "-")
        rows.append({
            "ID": d.customer_id, "Customer": d.name, "Risk": d.score,
            "Band": f"{BAND_EMOJI[d.band]} {d.band}", "Disposition": ACTION_EMOJI[d.action],
            "Confidence": d.confidence, "Tier": TIER_LABEL.get(d.tier, d.tier), "Top signal": top,
            "Country": d.country, "Flags": ", ".join(d.flags) or "-",
        })
    return pd.DataFrame(rows).sort_values("Risk", ascending=False).reset_index(drop=True)


# --------------------------------------------------------------------------- Queue view

def queue_page():
    st.title("🛡️ Financial Risk Signal Aggregator")
    st.caption("Fragmented signals → one prioritised, explained, auditable analyst queue. "
               f"Ruleset {CONFIG['ruleset_version']} · {len(DECISIONS)} customers.")

    counts = {a: sum(1 for d in DECISIONS if d.action == a) for a in ACTION_EMOJI}
    escalated = counts["ESCALATE"]
    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Total customers", len(DECISIONS))
    c2.metric("🔴 Escalate", escalated)
    c3.metric("🟡 Review", counts["REVIEW"])
    c4.metric("🟢 Auto-cleared", counts["AUTO_CLEAR"],
              help="Low-risk + high-confidence; handled without analyst time")

    st.divider()

    # natural-language query
    q = st.text_input("🔎 Ask the queue",
                      placeholder='e.g. "high-risk customers with a sanctions hit"  ·  "everything escalated"  ·  "score over 80"')
    shown = DECISIONS
    if q:
        spec = nlquery.parse(q)
        shown = nlquery.apply(spec, DECISIONS)
        st.info(f"{nlquery.explain(spec)} — {len(shown)} match", icon="🔎")

    df = _queue_df(shown)
    event = st.dataframe(
        df, hide_index=True, use_container_width=True, on_select="rerun",
        selection_mode="single-row",
        column_order=["ID", "Customer", "Risk", "Band", "Disposition", "Confidence", "Tier", "Top signal", "Country", "Flags"],
        column_config={
            "Risk": st.column_config.ProgressColumn("Risk", min_value=0, max_value=100, format="%d"),
            "Confidence": st.column_config.ProgressColumn("Confidence", min_value=0.0, max_value=1.0, format="%.2f"),
        },
    )
    st.caption("Select a row to open the case. Queue is ranked by risk; analysts work top-down.")

    with st.expander("Open a specific case"):
        opts = [f"{d.customer_id} — {d.name} ({d.band} {d.score})"
                for d in sorted(shown, key=lambda x: -x.score)]
        pick = st.selectbox("Customer", opts, label_visibility="collapsed") if opts else None
        if pick and st.button("Open case →"):
            st.session_state.case_id = pick.split(" — ")[0]
            st.switch_page(CASE_PAGE)

    if event.selection.rows:
        st.session_state.case_id = df.iloc[event.selection.rows[0]]["ID"]
        st.switch_page(CASE_PAGE)


# --------------------------------------------------------------------------- Case detail view

def _driver_bars(decision):
    st.markdown("**Why this score** — driver contributions (sum to the score)")
    total = sum(x["contribution"] for x in decision.drivers)
    for drv in decision.drivers:
        pct = drv["contribution"] / 100
        st.progress(pct, text=f"{drv['code']}  ·  +{drv['contribution']}  —  {drv['rationale']}")
    st.caption(f"Σ drivers = {total}  =  score {decision.score}")


def case_page():
    cid = st.session_state.get("case_id")
    if not cid or cid not in BY_ID:
        st.info("No case selected.")
        if st.button("← Back to queue"):
            st.switch_page(QUEUE_PAGE)
        st.stop()

    dec = BY_ID[cid]
    dossier = DOSSIERS[cid]

    top = st.columns([3, 1])
    with top[0]:
        st.title(f"{BAND_EMOJI[dec.band]} {dec.name}")
        st.caption(f"{cid} · {dossier.kyc.get('occupation','?')} · {dec.country} · "
                   f"account {dossier.profile.get('tenure_days','?')}d old")
    with top[1]:
        if st.button("← Back to queue", use_container_width=True):
            st.switch_page(QUEUE_PAGE)

    m1, m2, m3, m4 = st.columns(4)
    m1.metric("Risk score", dec.score, dec.band)
    m2.metric("Disposition", dec.action.replace("_", " ").title())
    m3.metric("Confidence", f"{dec.confidence:.2f}")
    m4.metric("Routed to", TIER_LABEL.get(dec.tier, dec.tier))

    if dec.flags:
        st.error(f"🚨 Kill-switch: {', '.join(dec.flags)} — mandatory escalation regardless of score.", icon="🚨")
    if dec.engine_path == "rules_only":
        st.warning("Degraded path (LLM unavailable) — confidence capped; not auto-cleared.", icon="⚠️")
    elif dec.engine_path == "rules+sim":
        st.caption("ℹ️ Second opinion is a deterministic simulation (no API key). Set ANTHROPIC_API_KEY for live Claude.")

    left, right = st.columns([3, 2])

    with left:
        _driver_bars(dec)
        st.divider()
        st.markdown("**Findings & evidence**")
        for f in dec.findings:
            tag = "🚨 override" if f["is_override"] else f"+{f['weight']}"
            with st.expander(f"{f['code']}  ({tag}) — {f['rationale']}"):
                st.json(f["evidence"])
        st.markdown("**Analyst rationale (model)**")
        st.info(dec.rationale)

    with right:
        st.markdown("**Customer dossier**")
        st.markdown("*KYC / identity*")
        st.json({k: dossier.kyc.get(k) for k in
                 ("name", "nationality", "occupation", "id_doc", "onboarded", "kyc_complete")})
        st.markdown("*Profile*")
        st.json(dossier.profile)
        scr = dossier.screening
        st.markdown("*Screening*")
        st.json({"sanctions": scr.get("sanctions"), "pep_confirmed": scr.get("pep_confirmed"),
                 "adverse_media": scr.get("adverse_media")})
        st.markdown(f"*Transactions* ({len(dossier.transactions)})")
        if dossier.transactions:
            tdf = pd.DataFrame([{"date": t.date, "dir": t.direction, "amount": float(t.amount),
                                 "type": t.txn_type, "counterparty": t.counterparty,
                                 "cp_country": t.counterparty_country} for t in dossier.transactions])
            st.dataframe(tdf.sort_values("date"), hide_index=True, use_container_width=True, height=220)
        else:
            st.caption("No transaction data on file (incomplete dossier).")

    st.divider()
    st.markdown("### Analyst decision (human-in-the-loop)")
    taken = st.session_state.actions_taken.get(cid)
    if taken:
        st.success(f"Recorded: **{taken['action']}** by {taken['actor']} — {taken['note']}")
    signoff = None
    if dec.requires_signoff:
        signoff = st.text_input("Maker-checker sign-off (required to escalate)", placeholder="reviewer id")
    note = st.text_input("Decision note", value=dec.rationale, key=f"note_{cid}")
    b1, b2, b3 = st.columns(3)

    def _record(action):
        if action == "ESCALATE" and dec.requires_signoff and not signoff:
            st.toast("Sign-off required to escalate.", icon="⚠️")
            return
        log_analyst_action(cid, action, actor="analyst:demo", rationale=note,
                           override_of=dec.customer_id if action == "OVERRIDE_CLEAR" else None,
                           signoff_by=signoff)
        st.session_state.actions_taken[cid] = {"action": action, "actor": "analyst:demo", "note": note}

    b1.button("✅ Approve / Clear", use_container_width=True, on_click=_record, args=("APPROVE_CLEAR",))
    b2.button("🔴 Escalate (SAR)", use_container_width=True, type="primary", on_click=_record, args=("ESCALATE",))
    b3.button("⚠️ Override → clear", use_container_width=True, on_click=_record, args=("OVERRIDE_CLEAR",))


# --------------------------------------------------------------------------- Audit view

def audit_page():
    st.title("📜 Audit Trail")
    st.caption("Append-only. Every engine decision (clears AND escalates) plus every analyst action, "
               "with input fingerprint and ruleset version — regulator-defensible.")
    records = audit.read_all()
    if not records:
        st.info("No records yet.")
        return
    df = pd.DataFrame(records)
    cols = [c for c in ["ts", "customer_id", "actor", "action", "score", "confidence",
                        "engine_path", "band", "signoff_by", "input_fingerprint"] if c in df.columns]
    st.dataframe(df[cols].iloc[::-1], hide_index=True, use_container_width=True, height=520)
    st.download_button("Download audit log (JSONL)",
                       data="\n".join(json.dumps(r, default=str) for r in records),
                       file_name="audit_log.jsonl")


# --------------------------------------------------------------------------- nav

QUEUE_PAGE = st.Page(queue_page, title="Triage Queue", icon="📋", default=True)
CASE_PAGE = st.Page(case_page, title="Case Detail", icon="🔍")
AUDIT_PAGE = st.Page(audit_page, title="Audit Trail", icon="📜")

st.navigation([QUEUE_PAGE, CASE_PAGE, AUDIT_PAGE]).run()
