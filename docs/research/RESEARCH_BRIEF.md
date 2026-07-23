# Research Brief — Financial Risk Signal Aggregator

> Consolidated output of the ultracode deep-research Workflow (`wf_4b4ee379-771`, 6 research agents + synthesis).
> AML risk-triage POC (Python/Streamlit, pro-code). Decision-oriented; this drives the implementation.

---

## 1. Recommended architecture (components + data flow)

Single-process Streamlit app, six modules, no services, no DB server. SQLite/JSONL for the audit trail.

```
generate.py    -> dossiers.json        (seeded synthetic 20-profile fixture)
config.py      -> weights/floors/windows/bands/thresholds (one dict, the tuning knob)
rules.py       -> FACTOR_RULES + TYPOLOGY_RULES (pure fns -> Finding|None); evaluate()
llm.py         -> instructor+pydantic cross-check, try/retry/fallback -> always valid
engine.py      -> orchestrates: rules -> llm crosscheck -> reconcile -> route() -> AuditRecord
audit.py       -> append-only sqlite3/JSONL writer + reader
app/           -> st.navigation: Queue / Case detail / Audit
```

**Data flow per customer:** dossier (KYC + txns + sanctions/PEP + adverse-media) → deterministic rules produce `score/band/findings` (source of truth) → LLM cross-check returns independent `score+confidence+rationale` (advisory, schema-locked) → reconcile (agreement → confidence; disagreement or rules-only → force human) → `route()` tiers the disposition with a kill-switch override gate → one append-only `AuditRecord` per decision (clears and escalates alike) → Streamlit reads the decision store as the analyst queue.

**Key invariant:** the rules score is the auditable number; the LLM never writes the arithmetic. The engine never raises to the caller — the rules-only path always returns a valid result.

## 2. Scoring model (rules + weights + bands + typologies)

Two-layer factor model, each factor a pure function → `Finding|None`, ordinal points:
- *Profile/static:* entity type, geography (high-corruption/high-risk jurisdiction), PEP, occupation, KYC completeness, tenure.
- *Activity/dynamic:* cash intensity, velocity, injected typology, adverse-media volume/recency.

**Order of operations (non-negotiable):** (1) overrides/vetoes FIRST — sanctions exact match, PEP+high-risk-geo → force HIGH/ESCALATE regardless of arithmetic; (2) weighted sum → normalise 0–100 (weights sum to 1.0, in config); (3) bands 0–35 Low, 36–65 Medium, 66–100 High.

```python
@dataclass(frozen=True)
class Finding:
    code: str; points: int; weight: float
    is_override: bool; rationale: str; evidence: dict

def score_customer(c) -> RiskResult:
    findings = [f for f in (r(c) for r in FACTOR_RULES + TYPOLOGY_RULES) if f]
    if any(f.is_override for f in findings):
        return RiskResult(100, "HIGH", findings)
    score = round(min(100, sum(f.points*f.weight for f in findings)/MAX_WEIGHTED*100))
    band = "HIGH" if score>=66 else "MED" if score>=36 else "LOW"
    return RiskResult(score, band, findings)
```

**Typology detectors** — temporal, pandas per-customer (proximity-in-time, not amount alone):
- **structuring** — ≥3 cash txns in `[0.8×FLOOR, FLOOR)` in a 7-day rolling window, summing > FLOOR.
- **layering** — ≥3 hops, each forwarding ~90%, distinct counterparties.
- **round_trip** — funds out then back to origin via a different counterparty within a window.
- **dormant_spike** — long inactivity then sudden burst.

Every `Finding` carries `evidence` (txn ids, amounts, window). `Decimal` for money; no `datetime.now()`/random inside predicates; a throwing predicate degrades to a recorded finding, never a crash.

## 3. Never-fails LLM guardrail (validate → retry → fallback)

- **`instructor` + `pydantic` v2** is the whole boundary. `client = instructor.from_anthropic(Anthropic())`; call with `response_model=RiskFinding, max_retries=3`. Instructor feeds the `ValidationError` back into each retry (self-healing: ~60% blind → >95% with error feedback).
- **Semantic cross-checks live in Pydantic** — `Field(ge=0, le=100)`, `Literal` bands, `@field_validator` asserting band agrees with score. A raised `ValueError` becomes retry feedback automatically.
- **One `try/except` wraps the call and always returns the rules-only finding** — the never-fails guarantee.
- **temperature 0**; log model version + prompt hash + retry count + path (`rules+llm` vs `rules_only`) + confidence.

```python
class RiskFinding(BaseModel):
    customer_id: str
    score: int = Field(ge=0, le=100)
    band: Literal["low","medium","high"]
    rationale: str = Field(min_length=10)

def crosscheck(features, rules_score) -> RiskFinding:
    try:
        return client.chat.completions.create(model="claude-...",
            response_model=RiskFinding, max_retries=3,
            messages=[{"role":"user","content":build_prompt(features)}])
    except Exception as e:
        log.warning("llm_path_failed", error=str(e))
        return rules_only_finding(features, rules_score)   # always valid
```

Skip `tenacity` (instructor covers retry), skip LangChain/PydanticAI. Never `df.query()`/`eval` on LLM text. One check: mock the client to raise, assert fallback returns a valid `RiskFinding`.

## 4. HITL tiering + audit-record + explainability

**Four bands + override gate** (thresholds in config):

```python
HARD_ESCALATE = {"sanctions_exact_match", "pep_confirmed"}
def route(score, drivers, flags) -> Disposition:
    if flags & HARD_ESCALATE:                       # kill-switch FIRST
        return Disposition("ESCALATE", tier="named_reviewer", requires_signoff=True)
    if score < 15: return Disposition("AUTO_CLEAR", tier="none")
    if score < 40: return Disposition("REVIEW",  tier="junior")
    if score < 70: return Disposition("REVIEW",  tier="senior")
    return Disposition("ESCALATE", tier="senior", requires_signoff=True)
```

**Confidence = engine agreement:** `confidence = 1 - abs(rules_score - llm_score)/100` when both ran; forced LOW on the rules-only fallback path. A degraded path must never silently auto-clear — rules-only caps confidence and forces ≥ junior review. MED band or rules↔LLM disagreement → analyst queue.

**Explainability = additive drivers as our SHAP.** Each rule contributes signed points that sum to the score (SHAP local-accuracy, hand-rolled, zero deps, deterministic). Per-driver bars in Streamlit — the analyst explanation and the audit evidence, unified. Avoid LIME (non-deterministic → disqualifying); skip `shap` dep.

**One append-only `AuditRecord` per decision** (clears and escalates alike — regulators inspect whether *closures* are defensible):

```python
@dataclass
class AuditRecord:
    record_id; customer_id; ts               # WHEN
    actor                                    # WHO "engine:v3" | "analyst:jdoe"
    action                                   # WHAT AUTO_CLEAR|REVIEW|ESCALATE|OVERRIDE
    score; confidence; engine_path           # rules+llm | rules_only
    band; thresholds                         # WHY (band + config snapshot)
    drivers: list[dict]                      # [{feature, contribution, value}] sums to score
    rationale; override_of=None; signoff_by=None   # maker-checker on ESCALATE
    ruleset_version; input_fingerprint       # sha256 of canonical input → reproducibility
```

Two invariants under test: `route()` never auto-clears a kill-switch flag; driver contributions sum to score.

## 5. Data model & synthetic-generator

One seed-driven `generate.py`, declarative 20-row profile table. Seed all RNGs once — `Faker.seed(n); random.seed(n); np.random.default_rng(n)` — thread one `rng`; never reseed inside helpers.

Five data families: (1) KYC (Faker, locale per nationality; high-risk nationality/occupation, incomplete onboarding as signals); (2) sanctions/PEP (exact vs fuzzy `match_score`); (3) adverse media (0–N snippets, sentiment+recency); (4) transactions (benign base — salary credit, direct debits, poisson-spaced card spend, lognormal amounts + occasional round numbers — with one injected typology); (5) robustness metadata (missing/extra-doc flags).

**Mix:** ~6 low, ~7 medium, ~5 high, ~2 critical; one typology each for high/critical, benign elsewhere. Deliberately invert real-world imbalance (PaySim ~0.13%, SAML-D ~0.10% suspicious) to exercise every band. Four typologies as pure functions (fan-out/fan-in/cycle/scatter-gather from AMLSim/SAML-D — skip the Java simulator). Robustness fixtures: ~2 `missing_docs` (drop KYC id or txns), ~1 extra-doc. `__main__` self-check: same seed → identical dossier hash; each band populated; each injected typology detectable by its rule. Exclude derived balance fields from scoring (PaySim balance-leak caveat). Libs: Faker + numpy `default_rng` + pandas + dataclasses; `networkx` optional (validate subgraphs only).

## 6. Streamlit UI

- **Nav:** `st.Page` + `st.navigation` (≥1.36), not legacy `pages/`. `st.set_page_config(layout="wide")` first. Pages: Queue / Case detail / Audit.
- **Master→detail via native `st.dataframe`** (skip st-aggrid for 20 rows): `on_select="rerun", selection_mode="single-row"`, risk as `column_config.ProgressColumn`. Selection in namespaced `session_state`; navigate with `st.switch_page()` — never markdown/HTML links (they reset state). Guard detail: `if case_id is None: st.stop()`.
- **HITL via `on_click` callbacks** writing `session_state.decisions[cid]`.
- **Colour:** `ProgressColumn` in queue; `Styler.map` in detail (Styler outside cached fns). Driver contributions as `st.progress`/bar chart.
- **NL query → SAFE structured filter, never executable code.** LLM emits a validated Pydantic filter spec with whitelisted `Literal` fields/ops; build the pandas mask via a fixed op-map. Never `df.query()`/`eval`/PandasQueryEngine on model text.
- **Caching:** `@st.cache_data` for DataFrames/scores; `@st.cache_resource` for the LLM client/engine; prefix un-hashable args (Styler, client) with `_`.

## 7. Libraries (locked)

stdlib `dataclasses`/`decimal`/`hashlib`/`sqlite3` (engine + audit, ~40-line core, no rules-engine dep) · pandas · numpy (`default_rng`) · Faker · instructor · pydantic v2 · anthropic (temp 0) · streamlit ≥1.36 · pytest.
**Skipped:** rules-engine DSLs (`business-rules`, `durable_rules`, json-logic), `tenacity`, LangChain/PydanticAI, `st-aggrid`, `shap`/LIME, PandasAI/PandasQueryEngine.

## 8. Top pitfalls

- Weighted average masking a hard signal → overrides/vetoes before the sum.
- Score-only routing ignoring the override gate → silently auto-clears a sanctions hit (classic failure).
- Degraded path auto-clearing → rules-only must cap confidence and force review.
- LLM in the scoring arithmetic → it's advisory/logged/gated only.
- Blind retry / retrying non-retryable errors → feed validation error back; classify transient vs schema vs business.
- Letting the LLM path throw → one try/except catches everything and falls back.
- Explanations detached from the score → enforce driver contributions sum to score; LIME disqualified.
- Mutable audit history → append-only; every finding carries evidence.
- Documenting only escalations → closures must be equally defensible.
- Non-determinism creep → dict order, `float` money, `datetime.now()`/random in predicates, reseeding in helpers.
- Streamlit traps → markdown links wipe state; `set_page_config` not first; caching un-hashable args; balance fields leaking the label.
- Fake-looking data → uniform amounts; structuring not clustered under a named floor; layering with <3 hops.

## 9. Build decisions locked in

1. Registry-of-pure-functions rules engine in stdlib (~40 lines). No rules-engine library.
2. Overrides first → weighted 0–100 → bands, exactly that order; sanctions/PEP as `is_override` rules.
3. Single `config.py` dict for floors, weights, windows, band cutoffs, routing thresholds.
4. Rules score = source of truth; LLM = logged, confidence-gated cross-check only.
5. `instructor` + Pydantic v2 boundary: `response_model` + `max_retries=3` + `field_validator`; temperature 0.
6. One `try/except` returning rules-only finding = the never-fails guarantee; log path + confidence + retries.
7. Four routing bands + kill-switch gate (auto-clear <15, junior 15–40, senior 40–70, escalate ≥70); rules-only forces ≥ junior.
8. `confidence = 1 - |rules−llm|/100`; disagreement or fallback → human queue; maker-checker signoff on ESCALATE.
9. Additive drivers that sum to the score as explainability + audit evidence. No shap/LIME.
10. One append-only `AuditRecord` per decision (who/what/why/when + drivers + override_of + signoff + ruleset_version + input_fingerprint), for clears and escalates.
11. Streamlit native `st.dataframe(on_select)` + `st.Page`/`st.navigation`, `layout="wide"`; NL → whitelisted Pydantic filter spec → pandas mask; `cache_data` raw + `cache_resource` client.
12. One seeded `generate.py`, declarative 20-profile table, 4 typologies as pure functions, 5 families, missing/extra-doc fixtures; `__main__` self-check on determinism + band coverage + typology detectability. One golden pytest per typology and per override.

**Key sources:** [Flagright risk scoring](https://www.flagright.com/post/how-to-do-risk-scoring) · [azakaw CRR](https://www.azakaw.com/blog/customer-risk-rating) · [Sanction Scanner TM rules](https://www.sanctionscanner.com/blog/transaction-monitoring-rules-and-scenarios-a-practitioners-guide-to-effective-detection-logic-1371) · [DZone deterministic engines](https://dzone.com/articles/how-deterministic-rules-engines-improve-compliance) · [Instructor](https://python.useinstructor.com/) · [structured feedback repair (arxiv)](https://arxiv.org/html/2607.14167v1) · [KLA AML control/evidence map](https://kla.digital/blog/aml-agent-control-and-evidence-map) · [CrowdStrike SHAP](https://www.crowdstrike.com/en-us/blog/ai-decision-making-with-shap/) · [Streamlit multipage nav](https://docs.streamlit.io/develop/concepts/multipage-apps/page-and-navigation) · [IBM AMLSim](https://github.com/IBM/AMLSim/wiki/Transaction-Model:-Alert-Model) · [SAML-D](https://github.com/BOztasUK/Anti_Money_Laundering_Transaction_Data_SAML-D) · [PaySim](https://www.kaggle.com/datasets/ealaxi/paysim1)
