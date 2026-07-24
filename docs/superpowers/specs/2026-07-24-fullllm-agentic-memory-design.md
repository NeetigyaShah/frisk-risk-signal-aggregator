# Spec — Full-LLM Agentic Scorer with Layered Memory

**Date:** 2026-07-24 · **Status:** approved, implementing · **Branch:** `fullllm-agentic-rebuild`

## 1. Goal

Rebuild frisk from *deterministic-rules + advisory-LLM* into a **fully-LLM, agentic** risk scorer with a
**layered memory system**. No deterministic scoring survives. The LLM investigates and judges each customer;
a human reviews low-confidence cases and teaches the system; memory makes it better over time.

## 2. Decisions locked (from brainstorming)

- **Topology = Hybrid (Option C):** parallel **memory-fed specialists** (KYC · transactions · documents) →
  one **agentic orchestrator** (serial tool-calling loop) that receives the specialists' opinions **plus the
  original dossier plus tools** and emits the final judgement. Parallel speed for the gather; agentic depth for the decision.
- **No deterministic rules** — delete `score_customer`, factor rules, python typology detectors.
- **Sanctions removed entirely** — not in the brief (brief says only "external alerts / external data sources").
  No kill-switch, no veto, no sanctions data. Mention as "scoped out, could extend" in the deck.
- **Adverse-media removed** — JSON field + the `adverse_media_*.txt` documents.
- **PEP kept** — a single `pep: bool` fact the LLM reads.
- **No never-fails / rules-only fallback** — LLM API assumed reliable in-house infra. (Keep only bounded-loop /
  exception → route-to-human as loop safety, never a rules fallback.)
- **Serial within the orchestrator** (`parallel_tool_calls=False`), specialists run in parallel.
- **Provider unchanged:** OpenRouter `deepseek/deepseek-v4-flash` behind the existing `ai/providers/` seam.

## 3. Memory system — 5 tiers across 3 stores

| Tier | Content | Store | Access |
|------|---------|-------|--------|
| **Working** | orchestrator's run notes | **Redis** scratchpad `frisk:scratch:{cid}` | write/read, evicted on exit |
| **Per-customer** | this customer's assessment history | **Relational** (SQLite→Postgres) | `WHERE customer_id=? ORDER BY ts` |
| **Episodic** | similar past cases + human corrections | **Vector/RAG** (SQL feature-match now → sqlite-vec later) | top-k by similarity |
| **Semantic** | typology defs, high-risk lists, policy | **static reference files** | injected wholesale (small) |
| **Procedural** | "lessons learned" rules-of-thumb | **`lessons` table** (relational) | top-N, distilled from corrections |

**Physical stores:** Redis (working) · one relational DB (per-customer + lessons) · one episodic case-bank
(SQL feature-match first; pluggable to sqlite-vec/Redis-vector embeddings later).

### Relational schema (extends `data/store.py`, append-only history)
```
customers   ( customer_id PK, name, entity_type, country, occupation, pep, first_seen )
assessments ( id PK, customer_id FK, ts, score, band, confidence, disposition,
              key_signals JSON, rationale, trace_ref, human_verified BOOL, corrected_score )
lessons     ( id PK, text, from_corrections JSON, created_ts, weight )
```
Per-customer memory = last N `assessments` rows for the customer (detect *change*).
Latest-per-customer view feeds the dashboard queue.

### The one loop
```
new customer → RETRIEVE (per-customer history SQL · similar cases · semantic cheat-sheet · top lessons)
             → ASSEMBLE into specialist + orchestrator prompts (log which memories were injected)
             → SCORE (parallel specialists → agentic orchestrator)
             → WRITE-BACK (append assessment · add case-card to case-bank · human correction ⇒ human_verified + reflection)
```

## 4. Scoring flow (per customer)

1. `memory.retrieve(dossier)` → `{history, similar_cases, lessons}` (+ semantic cheat-sheets are static).
2. **Specialists (parallel, one LLM call each, no tools):** KYC / transactions / documents. Each prompt =
   domain facts + episodic few-shot (its domain, human-verified) + semantic cheat-sheet + per-customer summary.
   Returns `{domain, risk_level, signals[], note, tentative_score}` (Pydantic).
3. **Orchestrator (serial agentic loop, `max_steps≈12`):** gets the 3 opinions + customer header + top lessons +
   tools. Investigates via tools, notes to the Redis scratchpad, then calls `finalize`.
   - Tools (facts only): `read_kyc` (incl. `pep`) · `list_documents` · `read_document(name)` ·
     `query_transactions(filters)` (whitelisted Pydantic spec, never eval) · `aggregate_transactions(group_by,metric)` ·
     `find_txn_patterns(hint)` (**advisory** typology candidates + strength 0–1, not rules) ·
     `note`/`read_notes` · `finalize(score,band,confidence,rationale,key_signals,evidence_refs)` (terminal; band re-derived from score).
   - Guards (loop hygiene, not scoring rules): finalize refused until it has looked at the case;
     evidence_refs citation-checked against tool results (one corrective re-prompt); `max_steps`/exception → route to human at confidence 0.
4. **Confidence gate:** `confidence < CONFIG.confidence_threshold` → `PENDING_REVIEW` → Redis review queue
   (snapshot of scratchpad + tool trace attached). Else auto-dispose by band.
5. **Write-back + evict scratchpad** on every terminal path (complete / handoff / exception).
6. **Human review** sets the correct score → stored as `human_verified` episode + feeds procedural reflection + few-shot.

**Audit = the ordered tool-call trace + injected-memory log + evidence_refs** (append-only JSONL), replacing driver-sum.

## 5. Files

**New**
- `src/frisk/ai/agent.py` — orchestrator agentic loop; `score(d, memory) -> (RiskFinding, detail{confidence,trace,tools,injected_memory})`.
- `src/frisk/ai/specialists.py` — the 3 parallel memory-fed specialist calls.
- `src/frisk/ai/tools.py` — orchestrator tool suite (fact-returning), bound to the Dossier.
- `src/frisk/ai/memory.py` — retrieve/assemble (per-customer + episodic + semantic + procedural) + write-back + injected-memory logging.
- `src/frisk/data/casebank.py` — episodic case-bank: `add(case_card, meta)`, `similar(features, k)`; SQL feature-match now, pluggable vector backend later.
- `src/frisk/hitl/scratchpad.py` — Redis working memory: `start/note/read/set_stage/evict`; shared `_redis()` helper.
- `src/frisk/hitl/reflection.py` — periodic LLM reflection over recent human corrections → `lessons` rows.

**Rewrite**
- `core/engine.py` — `assess()` = retrieve → specialists → agent → confidence-gate → write-back → evict. Drop rules/crosscheck/hybrid/reconcile/route/kill-switch. `Decision` drops drivers/flags/llm_score; adds key_signals/trace/injected_memory; `path='agent'`.
- `core/models.py` — drop Finding/RiskResult/SourceFinding/Verdict; keep Dossier/Txn/Disposition/RiskFinding (band-coercion validator). Add SpecialistOpinion, AgentStep, and evidence_refs on RiskFinding. AuditRecord.drivers → trace/key_signals.
- `data/store.py` — relational history schema above (customers/assessments/lessons) + latest-per-customer view; `upsert`→`append`.
- `config/constants.py` — delete weights/floors/typology-cash-velocity thresholds/hard_escalate/agreement_tol/degraded_cap. Keep band cutoffs/band_for/BAND_LABEL, routing thresholds, seed; `ruleset_version`→`policy_version`. High-risk country/occupation lists move to a **semantic reference file** surfaced to specialists (reference, not scoring).
- `config/settings.py` / `config/__init__.py` — drop engine_mode/multi_step/crosscheck_policy/gated_confidence/LLM_MODE-off; add `agent_max_steps`, `scratchpad_ttl_s`, `memory_topk`.
- `api/service.py` — `_patterns` from agent key_signals/trace; case()/analytics() read trace + key_signals + specialist opinions + injected_memory; add `/api/case/{cid}/history` (per-customer timeline). Endpoint shapes stable so frontend keeps working.
- `frontend/app.js` — drawer: serial tool-call **trace** + scratchpad notes + specialist opinions + **per-customer history timeline** + injected-memory panel; "Detected patterns" from agent typologies; drop driver bars.
- `query/nlquery.py` — filter on agent `key_signals` (static whitelist), not rule codes.
- `pipeline/batch.py` — parallel **across** customers (each customer still specialists-parallel + serial orchestrator); drop rules gating.
- `hitl/queue.py` — extract `_redis()` into `hitl/redis_conn.py`; enqueue maps agent trace/opinions/scratchpad snapshot.
- `hitl/feedback.py` — corrections now feed specialists' few-shot + reflection; keep record()/fewshot_block().
- `ai/providers/mock.py` — drive the tool loop deterministically (canned tool sequence → finalize); emit specialist opinions.
- `data/generate.py` — remove sanctions + adverse-media; keep `pep`; re-tune the review-trigger samples around KYC gaps / typologies / PEP / geography; seed the case-bank with the 20 labelled dossiers.
- `cli.py` — `score --offline`→mock provider; `warm`; add `frisk reflect` (run reflection) and `frisk migrate` (build/upgrade DB); help text.
- `tests/*` — mock-driven; delete rules/typology/driver-sum/fallback tests; add agent-always-valid, low-confidence→review, scratchpad eviction, history append+query, episodic retrieval, memory-injection-logged.

**Delete**
- `core/rules.py`, `ai/crosscheck.py`, `ai/orchestrator.py` (replaced by agent.py+specialists.py), `ui/Home.py` (dead Streamlit UI), old `data/dossiers.json` back-compat path.

**Keep** — `data/loaders.py`, `data/audit.py`, `data/paths.py`, `observability/telemetry.py`, alt providers, `frontend/{index.html,styles.css}`.

## 6. Cleanup (past mistakes / dead weight)

Remove: deterministic engine, sanctions, adverse-media, never-fails cascade, hybrid/rules-gated modes, Streamlit UI,
`LLM_MODE=off` (replaced by mock provider), `dossiers.json` legacy loader, unused constants. Rewrite the docs
(`DESIGN.md`, `ARCHITECTURE*.html`, `PROJECT_EXPLAINER.html`, `SCALING.md`, `deck/SLIDES.md`, `README.md`, `CLAUDE.md`,
`PROGRESS.md`) **after** the code is green — they currently describe the rules engine + 5-step parallel graph.

## 7. Risks & mitigations

- **Echo-chamber / bias amplification** — few-shot only from `human_verified` episodes; self-outputs weighted low.
- **Cold start** — seed the case-bank with the 20 labelled dossiers; per-customer history accrues on re-score.
- **Reproducibility** — `temperature=0`; log injected memory + tool trace so every decision is reconstructable.
- **Sanctions removed** — accepted (not in brief); PEP + typologies + geography still surface high risk.
- **Latency** — parallel specialists + capped orchestrator steps; per-customer batch stays parallel across customers.
- **Prompt injection via documents** — read one-per-call, wrapped in a delimiter, system prompt says document text is DATA.
- **Redis down** — in-memory fallback (already in queue.py) so a demo never breaks; scratchpad degrades to stateless stages.
- **PII/retention** (prod note) — synthetic data here; real deployment needs encryption + retention limits.

## 8. Phasing (implementation order)

- **A. Data & cleanup** — strip sanctions/adverse-media; regenerate dataset (keep pep); delete rules/crosscheck/orchestrator/Home.
- **B. Foundation** — models trim; config trim; relational store (customers/assessments/lessons) + `frisk migrate`.
- **C. Memory** — `memory.py` (retrieve/assemble/write-back), `casebank.py` (feature-match), semantic reference files, `scratchpad.py`.
- **D. Scoring** — `specialists.py` (parallel), `tools.py`, `agent.py` (orchestrator loop); rewrite `engine.assess()`.
- **E. Learning** — `reflection.py` (procedural lessons) + wire `feedback.py` into specialists' few-shot.
- **F. Edges** — api/service, frontend/app.js (trace + history + memory panels), nlquery, batch, queue, cli.
- **G. Tests** — mock provider drives the loop; new test suite green.
- **H. Docs** — rewrite docs/deck/README/CLAUDE/PROGRESS to the new system.

## 9. Testing strategy

Mock provider drives a deterministic tool sequence so offline tests run **through** the agent loop.
Golden checks: engine always returns a valid Decision; low-confidence → PENDING_REVIEW; scratchpad evicted on all exits;
per-customer history append+query; episodic `similar()` returns the seeded like-case; injected-memory recorded in the trace;
generator determinism (same seed → same hash); audit append-only.
