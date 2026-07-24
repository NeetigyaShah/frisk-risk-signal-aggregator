# Financial Risk Signal Aggregator — 5-Slide Deck

AML / financial-crime risk triage. HyperVerge take-home POC. Fully-LLM agentic scorer with layered memory.
Python · pydantic v2 · LangChain (tool-calling over OpenRouter) · FastAPI · custom JS frontend.

---

## Slide 1 — Problem Understanding and Objective

- Compliance analysts triage **fragmented signals** (KYC, account, transactions, external alerts) under
  heavy false-positive noise, with inconsistent per-analyst scoring.
- **Objective:** join each customer's fragmented signals into one dossier, **score and prioritise** them,
  and **explain** every decision — a triage queue an analyst can act on, not a black box.
- **Design tension:** a false negative is catastrophic, a false positive is expensive, and the reasoning
  must be **reconstructable** for review.
- **North star:** a *fully-LLM, agentic* investigator that reads the whole dossier, is **honest about its
  confidence**, routes what it is unsure about to a **human**, and **learns from the correction**.

> Speaker note: We optimise for a defensible, self-improving investigation — the model does the judging, a human closes the gap, memory makes it better.

---

## Slide 2 — Solution Architecture and Design Flow

```
  data/customers/CUST_xxx/  (structured + unstructured)
                 │
                 ▼
   memory.retrieve  ── per-customer history (relational) · similar cases (episodic)
                 │        · semantic cheat-sheets · lessons (procedural)
                 ▼
   3 PARALLEL specialists  (KYC · transactions · documents)  memory-fed, one call each
                 │  opinions
                 ▼
   AGENTIC ORCHESTRATOR  (serial tool-calling ReAct loop, temperature 0)
     read_kyc · query/aggregate_transactions · find_txn_patterns (advisory)
     · read_document · note/read_notes (Redis scratchpad) · finalize
                 │  RiskFinding (score/band/confidence/evidence)
                 ▼
   route_llm  ── confidence < 0.60 ─► Redis review queue ─► Human panel ─► correction
                 │                                                  │ (human-verified episode + lessons)
                 ▼                                                  └─────────────► memory (write-back)
   SQLite store (history) · append-only audit (the TOOL-CALL TRACE) · FastAPI + JS frontend
```

- **Per-customer flow:** retrieve memory → parallel specialists → agentic orchestrator → confidence-gate →
  persist + evict working memory. **No deterministic scoring, no sanctions rail, no fallback rules.**
- **5-tier memory across 3 stores:** working (Redis) · per-customer (relational) · episodic (case-bank) ·
  semantic (reference files) · procedural (lessons).

> Speaker note: Parallel specialists for speed and focus; one agentic orchestrator with tools + full context for depth; memory makes each run smarter than the last.

---

## Slide 3 — Implementation Highlights

- **Hybrid topology:** three memory-fed **specialists** run in parallel (fast, focused), then a single
  **agentic orchestrator** — a serial ReAct loop (`parallel_tool_calls=False`) over LangChain tool-calling —
  gets their opinions + the original documents + tools and does the deep investigation.
- **Tools return facts, never verdicts.** `find_txn_patterns` surfaces typology **candidates** with a
  strength 0-1 (structuring / layering / round-trip / dormant-spike) and evidence txn ids — the LLM decides
  if a candidate is real. `query_transactions` uses a whitelisted spec (never eval).
- **Layered memory:** a Redis **scratchpad** as working memory (evicted on every exit); a relational
  **assessments** table for per-customer history ("what changed"); an episodic **case-bank** (feature-match,
  vector-pluggable) drawing few-shot only from **human-verified** cases; semantic cheat-sheets; and
  **lessons** distilled from corrections.
- **Confidence-gated HITL + teach-the-model loop:** low confidence → Redis review queue → the reviewer's
  score becomes a human-verified episode and feeds `frisk reflect` → lessons injected into future prompts.
- **Auditability without arithmetic drivers:** the **ordered tool-call trace** + `evidence_refs` +
  injected-memory log is the append-only record — reconstructable and tied to evidence.
- **Reliability as loop hygiene:** citation-check on evidence; a bounded loop / exception routes to a human
  at confidence 0 — never blank. Offline, a **mock provider drives the same tool loop** deterministically.

> Speaker note: The engineering is the harness around the model — tools, memory, the confidence gate, and the trace-as-audit — not a prompt.

---

## Slide 4 — Challenges and Learnings

- **Removing the deterministic safety net:** the earlier design used rules as the source of truth. Going
  fully-LLM means the model owns the number — so the guardrails move to *investigation hygiene* (mandatory
  fact-gathering, citation checks, bounded loop → human) rather than a scoring formula.
- **Echo-chamber risk:** if the system learns from its own outputs, mistakes compound. We draw episodic
  few-shot **only from human-verified cases**, so the memory calibrates toward expert judgement.
- **Serial vs parallel:** most models emit parallel tool calls; we force serial (`parallel_tool_calls=False`)
  and execute only the first call per turn, so the trace is a clean, auditable investigation.
- **Reproducibility:** a fully-LLM score isn't byte-identical run-to-run. We set `temperature=0` and **log
  which memory was injected + the full tool trace**, so every decision is explainable after the fact.
- **Scoping to the brief:** sanctions and adverse-media were **deliberately cut** — the brief names only
  "external alerts / external data sources"; we kept PEP and note sanctions as a clear future extension.

> Speaker note: The interesting problem is making an autonomous investigator safe and auditable without a deterministic backstop.

---

## Slide 5 — Demo Summary and Next Steps

- **End-to-end demo:** the dashboard ranks 20 customers (gauges, confidence, pattern chips + charts); open a
  case to see the **parallel specialist opinions**, the **serial tool-call trace** with cited evidence, the
  **injected memory**, and the **per-customer history**; low-confidence cases land in the **Human Review**
  queue where a correction **teaches** the system; the **Audit** tab is the append-only trace. Ingest lets you
  **batch-score** any subset of samples in parallel.
- **Worked contrast:** `CUST_018` (Iranian arms dealer) → the agent runs `read_kyc → query_transactions →
  find_txn_patterns (structuring, strength 1.0) → read_document → finalize` → **HIGH / ESCALATE** citing the
  structuring txn ids; `CUST_000` (domestic teacher) → **LOW / AUTO_CLEAR**. Same agent, both ends of the queue.
- **Next steps, given more time:**
  - **Vector-embedding** episodic recall (drop-in behind the case-bank's `similar()`), + per-customer change alerts.
  - Re-add **external-alert feeds** (sanctions / adverse-media / World-Check) as tools the agent queries.
  - **Confidence calibration** against labelled outcomes; richer reviewer analytics.
  - **Case management** — assignment, SLAs, escalation workflow, and a fuller reflection cadence.

> Speaker note: The POC proves the agentic loop + layered memory end-to-end; production is vector memory, live feeds, and tuned confidence.
