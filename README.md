# Financial Risk Signal Aggregator

An AML / financial-crime **risk-triage** prototype (HyperVerge take-home). It ingests a
fragmented, multi-source dossier per customer and produces a **prioritised, risk-scored analyst
triage queue** with per-finding rationale, confidence-gated human routing, additive explainability,
and an append-only audit trail.

## Setup

```bash
python -m venv .venv && . .venv/Scripts/activate     # Windows: .venv\Scripts\activate
pip install -e ".[llm,ui,observability,dev]"          # installable package + optional extras
frisk generate                     # regenerate data/dossiers.json (seeded, deterministic) + self-check
pytest                             # 16 tests: typologies, override, fallback, driver-sum, gating, store
streamlit run src/frisk/ui/Home.py # Queue -> Case detail -> Audit

# handy: frisk score --offline   (rules-only ranked queue)   ·   frisk warm   (populate the LLM cache)
```

**Package layout** (`src/frisk/`): `config/` (pydantic-settings + tuning constants) · `core/` (models, rules,
engine) · `ai/` (providers boundary, prompts, crosscheck, LangGraph orchestrator) · `data/` (generate,
loaders, store, audit) · `hitl/` (Redis review queue + feedback) · `pipeline/` · `query/` · `ui/`.

### Modes & the human-in-the-loop

- **`engine_mode=llm`** (default): the LLM scores each customer via the 5-step graph (reading structured
  *and* unstructured docs); a **composite confidence** decides routing. Low confidence → the case is pushed to a
  **Redis review queue** and a human sets the correct score, which is fed back as a few-shot example.
  `engine_mode=hybrid` restores deterministic rules as the source of truth.
- **Data** lives in `data/customers/CUST_xxx/` — structured (`kyc.json`, `account.json`, `transactions.csv`,
  `screening.json`) + unstructured (`id_document.txt`, `rm_notes.txt`, `adverse_media_*.txt`, `correspondence.txt`).
  Regenerate with `frisk generate`.
- **Review queue broker:** `docker run -d --name frisk-redis -p 6379:6379 redis:7-alpine` (falls back to an
  in-memory queue if Redis is down). Offline (`LLM_MODE=off`) sends every non-sanctioned case to the human
  queue — a full demo of the review panel with no API key.

The demo runs **fully offline** — no API key required (see *Data assumptions*). To use the real
LLM cross-check, set `ANTHROPIC_API_KEY`; the engine auto-detects it.

## Approach — a "never-fails" engine

Deterministic **rules are the auditable source of truth**; the LLM is an **independent, advisory
cross-check**; a **rules-only fallback** guarantees the engine never returns nothing.

1. **Rules** (`src/rules.py`) — pure `Dossier -> Finding|None` functions. Order is non-negotiable:
   **overrides/vetoes first** (sanctions exact match, PEP-in-high-risk-geo force score 100/HIGH),
   then a **weighted additive sum normalised 0-100**, then bands (LOW ≤35 / MED ≤65 / HIGH).
   Temporal **typology detectors**: structuring (≥3 sub-floor cash deposits in 7 days), layering
   (≥3 ~80%-forwarded hops), round-trip, dormant-then-spike. Every finding carries `evidence`
   (txn ids / amounts / window).
2. **LLM cross-check** (`src/orchestrator.py`, `src/llm.py`) — a **5-step LangGraph orchestration**, not one
   fragile call: three domain analysts (KYC / transactions / screening) run **in parallel**, a synthesis node
   correlates them, and a verification node adversarially re-checks the score (chain-of-verification). Powered by
   **NVIDIA Nemotron-3-Ultra-550B** via LangChain's `ChatOpenAI` structured output (`temperature=0`, *not* told
   the rules score). Provider-configurable in `config.py` (`nvidia` / `gemini` / `anthropic`); `multi_step` and
   the single-call path are both selectable. Every node degrades independently; findings are disk-cached by prompt
   hash; the whole thing cascades graph → single call → rules-only, so nothing can raise into the engine.
   See **`docs/SCALING.md`** for how this runs at 10k+/day (gating + parallelism + a SQLite/Postgres read store).
3. **Reconcile + route** (`src/engine.py`) — `confidence = 1 − |rules−llm|/100`. Routing is
   **kill-switch first** (sanctions/PEP-high-geo → ESCALATE + named reviewer + signoff), else
   auto-clear <15 / junior <40 / senior <70 / escalate ≥70. The rules-only or missing-data path
   **caps confidence and never auto-clears**. Maker-checker signoff on every ESCALATE.
4. **Explainability + audit** — additive driver contributions that **sum exactly to the score**
   (hand-rolled SHAP-style, no `shap`/LIME). One append-only `AuditRecord` per decision (clears
   *and* escalates) with a sha256 input fingerprint.

## Tools

Python · pandas · numpy · Faker (synthetic data) · pydantic v2 + instructor + anthropic (LLM
boundary) · Streamlit (UI) · pytest. Stdlib `dataclasses`/`decimal`/`hashlib` for the engine and
audit core — no rules-engine DSL, no `shap`/LIME, no LangChain.

## Data assumptions

- **20 seeded synthetic customers** (`data/generate.py`, seed 42, fixed reference date → byte-identical
  output). No real PII. Five data families per dossier: KYC/identity, customer risk factors
  (geo/PEP/occupation/tenure), transactions (benign base stream + at most one injected typology),
  screening (sanctions/PEP/adverse-media, exact vs fuzzy `match_score`), and robustness metadata
  (missing/extra-doc fixtures).
- Class balance is **deliberately inverted** vs the real ~0.1% suspicious rate so every band and
  typology is exercised (6 LOW / 7 MED / 5 HIGH / 2 critical).
- **Offline second opinion:** with no `ANTHROPIC_API_KEY`, a *deterministic simulated* second
  opinion stands in (clearly labelled in audit metadata) so the confidence / auto-clear mechanics
  still demo. Money is `Decimal` end-to-end; no `datetime.now()`/random inside rule predicates.

## Worked example (input → output)

**Input — `CUST_018`:** Iranian (`IR`) *arms dealer*, screening carries an **exact OFAC SDN
sanctions match** (`match_score = 1.0`), plus a **structuring cluster** (≥3 cash deposits each just
under the £10,000 floor within 7 days).

**Output:**

| field | value |
|-------|-------|
| override | `SANCTIONS_MATCH` (kill-switch, evaluated before the sum) |
| score / band | **100 / HIGH** |
| disposition | **ESCALATE** → `named_reviewer`, `requires_signoff = True` |
| top driver | `SANCTIONS_MATCH` (+100) |
| rationale | cites the exact sanctions hit; structuring corroborates |
| audit | append-only record with sha256 input fingerprint |

**Contrast — `CUST_000`:** domestic GB *teacher*, complete KYC, benign transactions, no adverse
media → **score 0 / LOW → AUTO_CLEAR** (no signoff). Same engine, opposite end of the queue.

Current disposition split across the 20: **5 AUTO_CLEAR / 9 REVIEW / 6 ESCALATE**.
