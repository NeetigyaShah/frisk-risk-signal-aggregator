# Deck screenshots

Captured from the live app (22 customers scored by the real LLM). Use these in the 5-slide deck —
the mapping below matches `docs/deck/SLIDES.md`.

| File | Shows | Use on slide |
|---|---|---|
| `01-dashboard.png` | Full dashboard — score distribution, 27% auto-cleared, KPI row, 3 charts, typology legend | **5** (Results) · also good as a title-slide backdrop |
| `02-ranked-queue.png` | The prioritised risk queue — cases ranked highest-risk-first with signals + confidence | **1** (Problem → the output that solves it) |
| `03-case-specialists.png` | Case drawer top — score 83/ESCALATE + the three **parallel specialist opinions** | **2** (Architecture — the parallel stage) |
| `04-tool-trace.png` | ⭐ The **serial tool-call trace**, cited evidence, memory injected, detected patterns | **3** (Input → Agent loop → Output) — *the key visual* |
| `05-memory-history.png` | Memory-injected panel + per-customer history + transactions with anomalies highlighted | **2** (memory tiers) or **3** |
| `06-review-queue.png` | Low-confidence case routed to a human, with specialist disagreement visible | **4** (Human-in-the-loop) |
| `07-teach-the-model.png` | ⭐ The correction form — "agent proposed 45 at confidence 0.50, below threshold" + score slider | **4** — *the key HITL visual* |
| `08-case-comparison.png` | Two cases side by side, 75-point gap, signals unique to each | **5** (or a spare/appendix slide) |
| `09-sar-list.png` | Cases that may warrant a filing, each with a "Draft SAR" action | **5** (deliverables) |
| `10-sar-document.png` | ⭐ The generated **Suspicious Activity Report** — formal document, DRAFT watermark, signature block | **5** — *strongest "real output" proof* |
| `11-ingest-batch.png` | Ingest page — 40 sample profiles, batch parallel scoring, file upload | **2** (Ingest stage) |
| `12-audit-trail.png` | Append-only audit log of every decision | **4** (auditability) |

## Suggested minimum set (if you want one image per slide)

1. **Problem/Objective** → `02-ranked-queue.png`
2. **Architecture** → `03-case-specialists.png`
3. **Input → Loop → Output** → `04-tool-trace.png`
4. **Human-in-the-loop** → `07-teach-the-model.png`
5. **Results** → `01-dashboard.png` (+ `10-sar-document.png` if you have room)

## Notes
- All synthetic data — no real customer information.
- `CUST_018` (the arms dealer) is the strongest example: 4 sub-threshold cash deposits in 6 days,
  score 83, ESCALATE at 0.85 confidence, with the structuring transaction IDs cited as evidence.
