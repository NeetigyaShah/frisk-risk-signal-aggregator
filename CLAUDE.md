# Financial Risk Signal Aggregator — Project Memory

> HyperVerge take-home POC. **This file is the entry point for any Claude session on this project.**
> Resuming (e.g. after `/clear`)? Read this file FIRST, then `PROGRESS.md`, then the relevant `docs/` file.

## What this project is

An AI prototype that ingests fragmented financial data (KYC, account, transactions, external-alert facts
incl. PEP) for ~20 synthetic customers and produces a **prioritised, risk-scored analyst triage queue** with
per-decision rationale + a full investigation trace. Domain: AML / financial-crime compliance. Deliverables:
working demo (≤3-min recording) + 5-slide deck + README. Pro-code: Python, pydantic v2, LangChain (tool-calling
over OpenRouter), FastAPI + a custom vanilla-JS frontend. LLM is provider-configurable in `config/settings.py`
— default **OpenRouter → `deepseek/deepseek-v4-flash`** (prefers **Baidu Qianfan** via provider routing),
with NVIDIA / Gemini / Claude / mock alternates. Keys in `.env` (gitignored): `OPENROUTER_API_KEY` etc.

**North star (FULLY LLM + AGENTIC — no deterministic scoring).** Per customer: retrieve layered memory →
run **3 parallel memory-fed specialists** (KYC · transactions · documents) → hand their opinions + the
original docs + tools to **one agentic orchestrator** (a serial tool-calling ReAct loop) that investigates
and emits a `RiskFinding` (score/band/confidence/rationale/evidence). A **confidence gate** routes low-confidence
cases to a **real Redis review queue** → the **Human Review panel**; the correction is stored as a
**human-verified episode** and distilled into **lessons** that feed back into future prompts. The ordered
**tool-call trace is the audit record**. There is NO deterministic rules engine, NO sanctions rail, NO
never-fails fallback (the LLM API is assumed reliable in-house infra); a bounded loop / exception still
resolves every case to a human.

**Layered memory (5 tiers, 3 stores).** Working = Redis scratchpad (evicted on every exit) · Per-customer =
relational history (SQLite `assessments`) · Episodic = case-bank (feature-match now, vector-pluggable) ·
Semantic = reference cheat-sheets (`data/reference/`) · Procedural = `lessons` distilled from corrections.

> Spec: `docs/superpowers/specs/2026-07-24-fullllm-agentic-memory-design.md` · Plan:
> `docs/superpowers/plans/2026-07-24-fullllm-agentic-memory.md`. Sanctions + adverse-media were scoped OUT
> (not in the brief — it says only "external alerts"); PEP kept.

## Files — what to read for what

| File | Purpose |
|------|---------|
| `CLAUDE.md` (this) | Project overview + file map + working rules. Read FIRST on resume. |
| `PROGRESS.md` | Live status: phase, status board, next actions, decisions, changelog. Read SECOND. |
| `docs/DESIGN.md` | Product design & architecture (data flow, scoring, HITL, audit). |
| `docs/research/RESEARCH_BRIEF.md` | Deep research: production patterns, code shapes, library choices, pitfalls. |
| `bugs/BUGS.md` | Master bug log. Log EVERY bug here. Per-feature files: `bugs/<feature>.md`. |
| `pyproject.toml` | Installable package (`pip install -e .`), `frisk` console entry, optional extras (llm/ui/observability/dev). |
| `src/frisk/paths.py` | Central filesystem paths (data/db) — overridable via `FRISK_DATA_DIR`. |
| `src/frisk/config/constants.py` | Disposition policy — band cutoffs + HITL routing thresholds + seed (deterministic scoring is GONE). |
| `src/frisk/config/settings.py` | pydantic-settings `Settings` — env-bound provider/agent/memory knobs + API keys (`FRISK_*` / `*_API_KEY`). |
| `src/frisk/config/__init__.py` | Assembles `CONFIG` (domain + env) + `band_for`/`BAND_LABEL`. |
| `src/frisk/core/models.py` | Shared schemas: Dossier, Txn, RiskFinding, **SpecialistOpinion**, **AgentStep**, Disposition, AuditRecord. |
| `src/frisk/core/engine.py` | Orchestrator: retrieve memory → specialists → **agent.score** → `route_llm` (confidence-gate) → Decision + AuditRecord; evicts scratchpad. |
| `src/frisk/ai/agent.py` | **The agentic orchestrator** — serial tool-calling ReAct loop; trace-as-audit; citation check; bounded→human. |
| `src/frisk/ai/specialists.py` | 3 parallel memory-fed domain analysts (KYC/transactions/documents) → `SpecialistOpinion`. |
| `src/frisk/ai/tools.py` | Orchestrator fact-tools bound to a Dossier + advisory typology candidates (`find_txn_patterns`) + `dossier_summary`. |
| `src/frisk/ai/memory.py` | Layered-memory orchestration: `retrieve` / `fewshot_for` / cheat-sheets / `write_back` + injected-memory log. |
| `src/frisk/ai/providers/` | Provider boundary: `base.py` (ABC), `factory.py` (`get_provider`), `openrouter/nvidia/gemini/anthropic/mock.py`. `mock` drives the tool loop offline. |
| `src/frisk/data/generate.py` | Seeded generator → `data/customers/CUST_xxx/` folders (structured JSON/CSV + unstructured TXT). PEP-only screening. |
| `src/frisk/data/loaders.py` | Ingestion: read a customer folder → Dossier (structured fields + `.documents`); `parse_pasted()`. |
| `src/frisk/data/store.py` | **Relational store** (SQLite→Postgres): `customers` / `assessments` (per-customer history) / `lessons`; `latest_all`. |
| `src/frisk/data/casebank.py` | **Episodic case-bank** — `add`/`similar` feature-match retrieval (vector-pluggable). |
| `src/frisk/data/reference/` | **Semantic** cheat-sheets (`typologies.md`, `high_risk.md`) injected into specialists. |
| `src/frisk/data/audit.py` | Append-only decision store (JSONL) — records the tool-call trace + key_signals. |
| `src/frisk/hitl/redis_conn.py` | One shared Redis client (+ in-memory fallback) reused by the queue + scratchpad. |
| `src/frisk/hitl/scratchpad.py` | **Working memory** — per-customer Redis scratchpad `start/note/read/evict` (evicted on every exit). |
| `src/frisk/hitl/queue.py` | Real **Redis** review message queue (producer/consumer) + in-memory fallback. Needs `frisk-redis` container. |
| `src/frisk/hitl/feedback.py` | Human corrections → few-shot examples (teach-the-model loop) + input to reflection. |
| `src/frisk/hitl/reflection.py` | **Procedural memory** — distil "lessons learned" from corrections → `lessons` table (`frisk reflect`). |
| `src/frisk/pipeline/batch.py` | Scale layer: parallel batch scoring ACROSS customers (each customer specialists-parallel + orchestrator-serial). |
| `src/frisk/query/nlquery.py` | NL → whitelisted Pydantic filter spec → mask over `key_signals` (never eval/df.query). |
| `src/frisk/observability/telemetry.py` | LangSmith status/wiring (opt-in). |
| `src/frisk/cli.py` | `frisk generate` / `samples` / `migrate` / `reflect` / `serve` / `score [--offline]` / `warm`. |
| `src/frisk/api/service.py` | **FastAPI backend** — REST over the engine + serves `frontend/`. Endpoints: stats/queue/case/samples/review/audit/**analytics**; `POST /api/ingest`, `/api/ingest/files`, **`/api/ingest/batch`** (+ `GET .../batch/{job_id}` poll). Run: `frisk serve`. |
| `frontend/` | Custom SPA (vanilla JS + Tailwind + Chart.js CDN, no build): `index.html`, `app.js`, `styles.css`. Dashboard (ranked queue + charts) · Review Queue · Ingest (multi-select **batch parallel scoring**) · Audit · case drawer (**specialist opinions + tool-call trace + memory + history**). |
| `docs/SCALING.md` | How to run at 10k+/day: gating, parallelism, caching, read store, infra diagram. |
| `docs/PROJECT_EXPLAINER.html` | Product-level visual walkthrough (Mermaid diagrams). |
| `docs/ARCHITECTURE.html` | Engineering codebase walkthrough: structure, ingestion pipeline, read/translate, inference, prompts, UI. |
| `docs/ARCHITECTURE_DIAGRAMS.html` | **Beautiful branded explainer of the CURRENT agentic architecture**: end-to-end flow, data input, specialists→orchestrator topology, the agent tool-loop, the **5-tier layered memory**, confidence-gate + HITL teach loop, and a before/after table. |
| `tests/` | Golden tests (mock-driven): engine-always-valid, low-conf→review, scratchpad eviction, history, episodic recall, injected-memory, audit, specialists, nlquery safety, batch. |
| `README.md` | One-page submission README (setup, approach, worked example). |
| `docs/deck/SLIDES.md` · `deck.pptx` | 5-slide submission deck (+ `build_pptx.py` renderer). |
| `docs/DEMO_SCRIPT.md` | 3-minute demo recording script. |
| `docs/screenshots/` | UI screenshots (queue, case, audit). |
| `~/.claude/plans/ok-do-so-as-shimmering-pizza.md` | The approved implementation plan. |

## Working rules (STRICT — persistence behaviour)

1. **After completing EVERY feature/meaningful step** → update `PROGRESS.md`: tick it done, note what's next,
   add a dated changelog line.
2. **Save session-worthy context** (decisions, gotchas, links) into the right `docs/` file so a fresh
   session after `/clear` loses nothing.
3. **Every bug** → `bugs/BUGS.md` (id, date, symptom, root cause, fix, status). When a feature accrues
   several bugs, split into `bugs/<feature>.md`.
4. **Keep THIS file current** — if structure, key decisions, or the file map change, edit `CLAUDE.md` yourself.
5. **Feature work happens in isolated git worktrees**, merged back only after its check runs green.
   (Spine modules are single-owner/sequential; only the Phase-2 leaves fan out.)

## Engineering invariants (do not violate)

- **No deterministic scoring** — the LLM (agent) produces the score; there is no rules engine, no sanctions rail.
- The orchestrator is **serial** (`parallel_tool_calls=False`); specialists run in parallel; `temperature=0`.
- The engine **always returns a valid Decision**: bounded loop / exception → route to human at confidence 0 (never blank).
- The **scratchpad is evicted on every exit path** (complete / handoff / exception) — no working memory leaks.
- **Audit = the ordered tool-call trace** + key_signals + evidence_refs; append-only JSONL.
- **Episodic few-shot draws from human-verified cases** (avoid the echo-chamber of learning from own outputs).
- `Decimal` for money; deterministic seed order; log which memory was injected (reproducibility).
- Tools return FACTS, never verdicts; `find_txn_patterns` yields advisory **candidates** (strength), not scores.
- NL query never `eval`/`df.query()` on model text — only a whitelisted filter spec over `key_signals`.
- Offline/tests use the **mock provider** (drives the tool loop), not a rules bypass.
- When wiring a library (LangChain, instructor, FastAPI), fetch current docs via Context7 first.

## Status

See `PROGRESS.md` for the live board.
