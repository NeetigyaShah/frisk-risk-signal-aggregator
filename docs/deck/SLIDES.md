# Financial Risk Signal Aggregator — 5-Slide Deck

AML / financial-crime risk triage. HyperVerge take-home POC. Python · Streamlit · pydantic v2 ·
instructor · anthropic.

---

## Slide 1 — Problem Understanding and Objective

- Compliance analysts triage **fragmented signals** (KYC, transactions, sanctions/PEP, adverse media)
  under ~95% false-positive noise, with inconsistent per-analyst scoring.
- **Objective:** join per-customer signals into one dossier, score them **deterministically and
  defensibly**, rank them, and explain every finding — a prioritised triage queue, not a black box.
- **Design tension:** a false negative (a missed sanctioned entity) is catastrophic; a false positive
  is expensive. The system must be **auditable to a regulator** and **calibratable by a risk team**.
- **North star:** a *never-fails* engine — rules are the source of truth, the LLM is an advisory
  cross-check, and a rules-only fallback means the engine never returns nothing.

> Speaker note: We optimise for defensible, consistent triage under regulatory scrutiny — not raw model accuracy.

---

## Slide 2 — Solution Architecture and Design Flow

```
  data/generate.py ─► dossiers.json ─┐
  (20 seeded synthetic profiles)     │
                                     ▼
  config.py ──────►  ┌─────────────────────────────────────────────┐
  (the tuning knob)  │              engine.py (orchestrator)         │
                     │                                               │
   rules.py  ───────►│  score_customer()   SOURCE OF TRUTH           │
   (deterministic)   │   overrides FIRST ─► weighted 0-100 ─► band   │
                     │          │                                    │
   llm.py  ─────────►│  crosscheck()  advisory, schema-locked        │
   (never-fails)     │   instructor+pydantic, temp 0, retry x3       │
                     │   └─ try/except ─► rules-only fallback        │
                     │          │                                    │
                     │  reconcile(confidence) = 1-|rules-llm|/100    │
                     │  route()  kill-switch ─► band thresholds      │
                     └───────────────┬───────────────────────────────┘
                        drivers (sum │ to score)      ▼
                        for explain  │        audit.py (append-only,
                                     ▼        sha256 fingerprint)
                            src/app/ (Streamlit)
                        Queue ─► Case detail ─► Audit
```

- **Per-customer flow:** dossier → rules `score/band/findings` → independent LLM `score/confidence/
  rationale` → reconcile (agreement = confidence) → route (HITL disposition) → one `AuditRecord`.
- **Invariant:** the rules score is the auditable number; the LLM **never writes the arithmetic**.

> Speaker note: Single-process app, six modules — rules produce the number, the LLM only cross-checks it.

---

## Slide 3 — Implementation Highlights

- **Rules as a registry of pure functions** (~stdlib, no rules-engine DSL): overrides/vetoes
  evaluated **before** the weighted sum, so a sanctions hit is never averaged away.
- **Typology detectors are temporal**, not amount-only: structuring (≥3 sub-£10k cash in 7 days),
  layering (≥3 ~80%-forwarded hops), round-trip, dormant-then-spike. Every finding carries evidence.
- **LLM boundary = instructor + Pydantic v2:** `Field(ge=0,le=100)`, `Literal` band, `field_validator`
  asserting band↔score; `max_retries=3` feeds validation errors back for self-healing; `temperature=0`.
  The model is **not** told the rules score, so agreement is meaningful.
- **Never-fails guarantee:** one `try/except` funnels every failure (no key, network, schema-invalid)
  into a deterministic rules-only finding. Offline, a *labelled simulated* second opinion stands in.
- **Explainability = additive drivers that sum exactly to the score** (hand-rolled SHAP local-accuracy,
  zero deps, deterministic — LIME rejected as non-reproducible). Largest-remainder apportionment
  keeps integer drivers summing to the score even when capped at 100.
- **Audit:** append-only `AuditRecord` per decision with sha256 input fingerprint + config snapshot.

> Speaker note: Determinism and auditability are engineered in — Decimal money, seeded data, no wall-clock in predicates.

---

## Slide 4 — Challenges and Learnings

- **False-positive vs false-negative:** we bias toward escalation — the rules-only and low-confidence
  paths **never auto-clear**, and kill-switch flags escalate first. Missing a sanctioned entity is
  the unacceptable error; extra review is the accepted cost.
- **LLM non-determinism → deterministic guardrails:** an LLM can hallucinate a score, so it is
  advisory only. Pydantic validation + retry + a rules-only fallback bound it; the auditable number
  always comes from code, never the model.
- **Explainability is a hard requirement, not a nice-to-have:** regulators inspect *closures* too, so
  every decision — clear and escalate alike — carries drivers that reconcile exactly to the score.
- **Calibration is a first-class surface:** all weights, floors, windows, bands, and routing
  thresholds live in one `config.py` dict — the knob a real risk team recalibrates against outcomes.
- **Honest reflection:** offline the "second opinion" is a *deterministic simulation*, clearly labelled
  in audit metadata — it demonstrates the confidence/auto-clear mechanics without pretending to be a
  live model. With a real key the same seam calls Claude Haiku unchanged.

> Speaker note: The interesting engineering is the guardrails — making a non-deterministic model safe inside a deterministic, auditable pipeline.

---

## Slide 5 — Demo Summary and Next Steps

- **End-to-end demo:** generate 20 dossiers → ranked triage **Queue** (risk bars) → **Case detail**
  (driver bars + rationale + evidence + approve/escalate) → append-only **Audit** log. Current split:
  **5 AUTO_CLEAR / 9 REVIEW / 6 ESCALATE**.
- **Worked contrast:** `CUST_018` (Iranian arms dealer, exact OFAC match + structuring) →
  `SANCTIONS_MATCH` override → score 100 / ESCALATE / signoff required; `CUST_000` (domestic teacher,
  benign) → score 0 / AUTO_CLEAR. Same engine, both ends of the queue.
- **Next steps, given more time:**
  - Real **adverse-media / sanctions API feeds** (World-Check, OFAC, Dow Jones) replacing fixtures.
  - **ML-tuned thresholds** — calibrate weights/cutoffs against labelled outcomes instead of hand-set values.
  - **Case management** — assignment, SLAs, disposition history, escalation workflow.
  - **Feedback loop** — analyst decisions retrain scoring and recalibrate confidence over time.

> Speaker note: The POC proves the safe pipeline end-to-end; production is swapping fixtures for live feeds and closing the analyst feedback loop.
