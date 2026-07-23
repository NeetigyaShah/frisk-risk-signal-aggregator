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
