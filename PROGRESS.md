# PROGRESS — Financial Risk Signal Aggregator

**Last updated:** 2026-07-24 · **Deadline:** 2026-07-25
**Overview:** see `CLAUDE.md`. **Design:** `docs/DESIGN.md`. **Research:** `docs/research/RESEARCH_BRIEF.md`.

## Current phase
**COMPLETE** — all phases done and verified. Remaining human step: record the ≤3-min demo
(script in `docs/DEMO_SCRIPT.md`) and submit.

## Status board
- [x] Brainstorm + agreed design
- [x] Deep research brief (ultracode Workflow) → `docs/research/RESEARCH_BRIEF.md`
- [x] Approved plan (`~/.claude/plans/ok-do-so-as-shimmering-pizza.md`)
- [x] Phase 0: persistence infra (CLAUDE.md, PROGRESS.md, DESIGN.md, bugs/, requirements.txt)
- [x] Phase 1 spine: `config.py` → `models.py` → `data/generate.py` → `rules.py` → `llm.py` → `engine.py` + `audit.py`
- [x] Phase 1: golden tests (12 pass)
- [x] Phase 2 leaves: Streamlit UI (verified in-browser) · nlquery · README + 5-slide deck (deck.pptx)
- [x] Phase 3: e2e verified (generator, tests, engine, self-checks, UI screenshots)
- [ ] Human: record ≤3-min demo (see `docs/DEMO_SCRIPT.md`), submit deck + README + demo

## Verified so far
- Generator deterministic; 20 dossiers; bands aligned to expectations.
- Rules drivers sum to score; overrides force HIGH/ESCALATE.
- Engine dispositions: 5 AUTO_CLEAR / 9 REVIEW / 6 ESCALATE (offline sim path).
- Never-fails: no-key + raising-client both fall back to a valid finding.
- Kill-switch and missing-data never auto-clear.

## Next actions
1. Build `src/nlquery.py` (NL → whitelisted filter spec).
2. Build `src/app/` Streamlit UI (Queue / Case detail / Audit).
3. README + 5-slide deck (parallel subagent).
4. Phase 3: e2e verify + demo.

## Key design decisions (see DESIGN.md / RESEARCH_BRIEF.md for full)
- Multi-source dossier per person (5 data families), not per-transaction-row.
- Deterministic rules = source of truth; LLM = advisory confidence-gated cross-check; rules-only fallback.
- Order: overrides/vetoes → weighted 0–100 → bands (0–35 low / 36–65 med / 66–100 high).
- HITL routing: kill-switch first, then auto-clear <15 / junior <40 / senior <70 / escalate ≥70; rules-only forces ≥ junior.
- `confidence = 1 − |rules−llm|/100`; maker-checker signoff on ESCALATE.
- Additive drivers sum to score (hand-rolled SHAP, no shap/LIME).
- Append-only `AuditRecord` per decision (clears + escalates) with sha256 input fingerprint.
- Single `config.py` dict = the tuning knob; `Decimal` money; seeded determinism.
- Stack: pandas, numpy, Faker, pydantic v2, instructor, anthropic (temp 0), streamlit ≥1.36, pytest.

## Changelog
- 2026-07-24: Git initialised; dirs + .gitignore created.
- 2026-07-24: Ultracode research Workflow (6 agents + synthesis) completed; brief saved.
- 2026-07-24: Plan approved; task list created (#1–#11).
- 2026-07-24: Phase 0 started — RESEARCH_BRIEF.md, CLAUDE.md, PROGRESS.md written.
- 2026-07-24: Phase 1 spine built + calibrated (config, models, generate, rules, llm, engine, audit).
- 2026-07-24: 12 golden tests pass. Phase 1 complete. Starting Phase 2.
- 2026-07-24: Phase 2 — nlquery (safe whitelisted filter), Streamlit UI (Queue/Case/Audit) verified in-browser, README + 5-slide deck (deck.pptx) via subagent.
- 2026-07-24: Phase 3 — full e2e verification green (5/9/6 dispositions); screenshots + DEMO_SCRIPT.md. BUILD COMPLETE.
