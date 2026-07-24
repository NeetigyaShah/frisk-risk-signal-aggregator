# Full-LLM Agentic Scorer with Layered Memory — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace frisk's deterministic rules engine with a fully-LLM agentic scorer — parallel memory-fed specialists → an agentic tool-using orchestrator — backed by a 5-tier memory system (working/per-customer/episodic/semantic/procedural) across Redis + a relational DB + a case-bank.

**Architecture:** Per customer: retrieve memory → 3 parallel specialist LLM calls → 1 serial tool-calling orchestrator that reads their opinions + original docs + tools → `finalize` a RiskFinding → confidence-gate to auto-dispose or human review → write back to memory. No deterministic scoring, no sanctions, no fallback rules.

**Tech Stack:** Python 3.11, pydantic v2, LangChain `ChatOpenAI` over OpenRouter (deepseek-v4-flash), SQLite (relational + case-bank), Redis (working memory + review queue), FastAPI + vanilla-JS frontend, pytest.

## Global Constraints

- No deterministic scoring, no sanctions logic, no never-fails/rules-only fallback (LLM API assumed reliable).
- Orchestrator LLM bound with `parallel_tool_calls=False`; `temperature=0`; `agent_max_steps=12`.
- `Decimal` for money; deterministic seed order; no `datetime.now()`/random inside any scoring-decision predicate.
- Audit store append-only JSONL; every decision carries a tool-call trace + injected-memory log + evidence_refs.
- NL query: whitelisted Pydantic filter spec only — never `eval`/`df.query` on model text.
- Provider access only through `ai/providers/` factory (`get_provider()`), never hardcoded.
- Offline/test determinism via the **mock provider** (not `LLM_MODE=off`).
- Redis has an in-memory fallback so the demo never hard-fails on a missing broker.

---

## File map (what each unit owns)

**New**
- `src/frisk/data/store.py` (rewrite) — relational history: `customers`, `assessments`, `lessons` + migrate.
- `src/frisk/data/casebank.py` — episodic case-bank: `add(card, meta)`, `similar(features, k)` (SQL feature-match).
- `src/frisk/hitl/redis_conn.py` — one shared Redis client (+ in-memory fallback) reused by queue + scratchpad.
- `src/frisk/hitl/scratchpad.py` — working memory `start/note/read/set_stage/evict` on `frisk:scratch:{cid}`.
- `src/frisk/hitl/reflection.py` — LLM reflection over corrections → `lessons` rows.
- `src/frisk/ai/memory.py` — `retrieve(dossier)`, `assemble_*`, `write_back(decision)`, injected-memory log.
- `src/frisk/ai/tools.py` — orchestrator fact-tools bound to a Dossier.
- `src/frisk/ai/specialists.py` — 3 parallel memory-fed specialist calls.
- `src/frisk/ai/agent.py` — orchestrator serial tool-calling loop; `score(d, mem) -> (RiskFinding, detail)`.
- `src/frisk/data/reference/` — semantic cheat-sheets (`typologies.md`, `high_risk.md`).

**Rewrite** — `core/engine.py`, `core/models.py`, `config/{constants,settings,__init__}.py`, `api/service.py`,
`frontend/app.js`, `query/nlquery.py`, `pipeline/batch.py`, `hitl/queue.py`, `hitl/feedback.py`,
`ai/providers/mock.py`, `data/generate.py`, `cli.py`, `tests/*`.

**Delete** — `core/rules.py`, `ai/crosscheck.py`, `ai/orchestrator.py`, `ui/Home.py`.

**Keep** — `data/loaders.py`, `data/audit.py`, `data/paths.py`, `ai/providers/{base,factory,openrouter,nvidia,gemini,anthropic}.py`, `observability/telemetry.py`, `frontend/{index.html,styles.css}`.

---

## PHASE A — Data model & config

### Task A1: Strip sanctions + adverse-media from the generator, keep PEP

**Files:** Modify `src/frisk/data/generate.py`; regenerate `data/customers/` + `data/upload_samples/`.

**Interfaces — Produces:** `screening.json` shape becomes `{"pep_confirmed": bool}` only (no `sanctions`, no `adverse_media`); no `adverse_media_*.txt` documents written.

- [ ] Step 1 — In `generate.py`, delete all sanctions generation (the `sanctions` list, any `SANCTIONS`/`match_score` code) and all adverse-media generation (the `adverse_media` list + the `adverse_media_*.txt` render). Keep `pep_confirmed`.
- [ ] Step 2 — In the review-trigger sample profiles, replace any `adverse_*`/sanctions-based conflict types with conflicts built from KYC gaps / transaction typologies / PEP / high-risk geography (so 5/40 still route to human review without adverse-media).
- [ ] Step 3 — Update `_selfcheck()` to assert no `sanctions`/`adverse_media` keys exist and `pep_confirmed` present.
- [ ] Step 4 — Run: `python -m frisk.cli generate && python -m frisk.cli samples`. Expected: folders written, self-check OK.
- [ ] Step 5 — Verify: `grep -rl "adverse_media\|sanctions" data/customers/ || echo clean` → `clean`.
- [ ] Step 6 — Commit: `chore(data): remove sanctions + adverse-media from generator, keep PEP`.

### Task A2: Trim config knobs

**Files:** Modify `config/constants.py`, `config/settings.py`, `config/__init__.py`.

**Interfaces — Produces:** `CONFIG` gains `agent_max_steps:int`, `scratchpad_ttl_s:int`, `memory_topk:int`; loses `weights`, `reporting_floor`, typology/cash/velocity thresholds, `hard_escalate`, `agreement_tolerance`, `degraded_confidence_cap`, `engine_mode`, `multi_step`, `crosscheck_policy`, `gated_confidence`. `band_for`/`BAND_LABEL`/routing thresholds/`confidence_threshold`/`redis_url` kept. `ruleset_version`→`policy_version`.

- [ ] Step 1 — Write failing test `tests/test_config.py::test_config_has_agent_knobs`:
```python
from frisk.config import CONFIG
def test_config_has_agent_knobs():
    assert CONFIG["agent_max_steps"] >= 4
    assert CONFIG["memory_topk"] >= 1
    assert "weights" not in CONFIG and "engine_mode" not in CONFIG
    from frisk.config import band_for, BAND_LABEL
    assert BAND_LABEL[band_for(90)] == "HIGH"
```
- [ ] Step 2 — Run: `pytest tests/test_config.py -v` → FAIL.
- [ ] Step 3 — Edit the three config files: remove the rule knobs; add `agent_max_steps=12`, `scratchpad_ttl_s=3600`, `memory_topk=3` to `settings.py` and thread into `CONFIG` in `__init__.py`. Rename `ruleset_version`→`policy_version`. Keep band/routing/confidence/redis.
- [ ] Step 4 — Run: `pytest tests/test_config.py -v` → PASS.
- [ ] Step 5 — Commit: `refactor(config): drop rule knobs, add agent + memory knobs`.

---

## PHASE B — New leaf modules (no dependency on old rules code)

### Task B1: Relational store (customers / assessments / lessons)

**Files:** Rewrite `src/frisk/data/store.py`; Test `tests/test_store.py`.

**Interfaces — Produces:**
```python
migrate() -> None                       # create tables if absent
record_assessment(dec: dict) -> int     # append one row, returns id; upserts customers row
history(customer_id: str, k: int = 5) -> list[dict]   # newest-first assessments for a customer
latest_all() -> list[dict]              # latest assessment per customer (dashboard queue)
add_lesson(text: str, from_corrections: list) -> int
top_lessons(k: int = 5) -> list[dict]
count() -> int
```
`dec` keys used: `customer_id,name,entity_type,country,occupation,pep,ts,score,band,confidence,disposition,key_signals(list),rationale,trace_ref,human_verified(bool),corrected_score`.

- [ ] Step 1 — Failing test:
```python
from frisk.data import store
def test_history_and_latest(tmp_path, monkeypatch):
    monkeypatch.setenv("FRISK_DATA_DIR", str(tmp_path))
    store.migrate()
    base = dict(customer_id="C1", name="A", entity_type="ind", country="GB", occupation="x",
                pep=False, band="LOW", confidence=0.9, disposition="AUTO_CLEAR",
                key_signals=["k"], rationale="r", trace_ref="t", human_verified=False, corrected_score=None)
    store.record_assessment({**base, "ts": "2026-01-01T00:00:00Z", "score": 10})
    store.record_assessment({**base, "ts": "2026-02-01T00:00:00Z", "score": 40})
    h = store.history("C1", k=5)
    assert [r["score"] for r in h] == [40, 10]       # newest first
    assert len(store.latest_all()) == 1 and store.latest_all()[0]["score"] == 40
```
- [ ] Step 2 — Run → FAIL.
- [ ] Step 3 — Implement with stdlib `sqlite3` at `paths.DB_DIR/frisk.db`. Three tables per the spec schema; `record_assessment` does `INSERT INTO assessments` + `INSERT OR REPLACE INTO customers`; `history` = `SELECT ... WHERE customer_id=? ORDER BY ts DESC LIMIT ?`; `latest_all` = group by customer_id taking max(ts); JSON-encode `key_signals`.
- [ ] Step 4 — Run → PASS.
- [ ] Step 5 — Commit: `feat(store): relational assessment history + lessons`.

### Task B2: Shared Redis connection + working-memory scratchpad

**Files:** Create `src/frisk/hitl/redis_conn.py`, `src/frisk/hitl/scratchpad.py`; Test `tests/test_scratchpad.py`. Modify `hitl/queue.py` to import `_redis()` from `redis_conn`.

**Interfaces — Produces:**
```python
# redis_conn.py
def redis_conn() -> tuple[client|None, dict]   # (real client or None, in-memory fallback dict)
# scratchpad.py
start(cid: str, facts: dict) -> None
note(cid: str, key: str, value: str) -> None
set_stage(cid: str, stage: str) -> None
read(cid: str) -> dict                          # {run_id,facts,notes,scratch,stage,working_score,confidence}
evict(cid: str) -> dict                          # returns snapshot then deletes
```

- [ ] Step 1 — Failing test (uses in-memory fallback, no real Redis):
```python
from frisk.hitl import scratchpad
def test_scratchpad_lifecycle():
    scratchpad.start("C9", {"pep": True})
    scratchpad.note("C9", "cash", "clustered")
    r = scratchpad.read("C9")
    assert r["facts"]["pep"] is True and r["notes"]["cash"] == "clustered"
    snap = scratchpad.evict("C9")
    assert snap["notes"]["cash"] == "clustered"
    assert scratchpad.read("C9") == {}            # gone
```
- [ ] Step 2 — Run → FAIL.
- [ ] Step 3 — `redis_conn.py`: try `redis.from_url(CONFIG["redis_url"])` + `ping()`; on failure return `(None, {})` and use the module-level dict as fallback. `scratchpad.py`: HASH ops when client present else the dict; JSON-encode `facts`/`notes`; `start` DELs stale key + sets TTL `scratchpad_ttl_s`; `evict` reads-then-DELs. Point `queue.py` at `redis_conn.redis_conn()`.
- [ ] Step 4 — Run → PASS. Also run existing `tests/` for queue to confirm no regression.
- [ ] Step 5 — Commit: `feat(hitl): shared redis conn + working-memory scratchpad`.

### Task B3: Episodic case-bank (feature-match)

**Files:** Create `src/frisk/data/casebank.py`; Test `tests/test_casebank.py`.

**Interfaces — Produces:**
```python
add(customer_id: str, card: str, features: dict, band: str, disposition: str, human_verified: bool) -> None
similar(features: dict, k: int = 3, prefer_verified: bool = True) -> list[dict]  # [{card, band, disposition, score}]
seed_from_dossiers(dossiers: list, decisions: list) -> int
```
`features` keys: `entity_type,country,occupation,pep,band` (+ optional `top_signal`). Similarity = weighted overlap count.

- [ ] Step 1 — Failing test:
```python
from frisk.data import casebank
def test_similar_ranks_overlap(tmp_path, monkeypatch):
    monkeypatch.setenv("FRISK_DATA_DIR", str(tmp_path))
    casebank.add("A","cardA",{"country":"SY","occupation":"director","pep":True},"HIGH","ESCALATE",True)
    casebank.add("B","cardB",{"country":"GB","occupation":"teacher","pep":False},"LOW","AUTO_CLEAR",True)
    top = casebank.similar({"country":"SY","occupation":"director","pep":True}, k=1)
    assert top[0]["card"] == "cardA"
```
- [ ] Step 2 — Run → FAIL.
- [ ] Step 3 — Implement over a `cases` SQLite table (same `frisk.db`): store `features` JSON; `similar` loads rows, scores each by matching feature fields (weights: country 2, occupation 2, pep 1, entity_type 1, band 1), tie-break `human_verified`, return top-k. `# ponytail: feature-match now; swap to sqlite-vec embeddings behind this same signature later.`
- [ ] Step 4 — Run → PASS.
- [ ] Step 5 — Commit: `feat(casebank): episodic feature-match case store`.

### Task B4: Semantic reference files + loader

**Files:** Create `src/frisk/data/reference/typologies.md`, `.../high_risk.md`; add `reference(name)` loader in `ai/memory.py` (created next task) — for now a tiny `src/frisk/data/reference/__init__.py` with `load(name)->str`.

- [ ] Step 1 — Write `typologies.md` (plain-language structuring/layering/round-trip/dormant-spike defs) and `high_risk.md` (high-risk country + occupation lists moved from old `constants.py`, as *reference*).
- [ ] Step 2 — `reference/__init__.py`: `load(name)->str` reads the `.md` (returns "" if missing).
- [ ] Step 3 — Test `tests/test_reference.py::test_load` asserts `"structuring" in load("typologies")`.
- [ ] Step 4 — Run → PASS. Commit: `feat(reference): semantic cheat-sheets for specialists`.

### Task B5: Memory orchestration module

**Files:** Create `src/frisk/ai/memory.py`; Test `tests/test_memory.py`.

**Interfaces — Produces:**
```python
retrieve(d: Dossier) -> dict     # {history:[...], similar:[...], lessons:[...], injected:{...log...}}
kyc_cheatsheet() / txn_cheatsheet() -> str        # from reference files
fewshot_for(domain: str, features: dict, k: int) -> str   # human-verified episodes as text
write_back(decision: dict, d: Dossier) -> None    # append assessment + add case-card
```

- [ ] Step 1 — Failing test with monkeypatched `store`/`casebank` returning canned rows; assert `retrieve(d)["injected"]` records counts of history/similar/lessons and that `write_back` calls `store.record_assessment` + `casebank.add`.
- [ ] Step 2 — Run → FAIL.
- [ ] Step 3 — Implement: `retrieve` = `store.history(cid)` + `casebank.similar(features(d))` + `store.top_lessons()`; build a `card(d, decision)` text; `write_back` appends + adds card (human_verified from decision). `features(d)` derives `{entity_type,country,occupation,pep}` from the Dossier. Log injected memory as `{history_n, similar_n, lessons_n, ids}`.
- [ ] Step 4 — Run → PASS. Commit: `feat(memory): retrieve/assemble/write-back across tiers`.

### Task B6: Orchestrator tools

**Files:** Create `src/frisk/ai/tools.py`; Test `tests/test_tools.py`.

**Interfaces — Produces:** `build_tools(d: Dossier, cid: str) -> list[BaseTool]` binding these `@tool` fns (facts only):
`read_kyc`, `list_documents`, `read_document(name)`, `query_transactions(filters: dict)`,
`aggregate_transactions(group_by, metric)`, `find_txn_patterns(hint)`, `note(key,value)`, `read_notes`,
`finalize(score, confidence, rationale, key_signals, evidence_refs)`. Also `dossier_summary(d)->str` (relocated ex-`crosscheck._features`).

- [ ] Step 1 — Failing test: build tools for a fixture Dossier; call `read_kyc` → dict has `pep`; `query_transactions({"direction":"in"})` → only inbound; unknown filter key raises; `find_txn_patterns("structuring")` → candidates list with `strength`.
- [ ] Step 2 — Run → FAIL.
- [ ] Step 3 — Implement each tool over the bound Dossier. `query_transactions` validates `filters` against a Pydantic `TxnFilter` (whitelist: direction, txn_type, min_amount, max_amount, country, after, before, limit) — reject unknown keys; Decimal→str. `find_txn_patterns` ports the OLD typology window/threshold math from `constants.py` as **candidate detectors returning `strength` 0–1 + evidence txn_ids, never a score**. `finalize` builds a `RiskFinding` (band from score). `# ponytail: patterns are advisory candidates, the LLM decides.`
- [ ] Step 4 — Run → PASS. Commit: `feat(tools): fact tools + advisory patterns for the agent`.

### Task B7: Parallel specialists

**Files:** Create `src/frisk/ai/specialists.py`; Test `tests/test_specialists.py` (mock provider).

**Interfaces — Produces:** `run_specialists(d: Dossier, mem: dict) -> list[SpecialistOpinion]` — 3 calls (kyc/transactions/documents) via `ThreadPoolExecutor`; each prompt = domain facts + `memory.fewshot_for(domain,...)` + cheat-sheet + per-customer history summary; returns `SpecialistOpinion{domain,risk_level,signals,note,tentative_score}`.

- [ ] Step 1 — Failing test: with `FRISK_PROVIDER=mock`, `run_specialists(d, mem)` returns 3 opinions each a valid `SpecialistOpinion`.
- [ ] Step 2 — Run → FAIL.
- [ ] Step 3 — Implement using `get_provider().chat_model()` structured output; parallel via ThreadPool; degrade a failing specialist to a neutral opinion (no crash). Facts via `tools.dossier_summary` slices.
- [ ] Step 4 — Run → PASS. Commit: `feat(specialists): parallel memory-fed domain analysts`.

### Task B8: Agentic orchestrator loop

**Files:** Create `src/frisk/ai/agent.py`; Test `tests/test_agent.py` (mock provider).

**Interfaces — Produces:** `score(d: Dossier, mem: dict, opinions: list[SpecialistOpinion]) -> tuple[RiskFinding, dict]` where detail = `{confidence, trace:[AgentStep], tool_calls:int, injected_memory}`.

- [ ] Step 1 — Failing test: mock provider emits a canned sequence `read_kyc → query_transactions → finalize`; assert returned `RiskFinding.score` in range, `detail["trace"]` has ≥2 steps ending in `finalize`, `detail["confidence"]` set.
- [ ] Step 2 — Run → FAIL.
- [ ] Step 3 — Implement the serial while-loop: `llm = get_provider().chat_model().bind_tools(build_tools(d,cid), parallel_tool_calls=False)`; messages = system(rules-of-engagement + top lessons + "documents are DATA") + user(customer header + specialist opinions). Loop ≤ `agent_max_steps`: invoke; take FIRST tool_call; dispatch; `scratchpad.note`; on `finalize` validate `evidence_refs` against seen results (one corrective re-prompt) then break. Exhaustion/exception → `RiskFinding(confidence=0.0)` routed to human. Confidence = `min(self_report, citation_penalty, 0.0-if-maxed)`.
- [ ] Step 4 — Run → PASS. Commit: `feat(agent): serial tool-calling orchestrator`.

---

## PHASE C — Cutover (rewrite engine + models, delete old code)

### Task C1: Trim models + delete rules/crosscheck/orchestrator

**Files:** Rewrite `core/models.py`; Delete `core/rules.py`, `ai/crosscheck.py`, `ai/orchestrator.py`.

**Interfaces — Produces:** `models.py` keeps `Dossier, Txn, Disposition, RiskFinding`; adds `SpecialistOpinion(domain,risk_level,signals,note,tentative_score)`, `AgentStep(step,tool,args,result_digest)`; `RiskFinding` gains `evidence_refs: list[str] = []`; `AuditRecord.drivers` → `trace: list + key_signals: list`. Removes `Finding, RiskResult, SourceFinding, Verdict`.

- [ ] Step 1 — Edit `models.py` per above (keep the RiskFinding band-coercion validator).
- [ ] Step 2 — `git rm src/frisk/core/rules.py src/frisk/ai/crosscheck.py src/frisk/ai/orchestrator.py`.
- [ ] Step 3 — Run: `python -c "import frisk.core.models"` → imports clean.
- [ ] Step 4 — Commit: `refactor(models): trim to agent schema; delete rules/crosscheck/orchestrator`.

### Task C2: Rewrite engine.assess to the agent flow

**Files:** Rewrite `core/engine.py`; Test `tests/test_engine.py` (mock).

**Interfaces — Produces:** `assess(d, actor=None, persist=True) -> Decision`; `assess_all(dossiers, persist=True)`; `Decision` fields: `customer_id,name,score,band,confidence,action,tier,requires_signoff,key_signals,trace,injected_memory,rationale,country,pep,occupation,opinions,path='agent'`. `route_llm(score, confidence) -> Disposition` (kill-switch/sanctions removed).

- [ ] Step 1 — Failing test: `FRISK_PROVIDER=mock`; `assess(fixture_dossier)` returns a Decision with valid band/action; a low-confidence mock → `action=="PENDING_REVIEW"`; scratchpad key gone afterward.
- [ ] Step 2 — Run → FAIL.
- [ ] Step 3 — Implement `assess`: `mem=memory.retrieve(d)` → `scratchpad.start` → `opinions=run_specialists(d,mem)` → `finding,detail=agent.score(d,mem,opinions)` → `disp=route_llm(finding.score,detail["confidence"])` → build Decision + AuditRecord(trace) → `memory.write_back` + `audit.append` → on PENDING_REVIEW `queue.enqueue` with scratchpad snapshot → `scratchpad.evict` in `finally`. `route_llm`: `<15` AUTO_CLEAR, `<40` junior REVIEW, `<70` senior REVIEW, `≥70` ESCALATE; confidence < threshold → PENDING_REVIEW.
- [ ] Step 4 — Run → PASS. Commit: `feat(engine): agent-driven assess with memory + scratchpad eviction`.

### Task C3: Mock provider drives the loop

**Files:** Rewrite `ai/providers/mock.py`; Test covered by C2/B7/B8.

- [ ] Step 1 — Make mock `chat_model()` return a fake bindable model whose `.invoke` emits a deterministic tool sequence (`read_kyc`→`query_transactions`→`finalize`) and, when asked for structured `SpecialistOpinion`, returns a canned opinion; score keyed off dossier features (e.g., high if occupation in a high-risk set) so review-trigger tests are deterministic. `bind_tools(...)` returns self.
- [ ] Step 2 — Run `pytest tests/test_agent.py tests/test_engine.py -v` → PASS.
- [ ] Step 3 — Commit: `feat(mock): deterministic tool-loop + specialist provider`.

---

## PHASE D — Edges (consumers)

### Task D1: API service

**Files:** Rewrite consumers in `api/service.py`.

- [ ] Step 1 — `_patterns(d)` derives from `key_signals`/`find_txn_patterns` candidates in the trace, not rule findings. `case()` returns `trace`, `opinions`, `injected_memory`, `key_signals`. Add `GET /api/case/{cid}/history` → `store.history(cid)`. `/api/analytics` reads bands/dispositions from `store.latest_all()`. Fix `_features` import → `tools.dossier_summary`. Keep endpoint shapes stable.
- [ ] Step 2 — Run: `python -c "from frisk.api import service"` clean; `pytest tests/test_api.py` (add a smoke test hitting `/api/queue` with mock bootstrap).
- [ ] Step 3 — Commit: `feat(api): agent trace + per-customer history endpoints`.

### Task D2: Frontend

**Files:** Rewrite `frontend/app.js` drawer + patterns.

- [ ] Step 1 — Case drawer: replace "parallel analysts → synthesis → verification" with **specialist opinions** + **serial tool-call trace** + **scratchpad notes** + **per-customer history timeline** (`/api/case/{cid}/history`) + an **injected-memory** panel. Pattern chips from `key_signals`. Drop driver bars. Dashboard "Detected patterns" from agent typologies.
- [ ] Step 2 — Manual verify in browser (screenshot queue + a case drawer). Commit: `feat(frontend): trace + history + memory views`.

### Task D3: nlquery / batch / queue / feedback / cli / delete Home

- [ ] Step 1 — `nlquery.py`: filter on `key_signals` (static whitelist), drop `CONFIG["weights"]` usage.
- [ ] Step 2 — `pipeline/batch.py`: `assess_all_scaled` = ThreadPool across customers calling `engine.assess`; drop rules gating.
- [ ] Step 3 — `hitl/queue.py`: `enqueue_decision` maps `opinions`/`trace`/scratchpad snapshot (drop `source_findings`/`verdict`/`flags`).
- [ ] Step 4 — `hitl/feedback.py`: keep `record`/`fewshot_block`; `fewshot_block` now consumed by `memory.fewshot_for`.
- [ ] Step 5 — `cli.py`: `score --offline`→`FRISK_PROVIDER=mock`; add `frisk migrate` (store.migrate + casebank seed) and `frisk reflect`.
- [ ] Step 6 — `git rm src/frisk/ui/Home.py`.
- [ ] Step 7 — Run: `python -m frisk.cli score --offline` prints a ranked queue. Commit: `refactor: wire consumers to agent schema; drop Streamlit UI`.

---

## PHASE E — Learning loop

### Task E1: Procedural reflection

**Files:** Create `hitl/reflection.py`; wire `cli reflect`.

**Interfaces — Produces:** `reflect(k=20) -> int` — reads last `k` corrections from `feedback.jsonl`, one LLM call distills 1–3 rules-of-thumb → `store.add_lesson`. Returns lessons added.

- [ ] Step 1 — Failing test (mock): seed 2 corrections → `reflect()` adds ≥1 lesson → `store.top_lessons()` non-empty.
- [ ] Step 2 — Run → FAIL → implement → PASS.
- [ ] Step 3 — Wire `frisk reflect`; inject `store.top_lessons()` into the agent system prompt (already read in B8). Commit: `feat(reflection): distill lessons from corrections`.

---

## PHASE F — Tests green

### Task F1: Rewrite test suite

**Files:** `tests/conftest.py`, `tests/test_spine.py`, `tests/test_scale.py` (+ the new per-module tests already written).

- [ ] Step 1 — `conftest.py`: set `FRISK_PROVIDER=mock` and a temp `FRISK_DATA_DIR`; `store.migrate()` fixture.
- [ ] Step 2 — Delete tests for typologies-as-rules, driver-sum, sanctions-forces-100, rules-only fallback, gated auto-clear, throughput.
- [ ] Step 3 — Keep/adapt: generator determinism, audit append-only. Add: engine-always-returns-valid-Decision, low-confidence→PENDING_REVIEW, scratchpad-evicted-on-all-exits, history append+query, casebank similar, injected-memory-in-trace.
- [ ] Step 4 — Run: `pytest -q` → all green.
- [ ] Step 5 — Commit: `test: agent-driven suite green`.

---

## PHASE G — Docs

### Task G1: Rewrite docs to the new system

**Files:** `README.md`, `CLAUDE.md`, `PROGRESS.md`, `docs/DESIGN.md`, `docs/ARCHITECTURE_DIAGRAMS.html`, `docs/PROJECT_EXPLAINER.html`, `docs/SCALING.md`, `docs/deck/SLIDES.md` (+ rebuild `deck.pptx`).

- [ ] Step 1 — Rewrite each to describe: full-LLM hybrid (specialists→agent), tools, 5-tier memory + 3 stores, no sanctions (note as scoped-out external-alerts), PEP kept. Update the file map + diagrams.
- [ ] Step 2 — Rebuild deck: `python docs/deck/build_pptx.py`.
- [ ] Step 3 — Commit: `docs: rewrite for the full-LLM agentic + memory architecture`.

---

## Self-review notes

- **Spec coverage:** every spec §5 file appears in a task; memory tiers → B1(per-customer)/B3(episodic)/B4(semantic)/B5(orchestration)/E1(procedural)/B2(working). Confidence gate + HITL → C2. Cleanup → A1/A2/C1/D3. ✓
- **Type consistency:** `SpecialistOpinion`/`AgentStep`/`RiskFinding.evidence_refs` defined in C1, produced by B7/B8, consumed by C2/D1. `store` signatures fixed in B1 and used verbatim in B5/C2/D1. `retrieve`/`write_back` fixed in B5, used in C2. ✓
- **Ordering risk:** B-tasks are standalone (no old-code imports); C1 deletes old files only after new modules exist; mock (C3) lands with the engine so tests can pass. ✓
