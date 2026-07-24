# Financial Risk Signal Aggregator

An AML / financial-crime **risk-triage** prototype (HyperVerge take-home). It ingests a fragmented,
multi-source dossier per customer and produces a **prioritised, risk-scored analyst triage queue** —
scored end-to-end by a **fully-LLM, agentic** pipeline with a **layered memory system**, **confidence-gated
human review**, and an **append-only investigation trace** as the audit record.

## Setup

```bash
python -m venv .venv && . .venv/Scripts/activate     # Windows: .venv\Scripts\activate
pip install -e ".[llm,api,observability,dev]"         # installable package + optional extras

frisk generate            # regenerate the 20 seeded customer folders (deterministic) + self-check
frisk migrate             # create the relational DB (customers / assessments / lessons / cases)
pytest                    # 14 tests (mock provider drives the tool loop — no API key needed)
frisk serve               # backend API + custom frontend -> http://127.0.0.1:8000

# handy:  frisk score --offline   (deterministic mock ranked queue)
#         frisk samples           (40 manual-upload sample profiles)
#         frisk reflect           (distil "lessons learned" from human corrections)
```

Set `OPENROUTER_API_KEY` in `.env` for the real LLM (default `deepseek/deepseek-v4-flash`, Baidu-preferred
routing). With no key, everything still runs on the **mock provider**. Optional review-queue broker:
`docker run -d --name frisk-redis -p 6379:6379 redis:7-alpine` (falls back to in-memory if absent).

**Package layout** (`src/frisk/`): `config/` (settings + disposition policy) · `core/` (models, engine) ·
`ai/` (providers boundary, **specialists**, **tools**, **agent**, **memory**) · `data/` (generate, loaders,
**store**, **casebank**, **reference**, audit) · `hitl/` (Redis queue, **scratchpad**, feedback, **reflection**) ·
`pipeline/` · `query/` · `api/`. Frontend in `frontend/`.

## Approach — a fully-LLM agentic scorer

There is **no deterministic scoring** — the LLM investigates and judges each customer. Per customer:

1. **Retrieve layered memory** (`ai/memory.py`) — per-customer history (relational store), similar past
   cases (episodic case-bank), semantic cheat-sheets, and distilled "lessons".
2. **Parallel specialists** (`ai/specialists.py`) — three memory-fed single-call analysts (KYC · transactions ·
   documents) each return a `SpecialistOpinion` (risk level, signals, tentative score). Fast; focused context.
3. **Agentic orchestrator** (`ai/agent.py`) — one **serial tool-calling ReAct loop** (`parallel_tool_calls=False`,
   `temperature=0`) that gets the specialists' opinions + the original docs + **tools** (`read_kyc`,
   `query_transactions`, `aggregate_transactions`, `find_txn_patterns` (advisory candidates), `read_document`,
   `note`/`read_notes` scratchpad, `finalize`). It investigates, writes to working memory, and emits a
   `RiskFinding` (score/band/confidence/rationale/**evidence_refs**). Guards are loop hygiene, not scoring:
   evidence is citation-checked; a bounded loop / exception still routes to a human at confidence 0 (never blank).
4. **Confidence gate + HITL** (`core/engine.py`) — score decides the band; **confidence < 0.60 → PENDING_REVIEW**
   → a real **Redis review queue** → the Human Review panel. The reviewer's correct score is stored as a
   **human-verified episode** and distilled by `frisk reflect` into **lessons** that feed future prompts.
5. **Audit** — the **ordered tool-call trace** + `key_signals` + `evidence_refs` is the append-only record
   (`data/audit.py`), plus the injected-memory log for reproducibility.

### Layered memory (5 tiers, 3 stores)

| Tier | Content | Store |
|------|---------|-------|
| Working | the agent's run notes | **Redis** scratchpad (evicted on every exit) |
| Per-customer | this customer's assessment history | **relational** SQLite `assessments` (→ Postgres) |
| Episodic | similar past cases + corrections | **case-bank** (feature-match; vector-pluggable) |
| Semantic | typology defs, higher-risk lists | static **reference** files |
| Procedural | "lessons learned" | `lessons` table (distilled from corrections) |

## Tools

Python · pydantic v2 · **LangChain** `ChatOpenAI` tool-calling over **OpenRouter** (deepseek-v4-flash) ·
instructor (structured single calls) · Faker (synthetic data) · SQLite (relational + case-bank) · Redis
(working memory + review queue) · FastAPI + vanilla-JS frontend + Chart.js · pytest.

## Data assumptions

- **20 seeded synthetic customers** (`data/generate.py`, seed 42, fixed reference date → byte-identical output).
  No real PII. Each is a folder mixing **structured** (`kyc.json`, `account.json`, `transactions.csv`,
  `screening.json`) + **unstructured** (`id_document.txt`, `rm_notes.txt`, `correspondence.txt`).
- **Sanctions and adverse-media were scoped out** — the brief names only "external alerts / external data
  sources", so `screening.json` keeps just the **PEP** fact; sanctions/adverse-media are noted as a future
  extension. The LLM identifies risk from KYC, transactions, typology candidates, PEP, and geography.
- Class balance is **deliberately inverted** vs the real ~0.1% suspicious rate so every band is exercised.
- **Offline:** the mock provider drives the same agent loop deterministically (no API key), so the full
  demo — including the human-review routing — runs with zero cost.

## Worked example (input → output)

**Input — `CUST_018`:** Iranian (`IR`) *arms dealer*; transactions include a **structuring cluster**
(≥3 cash deposits each just under the £10,000 floor within days).

**Output (live LLM):** the transactions specialist flags the sub-threshold cash cluster; the agent calls
`read_kyc → query_transactions → find_txn_patterns (structuring, strength 1.0) → read_document(rm_notes) →
finalize` and returns **score ~83–100 / HIGH → ESCALATE**, citing the exact structuring txn ids as
`evidence_refs`. The whole tool-call trace is the audit record.

**Contrast — `CUST_000`:** domestic GB *teacher*, complete KYC, benign salary+card activity →
**LOW → AUTO_CLEAR**. Same agent, opposite end of the queue.

> Design spec: `docs/superpowers/specs/2026-07-24-fullllm-agentic-memory-design.md` ·
> Implementation plan: `docs/superpowers/plans/2026-07-24-fullllm-agentic-memory.md`.
