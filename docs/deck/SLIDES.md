# Frisk — 5-Slide Summary Deck

> Dense, technical, agent-workflow focused. Each slide lists **what to show** and **what to say**.
> Speaker notes are the `>` lines. Build with `python docs/deck/build_pptx.py`.

---

## Slide 1 — Problem & Objective

### The analyst's reality
A compliance analyst opens one customer and finds **five disconnected artefacts**:

| Source | Format | What it hides |
|---|---|---|
| `kyc.json` | structured | identity, occupation, PEP status |
| `account.json` | structured | tenure, product, jurisdiction |
| `transactions.csv` | structured | the actual behaviour — hundreds of rows |
| `rm_notes.txt` | **free text** | the relationship manager's unease |
| `id_document.txt` / `correspondence.txt` | **free text** | document anomalies, admissions |

They read all of it, judge "is this money laundering?", and repeat — hundreds of times.

### Three failures this creates
1. **Slow** — minutes per customer, and the queue is unordered, so the riskiest case may be read last.
2. **Inconsistent** — two analysts score the same file differently; there is no shared calibration.
3. **Unauditable** — the reasoning lives in someone's head. A regulator asking *"why was this cleared?"*
   six months later gets a shrug.

### Objective
> Build an AI that does the **first pass**: reads every source, investigates like an analyst,
> **ranks the whole book by risk**, and **shows its work** — so the human starts from evidence,
> not a blank page.

**Design constraint that shaped everything:** a false negative (missed launderer) is catastrophic;
a false positive is merely expensive. So the system must **know when it is unsure** and escalate,
rather than guess confidently.

> Speaker note: Lead with the analyst's desk, not the tech. The problem is fragmentation +
> inconsistency + no audit trail. Everything in the next four slides answers one of those three.

---

## Slide 2 — Architecture & Agent Orchestration

### The pipeline — four stages, one customer at a time

```
 INGEST                RETRIEVE MEMORY           INVESTIGATE                DECIDE + LEARN
 ──────                ───────────────           ───────────                ──────────────
 kyc.json      ┐                                ┌ KYC specialist ┐
 account.json  │       per-customer history     ├ Transactions   ┼─► AGENTIC          confidence ≥ 0.60
 txns.csv      ┼─► Dossier ─► similar cases ──► └ Documents      ┘   ORCHESTRATOR  ─►  auto-dispose
 *.txt docs    │       lessons learned            (3 PARALLEL,       (SERIAL tool          │
 screening.json┘       reference notes             1 call each)       loop, temp 0)   < 0.60 │
                                                                          │           human queue
                                                                     finalize()            │
                                                                          │        correction ─┘
                                                                    RiskFinding      → memory
```

### Why two different topologies
| | Specialists | Orchestrator |
|---|---|---|
| **Execution** | 3 **parallel** calls | **serial** loop (`parallel_tool_calls=False`) |
| **Sees** | only its own domain slice | all 3 opinions + full dossier + tools |
| **Returns** | `SpecialistOpinion` (schema-validated) | `RiskFinding` via `finalize()` |
| **Why** | speed + focused context, no cross-contamination | each step's tool result informs the next question |

**The key design decision:** the orchestrator is serial *because investigation is inherently
sequential* — you cannot know which document to open until you have seen the transactions.

### The layered memory — 5 tiers, 3 stores
| Tier | Holds | Store | Lifetime |
|---|---|---|---|
| **Working** | notes during this investigation | Redis scratchpad | evicted on every exit |
| **Per-customer** | this customer's score history | SQLite `assessments` | permanent |
| **Episodic** | similar past cases + corrections | case-bank | permanent |
| **Semantic** | typology definitions, risk reference lists | static files | static |
| **Procedural** | lessons distilled from corrections | `lessons` table | grows with use |

> Speaker note: The two-topology split is the core architectural claim — parallel where independent,
> serial where dependent. And the memory table is what makes it a *system* rather than a prompt.

---

## Slide 3 — Input → Agent Loop → Output

### Input: one folder, mixed formats
```
data/customers/CUST_018/
├── kyc.json           {"name":"Mr Hugh Taylor","occupation":"arms dealer","nationality":"IR",...}
├── account.json       {"country":"IR","pep":false,"tenure_days":1268,...}
├── transactions.csv   31 rows — date, amount(Decimal), direction, counterparty, country, type
├── screening.json     {"pep_confirmed": false}
├── id_document.txt    OCR of the passport
└── rm_notes.txt       "...vague about source of funds..."
```

### The loop — a real trace from `CUST_018`
```
 step  tool                    what it learned
 ────  ──────────────────────  ─────────────────────────────────────────────────────────
  1    read_document           id_document.txt — Iranian passport, valid
  2    read_document           rm_notes.txt — RM flags poorly evidenced source of funds
  3    query_transactions      31 transactions, £62,174 credits
  4-9  query_transactions ×6   filtered: cash deposits, by counterparty, by window
 10    find_txn_patterns       STRUCTURING candidate, strength 1.0, txn_ids S00–S03
 11    note                    "4 sub-threshold deposits in 6 days — deliberate"
 12    finalize                score 83, HIGH, ESCALATE, confidence 0.85
```

### Output: a decision that carries its own evidence
```json
{ "score": 83, "band": "HIGH", "action": "ESCALATE", "confidence": 0.85,
  "key_signals": ["Iran (IR) high-risk jurisdiction",
                  "arms dealer occupation — proliferation financing risk",
                  "confirmed structuring: 4 sub-threshold cash deposits totalling $37k in 6 days"],
  "evidence_refs": ["CUST_018-S00","S01","S02","S03","rm_notes.txt"],
  "trace": [ ...12 ordered tool calls... ] }
```

### Guardrails that make the output trustworthy
- **Citation check** — `evidence_refs` are validated against what tools actually returned; a fabricated
  reference is rejected and re-prompted.
- **Bounded loop** — 12 steps max; exceeding it routes to a human rather than looping forever.
- **Never blank** — any exception still produces a valid decision routed to review.
- **Tools return facts, never verdicts** — `find_txn_patterns` yields *candidates* with a strength
  score; the LLM must decide whether the pattern is real and justify it.

> Speaker note: Walk the trace line by line — this is the "show your work" claim made concrete.
> Point out step 10: the tool only *suggests* structuring; the agent had to accept it and cite it.

---

## Slide 4 — Human-in-the-Loop: the flywheel

### The gate
```
        RiskFinding + confidence
                  │
      ┌───────────┴───────────┐
 conf ≥ 0.60              conf < 0.60
      │                        │
 auto-dispose            PENDING_REVIEW
 by band                        │
 (clear/review/escalate)   Redis queue
                                │
                        human sets correct score
                                │
              ┌─────────────────┼─────────────────┐
      human-verified       feedback.jsonl    frisk reflect
        episode                                    │
              │                                 lessons
              └──────────► MEMORY ◄─────────────────┘
                              │
                    injected into future prompts
```

### Why confidence-gating rather than a fixed threshold on score
A score of 58 is not automatically uncertain — the agent may be *very* confident it is a 58.
What matters is whether **the evidence supports the conclusion**. Confidence is the agent's own
honest self-report, and the prompt explicitly tells it that low-confidence cases go to a human —
so admitting uncertainty is the rewarded behaviour, not a failure.

### What the reviewer sees (nothing is hidden)
- the three specialist opinions **and where they disagreed**
- the full ordered tool-call trace
- the agent's scratchpad notes from during the investigation
- which memories were injected into the prompt

### The flywheel — three distinct learning paths
| Correction becomes | Effect |
|---|---|
| a **human-verified episode** in the case bank | future similar customers retrieve it as few-shot |
| a **lesson** via `frisk reflect` | injected into every future orchestrator prompt |
| a row in that customer's **history** | next assessment sees "what changed since last time" |

**Anti-echo-chamber guard:** episodic few-shot draws **only from human-verified cases** — the system
never learns from its own unreviewed output, so mistakes cannot compound into false precedent.

> Speaker note: This is the slide that answers "so it improves?". Emphasise the three paths — most
> systems have one (few-shot). And the anti-echo-chamber rule is the detail that shows rigour.

---

## Slide 5 — Results, Trade-offs & Next Steps

### It works end-to-end
| Metric | Result |
|---|---|
| Customers scored | **22** (20 seeded + uploads) |
| Disposition split | 6 auto-cleared · 12 review · 3 escalate · 1 human queue |
| Analyst load saved | **27%** auto-cleared with zero human time |
| Per customer | ~11 tool calls, 45–90s live |
| Tests | **14 passing**, no API key required (mock provider) |

**Worked contrast — same agent, opposite ends:**
`CUST_018` (arms dealer, Iran, structuring) → **83 / HIGH / ESCALATE** @ 0.85 ·
`CUST_000` (UK teacher, salary + card spend) → **5 / LOW / AUTO_CLEAR** @ 0.95

### Engineering decisions worth defending
- **No deterministic scoring** — the LLM judges; code supplies tools, memory, guardrails.
- **Sanctions/adverse-media deliberately scoped out** — the brief said "external alerts"; only PEP kept.
- **Money is `Decimal`**, seeded generation is byte-identical, the audit log is append-only.
- **The scratchpad is evicted on every exit path** — no working-memory leaks between runs.

### Honest limits
- **Latency** ~45–90s/customer — that is ~11 sequential LLM round-trips; serial depth is the cost of
  a real investigation. Batch mode overlaps customers to hide it.
- **Not byte-reproducible** — mitigated with `temperature=0` plus a logged trace and injected-memory
  record, so any decision is reconstructable after the fact.
- **Episodic retrieval is feature-match**, not embeddings — the `similar()` interface is vector-pluggable.

### Next steps
1. **Vector episodic memory** — swap feature-match for embeddings as the case bank grows.
2. **Live watchlist feeds** — re-add sanctions/adverse-media as agent *tools* it can query.
3. **Confidence calibration** — measure agreement against human corrections; auto-tune the threshold.
4. **Case management** — assignment, SLAs, escalation workflow, reviewer analytics.

> Speaker note: Close on the trade-offs, not the wins — showing you know where it is weak is more
> convincing than claiming it is finished. The next steps should each map to a limit named above.
