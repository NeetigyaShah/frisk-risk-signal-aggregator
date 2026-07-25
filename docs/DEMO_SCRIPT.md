# 2-Minute Demo Script

**Format:** screen recording with voiceover · **Target:** 2:00 (hard cap 3:00)

### Before you hit record
1. `frisk serve` — and **load the dashboard once** so the 20 customers are already scored.
   (First load scores live and takes 1–2 min; you do not want that on camera.)
2. Browser at ~1400px wide, zoom 100%, close devtools, hide the bookmarks bar.
3. Have these reachable in one click: Dashboard · a case · Review Queue · SAR Drafts.
4. Speak at ~150 wpm. The script below is ~300 words ≈ 2 minutes.

---

## 0:00 – 0:20 · The problem  *(Dashboard on screen, don't scroll yet)*

> "A compliance analyst opens one customer and finds five disconnected files — KYC, an account record,
> a transactions CSV, the relationship manager's notes, an ID scan. They read all of it, decide
> 'is this money laundering?', and repeat that hundreds of times. It's slow, it's inconsistent between
> analysts, and six months later nobody can explain why a case was cleared.
>
> This is Frisk. It does that first pass — and shows its work."

**On screen:** the dashboard, static. Let them take in the ranked queue and charts.

---

## 0:20 – 0:40 · What it produced  *(scroll slowly down the dashboard)*

> "Twenty-two customers, scored and ranked. Twenty-seven percent auto-cleared with zero human time.
> Three escalated. One the system wasn't confident about — that one went to a human, and I'll come
> back to it.
>
> The charts are risk bands, disposition, and the transaction patterns it detected — structuring,
> layering, round-tripping, dormant-then-spike."

**On screen:** scroll from hero chart → KPI row → the three charts → top of the ranked queue.

---

## 0:40 – 1:20 · How the agent actually works  *(click case #1, Mr Hugh Taylor)*  ← **the core**

> "Let's open the top case. Iranian arms dealer, score 83, escalated.
>
> First — three specialists ran **in parallel**: one on KYC, one on transactions, one on the documents.
> Each only sees its own slice, so they can't contaminate each other.
>
> Then their opinions go to one **agentic orchestrator** — and this is the important part — this is its
> actual investigation, step by step. It read the ID document, read the RM notes, filtered the
> transactions six different ways, ran the pattern scan, wrote itself a note, then finalised.
> **Eleven tool calls, all recorded.**
>
> And look at the evidence it cites — four specific transaction IDs. Those are four cash deposits,
> each just under the ten-thousand reporting threshold, made within six days. That's textbook
> structuring, and the agent had to point at the exact rows to claim it.
>
> The trace *is* the audit record. That's how you answer 'why was this escalated' six months later."

**On screen, in order:**
1. Top of drawer — score 83, ESCALATE, confidence 0.85
2. **Specialist opinions** — the three cards
3. **Tool-call trace** — scroll it slowly; this is the money shot
4. **Cited evidence** — point at the transaction IDs
5. Transactions table with anomalies highlighted red

---

## 1:20 – 1:45 · Human-in-the-loop  *(click Review Queue)*

> "Now the case it *wasn't* sure about. Confidence 0.55, below the threshold, so instead of guessing
> it routed to a person. The reviewer sees everything — where the specialists disagreed, the full
> trace, the agent's own notes.
>
> When I correct the score, three things happen: it's stored as a human-verified case that similar
> customers will retrieve later, it's distilled into a lesson injected into future prompts, and it
> goes into that customer's history.
>
> And it only ever learns from human-verified cases — never from its own unreviewed output. So its
> own mistakes can't compound into false precedent."

**On screen:** Review Queue → open the case → specialist disagreement → the correction form.
*(Optional: actually submit a correction if you have 3 spare seconds.)*

---

## 1:45 – 2:00 · The deliverable + close  *(SAR Drafts → open one)*

> "Finally — a real analyst output. This drafts a Suspicious Activity Report from the case's own
> evidence: subject, the suspicious activity with amounts and dates, supporting evidence, analysis,
> recommended action. Marked draft, unsigned, with a signature block — because a human files it,
> not the AI.
>
> Fully LLM-driven, no rules engine, with layered memory that makes it better every time a human
> corrects it."

**On screen:** the SAR document — scroll once, top to bottom. End there.

---

## Timing cheat-sheet

| Time | Section | Screen |
|---|---|---|
| 0:00 | Problem | Dashboard, static |
| 0:20 | Results | Scroll dashboard |
| **0:40** | **Agent workflow** ← core | Case drawer: specialists → trace → evidence |
| 1:20 | Human-in-the-loop | Review Queue → correction form |
| 1:45 | SAR + close | SAR document |

## If you have 3 minutes instead of 2
Add after the trace (~20s): **Case Comparison** — the arms dealer next to the cleared teacher, side by
side: *"same agent, 75-point gap, and here's exactly which signals differ."* It's the clearest proof
the scoring discriminates on real evidence.

## Avoid
- Don't trigger a live score on camera (45–90s of dead air).
- Don't read JSON aloud — point at it and summarise.
- Don't apologise for latency. If asked: ~11 sequential LLM calls, which is the cost of a real
  investigation; batch mode overlaps customers.
