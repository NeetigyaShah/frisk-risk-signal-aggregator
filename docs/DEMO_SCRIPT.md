# Demo Video — Plan & Script

**Target: 2:00** (hard cap 3:00) · screen recording with voiceover · ~300 spoken words

The point of the video is not to tour the UI. It is to show **one investigation happening live**, and
then show **a human correcting it**. Everything else is setting.

---

## Part 1 — Before you hit record

### The five demo customers

`frisk demo` writes five customers the app has **never scored**, so a live assessment on camera is
genuinely live — not a replay.

```bash
python -m frisk.cli demo      # → data/demo_samples/
```

| ID | Who | Why it is in the set |
|---|---|---|
| **`DEMO_000`** | Ms Andrea Horton — arms dealer, Iran | **The headline.** Four cash deposits of $8,169–$9,372, all under the $10,000 reporting limit, inside six days. The agent should find it and cite the exact rows. |
| **`DEMO_001`** | Geraldine Porter — primary school teacher, GB | **The contrast.** Salary in, rent out, nothing else. Same agent, cleared in one breath. |
| **`DEMO_002`** | Bruce Gordon-Whitehead — parish councillor, GB | **The human moment.** Holds public office (higher risk) but the activity is entirely mundane. The specialists disagree → low confidence → review queue. |
| **`DEMO_003`** | Lawrence Newton — crypto dealer, GB | **A different pattern.** £585k out to three Cyprus shell companies in five days, against a £4.4k salary. Proves the demo is not one trick. |
| **`DEMO_004`** | Clare Watson — importer, Venezuela | **Robustness.** `transactions.csv` is missing entirely. It must still return a real decision, not a crash. |

> Verified in the generated data — these are not aspirational descriptions.

### Setup checklist

1. **`frisk serve`**, then **load the dashboard once** and let it finish. The first load scores the 20
   base customers live (1–2 min). You do not want that on camera.
2. **Do NOT score the demo customers yet.** They are your live moment.
3. Browser at **~1400px wide**, zoom 100%, devtools closed, bookmarks bar hidden.
4. Open `data/demo_samples/DEMO_000/` in a file explorer window, ready to drag from.
5. Check your OpenRouter credit — a live score costs a few cents, but zero credit means dead air.
6. Speak at ~150 wpm. Script below is ~300 words ≈ 2 minutes.

### The one risky moment, and the safety net

Scoring `DEMO_000` live takes **45–90 seconds**. That is too long to sit in silence.

**Plan:** start the score, then *keep talking over it* — the progress UI is on screen while you explain
what is happening underneath. That turns the wait into the explanation instead of dead air.

**Safety net:** if it is still running past ~60s, say *"this takes about a minute — here's one I ran
earlier"* and cut to an already-scored case. Have `CUST_018` open in a second tab. **Record the live
attempt first**; if it goes badly you still have the fallback, and if it goes well you have the best
30 seconds of the video.

---

## Part 2 — Shot list

| Time | Section | What is on screen | What you are doing |
|---|---|---|---|
| 0:00–0:15 | The problem | Dashboard, static | Talking, not clicking |
| 0:15–0:30 | What it produced | Scroll the dashboard | Slow scroll |
| **0:30–1:10** | **Live investigation** ← the core | Ingest → upload → progress → the trace | Upload `DEMO_000`, talk over the wait |
| 1:10–1:35 | Human-in-the-loop | Review Queue → correction form | Open the case, point at the disagreement |
| 1:35–2:00 | The deliverable | SAR document | Scroll once, top to bottom |

---

## Part 3 — The script

### 0:00 – 0:15 · The problem
*(Dashboard on screen. Do not scroll yet.)*

> "A compliance reviewer opens one customer and finds five files that don't talk to each other —
> their details, their account, a spreadsheet of payments, their banker's notes, an ID scan. They read
> all of it, decide 'is this a problem?', and do it again a few hundred times.
>
> Nine out of ten alarms turn out to be nothing. And six months later nobody can explain why a
> customer was cleared.
>
> This is Frisk. It does that first pass, and it shows its working."

---

### 0:15 – 0:30 · What it produced
*(Scroll slowly: hero chart → KPI row → the three charts → top of the queue.)*

> "Twenty-two customers, scored and ranked worst-first. Twenty-seven percent cleared automatically with
> zero human time. Three escalated. One it wasn't sure about — I'll come back to that one.
>
> But rather than show you results I prepared earlier, let's actually run one."

---

### 0:30 – 1:10 · A live investigation ← **the core of the video**
*(Click **Ingest / Upload**. Drag in all of `DEMO_000`. Click **Score uploaded files**.)*

> "This customer has never been scored. I'm dropping in her raw files now — and while that runs, here's
> what's happening underneath.
>
> First, three specialists work **at the same time** — one on her background, one on the money, one on
> the documents. Each only sees its own slice, so they can't talk each other into anything.
>
> Their three opinions then go to a **lead investigator**, which works **one step at a time**. And that
> matters: you can't know which document to open until you've seen the payments. So it reads, then
> decides what to ask next, then reads again."

*(Result lands. Open the case. Scroll to the tool trace.)*

> "There it is. And this is the part I care about — **every step it took is recorded**. It read the ID
> scan, read the banker's notes, sliced the payments six different ways, ran a pattern scan, wrote
> itself a note, then decided.
>
> Look at what it points at: four specific payments. Four cash deposits, each just under the
> ten-thousand reporting limit, all within six days. That's textbook — and it had to name the exact
> rows to claim it. It cannot make up evidence; every reference is checked against what the tools
> actually returned.
>
> **That trace is the audit record.** That's how you answer 'why was this escalated' six months later."

**On screen, in order:** score + escalate → the three specialist cards → **the tool trace (linger
here)** → the cited payment IDs → the payments table with the odd rows highlighted.

---

### 1:10 – 1:35 · When it is not sure
*(Click **Review Queue**, open the low-confidence case.)*

> "Now the one it *wasn't* sure about. Below the confidence line — so instead of guessing, it handed
> the case to a person.
>
> And notice we gate on **how sure it is**, not how bad the score is. A confident middling score needs
> nobody. A shaky one needs a human. The reviewer sees everything — where the specialists disagreed,
> every step, its own notes.
>
> When I correct this score, three things happen: it's stored as a worked example that similar
> customers will be shown, it's distilled into a lesson injected into every future case, and it goes on
> this customer's own file.
>
> And it only ever learns from cases a **person** checked — never from its own unreviewed work. So its
> mistakes can't quietly become the house rule."

*(If you have three spare seconds: actually submit the correction.)*

---

### 1:35 – 2:00 · The deliverable
*(**SAR Drafts** → open one. Scroll once, top to bottom. End there.)*

> "Finally, a real analyst output. It drafts the Suspicious Activity Report from the case's own
> evidence — who, what happened with amounts and dates, the supporting evidence, the reasoning, the
> recommendation.
>
> Marked draft, unsigned, with a signature block — because a person files it, not the AI.
>
> No scoring formula anywhere in the code. Layered memory that makes it better every time a human
> corrects it. And every decision carries its own evidence."

---

## Part 4 — Rules

**Do:**
- Let the trace breathe. It is the single most convincing thing in the video — give it 10 seconds.
- Point with the cursor when you say "look at what it points at". Do not just say it.
- Keep talking during the live score. Silence reads as broken; narration reads as confidence.

**Don't:**
- Don't read JSON aloud. Point at it and summarise.
- Don't apologise for latency. If it comes up: *"about eleven AI calls one after another — that's the
  cost of it actually investigating rather than pattern-matching. On dedicated infrastructure it's
  under fifteen seconds."*
- Don't tour every page. Case Comparison and Audit Trail are good pages; they are not worth 15 seconds
  of a 2-minute video.
- Don't trigger a second live score. One is the demo; two is dead air.

**If you have 3 minutes instead of 2:** add **Case Comparison** after the trace (~20s) — the arms
dealer beside the cleared teacher, side by side: *"same agent, seventy-eight point gap, and here's
exactly which signals differ."* It is the cleanest proof the scoring discriminates on real evidence.

---

## Part 5 — After recording

- Trim dead air at the head and tail.
- If the live score ran long, cut the middle of the wait — keep your narration, drop the spinner.
- Check the audio is louder than the typing.
- Export 1080p. Confirm the tool trace text is legible at the final resolution — that is the one shot
  that must survive compression.
