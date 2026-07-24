# Financial Risk Signal Aggregator — Project Memory

> HyperVerge take-home POC. **This file is the entry point for any Claude session on this project.**
> Resuming (e.g. after `/clear`)? Read this file FIRST, then `PROGRESS.md`, then the relevant `docs/` file.

## What this project is

An AI prototype that ingests fragmented financial data (KYC, transactions, sanctions/PEP, adverse media)
for ~20 synthetic customers and produces a **prioritised, risk-scored analyst triage queue** with
per-finding rationale. Domain: AML / financial-crime compliance. Deliverables: working Streamlit demo
(≤3-min recording) + 5-slide deck + README. Deadline: 2026-07-25. Pro-code: Python, pandas, pydantic v2,
Streamlit, instructor. LLM cross-check is provider-configurable in `config.py` — default
**NVIDIA Nemotron-3-Ultra-550B** (OpenAI-compatible endpoint), with Gemini and Claude as alternates.

**North star:** a "never-fails" engine — deterministic rules are the auditable **source of truth**, the LLM
is an **advisory, confidence-gated cross-check**, and there is a **rules-only fallback** so the engine never
returns nothing. Feeds a confidence-gated **Human-in-the-Loop** triage (auto-clear / review / escalate),
with additive-driver explainability and an append-only audit trail.

## Files — what to read for what

| File | Purpose |
|------|---------|
| `CLAUDE.md` (this) | Project overview + file map + working rules. Read FIRST on resume. |
| `PROGRESS.md` | Live status: phase, status board, next actions, decisions, changelog. Read SECOND. |
| `docs/DESIGN.md` | Product design & architecture (data flow, scoring, HITL, audit). |
| `docs/research/RESEARCH_BRIEF.md` | Deep research: production patterns, code shapes, library choices, pitfalls. |
| `bugs/BUGS.md` | Master bug log. Log EVERY bug here. Per-feature files: `bugs/<feature>.md`. |
| `data/generate.py` | Seeded synthetic 20-profile generator (+ `__main__` self-check). |
| `data/dossiers.json` | Frozen deterministic dataset the app loads. |
| `src/config.py` | THE tuning knob — all weights, floors, windows, band cutoffs, routing thresholds. |
| `src/models.py` | Shared schemas (Dossier, Txn, Finding, RiskResult, RiskFinding, Disposition, AuditRecord). |
| `src/rules.py` | Deterministic engine: FACTOR_RULES + TYPOLOGY_RULES + `score_customer()`. |
| `src/llm.py` | Never-fails LLM boundary: multi-provider (nvidia/gemini/anthropic) + cache + retry/backoff + fallback + LangSmith `@traceable`. |
| `src/orchestrator.py` | Multi-step LangGraph graph: 3 parallel domain analysts → synthesize → verify → finalize. |
| `src/engine.py` | Orchestrator: rules → llm/graph → reconcile(confidence) → route() → Decision + AuditRecord. |
| `src/pipeline.py` | Scale layer: parallel batch scoring (ThreadPool) + LLM gating (MED-band only). |
| `src/store.py` | SQLite decisions store — scalable read path the UI/API query (→ Postgres). |
| `src/audit.py` | Append-only decision store (sqlite3/JSONL). |
| `src/nlquery.py` | NL → whitelisted Pydantic filter spec → pandas mask (stretch). |
| `docs/SCALING.md` | How to run at 10k+/day: gating, parallelism, caching, read store, infra diagram. |
| `src/app/` | Streamlit UI (Queue / Case detail / Audit). |
| `tests/` | Golden tests (one per typology + override + fallback + driver-sum). |
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

- Overrides/vetoes evaluated BEFORE the weighted sum (a hard signal must never be averaged away).
- The LLM never writes the score arithmetic; the rules score is the auditable number.
- The engine never raises to the caller — degrade to rules-only, never blank.
- Rules-only / degraded path never silently auto-clears; it caps confidence and forces ≥ review.
- `Decimal` for money; no `datetime.now()`/random inside rule predicates; deterministic dict/seed order.
- Audit store is append-only; every finding carries `evidence`; driver contributions sum to the score.
- NL query never `eval`/`df.query()` on model text — only a whitelisted filter spec.
- When wiring a library (instructor, anthropic, streamlit), fetch current docs via Context7 first.

## Status

See `PROGRESS.md` for the live board.
