"""frisk backend service — a REST API over the engine, plus it serves the custom frontend.

The whole system runs as a backend: the frontend (in /frontend) is pure HTML/JS that calls these
endpoints. Launch with `frisk serve` (uvicorn).
"""
from __future__ import annotations

from collections import Counter

from fastapi import Body, FastAPI, File, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from frisk.ai.crosscheck import _features
from frisk.core.engine import assess, assess_all, log_analyst_action
from frisk.core.models import load_dossiers
from frisk.data import audit, store
from frisk.data.loaders import dossier_from_files, load_customer
from frisk.hitl import feedback
from frisk.hitl import queue as review_queue
from frisk.paths import PROJECT_ROOT, UPLOAD_SAMPLES

FRONTEND = PROJECT_ROOT / "frontend"
_TYPOLOGIES = {"STRUCTURING", "LAYERING", "ROUND_TRIP", "DORMANT_SPIKE"}

app = FastAPI(title="frisk API", version="0.1.0")
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])

_STATE: dict = {}


def _bootstrap() -> dict:
    if _STATE:
        return _STATE
    audit.reset()
    review_queue.reset()
    ds = load_dossiers()
    decs = assess_all(ds, persist=True)
    store.upsert_many(decs)
    for d in decs:
        if d.action == "PENDING_REVIEW":
            review_queue.enqueue_decision(d)
    _STATE["dossiers"] = {x.customer_id: x for x in ds}
    _STATE["decisions"] = {d.customer_id: d for d in decs}
    return _STATE


def _patterns(d) -> list[dict]:
    """The detected patterns / anomalies — the transaction typology detectors that fired."""
    out = []
    for f in d.findings:
        if f["code"] in _TYPOLOGIES:
            out.append({"code": f["code"], "label": f["code"].replace("_", "-").title(),
                        "rationale": f["rationale"], "txn_ids": f["evidence"].get("txn_ids", [])})
    return out


def _summary(d) -> dict:
    return {"id": d.customer_id, "name": d.name, "score": d.score, "band": d.band, "action": d.action,
            "confidence": d.confidence, "tier": d.tier, "country": d.country, "occupation": d.occupation,
            "flags": d.flags, "summary": d.rationale, "patterns": _patterns(d),
            "engine_path": d.engine_path}


@app.get("/api/stats")
def stats():
    decs = list(_bootstrap()["decisions"].values())
    c = Counter(d.action for d in decs)
    return {"total": len(decs),
            "auto_clear": c.get("AUTO_CLEAR", 0), "review": c.get("REVIEW", 0),
            "escalate": c.get("ESCALATE", 0), "pending_review": c.get("PENDING_REVIEW", 0),
            "review_queue": review_queue.count(), "broker": review_queue.backend()}


@app.get("/api/queue")
def queue():
    decs = sorted(_bootstrap()["decisions"].values(), key=lambda d: -d.score)
    return [_summary(d) for d in decs]


@app.get("/api/case/{cid}")
def case(cid: str):
    st = _bootstrap()
    d = st["decisions"].get(cid)
    dossier = st["dossiers"].get(cid)
    if not d:
        return {"error": "not found"}
    anomalous = {t for p in _patterns(d) for t in p["txn_ids"]}
    txns = [{"id": t.id, "date": t.date, "amount": float(t.amount), "direction": t.direction,
             "type": t.txn_type, "counterparty": t.counterparty, "cp_country": t.counterparty_country,
             "anomalous": t.id in anomalous} for t in dossier.transactions] if dossier else []
    return {**_summary(d), "llm_detail": d.llm_detail, "drivers": d.drivers, "findings": d.findings,
            "dossier": {"kyc": dossier.kyc, "profile": dossier.profile, "screening": dossier.screening,
                        "transactions": txns, "documents": dossier.documents} if dossier else {}}


@app.get("/api/samples")
def samples():
    if not UPLOAD_SAMPLES.exists():
        return []
    return sorted(p.name for p in UPLOAD_SAMPLES.iterdir() if p.is_dir())


def _ingest(dossier):
    d = assess(dossier, persist=True)
    store.upsert_many([d])
    st = _bootstrap()
    st["decisions"][d.customer_id] = d
    st["dossiers"][d.customer_id] = dossier
    if d.action == "PENDING_REVIEW":
        review_queue.enqueue_decision(d)
    return {**_summary(d), "llm_detail": d.llm_detail}


@app.post("/api/ingest")
def ingest(sample_id: str = Body(..., embed=True)):
    return _ingest(load_customer(UPLOAD_SAMPLES / sample_id))


@app.post("/api/ingest/files")
async def ingest_files(files: list[UploadFile] = File(...)):
    fmap = {f.filename: (await f.read()).decode("utf-8", "ignore") for f in files}
    return _ingest(dossier_from_files(fmap))


@app.get("/api/review")
def review():
    return review_queue.pending()


@app.post("/api/review/{cid}/resolve")
def resolve(cid: str, body: dict = Body(...)):
    review_queue.resolve(cid, {**body, "reviewer": "analyst:web"})
    dossier = _bootstrap()["dossiers"].get(cid)
    feats = _features(dossier) if dossier else body.get("note", "")
    feedback.record(cid, feats, int(body.get("score", 0)), body.get("band", "MED"),
                    body.get("action", "REVIEW"), body.get("note", ""), "analyst:web")
    log_analyst_action(cid, body.get("action", "REVIEW"), actor="analyst:web",
                       rationale=body.get("note", ""), signoff_by="analyst:web")
    return {"ok": True, "remaining": review_queue.count()}


@app.get("/api/audit")
def audit_log():
    return list(reversed(audit.read_all()))[:200]


if FRONTEND.exists():
    app.mount("/", StaticFiles(directory=str(FRONTEND), html=True), name="frontend")
