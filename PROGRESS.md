# PROGRESS — Financial Risk Signal Aggregator

**Last updated:** 2026-07-24 · **Deadline:** 2026-07-25
**Overview:** see `CLAUDE.md`. **Design:** `docs/DESIGN.md`. **Research:** `docs/research/RESEARCH_BRIEF.md`.

## Current phase
**Phase 0 — foundations** (persistence infra + research brief saved). Next: Phase 1 spine.

## Status board
- [x] Brainstorm + agreed design
- [x] Deep research brief (ultracode Workflow) → `docs/research/RESEARCH_BRIEF.md`
- [x] Approved plan (`~/.claude/plans/ok-do-so-as-shimmering-pizza.md`)
- [~] Phase 0: persistence infra (CLAUDE.md, PROGRESS.md, DESIGN.md, bugs/, requirements.txt)
- [ ] Phase 1 spine: `config.py` → `models.py` → `data/generate.py` → `rules.py` → `llm.py` → `engine.py` + `audit.py`
- [ ] Phase 1: golden tests
- [ ] Phase 2 leaves: Streamlit UI · nlquery · README + 5-slide deck
- [ ] Phase 3: integrate, verify on all 20, record ≤3-min demo

## Next actions
1. Finish Phase 0 (this: DESIGN.md, bugs/BUGS.md, requirements.txt).
2. Phase 1 spine, sequential (shared schema). Build `config.py` + `models.py` first.
3. After each module: run its check, update this file.

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
