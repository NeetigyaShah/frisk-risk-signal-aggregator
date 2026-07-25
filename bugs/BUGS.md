# Bug Log — master

Every bug goes here (newest first). When a single feature accrues several bugs, split it into
`bugs/<feature>.md` and link it from this file.

## Entry format
```
- BUG-NNN | YYYY-MM-DD | OPEN|RESOLVED | <feature/module>
  - Symptom:    what was observed
  - Root cause: the underlying reason (not the symptom)
  - Fix:        what changed (file:line if useful)
```

## Per-feature bug files
- (none yet — add as `bugs/<feature>.md` when needed)

## Open
- (none)

## Resolved
- BUG-003 | 2026-07-24 | RESOLVED | nlquery / app
  - Symptom:    `python nlquery.py` crashed with UnicodeEncodeError on `≥`/`≤` in Windows cp1252 console.
  - Root cause: non-ASCII glyphs printed to a legacy code-page terminal.
  - Fix:        use ASCII `>=`/`<=` in `explain()` (src/nlquery.py). Streamlit (UTF-8) was unaffected.
- BUG-002 | 2026-07-24 | RESOLVED | app
  - Symptom:    audit download button referenced `pd.io.json.dumps` (removed in modern pandas).
  - Root cause: stale pandas API.
  - Fix:        use stdlib `json.dumps(r, default=str)` (src/app/Home.py).
- BUG-001 | 2026-07-24 | RESOLVED | llm
  - Symptom:    `SyntaxError: name '_client' assigned before global declaration` in llm.py __main__.
  - Root cause: needless `global` at module scope where assignment already rebinds the global.
  - Fix:        removed the `global` statement.

## PERF-01 — Case Comparison / dashboard slow to load
**Date:** 2026-07-25 · **Status:** FIXED
**Symptom:** Case Comparison page noticeably slow; dashboard sluggish.
**Root cause:** `api/service._patterns()` called `ai.tools.build_tools()` purely to run one heuristic
function. `build_tools()` constructs 9 LangChain `StructuredTool` objects (Pydantic schema
introspection) on every call — measured **375ms/call vs 0.9ms** for the raw detectors (~417x).
Paid once per customer per page load (20x on /api/queue and /api/analytics).
**Fix:** new `ai.tools.scan_patterns()` runs the detectors directly, no tool wrapping; `_patterns()`
uses it plus a per-customer cache invalidated on re-ingest. `build_tools()` unchanged for the agent.
**Verified:** 20 customers 7500ms -> 5ms cold, 0.01ms warm.

## PERF-02 — agent latency ~90s/customer; "why isn't parallel actually parallel"
**Date:** 2026-07-25 · **Status:** FIXED (mitigated)
**Symptom:** two customers scored concurrently took 76.7s and 90.8s vs ~15-30s solo.
**Investigation (measured, not assumed):**
- Both threads started at t=0.0s -> genuinely concurrent, no serialization bug in our code.
- **First hypothesis (rate limiting) was WRONG.** Queried the OpenRouter key: no request-rate cap
  (`rate_limit.requests: -1`, deprecated field), credit-based only. Empirically: 4 concurrent calls
  finished in 1.55s wall-clock vs 1.48s for a single call — zero throttling, zero 429s.
- **Actual cause: serial depth.** A realistic agent-sized call (9 tools bound, ~1.1k prompt tokens)
  takes **~3.2s**, not the ~1.5s of a trivial call. Audit-log analysis showed the agent used a mean
  of **15.0 of its 16 step budget** every run — `query_transactions` 4.5x/customer,
  `find_txn_patterns` 3x/customer — i.e. it spends whatever budget it is given. 15 x 3.2s ~= 48s,
  which matches the observed runtime.
**Fixes:**
1. Pre-load the facts the agent always fetches (KYC, documents list, txn aggregates, pattern
   candidates, first 60 transactions) into the opening message.
2. **Remove those tools from the bound toolset.** Prompt-only instruction ("do not re-request these")
   was measured to be *ignored* — the agent still spent 15 steps re-fetching. Structural removal works.
3. Reduce `agent_max_steps` 16 -> 12 and fire the finalize nudge at 2 remaining (was 3). 8 was tested
   and too tight: the agent hit the cap without finalizing -> false PENDING_REVIEW at confidence 0.
4. `llm_concurrency` set to 24 (safety backstop against runaway fan-out, NOT a throttle) after the
   measurements showed concurrency was never the bottleneck.
