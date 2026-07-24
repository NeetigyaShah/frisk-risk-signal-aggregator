# PROGRESS — Financial Risk Signal Aggregator

**Last updated:** 2026-07-24 · **Deadline:** 2026-07-25
**Overview:** see `CLAUDE.md`. **Design:** `docs/DESIGN.md`. **Research:** `docs/research/RESEARCH_BRIEF.md`.

## Current phase
**COMPLETE** — all phases done and verified. Remaining human step: record the ≤3-min demo
(script in `docs/DEMO_SCRIPT.md`) and submit.

## Status board
- [x] Brainstorm + agreed design
- [x] Deep research brief (ultracode Workflow) → `docs/research/RESEARCH_BRIEF.md`
- [x] Approved plan (`~/.claude/plans/ok-do-so-as-shimmering-pizza.md`)
- [x] Phase 0: persistence infra (CLAUDE.md, PROGRESS.md, DESIGN.md, bugs/, requirements.txt)
- [x] Phase 1 spine: `config.py` → `models.py` → `data/generate.py` → `rules.py` → `llm.py` → `engine.py` + `audit.py`
- [x] Phase 1: golden tests (12 pass)
- [x] Phase 2 leaves: Streamlit UI (verified in-browser) · nlquery · README + 5-slide deck (deck.pptx)
- [x] Phase 3: e2e verified (generator, tests, engine, self-checks, UI screenshots)
- [ ] Human: record ≤3-min demo (see `docs/DEMO_SCRIPT.md`), submit deck + README + demo

## Verified so far
- Generator deterministic; 20 dossiers; bands aligned to expectations.
- Rules drivers sum to score; overrides force HIGH/ESCALATE.
- Engine dispositions: 5 AUTO_CLEAR / 9 REVIEW / 6 ESCALATE (offline sim path).
- Never-fails: no-key + raising-client both fall back to a valid finding.
- Kill-switch and missing-data never auto-clear.

## Next actions
1. Build `src/nlquery.py` (NL → whitelisted filter spec).
2. Build `src/app/` Streamlit UI (Queue / Case detail / Audit).
3. README + 5-slide deck (parallel subagent).
4. Phase 3: e2e verify + demo.

## Key design decisions (see DESIGN.md / RESEARCH_BRIEF.md for full)
- Multi-source dossier per person (5 data families), not per-transaction-row.
- Deterministic rules = source of truth; LLM = advisory confidence-gated cross-check; rules-only fallback.
- Order: overrides/vetoes → weighted 0–100 → bands (0–35 low / 36–65 med / 66–100 high).
- HITL routing: kill-switch first, then auto-clear <15 / junior <40 / senior <70 / escalate ≥70; rules-only forces ≥ junior.
- `confidence = 1 − |rules−llm|/100`; maker-checker signoff on ESCALATE.
- Additive drivers sum to score (hand-rolled SHAP, no shap/LIME).
- Append-only `AuditRecord` per decision (clears + escalates) with sha256 input fingerprint.
- Single `config.py` dict = the tuning knob; `Decimal` money; seeded determinism.
- Stack: pandas, numpy, Faker, pydantic v2, instructor, anthropic (temp 0), streamlit ≥1.36, pytest.

## Changelog
- 2026-07-24: Git initialised; dirs + .gitignore created.
- 2026-07-24: Ultracode research Workflow (6 agents + synthesis) completed; brief saved.
- 2026-07-24: Plan approved; task list created (#1–#11).
- 2026-07-24: Phase 0 started — RESEARCH_BRIEF.md, CLAUDE.md, PROGRESS.md written.
- 2026-07-24: Phase 1 spine built + calibrated (config, models, generate, rules, llm, engine, audit).
- 2026-07-24: 12 golden tests pass. Phase 1 complete. Starting Phase 2.
- 2026-07-24: Phase 2 — nlquery (safe whitelisted filter), Streamlit UI (Queue/Case/Audit) verified in-browser, README + 5-slide deck (deck.pptx) via subagent.
- 2026-07-24: Phase 3 — full e2e verification green (5/9/6 dispositions); screenshots + DEMO_SCRIPT.md. BUILD COMPLETE.
- 2026-07-24: LLM cross-check made provider-configurable (nvidia|gemini|anthropic). Google free tier rate-limited (429s);
  switched default to **NVIDIA Nemotron-3-Ultra-550B** via instructor JSON (OpenAI-compatible endpoint). Disk cache
  (data/llm_cache.json) warmed -> instant. Added docs/PROJECT_EXPLAINER.html (Mermaid diagrams). API keys in
  .env (gitignored) — ROTATE the pasted Gemini + NVIDIA keys.
- 2026-07-24: MULTI-STEP orchestration — replaced the single LLM call with a 5-node **LangGraph** graph
  (`orchestrator.py`): 3 parallel domain analysts → synthesize → verify (chain-of-verification) → finalize;
  each node degrades independently; cascade graph→single→rules-only. RiskFinding.band now derived from score
  (accepts any model vocabulary). SCALE layer: `pipeline.py` (parallel batch + MED-band gating), `store.py`
  (SQLite decisions read store), LangSmith `@traceable` observability, `docs/SCALING.md` (10k/day infra).
- 2026-07-24: Model tuning — thinking disabled (config `nvidia_extra_body`), tried deepseek-v4-flash
  (faster ~12s but free endpoint throws 503 ResourceExhausted under load). Model + thinking are config knobs.
- 2026-07-24: RESTRUCTURED into installable **`frisk/` package** (src-layout, pyproject.toml, `frisk` CLI) per
  production patterns in the research notes: `config/` (pydantic-settings + constants + paths) · `core/` ·
  `ai/` (providers ABC+factory+mock, crosscheck, orchestrator) · `data/` · `pipeline/` · `query/` ·
  `observability/` · `ui/`. All imports updated. Run: `streamlit run src/frisk/ui/Home.py`.
- 2026-07-24: PIVOT to **LLM-only scoring + confidence-gated Human-in-the-Loop** (`engine_mode=llm`):
  * Data regenerated as REAL per-customer folders (`data/customers/CUST_xxx/`) mixing STRUCTURED
    (kyc.json, account.json, transactions.csv, screening.json) + UNSTRUCTURED (id_document.txt OCR,
    rm_notes.txt, adverse_media_*.txt, correspondence.txt). `loaders.load_all()` + `parse_pasted()`.
  * The LangGraph analysts now READ the unstructured docs. LLM score decides; composite confidence =
    min(self-report, node-agreement, verifier-consistency). Low confidence / dead LLM → PENDING_REVIEW.
  * REAL Redis broker (`docker run -d --name frisk-redis -p 6379:6379 redis:7-alpine`) via `frisk/hitl/queue.py`
    (in-memory fallback). `frisk/hitl/feedback.py` = human corrections → few-shot examples in the synthesis prompt.
  * Streamlit **Human Review Queue** page: reviewer sets correct score/band/action + note → resolve + teach.
  * Sanctions kill-switch kept as the one hard rail. 16 tests pass.
- 2026-07-24: LLM provider → **OpenRouter** (`deepseek/deepseek-v4-flash`), provider routing prefers **Baidu Qianfan**
  (`openrouter_extra_body.provider.order=[baidu,alibaba,deepinfra,fireworks]`, fallbacks on). Fast + reliable
  (single call ~2s; graph ~11-38s/customer). Verified live: CUST_000→auto-clear(0.93), CUST_018→escalate,
  CUST_014/006→low-confidence(0.30)→PENDING_REVIEW human queue. `OpenRouterProvider` added to the boundary.
  Cache warming via OpenRouter. `OPENROUTER_API_KEY` in .env (ROTATE — pasted in chat).
- 2026-07-24: **Custom frontend + FastAPI backend service** replaces Streamlit. `frisk/api/service.py`
  (REST over the engine) serves `frontend/` (vanilla JS + Tailwind CDN, no build). Views: Dashboard
  (ranked queue w/ gauges, confidence bars, pattern chips) · Human Review Queue (analyst breakdown +
  teach form) · Ingest/Upload · Audit Trail · case slide-over drawer. Run: `frisk serve`.
- 2026-07-24: **Batch parallel scoring** (Ingest page) + **dashboard charts**. `POST /api/ingest/batch {ids}`
  starts a background ThreadPool job (bounded to `min(workers,6)` — 40 raw-parallel = ~200 concurrent
  OpenRouter calls = 429s), `GET /api/ingest/batch/{job_id}` polled by the UI for a live progress bar +
  streaming result cards; low-confidence results auto-drop into the Human Review queue. New `GET /api/analytics`
  feeds three Chart.js charts (risk-band bars · disposition doughnut · detected-pattern frequency). UI:
  multi-select sample list + "Select all" + "Score selected (N) in parallel". Verified live (2 profiles →
  progress→complete→2 routed to review) + functionally with mock (analytics + 3-profile batch).
- 2026-07-24: Made the AML typologies **visible in-app + docs**. `frontend/app.js`: `PATTERN_DEFS` plain-language
  definitions surface as a legend under the dashboard charts, an info tooltip on the Detected-patterns chart,
  hover tooltips on pattern chips, and per-pattern meaning in the case drawer. Confirmed usage is real: `score_customer(d)`
  runs the 4 temporal detectors on EVERY customer (engine.py:104 to 154), and the LLM transactions-analyst is independently
  prompted to hunt the same four (orchestrator.py:87). Mirrored full definitions into `docs/PROJECT_EXPLAINER.html`
  (typology table) and `docs/deck/SLIDES.md` (rebuilt deck.pptx).
- 2026-07-24: New **`docs/ARCHITECTURE_DIAGRAMS.html`** — dark brand-themed Mermaid diagram deck (6 sections):
  end-to-end flow, data input/which-analyst-reads-what, **ingestion step-by-step** (per-file parser → typed output
  tables + the exact fact-strings each LLM sees), the 5-call LangGraph orchestration, the never-fails cascade, and the
  confidence-gate + teach-the-model HITL loop. Every node traced to real code; verified rendering in-browser (no Mermaid errors).
