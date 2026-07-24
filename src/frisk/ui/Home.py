"""Financial Risk Signal Aggregator — analyst triage UI.

Three views wired with st.navigation: Triage Queue -> Case Detail -> Audit Trail.
Run:  streamlit run src/app/Home.py
"""
from __future__ import annotations

import json
import os
import sys


import pandas as pd
import streamlit as st

from frisk.data import audit
from frisk.query import nlquery
from frisk.data import store
from frisk.config import CONFIG
from frisk.core.engine import assess, assess_all, log_analyst_action
from frisk.core.models import load_dossiers
from frisk.hitl import queue as review_queue, feedback
from frisk.ai.crosscheck import _features

st.set_page_config(page_title="Risk Signal Aggregator", page_icon="🛡️", layout="wide")

from frisk.paths import CUSTOMERS_DIR as DATA

BAND_EMOJI = {"LOW": "🟢", "MED": "🟡", "HIGH": "🔴"}
ACTION_EMOJI = {"AUTO_CLEAR": "🟢 Auto-clear", "REVIEW": "🟡 Review", "ESCALATE": "🔴 Escalate",
                "PENDING_REVIEW": "🟠 Human review"}
TIER_LABEL = {"none": "—", "junior": "Junior", "senior": "Senior", "named_reviewer": "MLRO"}


@st.cache_resource(show_spinner="Scoring customers…")
def bootstrap():
    """Score all customers once per session and seed the audit log."""
    audit.reset()
    ds = load_dossiers(DATA)
    decs = assess_all(ds, persist=True)  # sequential (cache-warm -> instant); one AuditRecord each
    store.upsert_many(decs)              # also populate the scalable SQLite read store
    review_queue.reset()                 # (re)build the human review queue from this run
    for dec in decs:
        if dec.action == "PENDING_REVIEW":
            review_queue.enqueue_decision(dec)
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
    c1, c2, c3, c4, c5 = st.columns(5)
    c1.metric("Total customers", len(DECISIONS))
    c2.metric("🔴 Escalate", counts["ESCALATE"])
    c3.metric("🟡 Review", counts["REVIEW"])
    c4.metric("🟢 Auto-cleared", counts["AUTO_CLEAR"], help="Low-risk + high-confidence; no analyst time")
    c5.metric("🟠 Human queue", counts["PENDING_REVIEW"], help="LLM was unsure → routed to a human reviewer")

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
    if not decision.drivers:
        return
    llm = decision.engine_path in ("rules+graph", "rules+llm", "rules+sim")
    st.markdown("**Deterministic rule cross-check** (reference)" if llm else "**Why this score** — driver contributions")
    total = sum(x["contribution"] for x in decision.drivers)
    for drv in decision.drivers:
        st.progress(min(1.0, drv["contribution"] / 100),
                    text=f"{drv['code']}  ·  +{drv['contribution']}  —  {drv['rationale']}")
    st.caption(f"rule points = {total}" + ("  (the shown score is the LLM's)" if llm else f"  =  score {decision.score}"))


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
    elif dec.engine_path == "rules+graph":
        st.caption("ℹ️ Second opinion via a 5-step LangGraph orchestration (3 parallel domain analysts → synthesis → QA verification).")
    elif dec.engine_path == "rules+sim":
        st.caption("ℹ️ Second opinion is a deterministic simulation (no API key set).")

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

        sources = dec.llm_detail.get("source_findings") if dec.llm_detail else None
        if sources:
            st.markdown("**Multi-step AI reasoning** — parallel domain analysts → synthesis → verification (LangGraph)")
            lv = {"low": "🟢", "medium": "🟡", "high": "🔴"}
            cols = st.columns(len(sources))
            for col, sf in zip(cols, sources):
                col.markdown(f"**{sf['domain'].title()}** {lv.get(sf['risk_level'],'⚪')} {sf['risk_level']}")
                col.caption(sf.get("note", ""))
            verd = dec.llm_detail.get("verdict")
            if verd:
                tag = "✅ verified consistent" if verd.get("consistent") else "✏️ score adjusted by QA"
                st.caption(f"QA verification: {tag} — {str(verd.get('note',''))[:220]}")

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


# --------------------------------------------------------------------------- Human review queue

def _why(c) -> str:
    srcs = c.get("source_findings") or []
    if srcs:
        return "analysts: " + ", ".join(f"{s['domain'][:4]}={s['risk_level']}" for s in srcs)
    return "LLM unavailable / low confidence"


def review_page():
    st.title("🟠 Human Review Queue")
    st.caption("Cases where the LLM was **not confident** are routed here for an independent human decision. "
               f"Broker: **{review_queue.backend()}**. Your decision resolves the case and *teaches the model* "
               "(saved as a calibration example for future scoring).")

    pend = review_queue.pending()
    if not pend:
        st.success("Queue empty — the model was confident on every case, nothing awaits human review.")
        return

    st.metric("Pending cases", len(pend))
    df = pd.DataFrame([{
        "ID": c["customer_id"], "Customer": c.get("name"), "LLM score": c.get("llm_score"),
        "Band": c.get("band"), "Confidence": c.get("confidence", 0.0), "Why queued": _why(c),
    } for c in pend])
    st.dataframe(df, hide_index=True, use_container_width=True, column_config={
        "Confidence": st.column_config.ProgressColumn("Confidence", min_value=0.0, max_value=1.0, format="%.2f")})

    pick = st.selectbox("Open a case to review", [c["customer_id"] for c in pend])
    case = next(c for c in pend if c["customer_id"] == pick)
    st.divider()
    st.subheader(f"{case['customer_id']} — {case.get('name')}  "
                 f"(LLM said {case.get('llm_score')} · confidence {float(case.get('confidence', 0)):.2f})")

    srcs = case.get("source_findings") or []
    if srcs:
        st.markdown("**Why the model was unsure — the domain analysts:**")
        lv = {"low": "🟢", "medium": "🟡", "high": "🔴"}
        cols = st.columns(len(srcs))
        for col, sf in zip(cols, srcs):
            col.markdown(f"**{sf['domain'].title()}** {lv.get(sf['risk_level'], '⚪')} {sf['risk_level']}")
            col.caption(sf.get("note", ""))
    verd = case.get("verdict")
    if verd:
        st.caption(f"QA verifier: {'consistent' if verd.get('consistent') else 'flagged/adjusted'} — "
                   f"{str(verd.get('note', ''))[:200]}")
    if case.get("reason"):
        st.info(case["reason"])

    d = DOSSIERS.get(pick)
    if d:
        with st.expander("Full dossier + unstructured documents (what the reviewer inspects)"):
            st.markdown("*KYC*"); st.json(d.kyc)
            st.markdown("*Screening*"); st.json(d.screening)
            for doc in d.documents:
                st.markdown(f"**📄 {doc['name']}**"); st.text(doc["text"])

    st.divider()
    st.markdown("### Your decision — sets the correct score and teaches the model")
    r1, r2, r3 = st.columns(3)
    score = r1.number_input("Correct score (0–100)", 0, 100, int(case.get("llm_score") or 50))
    bands = ["LOW", "MED", "HIGH"]
    band = r2.selectbox("Band", bands, index=bands.index(case.get("band", "MED")) if case.get("band") in bands else 1)
    action = r3.selectbox("Action", ["AUTO_CLEAR", "REVIEW", "ESCALATE"], index=1)
    note = st.text_input("Correction note (why — this is the lesson the model learns)", key=f"rev_{pick}")

    if st.button("✅ Submit & teach the model", type="primary"):
        review_queue.resolve(pick, {"human_score": score, "band": band, "action": action,
                                    "note": note, "reviewer": "analyst:demo"})
        feats = _features(DOSSIERS[pick]) if pick in DOSSIERS else case.get("reason", "")
        feedback.record(pick, feats, int(score), band, action, note, "analyst:demo")
        log_analyst_action(pick, action, actor="analyst:demo", rationale=note or "human review", signoff_by="analyst:demo")
        st.success(f"Resolved {pick}. Correction saved — future scoring will calibrate toward it.")
        st.rerun()


# --------------------------------------------------------------------------- Ingest / Upload

def upload_page():
    st.title("📤 Ingest / Upload  (CSV · JSON · text)")
    st.caption("Score a customer on demand from uploaded documents or a ready-made sample profile. "
               "Low-confidence results are pushed to the Human Review Queue.")

    from frisk.paths import UPLOAD_SAMPLES
    from frisk.data.loaders import load_customer, dossier_from_files

    src = st.radio("Source", ["Pick a sample profile", "Upload files"], horizontal=True)
    dossier = None
    if src == "Pick a sample profile":
        if UPLOAD_SAMPLES.exists():
            ids = sorted(p.name for p in UPLOAD_SAMPLES.iterdir() if p.is_dir())
            pick = st.selectbox("Sample profile", ids, help=f"from {UPLOAD_SAMPLES}")
            if pick:
                dossier = load_customer(UPLOAD_SAMPLES / pick)
        else:
            st.info("No sample set found. Generate it with:  `frisk samples`")
    else:
        files = st.file_uploader("Upload a customer's files: kyc.json, account.json, transactions.csv, "
                                 "screening.json, and any *.txt", accept_multiple_files=True)
        if files:
            dossier = dossier_from_files({f.name: f.getvalue().decode("utf-8", "ignore") for f in files})

    if dossier:
        st.caption(f"Ready: **{dossier.customer_id}** — {dossier.kyc.get('name', '?')} · "
                   f"{len(dossier.transactions)} txns · {len(dossier.documents)} unstructured docs")
        if st.button("▶ Score this customer", type="primary"):
            with st.spinner("Scoring via the LLM multi-step graph…"):
                dec = assess(dossier, persist=True)
            store.upsert_many([dec])
            m1, m2, m3 = st.columns(3)
            m1.metric("Score", dec.score, dec.band)
            m2.metric("Confidence", f"{dec.confidence:.2f}")
            m3.metric("Disposition", dec.action.replace("_", " ").title())
            st.info(dec.rationale)
            srcs = (dec.llm_detail or {}).get("source_findings") or []
            if srcs:
                lv = {"low": "🟢", "medium": "🟡", "high": "🔴"}
                cols = st.columns(len(srcs))
                for col, sf in zip(cols, srcs):
                    col.markdown(f"**{sf['domain'].title()}** {lv.get(sf['risk_level'], '⚪')} {sf['risk_level']}")
                    col.caption(sf.get("note", ""))
            if dec.action == "PENDING_REVIEW":
                review_queue.enqueue_decision(dec)
                st.warning("🟠 Low confidence — added to the **Human Review Queue** for a human decision.")
            else:
                st.success(f"Routed: {dec.action.replace('_', ' ').title()}")


# --------------------------------------------------------------------------- nav

QUEUE_PAGE = st.Page(queue_page, title="Triage Queue", icon="📋", default=True)
CASE_PAGE = st.Page(case_page, title="Case Detail", icon="🔍")
UPLOAD_PAGE = st.Page(upload_page, title="Ingest / Upload", icon="📤")
REVIEW_PAGE = st.Page(review_page, title="Human Review Queue", icon="🟠")
AUDIT_PAGE = st.Page(audit_page, title="Audit Trail", icon="📜")

st.navigation([QUEUE_PAGE, CASE_PAGE, UPLOAD_PAGE, REVIEW_PAGE, AUDIT_PAGE]).run()
