<div align="center">

# 🛡 Frisk — Financial Risk Signal Aggregator

**An agentic AI that investigates financial-crime risk the way an analyst does — then hands you the evidence.**

Ingests fragmented customer data (KYC, account, transactions, free-text documents), runs a **fully-LLM
agentic pipeline** over it, and produces a **prioritised, risk-scored triage queue** where every decision
carries its own investigation trace. Low-confidence cases route to a human, and the correction teaches
the system.

`Python 3.11+` · `FastAPI` · `LangChain tool-calling` · `Pydantic v2` · `SQLite + Redis` · `14 tests, no API key needed`

</div>

![Dashboard](docs/screenshots/dashboard.png)

---

## Table of contents

[The problem](#the-problem) · [Quick start](#quick-start) · [How it works](#how-it-works) ·
[Key design decisions](#key-design-decisions) · [What you can do with it](#what-you-can-do-with-it) ·
[Worked example](#worked-example) · [Architecture](#architecture) ·
[Data & assumptions](#data--assumptions) · [Testing](#testing) · [Known limits](#known-limits)

---

## The problem

Anti-money-laundering compliance is a haystack problem where the haystack is manufactured by the
detection system itself. Industry benchmarks put **~90–95% of AML alerts as false positives**, with only
**2–4% actionable** — meaning most analyst effort produces nothing, and the reasoning behind each
disposition is rarely captured in a form anyone can audit later.

A compliance analyst opens one customer and finds five disconnected artefacts:

| File | Format | What it hides |
|---|---|---|
| `kyc.json` | structured | identity, occupation, nationality, PEP status |
| `account.json` | structured | tenure, product, jurisdiction |
| `transactions.csv` | structured | the actual behaviour — hundreds of rows |
| `rm_notes.txt` | **free text** | the relationship manager's unease, in prose |
| `id_document.txt` | **free text** | document anomalies, admissions |

The two most incriminating sources are unstructured — no rules engine reads them. This creates three
failures: it is **slow** (minutes per customer, in an unordered queue), **inconsistent** (two analysts
score the same file differently), and **unauditable** (the reasoning lives in someone's head).

**Frisk does the first pass.** It reads everything, investigates like an analyst would, ranks the whole
book by risk, and shows its work — so the human starts from evidence instead of a blank page.

> **The design constraint that shaped everything:** a false negative (a missed launderer) is
> catastrophic; a false positive is merely expensive. That asymmetry means the system must *know when it
> is unsure and escalate*, rather than guess confidently. It is why **confidence — not score** — decides
> who sees a case.

---

## Quick start

### One command

```bash
git clone https://github.com/NeetigyaShah/frisk-risk-signal-aggregator.git
cd frisk-risk-signal-aggregator
./setup.sh --run
```

`setup.sh` creates a virtualenv, installs dependencies, generates the synthetic dataset, migrates the
database, runs the test suite, and (with `--run`) starts the server at **http://127.0.0.1:8000**.

<details>
<summary><b>Manual setup</b> — if you prefer, or on Windows PowerShell</summary>

```bash
python -m venv .venv
source .venv/bin/activate          # Windows: .venv\Scripts\activate

pip install -e ".[llm,api,dev]"    # or: pip install -r requirements.txt

python -m frisk.cli generate       # 20 synthetic customers (seeded, deterministic)
python -m frisk.cli samples        # 40 upload samples
python -m frisk.cli migrate        # create the database

pytest                             # 14 tests — no API key, no network
python -m frisk.cli serve          # → http://127.0.0.1:8000
```
</details>

### Configuration

Everything below is **optional** — the app runs fully without any of it.

| | |
|---|---|
| **LLM key** | Put an [OpenRouter](https://openrouter.ai/keys) key in `.env` as `OPENROUTER_API_KEY=sk-or-v1-...` to score with a real model. Without one, the **deterministic mock provider** runs the entire flow end-to-end with reproducible scores. |
| **Model** | Default `deepseek/deepseek-v4-flash`. NVIDIA, Gemini and Anthropic are drop-in alternates in `config/settings.py`. |
| **Redis** | `docker run -d --name frisk-redis -p 6379:6379 redis:7-alpine` — powers the review queue and working-memory scratchpad. Falls back to an in-memory queue if absent. |

> ℹ️ The first dashboard load scores all 20 customers **live** (~1–2 min, shown as a progress bar).
> This happens once; afterwards everything is served from the store.

### Commands

```bash
frisk serve              # backend API + frontend  → http://127.0.0.1:8000
frisk score --offline    # ranked queue in the terminal (mock provider, zero cost)
frisk generate           # regenerate the 20 synthetic customers
frisk samples            # regenerate the 40 upload samples
frisk migrate            # create/upgrade the database
frisk reflect            # distil lessons from accumulated human corrections
```

---

## How it works

Every customer goes through the same four stages. There is **no deterministic rules engine anywhere in
the codebase** — no scoring formula, no weights, no thresholds that produce a number. The LLM judges;
the code supplies tools, memory and guardrails.

```
   ┌────────────────────────────────────────────────────────────────────────────┐
   │  1. INGEST                                                                 │
   │     kyc.json · account.json · transactions.csv                             │
   │     id_document.txt · rm_notes.txt · correspondence.txt      → Dossier      │
   └────────────────────────────────────────────────────────────────────────────┘
                                      │
   ┌────────────────────────────────────────────────────────────────────────────┐
   │  2. RETRIEVE MEMORY        (what do we already know?)                      │
   │     per-customer history · similar past cases · lessons · reference notes   │
   └────────────────────────────────────────────────────────────────────────────┘
                                      │
   ┌────────────────────────────────────────────────────────────────────────────┐
   │  3. INVESTIGATE                                                            │
   │                                                                            │
   │     ┌── KYC specialist ──┐                                                 │
   │     ├── Transactions  ───┼──►  AGENTIC ORCHESTRATOR                        │
   │     └── Documents ───────┘     serial tool-calling loop, temperature 0     │
   │        (3 parallel calls)      read_document · query_transactions          │
   │                                find_txn_patterns · note → finalize()        │
   └────────────────────────────────────────────────────────────────────────────┘
                                      │
   ┌────────────────────────────────────────────────────────────────────────────┐
   │  4. DECIDE + LEARN                                                         │
   │     confidence ≥ 0.60 → auto-dispose by band (clear / review / escalate)    │
   │     confidence < 0.60 → human review queue → correction → memory            │
   └────────────────────────────────────────────────────────────────────────────┘
```

### 1 · Ingest
A customer folder of mixed structured + unstructured files is parsed into one typed `Dossier`. Money is
`Decimal` throughout; missing files degrade gracefully rather than failing the run.

### 2 · Retrieve memory — 5 tiers, 3 stores
Before scoring, the system gathers what it already knows. Memory is retrieved *before* the specialists
run, so every LLM call in the pipeline sees the same context. This is what makes it a system rather than
a prompt — and what makes it improve over time.

| Tier | What it holds | Where it lives | Lifetime |
|------|---------------|----------------|----------|
| **Working** | the agent's notes during one investigation | Redis scratchpad | evicted on every exit path |
| **Per-customer** | this customer's assessment history | SQLite `assessments` | permanent |
| **Episodic** | similar past cases + human corrections | case bank (feature-match) | permanent |
| **Semantic** | typology definitions, higher-risk reference lists | static `.md` files | static |
| **Procedural** | "lessons learned" distilled from corrections | SQLite `lessons` | grows with use |

### 3 · Investigate — specialists, then an agent
**Three specialists run in parallel** (KYC · transactions · documents), each seeing only its own slice
plus injected memory, each returning a schema-validated `SpecialistOpinion`.

Their opinions then go to **one agentic orchestrator** — a serial tool-calling loop that can read any
document, filter transactions, run an advisory pattern scan, and write notes to working memory, before
calling `finalize()`. It is bounded (12 steps), citation-checked (it may only cite evidence a tool
actually returned), and **the ordered tool-call trace becomes the audit record**.

### 4 · Decide and learn
Confidence gates the outcome. Confident cases auto-dispose by band; unsure ones go to a **real Redis
review queue**. When a human corrects a score, that correction takes three distinct paths: it becomes a
*human-verified episode* future similar customers retrieve, a *lesson* injected into every future
orchestrator prompt, and a *row in that customer's history*.

---

## Key design decisions

The six decisions below are the ones worth arguing about. Each is a trade-off, not an obvious default.

### 1 · No deterministic scoring — the LLM produces the number

A rules engine is auditable but blind to the free-text sources that carry the strongest signal, and it
is exactly what generates the 90%+ false-positive rate the industry complains about. Handing scoring to
the LLM trades reproducibility for the ability to read prose and reason across sources.

**How the trade-off is paid for:** `temperature=0`, a schema-validated output, a logged tool trace and a
record of exactly which memory was injected — so any decision is *reconstructable* even though it is not
byte-identical.

### 2 · Parallel specialists, serial orchestrator

Two different topologies in one pipeline, for two different reasons:

|  | 3 Specialists | 1 Orchestrator |
|---|---|---|
| Execution | 3 calls **in parallel** | **serial** loop, one call at a time |
| Sees | only its own slice | all 3 opinions + full dossier + tools |
| Returns | `SpecialistOpinion` | `RiskFinding` via `finalize()` |
| Why | speed, and no cross-contamination | each result informs the next question |

The orchestrator is serial (`parallel_tool_calls=False`) **because investigation is inherently
sequential** — you cannot know which document to open until you have seen the transactions. The
specialists are parallel **because their domains are independent** — running them together costs nothing
and stops them contaminating each other's reasoning.

### 3 · Tools return facts, never verdicts

`find_txn_patterns` does not decide that a customer is structuring. It returns *candidates* — "4 cash
deposits below the reporting threshold within 6 days, rows S00–S03" — which the agent must then judge
and cite. A tool that returned `{"structuring": true}` would make the LLM a rubber stamp and move the
real decision back into hard-coded logic.

This is also what makes the output auditable: the agent has to point at the exact rows to claim a
pattern, and `evidence_refs` is validated against what the tools actually returned.

### 4 · Gate on confidence, not on score

A score of 58 is not automatically uncertain — the agent may be *very* confident it is a 58. What
matters is whether the evidence supports the conclusion.

Confidence is the agent's own self-report, and the prompt tells it plainly that low-confidence cases go
to a human. That framing makes **admitting uncertainty the rewarded behaviour** rather than a penalty —
which is the only way a self-reported confidence is worth anything.

### 5 · Learn only from human-verified cases

Episodic retrieval would happily surface the agent's own unreviewed decisions as precedent, compounding
any early error into permanent bias — an echo chamber of its own making. Retrieval is therefore
restricted to cases a human actually verified. The system never learns from its own unreviewed output.

### 6 · The engine can never return blank

A bounded loop, an API failure, or an unhandled exception all still produce a *valid decision* routed to
a human — never an empty result and never a silent zero. An early bug where the agent hit the step cap
and returned `score 0, confidence 0` (which the router read as a legitimate "uncertain" case) is why
`finalize` is now bound as the **only** available tool in the final two turns. A bounded loop needs a
forced exit, not just a cap.

<details>
<summary><b>Further invariants</b></summary>

- The scratchpad is evicted on **every** exit path — complete, handoff, and exception
- Audit is append-only, and records clears as well as escalations
- Money is `Decimal` throughout; no float arithmetic on amounts
- Synthetic data generation is seeded and byte-identical across runs
- NL query never `eval`s model text — only a whitelisted, typed filter spec
- The provider boundary is an ABC + factory, so swapping models touches one file

</details>

📐 **[Full architecture diagrams →](docs/ARCHITECTURE_DIAGRAMS.html)** (open in a browser)

---

## What you can do with it

| | |
|---|---|
| **Dashboard** | Whole book ranked by risk, score distribution, disposition split, detected patterns |
| **Case detail** | The full investigation: specialist opinions, tool-call trace, cited evidence, injected memory, transactions with anomalies highlighted, and the source documents |
| **Review queue** | Low-confidence cases with a teach-the-model correction form |
| **Case comparison** | Two customers side by side — exactly which signals differ, and why one cleared |
| **SAR drafts** | A filing-ready Suspicious Activity Report narrative generated from the case's own evidence |
| **Audit trail** | Append-only record of every decision |
| **Ingest** | Upload documents, or batch-score any subset of 40 sample profiles in parallel |

### The case view — the whole system on one screen
![Case detail](docs/screenshots/case-detail.png)

### Human-in-the-loop — corrections become training signal
![Review queue](docs/screenshots/review-queue.png)

### Case comparison — why did one clear and the other escalate?
![Case comparison](docs/screenshots/case-comparison.png)

### SAR draft — a real analyst deliverable
![SAR draft](docs/screenshots/sar-draft.png)

---

## Worked example

**Input** — `CUST_018`: an Iranian arms dealer. Four cash deposits (`$8,881 / $9,840 / $9,248 / $9,507`)
made within six days, each individually just under the $10,000 reporting threshold.

**The agent investigates** — 12 recorded tool calls:

| Step | Tool | What came back |
|---|---|---|
| 1 | `read_document` | `id_document.txt` — Iranian passport, valid |
| 2 | `read_document` | `rm_notes.txt` — RM flags poor source of funds |
| 3 | `query_transactions` | 31 transactions, £62,174 in credits |
| 4–9 | `query_transactions` | filtered six ways: cash deposits, counterparty, time window |
| 10 | `find_txn_patterns` | STRUCTURING candidate, strength 1.0, rows S00–S03 |
| 11 | `note` | *"4 sub-threshold deposits in 6 days"* → working memory |
| 12 | `finalize` | **83 · HIGH · ESCALATE · confidence 0.85** |

**Output:**

```json
{ "score": 83, "band": "HIGH", "disposition": "ESCALATE", "confidence": 0.85,
  "evidence_refs": ["CUST_018-S00", "S01", "S02", "S03", "rm_notes.txt"],
  "key_signals": ["Iran high-risk jurisdiction", "arms dealer occupation",
                  "confirmed structuring — $37k across 4 deposits in 6 days",
                  "source of funds poorly evidenced"] }
```

**Contrast** — `CUST_000`, a UK teacher with regular salary and domestic card spending:
**score 5 → LOW → AUTO_CLEAR** at confidence 0.95. Same agent, opposite ends of the queue.

---

## Architecture

```
src/frisk/
├── ai/
│   ├── agent.py          the agentic orchestrator — serial tool-calling loop
│   ├── specialists.py    3 parallel memory-fed domain analysts
│   ├── tools.py          the tools the agent can call (facts only, never verdicts)
│   ├── memory.py         retrieve / assemble / write-back across all 5 tiers
│   ├── sar.py            Suspicious Activity Report drafting
│   └── providers/        provider boundary (OpenRouter · NVIDIA · Anthropic · mock)
├── core/
│   ├── engine.py         assess(): memory → specialists → agent → gate → persist
│   └── models.py         Dossier, RiskFinding, SpecialistOpinion, AgentStep…
├── data/
│   ├── generate.py       seeded synthetic customer generator
│   ├── loaders.py        folder / upload / paste → Dossier
│   ├── store.py          relational store (customers, assessments, lessons)
│   ├── casebank.py       episodic case bank
│   └── reference/        semantic cheat-sheets (typologies, higher-risk lists)
├── hitl/
│   ├── queue.py          Redis review queue
│   ├── scratchpad.py     working memory (evicted on every exit path)
│   ├── feedback.py       human corrections
│   └── reflection.py     corrections → lessons
├── api/service.py        FastAPI backend + serves the frontend
└── frontend/             vanilla JS + Chart.js, no build step
```

**Request path.** `POST /api/score/{id}` → `engine.assess()` → `memory.retrieve` → `scratchpad.start` →
`run_specialists` (3 parallel) → `agent.score` (serial loop) → confidence gate → persist + audit →
`scratchpad.evict` in a `finally`. The frontend is vanilla JS with no build step, so the whole app is
`git clone` → `./setup.sh` → open a browser.

---

## Data & assumptions

- **20 seeded synthetic customers**, byte-identical on every regeneration (seed 42). No real PII.
- Each is a folder mixing **structured** (`kyc.json`, `account.json`, `transactions.csv`) and
  **unstructured** (`id_document.txt`, `rm_notes.txt`, `correspondence.txt`) files.
- **Sanctions and adverse-media screening were deliberately scoped out.** The brief specifies "external
  alerts / external data sources", so only the **PEP** flag is kept. Re-adding live watchlist feeds as
  *tools the agent queries* is the natural extension.
- Class balance is **intentionally inverted** versus the real ~0.1% suspicious rate, so every band and
  every typology is exercised in a 20-customer demo.
- Four AML typologies are surfaced as **advisory candidates** the LLM must judge, never as automatic
  triggers: *structuring · layering · round-tripping · dormant-then-spike*.

---

## Testing

```bash
pytest              # 14 tests — mock provider, no API key or network needed
```

Covers: generator determinism · the engine always returns a valid decision · low confidence routes to a
human · the scratchpad is evicted on every exit path · per-customer history · episodic recall · injected
memory is logged · audit is append-only · specialists run in parallel · NL-query safety · batch scoring.

---

## Known limits

| Limit today | Why, and what comes next |
|---|---|
| **Latency ~45–90s per customer** | ~11 sequential LLM round-trips at ~3.2s each. That serial depth is the cost of a genuine investigation, not a bug — batch mode overlaps customers, and reducing steps per run is the next lever. |
| **Not byte-reproducible** | A fully-LLM score varies run to run. Mitigated with `temperature=0` plus a logged trace and injected-memory record. Next: pin model snapshots and store the full prompt hash. |
| **Episodic recall is feature-match** | Not embeddings yet. The `similar()` interface is deliberately vector-pluggable as the case bank grows. |
| **Fixed 0.60 confidence gate** | A reasonable starting point, not a calibrated one. Next: measure agreement against accumulated human corrections and auto-tune. |

---

<div align="center">
<sub>Built as a take-home POC. Synthetic data only — no real customer information.</sub>
</div>
