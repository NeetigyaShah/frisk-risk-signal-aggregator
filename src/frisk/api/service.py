"""frisk backend service — a REST API over the agentic engine, plus it serves the custom frontend.

The whole system runs as a backend: the frontend (in /frontend) is pure HTML/JS calling these endpoints.
Launch with `frisk serve` (uvicorn). Decisions carry the agent's tool-call trace + specialist opinions +
injected-memory log; transaction-pattern candidates are computed on demand for display.
"""
from __future__ import annotations

import threading
import uuid
from collections import Counter
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone

from fastapi import Body, FastAPI, File, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from frisk.ai.tools import build_tools, dossier_summary, scan_patterns
from frisk.config import CONFIG
from frisk.core.engine import assess, assess_all, log_analyst_action
from frisk.core.models import load_dossiers
from frisk.data import audit, store
from frisk.data.loaders import dossier_from_files, load_customer
from frisk.hitl import feedback
from frisk.hitl import queue as review_queue
from frisk.paths import PROJECT_ROOT, UPLOAD_SAMPLES

FRONTEND = PROJECT_ROOT / "frontend"
_BAND_UP = {"low": "LOW", "medium": "MED", "high": "HIGH"}
_BATCH_WORKERS = min(CONFIG["scale"]["workers"], 6)

app = FastAPI(title="frisk API", version="0.2.0")
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])

_STATE: dict = {"dossiers": {}, "decisions": {}}
_WARM = {"ready": False, "done": 0, "total": 0}
_START_LOCK = threading.Lock()
_started = False


def _score_one(d):
    try:
        dec = assess(d, persist=True)
        _STATE["decisions"][dec.customer_id] = dec
    except Exception:
        pass


def _bootstrap_bg():
    """Score the 20 customers in the BACKGROUND (parallel) so the UI never blocks on a cold load."""
    audit.reset(); review_queue.reset(); store.reset()
    try:
        from frisk.data import casebank
        casebank.reset()
    except Exception:
        pass
    ds = load_dossiers()
    _WARM["total"] = len(ds)
    _STATE["dossiers"] = {x.customer_id: x for x in ds}
    _STATE["decisions"] = {}
    with ThreadPoolExecutor(max_workers=_BATCH_WORKERS) as ex:
        for _ in as_completed([ex.submit(_score_one, d) for d in ds]):
            _WARM["done"] += 1
    _WARM["ready"] = True


def _ensure_started():
    global _started
    with _START_LOCK:
        if not _started:
            _started = True
            threading.Thread(target=_bootstrap_bg, daemon=True).start()


def _bootstrap() -> dict:
    _ensure_started()
    return _STATE


@app.on_event("startup")
def _startup():
    _ensure_started()


_PATTERN_CACHE: dict[str, list[dict]] = {}   # customer_id -> patterns; invalidated on re-ingest


def _patterns(dossier) -> list[dict]:
    """Advisory typology candidates computed on demand for display (not a rule that scored).

    Uses scan_patterns() directly (~1ms) rather than build_tools() (~375ms — LangChain schema
    introspection over all 9 agent tools, irrelevant for a read-only display lookup). Cached per
    customer since a dossier's transactions never change after ingest.
    """
    if dossier is None:
        return []
    cached = _PATTERN_CACHE.get(dossier.customer_id)
    if cached is not None:
        return cached
    out = []
    for c in scan_patterns(dossier):
        out.append({"code": c["pattern"].upper(), "label": c["pattern"].replace("_", "-").title(),
                    "rationale": c["note"], "strength": c.get("strength"), "txn_ids": c.get("txn_ids", [])})
    _PATTERN_CACHE[dossier.customer_id] = out
    return out


def _summary(d, dossier=None) -> dict:
    return {"id": d.customer_id, "name": d.name, "score": d.score, "band": _BAND_UP.get(d.band, d.band.upper()),
            "action": d.action, "confidence": d.confidence, "tier": d.tier, "country": d.country,
            "occupation": d.occupation, "pep": d.pep, "key_signals": d.key_signals, "summary": d.rationale,
            "patterns": _patterns(dossier), "engine_path": d.engine_path}


@app.get("/api/stats")
def stats():
    _ensure_started()
    if not _WARM["ready"]:
        return {"warming": True, "done": _WARM["done"],
                "total": _WARM["total"] or len(_STATE["dossiers"]), "broker": review_queue.backend()}
    decs = list(_STATE["decisions"].values())
    c = Counter(d.action for d in decs)
    return {"warming": False, "total": len(decs), "auto_clear": c.get("AUTO_CLEAR", 0),
            "review": c.get("REVIEW", 0), "escalate": c.get("ESCALATE", 0),
            "pending_review": c.get("PENDING_REVIEW", 0),
            "review_queue": review_queue.count(), "broker": review_queue.backend()}


@app.get("/api/queue")
def queue():
    st = _bootstrap()
    decs = sorted(st["decisions"].values(), key=lambda d: -d.score)
    return [_summary(d, st["dossiers"].get(d.customer_id)) for d in decs]


@app.get("/api/case/{cid}")
def case(cid: str):
    st = _bootstrap()
    d = st["decisions"].get(cid)
    dossier = st["dossiers"].get(cid)
    if not d:
        return {"error": "not found"}
    pats = _patterns(dossier)
    anomalous = {t for p in pats for t in p["txn_ids"]}
    txns = [{"id": t.id, "date": t.date, "amount": float(t.amount), "direction": t.direction,
             "type": t.txn_type, "counterparty": t.counterparty, "cp_country": t.counterparty_country,
             "anomalous": t.id in anomalous} for t in dossier.transactions] if dossier else []
    return {**_summary(d, dossier), "opinions": d.opinions, "trace": d.trace,
            "injected_memory": d.injected_memory, "evidence_refs": d.evidence_refs,
            "dossier": {"kyc": dossier.kyc, "profile": dossier.profile, "screening": dossier.screening,
                        "transactions": txns, "documents": dossier.documents} if dossier else {}}


@app.get("/api/case/{cid}/history")
def case_history(cid: str):
    _bootstrap()
    return store.history(cid, k=10)


@app.get("/api/case/{cid}/sar")
def case_sar(cid: str):
    """Draft a filing-ready Suspicious Activity Report narrative for one case."""
    from frisk.ai import sar
    st = _bootstrap()
    d = st["decisions"].get(cid)
    if not d:
        return {"error": "not found"}
    return sar.draft(d, st["dossiers"].get(cid))


@app.get("/api/compare")
def compare(a: str, b: str):
    """Side-by-side comparison of two scored cases — why did one clear and the other escalate?"""
    st = _bootstrap()
    out = []
    for cid in (a, b):
        d = st["decisions"].get(cid)
        if not d:
            return {"error": f"unknown customer {cid}"}
        dossier = st["dossiers"].get(cid)
        txns = dossier.transactions if dossier else []
        cash_in = sum(float(t.amount) for t in txns if t.direction == "in" and t.txn_type == "cash")
        credits = sum(float(t.amount) for t in txns if t.direction == "in")
        out.append({**_summary(d, dossier), "opinions": d.opinions, "trace": d.trace,
                    "evidence_refs": d.evidence_refs, "tools_used": len(d.trace),
                    "txn_count": len(txns), "cash_in": round(cash_in), "credits": round(credits),
                    "cp_countries": sorted({t.counterparty_country for t in txns}),
                    "documents": [x["name"] for x in (getattr(dossier, "documents", []) or [])],
                    "kyc_complete": bool((dossier.kyc or {}).get("kyc_complete", True)) if dossier else True})
    x, y = out
    shared = sorted(set(x["key_signals"]) & set(y["key_signals"]))
    return {"a": x, "b": y, "shared_signals": shared,
            "only_a": sorted(set(x["key_signals"]) - set(y["key_signals"])),
            "only_b": sorted(set(y["key_signals"]) - set(x["key_signals"])),
            "score_delta": x["score"] - y["score"]}


@app.get("/api/samples")
def samples():
    if not UPLOAD_SAMPLES.exists():
        return []
    return sorted(p.name for p in UPLOAD_SAMPLES.iterdir() if p.is_dir())


@app.get("/api/analytics")
def analytics():
    st = _bootstrap()
    decs = list(st["decisions"].values())
    bands = Counter(_BAND_UP.get(d.band, d.band.upper()) for d in decs)
    actions = Counter(d.action for d in decs)
    pats = Counter(p["label"] for d in decs for p in _patterns(st["dossiers"].get(d.customer_id)))
    return {"bands": {b: bands.get(b, 0) for b in ("LOW", "MED", "HIGH")},
            "actions": {a: actions.get(a, 0) for a in ("AUTO_CLEAR", "REVIEW", "ESCALATE", "PENDING_REVIEW")},
            "patterns": dict(pats.most_common()), "scores": sorted(d.score for d in decs)}


def _ingest(dossier):
    d = assess(dossier, persist=True)
    st = _bootstrap()
    st["decisions"][d.customer_id] = d
    st["dossiers"][d.customer_id] = dossier
    _PATTERN_CACHE.pop(d.customer_id, None)   # dossier changed (re-ingest) -> stale patterns
    return _summary(d, dossier)


@app.post("/api/ingest")
def ingest(sample_id: str = Body(..., embed=True)):
    return _ingest(load_customer(UPLOAD_SAMPLES / sample_id))


@app.post("/api/ingest/files")
async def ingest_files(files: list[UploadFile] = File(...)):
    fmap = {f.filename: (await f.read()).decode("utf-8", "ignore") for f in files}
    return _ingest(dossier_from_files(fmap))


_JOBS: dict = {}
_JOBS_LOCK = threading.Lock()


def _run_batch(job_id: str, ids: list[str]) -> None:
    def one(sid: str):
        try:
            res = _ingest(load_customer(UPLOAD_SAMPLES / sid))
        except Exception as e:
            res = {"id": sid, "name": sid, "error": str(e), "action": "ERROR"}
        with _JOBS_LOCK:
            j = _JOBS[job_id]; j["results"].append(res); j["done"] += 1
        return res

    with ThreadPoolExecutor(max_workers=_BATCH_WORKERS) as ex:
        list(ex.map(one, ids))
    with _JOBS_LOCK:
        _JOBS[job_id]["status"] = "complete"


@app.post("/api/ingest/batch")
def ingest_batch(ids: list[str] = Body(..., embed=True)):
    _bootstrap()
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


@app.get("/api/review")
def review():
    return review_queue.pending()


@app.post("/api/review/{cid}/resolve")
def resolve(cid: str, body: dict = Body(...)):
    review_queue.resolve(cid, {**body, "reviewer": "analyst:web"})
    st = _bootstrap()
    dossier = st["dossiers"].get(cid)
    feats = dossier_summary(dossier) if dossier else body.get("note", "")
    score = int(body.get("score", 0))
    band = body.get("band", "MED")
    action = body.get("action", "REVIEW")
    feedback.record(cid, feats, score, band, action, body.get("note", ""), "analyst:web")
    log_analyst_action(cid, action, actor="analyst:web", rationale=body.get("note", ""), signoff_by="analyst:web")
    # close the loop: store a human-verified episode so memory learns from the correction
    if dossier is not None:
        from frisk.ai import memory
        ts = datetime.now(timezone.utc).isoformat()
        memory.write_back({
            "customer_id": cid, "name": dossier.kyc.get("name", cid),
            "entity_type": dossier.profile.get("entity_type"), "country": dossier.profile.get("country", ""),
            "occupation": dossier.kyc.get("occupation", ""), "pep": bool(dossier.profile.get("pep")),
            "ts": ts, "score": score, "band": band, "confidence": 1.0, "disposition": action,
            "key_signals": [body.get("note", "")[:60]] if body.get("note") else [], "rationale": body.get("note", ""),
            "trace_ref": "", "human_verified": True, "corrected_score": score,
        }, dossier)
    return {"ok": True, "remaining": review_queue.count()}


@app.get("/api/audit")
def audit_log():
    return list(reversed(audit.read_all()))[:200]


if FRONTEND.exists():
    app.mount("/", StaticFiles(directory=str(FRONTEND), html=True), name="frontend")
