# 3-Minute Demo Script (screen recording)

Run once before recording:
```bash
python data/generate.py           # deterministic dataset
streamlit run src/app/Home.py     # opens http://localhost:8501
```
(Optional: `set ANTHROPIC_API_KEY=...` to use live Claude instead of the simulated second opinion.)

## Beats

**0:00 — The problem (10s).** "Compliance analysts drown in fragmented signals and ~95% false positives. This tool aggregates KYC, transactions, sanctions/PEP and adverse media per customer into one ranked, explained, auditable queue."

**0:15 — The queue (40s).** Show the tiles: 20 customers → **6 escalate / 9 review / 5 auto-cleared**. "The engine already cleared 5 low-risk customers with no analyst time, and pushed the 6 riskiest to the top." Point at the risk bars and 🔴/🟡/🟢 dispositions. Run a query: type **"high-risk customers with a sanctions hit"** → 2 results. Then **"everything escalated"** → 6.

**0:55 — A case (60s).** Open **CUST_018** (Mr Hugh Taylor). "Score 100, HIGH, Escalate to MLRO with mandatory sign-off." Point to the red **kill-switch** banner: "An exact OFAC sanctions match is evaluated *before* the weighted average — a hard signal can never be averaged away." Show the **driver bars**: "Every point is attributable; the drivers sum exactly to the score — that's the analyst's rationale and the audit evidence in one." Expand a finding to show the **evidence** (txn ids). Scroll to the dossier: KYC, screening, transactions.

**1:55 — Never-fails + HITL (40s).** Open a low-risk case (e.g. CUST_000): "Auto-cleared, high confidence." Then note CUST_004: "This dossier is *missing its transactions* — the engine still returns a score, but caps confidence and refuses to auto-clear. It degrades, it never blanks." Mention: "If the LLM API is down, it falls back to rules-only — same guarantee."

**2:35 — Audit + close (25s).** Open **Audit Trail**: "Every decision — clears and escalates alike — is append-only with an input fingerprint and ruleset version, so closures are as defensible as escalations." Close: "Deterministic rules are the auditable source of truth; the LLM is a confidence-gated second opinion; a human signs off on every escalation."

## Key talking points (if asked)
- Rules = source of truth; LLM never writes the arithmetic.
- Overrides → weighted 0–100 → bands; typologies are temporal (structuring/layering/round-trip/dormant-spike).
- Confidence = rules↔model agreement; disagreement or missing data → human queue.
- 20 seeded synthetic profiles; fully offline; no real/PII data.
