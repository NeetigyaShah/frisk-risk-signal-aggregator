"""frisk backend service — a REST API over the engine, plus it serves the custom frontend.

The whole system runs as a backend: the frontend (in /frontend) is pure HTML/JS that calls these
endpoints. Launch with `frisk serve` (uvicorn).
"""
from __future__ import annotations

import threading
import uuid
from collections import Counter
from concurrent.futures import ThreadPoolExecutor

from fastapi import Body, FastAPI, File, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from frisk.ai.crosscheck import _features
from frisk.config import CONFIG
from frisk.core.engine import assess, assess_all, log_analyst_action
from frisk.core.models import load_dossiers
from frisk.data import audit, store
from frisk.data.loaders import dossier_from_files, load_customer
from frisk.hitl import feedback
from frisk.hitl import queue as review_queue
from frisk.paths import PROJECT_ROOT, UPLOAD_SAMPLES

FRONTEND = PROJECT_ROOT / "frontend"
_TYPOLOGIES = {"STRUCTURING", "LAYERING", "ROUND_TRIP", "DORMANT_SPIKE"}
# ponytail: batch parallelism capped at 6 — each customer = a 5-call LLM graph, so
# firing all 40 at once would be ~200 concurrent OpenRouter calls -> instant 429s.
_BATCH_WORKERS = min(CONFIG["scale"]["workers"], 6)

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


# ---- batch scoring: fire N samples through the LLM graph in parallel, poll for results ----
_JOBS: dict = {}
_JOBS_LOCK = threading.Lock()


def _run_batch(job_id: str, ids: list[str]) -> None:
    def one(sid: str):
        try:
            res = _ingest(load_customer(UPLOAD_SAMPLES / sid))
        except Exception as e:  # one bad profile never sinks the batch
            res = {"id": sid, "name": sid, "error": str(e), "action": "ERROR"}
        with _JOBS_LOCK:
            j = _JOBS[job_id]
            j["results"].append(res)
            j["done"] += 1
        return res

    with ThreadPoolExecutor(max_workers=_BATCH_WORKERS) as ex:
        list(ex.map(one, ids))
    with _JOBS_LOCK:
        _JOBS[job_id]["status"] = "complete"


@app.post("/api/ingest/batch")
def ingest_batch(ids: list[str] = Body(..., embed=True)):
    _bootstrap()  # warm shared state before worker threads touch it
    job_id = uuid.uuid4().hex[:12]
    with _JOBS_LOCK:
        _JOBS[job_id] = {"status": "running", "done": 0, "total": len(ids),
                         "workers": _BATCH_WORKERS, "results": []}
    threading.Thread(target=_run_batch, args=(job_id, ids), daemon=True).start()
    return {"job_id": job_id, "total": len(ids), "workers": _BATCH_WORKERS}


@app.get("/api/ingest/batch/{job_id}")
def ingest_batch_status(job_id: str):
    with _JOBS_LOCK:
        j = _JOBS.get(job_id)
        return dict(j) if j else {"error": "not found"}


@app.get("/api/analytics")
def analytics():
    """Aggregates for the dashboard charts."""
    decs = list(_bootstrap()["decisions"].values())
    bands = Counter(d.band for d in decs)
    actions = Counter(d.action for d in decs)
    pats = Counter(p["label"] for d in decs for p in _patterns(d))
    return {
        "bands": {b: bands.get(b, 0) for b in ("LOW", "MED", "HIGH")},
        "actions": {a: actions.get(a, 0) for a in
                    ("AUTO_CLEAR", "REVIEW", "ESCALATE", "PENDING_REVIEW")},
        "patterns": dict(pats.most_common()),
        "scores": sorted(d.score for d in decs),
    }


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
