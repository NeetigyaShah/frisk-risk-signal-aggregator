<div align="center">

# 🛡 Frisk — Financial Risk Signal Aggregator

**An agentic AI that investigates financial-crime risk the way an analyst does — then hands you the evidence.**

Ingests fragmented customer data (KYC, account, transactions, documents), runs a **fully-LLM agentic
pipeline** over it, and produces a **prioritised, risk-scored triage queue** where every decision carries
its own investigation trace. Low-confidence cases route to a human, and the correction teaches the system.

</div>

![Dashboard](docs/screenshots/dashboard.png)

---

## The problem

A compliance analyst opens a customer file and finds a KYC record, a CSV of transactions, a relationship
manager's notes, an ID scan and an email thread — none of which talk to each other. They read all of it,
decide "is this money laundering?", and move to the next of several hundred. It is slow, inconsistent
between analysts, and the reasoning rarely survives in a form anyone can audit later.

**Frisk does the first pass.** It reads everything, investigates like an analyst would, ranks the whole
book by risk, and shows its work — so the human starts from evidence instead of a blank page.

---

## How it works

Every customer goes through the same four stages. There is **no deterministic rules engine** — the LLM
does the judging; the code provides tools, memory and guardrails.

```
   ┌────────────────────────────────────────────────────────────────────────────┐
   │  1. INGEST                                                                 │
   │     kyc.json · account.json · transactions.csv · screening.json            │
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
A customer folder of mixed structured + unstructured files is parsed into one typed `Dossier`.
Money is `Decimal` throughout; missing files degrade gracefully rather than failing.

### 2 · Retrieve memory — 5 tiers, 3 stores
Before scoring, the system gathers what it already knows. This is what makes it improve over time.

| Tier | What it holds | Where it lives |
|------|---------------|----------------|
| **Working** | the agent's notes during one investigation | Redis scratchpad (evicted on exit) |
| **Per-customer** | this customer's assessment history | SQLite `assessments` |
| **Episodic** | similar past cases + human corrections | case-bank (feature-match) |
| **Semantic** | typology definitions, higher-risk reference lists | static reference files |
| **Procedural** | "lessons learned" distilled from corrections | `lessons` table |

### 3 · Investigate — specialists, then an agent
**Three specialists run in parallel** (KYC · transactions · documents), each seeing only its own slice
plus injected memory, each returning a schema-validated `SpecialistOpinion`.

Their opinions then go to **one agentic orchestrator** — a serial tool-calling loop that can read any
document, filter transactions, run an advisory pattern scan, and write notes, before calling `finalize()`.
It is bounded (12 steps), citation-checked (it may only cite evidence a tool actually returned), and
**the ordered tool-call trace becomes the audit record**.

### 4 · Decide and learn
Confidence gates the outcome. Confident cases auto-dispose by band; unsure ones go to a **real Redis
review queue**. When a human corrects a score, that correction is stored as a *human-verified* episode
and distilled into a lesson injected into future prompts — closing the loop.

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

## Setup

**One command:**

```bash
./setup.sh          # installs everything, generates data, runs tests
./setup.sh --run    # ...and starts the server
```

<details>
<summary><b>Manual setup</b> (if you prefer, or on Windows CMD/PowerShell)</summary>

```bash
python -m venv .venv
source .venv/bin/activate        # Windows: .venv\Scripts\activate

pip install -e ".[llm,api,dev]"  # or: pip install -r requirements.txt

python -m frisk.cli generate     # 20 synthetic customers
python -m frisk.cli samples      # 40 upload samples
python -m frisk.cli migrate      # create the database

pytest                           # 14 tests, no API key needed
python -m frisk.cli serve        # → http://127.0.0.1:8000
```
</details>

**API key (optional).** Put an [OpenRouter](https://openrouter.ai/keys) key in `.env` to score with a
real LLM:

```
OPENROUTER_API_KEY=sk-or-v1-...
```

Without a key the app runs on the **deterministic mock provider** — the entire flow works end-to-end,
just with reproducible mock scores. Default model is `deepseek/deepseek-v4-flash`; NVIDIA, Gemini and
Anthropic are drop-in alternates in `config/settings.py`.

**Redis (optional).** `docker run -d --name frisk-redis -p 6379:6379 redis:7-alpine`.
Falls back to an in-memory queue if absent.

> ℹ️ The first dashboard load scores all 20 customers **live** (~1–2 min, shown as a progress bar).
> This happens once; afterwards everything is served from the store.

### Commands

```bash
frisk serve              # backend API + frontend  → http://127.0.0.1:8000
frisk score --offline    # ranked queue in the terminal (mock provider, no cost)
frisk generate           # regenerate the 20 synthetic customers
frisk samples            # regenerate the 40 upload samples
frisk migrate            # create/upgrade the database
frisk reflect            # distil lessons from human corrections
```

---

## Worked example

**Input** — `CUST_018`: an Iranian arms dealer. Four cash deposits (`$8,881 / $9,840 / $9,248 / $9,507`)
made within six days, each individually just under the $10,000 reporting threshold.

**The agent investigates** — reads the ID document and RM notes, filters the transactions, runs the
pattern scan, and finalizes:

| | |
|---|---|
| **Score** | **83 / 100 → HIGH** |
| **Disposition** | **ESCALATE** (confidence 0.85) |
| **Key signals** | high-risk jurisdiction (Iran) · high-risk occupation · confirmed structuring · source of funds poorly evidenced |
| **Cited evidence** | `CUST_018-S00`, `S01`, `S02`, `S03`, `rm_notes.txt` |
| **Trace** | 12 tool calls, every one recorded |

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
│   ├── casebank.py       episodic case-bank
│   └── reference/        semantic cheat-sheets
├── hitl/
│   ├── queue.py          Redis review queue
│   ├── scratchpad.py     working memory (evicted on every exit path)
│   ├── feedback.py       human corrections
│   └── reflection.py     corrections → lessons
├── api/service.py        FastAPI backend + serves the frontend
└── frontend/             vanilla JS + Chart.js, no build step
```

**Engineering invariants**
- No deterministic scoring — the LLM produces the score
- The orchestrator is serial (`parallel_tool_calls=False`), specialists parallel, `temperature=0`
- The engine always returns a valid decision — a bounded loop or exception routes to a human, never blank
- The scratchpad is evicted on **every** exit path (complete / handoff / exception)
- Audit = the ordered tool-call trace + cited evidence, append-only
- Episodic few-shot draws from **human-verified** cases only (avoids learning from its own mistakes)
- Tools return facts, never verdicts — `find_txn_patterns` yields *candidates* the LLM must judge
- NL query never `eval`s model text — only a whitelisted filter spec

📐 **[Full architecture diagrams →](docs/ARCHITECTURE_DIAGRAMS.html)** (open in a browser)

---

## Data & assumptions

- **20 seeded synthetic customers**, byte-identical on every regeneration (seed 42). No real PII.
- Each is a folder mixing **structured** (`kyc.json`, `account.json`, `transactions.csv`, `screening.json`)
  and **unstructured** (`id_document.txt`, `rm_notes.txt`, `correspondence.txt`) files.
- **Sanctions and adverse-media screening were deliberately scoped out** — the brief specifies
  "external alerts / external data sources", so only the **PEP** flag is kept. Re-adding live watchlist
  feeds is a natural extension.
- Class balance is **intentionally inverted** versus the real ~0.1% suspicious rate, so every band and
  every typology is exercised in a 20-customer demo.
- Four AML typologies are surfaced as **advisory candidates** the LLM must judge, never as automatic
  triggers: *structuring · layering · round-tripping · dormant-then-spike*.

---

## Testing

```bash
pytest              # 14 tests, mock provider, no API key or network needed
```

Covers: generator determinism · the engine always returns a valid decision · low confidence routes to
human · the scratchpad is evicted on every exit · per-customer history · episodic recall · injected
memory is logged · audit is append-only · specialists run in parallel · NL-query safety · batch scoring.

---

## Known limits

- **Latency** — ~45–90s per customer live. It is ~11 sequential LLM round-trips at ~3.2s each; that
  serial depth is the cost of a genuine investigation, not a bug. Batch mode overlaps customers.
- **Reproducibility** — a fully-LLM score is not byte-identical run to run. Mitigated with
  `temperature=0` plus a logged trace and injected-memory record, so any decision is reconstructable.
- **Episodic retrieval** is feature-match, not embeddings. The `similar()` interface is
  vector-pluggable when the case bank grows.

---

<div align="center">
<sub>Built as a take-home POC. Synthetic data only — no real customer information.</sub>
</div>
