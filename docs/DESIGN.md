# Design — Financial Risk Signal Aggregator

Product design & architecture. Depth (code shapes, sources, pitfalls) lives in `research/RESEARCH_BRIEF.md`.

## Problem

Compliance/risk analysts manually review fragmented signals (KYC, transactions, sanctions/PEP, adverse
media) under ~95% false-positive noise, with inconsistent per-analyst scoring. We join per-customer
signals, score them deterministically, rank them, and explain each finding defensibly.

## Architecture (single-process Streamlit app)

```
data/generate.py ──► data/dossiers.json ──►  src/engine.py  ──► src/audit.py (append-only store)
                                              │  │   │  │                 │
   src/config.py (tuning knob) ──────────────►│  │   │  │                 ▼
   src/rules.py (deterministic, SOURCE OF TRUTH)   │  │            src/app/ (Queue / Case / Audit)
   src/llm.py (advisory cross-check, never-fails)  │  │
        reconcile(confidence) ──► route() (HITL) ──┘  └──► drivers (sum to score) for explainability
```

**Per-customer flow:** dossier → `rules.score_customer()` (score/band/findings, the auditable number)
→ `llm.crosscheck()` (independent score+confidence+rationale, schema-locked, advisory) →
`engine.reconcile()` (confidence = agreement; disagreement or rules-only → force human) →
`engine.route()` (kill-switch first, then band thresholds) → one append-only `AuditRecord`.

## Data model — 5 families per dossier

1. **KYC/identity** — name, DOB, nationality, occupation, id_doc, onboarded date, completeness.
2. **Customer risk factors** — geography, product, PEP status, entity type, tenure.
3. **Transactions** — benign base stream + at most one injected typology.
4. **Screening** — sanctions hits (exact vs fuzzy `match_score`), PEP, adverse-media snippets (sentiment+recency).
5. **Robustness metadata** — missing/extra-doc flags (the never-fails testers).

## Scoring (deterministic — `rules.py`)

Two-layer factors (profile/static + activity/dynamic), each a pure fn → `Finding|None`.
**Order:** overrides/vetoes FIRST → weighted sum normalise 0–100 → bands (0–35 low / 36–65 med / 66–100 high).
Typology detectors are temporal (pandas per-customer): `structuring`, `layering`, `round_trip`, `dormant_spike`.
Every `Finding` carries `evidence` (txn ids, amounts, window).

## Never-fails LLM (`llm.py`)

`instructor.from_anthropic` + Pydantic `RiskFinding` (`Field(ge=0,le=100)`, `Literal` band, `field_validator`
band↔score), `max_retries=3` (self-healing), `temperature=0`. One `try/except` → rules-only finding on any
failure. LLM is advisory only; never writes the arithmetic.

## HITL routing + confidence (`engine.py`)

`confidence = 1 − |rules−llm|/100` (forced LOW on rules-only). `route()`: kill-switch (`sanctions_exact_match`,
`pep_confirmed`) → ESCALATE+signoff; else auto-clear <15 / junior <40 / senior <70 / escalate ≥70. Rules-only
never auto-clears (≥ junior). MED band or rules↔LLM disagreement → analyst queue.

## Explainability + audit

Additive **driver contributions that sum to the score** (hand-rolled SHAP local-accuracy) → per-driver bars.
**Append-only `AuditRecord`** per decision (clears + escalates): who/what/why/when + drivers + override_of +
signoff_by + ruleset_version + input_fingerprint (sha256). Maker-checker on ESCALATE.

## UI (`src/app/`)

`st.Page`/`st.navigation`, `layout="wide"`. Pages: **Queue** (ranked `st.dataframe` + `ProgressColumn`,
`on_select` single-row) → **Case detail** (dossier + driver bars + rationale + evidence + approve/escalate
callbacks) → **Audit** (decision log). NL box → whitelisted Pydantic filter spec → pandas mask (never eval).

## Standout vs the crowd

Multi-source dossier per person · never-fails engine with hard vetoes · confidence-gated HITL · additive
explainability + audit trail · live robustness demo on missing/extra-doc profiles.
