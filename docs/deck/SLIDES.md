# Frisk — 5-Slide Summary Deck

Covers the five required elements: **problem understanding · solution approach · key highlights ·
challenges · learnings.**

> Speaker notes are the `>` lines. Build with `python docs/deck/build_pptx.py` → `deck.pptx`.
> No screenshots — the deck carries the argument; the demo video carries the evidence.

---

## Slide 1 — Problem Understanding

### The domain, in numbers

Anti-money-laundering compliance is a haystack problem where the haystack is manufactured by the
detection system itself.

| Figure | Why it matters here |
|---|---|
| **~90–95%** of AML alerts are false positives | the bottleneck is triage, not detection |
| **2–4%** of alerts are actionable | 96%+ of analyst effort produces nothing |
| **70–80%** of analyst time goes to false positives | the scarce resource is *attention*, not data |
| **2–5% of global GDP** laundered annually (UNODC) | the false negatives are the expensive ones |

Directional industry estimates, not audited statistics — but the shape is consistent: **rules-based
systems generate more noise than any team can read, and the reasoning behind each disposition is
never captured.**

### The analyst's reality

One customer arrives as five disconnected artefacts, in three formats, with no join key but the
customer ID:

| File | Format | What it hides |
|---|---|---|
| `kyc.json` | structured | identity, occupation, nationality, PEP status |
| `account.json` | structured | tenure, product, jurisdiction |
| `transactions.csv` | structured | the actual behaviour — hundreds of rows |
| `rm_notes.txt` | **free text** | the relationship manager's unease, in prose |
| `id_document.txt` | **free text** | document anomalies, admissions |

The two most incriminating sources are unstructured. No rules engine reads them.

### Three failures this creates

1. **Slow** — minutes per customer, and the queue is unordered, so the riskiest case may be read last.
2. **Inconsistent** — two analysts score the same file differently. There is no shared calibration.
3. **Unauditable** — the reasoning lives in someone's head. A regulator asking *"why was this
   cleared?"* six months later gets a shrug.

### Objective

Do the first pass: **read every source, investigate like an analyst, rank the whole book by risk,
and show the work** — so the human starts from evidence rather than a blank page.

### The design constraint that shaped everything

A false negative (a missed launderer) is catastrophic; a false positive is merely expensive. That
asymmetry means the system must **know when it is unsure and escalate**, rather than guess
confidently. This one constraint is why confidence — not score — decides who sees a case.

> Speaker note: Lead with the analyst's desk, not the tech. The numbers establish that this is a
> triage and explainability problem, not a detection problem. Everything in the next four slides
> answers one of the three failures.

---

## Slide 2 — Solution Approach

### The pipeline — four stages, one customer at a time

```
INGEST              RETRIEVE MEMORY        INVESTIGATE                 DECIDE + LEARN
kyc · account   →   per-customer       →   3 specialists (PARALLEL) →  conf ≥ 0.60 → auto-dispose
transactions        similar cases          KYC · txns · docs           conf < 0.60 → human queue
id_doc · rm_notes   lessons learned            ↓                       correction  → memory
correspondence      reference notes        orchestrator (SERIAL)
→ one Dossier                              tools → finalize()
```

**No deterministic rules engine.** There is no scoring formula anywhere in the codebase. The LLM
produces the score; code supplies the tools, the memory and the guardrails.

### Why two different topologies

|  | 3 Specialists | 1 Orchestrator |
|---|---|---|
| Execution | 3 calls in parallel | serial loop, one call at a time |
| Sees | only its own slice | all 3 opinions + full dossier + tools |
| Returns | `SpecialistOpinion` | `RiskFinding` via `finalize()` |
| Why | speed, and no cross-contamination | each result informs the next question |

**The key design decision:** the orchestrator is serial *because investigation is inherently
sequential* — you cannot know which document to open until you have seen the transactions. The
specialists are parallel *because their domains are independent* — running them together costs
nothing and stops them contaminating each other's reasoning.

### The layered memory — 5 tiers, 3 stores

| Tier | Holds | Stored in | Lifetime |
|---|---|---|---|
| **Working** | the agent's notes during this run | Redis scratchpad | evicted on every exit path |
| **Per-customer** | this customer's assessment history | SQLite `assessments` | permanent |
| **Episodic** | similar past cases + human corrections | case bank | permanent |
| **Semantic** | typology definitions, high-risk reference | static `.md` files | static |
| **Procedural** | lessons distilled from corrections | SQLite `lessons` | grows with use |

Memory is retrieved *before* the specialists run, so every LLM call in the pipeline sees the same
context. This is what makes it a system rather than a prompt.

> Speaker note: The two-topology split is the core architectural claim — parallel where independent,
> serial where dependent. The memory table is the second claim: state outlives the request.

---

## Slide 3 — Key Highlights

### A real investigation — `CUST_018`, an Iranian arms dealer

| Step | Tool | What came back |
|---|---|---|
| 1 | `read_document` | `id_document.txt` — Iranian passport, valid |
| 2 | `read_document` | `rm_notes.txt` — RM flags poor source of funds |
| 3 | `query_transactions` | 31 transactions, £62,174 in credits |
| 4–9 | `query_transactions` | filtered six ways: cash deposits, counterparty, time window |
| 10 | `find_txn_patterns` | STRUCTURING candidate, strength 1.0, rows S00–S03 |
| 11 | `note` | *"4 sub-threshold deposits in 6 days"* → working memory |
| 12 | `finalize` | **83 · HIGH · ESCALATE · confidence 0.85** |

### The output carries its own evidence

```json
{ "score": 83, "band": "HIGH", "disposition": "ESCALATE", "confidence": 0.85,
  "evidence_refs": ["CUST_018-S00","S01","S02","S03","rm_notes.txt"],
  "key_signals": ["Iran high-risk jurisdiction", "arms dealer occupation",
                  "confirmed structuring — $37k across 4 deposits in 6 days"] }
```

### Four guardrails that make it trustworthy

- **Citation check** — `evidence_refs` are validated against what the tools actually returned. A
  fabricated reference is rejected before the decision is accepted.
- **Bounded loop** — 12 steps maximum. Exceeding it routes to a human; it never loops forever.
- **Never blank** — any exception still produces a valid decision, routed to review.
- **Facts, not verdicts** — `find_txn_patterns` returns *candidates*. The agent must judge them and
  cite the rows. The tool never decides.

### It works end-to-end

**22** customers scored live · **27%** auto-cleared with zero human time · **3** escalated ·
**1** routed to a human on low confidence · **14** tests pass with no API key required.

**Same agent, opposite ends of the queue:**
`CUST_018` (arms dealer, Iran, structuring) → **83 HIGH / ESCALATE** @ 0.85
`CUST_000` (UK teacher, salary + card spend) → **5 LOW / AUTO_CLEAR** @ 0.95

> Speaker note: Walk the trace. This is "show your work" made concrete. Point at step 10 — the tool
> only *suggests* structuring; the agent had to accept it and cite the exact rows to claim it.

---

## Slide 4 — Human-in-the-Loop

### The gate

```
RiskFinding + self-reported confidence
              ↓
      confidence ≥ 0.60 ?
       ├── YES → auto-dispose by band (AUTO_CLEAR / REVIEW / ESCALATE)
       └── NO  → Redis review queue → human sets the correct score
```

### Why gate on confidence rather than score

A score of 58 is not automatically uncertain — the agent may be very confident it is a 58. What
matters is whether **the evidence supports the conclusion**. Confidence is the agent's own honest
self-report, and the prompt tells it plainly that low-confidence cases go to a human — which makes
**admitting uncertainty the rewarded behaviour** rather than a penalty.

### What the reviewer sees — nothing is hidden

The proposed score and confidence · all three specialist opinions, including where they disagreed ·
the complete tool-call trace · the agent's own working notes · the memory that was injected.

### One correction, three distinct learning paths

1. **A human-verified episode** → future similar customers retrieve it as a few-shot example.
2. **A lesson** (`frisk reflect`) → distilled and injected into every future orchestrator prompt.
3. **A row in that customer's history** → the next assessment of that customer sees what changed.

Most systems have one of these. Three means one correction improves *similar cases*, *all cases*,
and *this case* simultaneously.

### Anti-echo-chamber guard

Episodic few-shot draws **only from human-verified cases**. The system never learns from its own
unreviewed output, so its mistakes cannot compound into false precedent. Every decision — cleared as
well as escalated — is written to an append-only audit log, so the flywheel is inspectable rather
than merely asserted.

> Speaker note: This is the slide that answers "does it improve?". Emphasise the three paths, then
> the anti-echo-chamber rule — that is the detail showing the failure mode was anticipated.

---

## Slide 5 — Challenges & Learnings

### Four challenges that changed the design

**1 · The agent that never finished.**
Early runs hit the 12-step cap mid-investigation and returned score 0 at confidence 0 — which the
router read as a legitimate "uncertain" case. A silent failure disguised as a valid decision.
*Fix:* in the final two turns, `finalize` is bound as the **only** available tool, plus a
budget-aware nudge and a specialist-mean fallback. A bounded loop needs a forced exit, not just a cap.

**2 · A deleted feature that would not die.**
Sanctions screening was cut from scope, yet kept appearing in output — traced to three separate
ghosts: a `{}` default in the loader, a stray phrase in a reference file, and a stale LLM cache.
*Fix:* purge data, not just code. Added an explicit scope guard to every prompt, then re-scored all
22 customers to verify zero mentions.

**3 · "It must be rate limiting."**
Parallel scoring took 76–90s and I assumed provider throttling. The data disagreed: the key has no
request cap, and four concurrent calls took 1.55s versus 1.48s for one. The real cause was **serial
depth** — the agent used 15 of its 16 steps every run — plus a tool factory rebuilt on every call
(375ms where the raw detector took 0.9ms).
*Fix:* cache the detectors. That path went from 7500ms to 5ms.

**4 · Learning from its own homework.**
Episodic retrieval would happily have surfaced the agent's own unreviewed decisions as precedent,
compounding any early error into permanent bias.
*Fix:* restrict retrieval to human-verified cases only.

### Four learnings

- **Give the model facts, not verdicts.** Tools returning *candidates* the agent must judge and cite
  produce better reasoning than tools returning conclusions — and the citation is auditable.
- **Confidence routes better than score.** A confident 58 needs no human; an unsure 30 does. Routing
  on certainty rather than severity is what makes escalation meaningful.
- **Measure before optimising.** My first latency diagnosis was wrong, and only measurement showed
  it. The fix I would have shipped would have addressed nothing.
- **In compliance, the trace *is* the product.** A correct score that cannot be explained is
  worthless to a regulator. Explainability is not bolted on afterwards; it is the output.

### Honest limits, and what comes next

| Limit today | Next step |
|---|---|
| ~45–90s per customer (≈11 sequential LLM round-trips) | batch mode already overlaps customers; reduce steps per run |
| Not byte-reproducible (temperature 0, mitigated by a logged trace) | pin model snapshots; store the full prompt hash |
| Episodic recall is feature-match, not embeddings | the `similar()` interface is deliberately vector-pluggable |
| Sanctions / adverse media scoped out (the brief said *"external alerts"*) | re-add as live watchlist **tools** the agent queries |
| Confidence threshold is a fixed 0.60 | calibrate against accumulated human corrections |

> Speaker note: Close on the challenges and learnings, not the wins. Showing that you found the
> silent failure — and that you were wrong once and the data corrected you — is more convincing than
> claiming it is finished.
