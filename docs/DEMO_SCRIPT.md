# Demo Video — Plan & Script

**Presenter: Neetigya Shah** · screen recording with voiceover · **430 spoken words ≈ 2:50**
(hard cap 3:00)

The point of the video is not to tour the UI. It is to show **one investigation happening live**, and
then show **a human correcting it**. Everything else is setting.

> **On the runtime.** Counted at 150 wpm this lands at **2:52**, and the live score adds wall-clock on
> top of the narration written to cover it — so plan for **2:50–3:00**, not 2:00. If you need a hard
> 2:00, take the three cuts listed in [Part 5](#part-5--cutting-to-200).

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
| **`DEMO_003`** | Lawrence Newton — crypto dealer, GB | **A different pattern.** £585k out to three Cyprus shell companies in five days, against a £4.4k salary. |
| **`DEMO_004`** | Clare Watson — importer, Venezuela | **Robustness.** `transactions.csv` is missing entirely. It must still return a real decision. |

> Verified against the generated data — these are not aspirational descriptions.

### Setup checklist

1. **`frisk serve`**, then **load the dashboard once** and let it finish. The first load scores the 20
   base customers live (1–2 min). You do not want that on camera.
2. **Do NOT score the demo customers yet.** They are your live moment.
3. Browser at **~1400px wide**, zoom 100%, devtools closed, bookmarks bar hidden.
4. Open `data/demo_samples/DEMO_000/` in a file explorer window, ready to drag from.
5. Second tab with `CUST_018` already open — your fallback (see below).
6. Check your OpenRouter credit. A live score costs a few cents; zero credit means dead air on the one
   shot that matters.

### The one risky moment, and the safety net

Scoring `DEMO_000` live takes **45–90 seconds** — too long to sit in silence.

**Plan:** start the score, then *keep talking over it*. The progress UI is on screen while you explain
what is happening underneath. The wait becomes the explanation instead of dead air.

**Safety net:** if it is still running past ~60s, say *"this takes about a minute — here's one I ran
earlier"* and cut to the `CUST_018` tab. **Record the live attempt first.** If it goes badly you still
have the fallback; if it goes well you have the best 30 seconds of the video.

---

## Part 2 — Shot list

| Time | Section | Words | On screen | What you are doing |
|---|---|---|---|---|
| 0:00–0:13 | **Intro** | 33 | Dashboard, static | Talking. No clicking. |
| 0:13–0:32 | The problem | 48 | Dashboard, still static | Talking |
| 0:32–0:43 | What it produced | 28 | Scroll the dashboard | Slow scroll |
| **0:43–1:45** | **Live investigation** ← the core | 155 | Ingest → upload → progress → the trace | Upload `DEMO_000`, narrate over the wait |
| 1:45–2:28 | Human-in-the-loop | 107 | Review Queue → correction form | Open the case, point at the disagreement |
| 2:28–2:52 | The deliverable | 59 | SAR document | Scroll once, top to bottom |

The live-investigation block is deliberately the longest — its 155 words exist to cover the 45–90s
score. If the score returns early, you will finish that section early; that is fine, keep going.

---

## Part 3 — The script

### 0:00 – 0:13 · Intro  *(33 words — keep it under 15 seconds)*
*(Dashboard on screen, static. Do not click anything yet.)*

> "Hi, I'm **Neetigya Shah**, and this is **Frisk** — a financial risk signal aggregator I built.
> It reviews bank customers the way an analyst would, and shows you the evidence behind every call."

**Say it once, cleanly, then move on.** The temptation is to explain your background here — don't.
The work is the introduction.

---

### 0:13 – 0:32 · The problem  *(48 words)*
*(Still static.)*

> "A reviewer opens one customer and finds five files that don't talk to each other — their details,
> their payments, their banker's notes, an ID scan. Nine out of ten alarms turn out to be nothing. And
> six months later, nobody can explain why a customer was cleared."

---

### 0:32 – 0:43 · What it produced  *(28 words)*
*(Scroll slowly: hero chart → KPI row → the three charts → top of the queue.)*

> "Twenty-two customers, ranked worst-first. Twenty-seven percent cleared automatically, three
> escalated, one it wasn't sure about — I'll come back to that. But let's run a fresh one live."

---

### 0:43 – 1:45 · A live investigation ← **the core of the video**  *(155 words)*
*(Click **Ingest / Upload**. Drag in all of `DEMO_000`. Click **Score uploaded files**.)*

> "This customer has never been scored. I'm dropping in her raw files — and while that runs, here's
> what's happening underneath.
>
> Three specialists work **at the same time** — background, money, documents. Each only sees its own
> slice, so they can't talk each other into anything.
>
> Their opinions go to a **lead investigator**, which works **one step at a time**. That matters — you
> can't know which document to open until you've seen the payments."

*(Result lands. Open the case. Scroll to the tool trace.)*

> "There it is. And this is the part I care about — **every step is recorded**. It read the ID scan,
> read the banker's notes, sliced the payments six ways, ran a pattern scan, then decided.
>
> Look what it points at — four cash deposits, each just under the ten-thousand reporting limit, all
> within six days. It had to name the exact rows to claim that. It can't invent evidence; every
> reference is checked against what the tools actually returned.
>
> **That trace is the audit record.** That's how you answer 'why was this escalated' six months later."

**On screen, in order:** score + escalate → the three specialist cards → **the tool trace (linger
here)** → the cited payment IDs → the payments table with the odd rows highlighted.

---

### 1:45 – 2:28 · When it is not sure  *(107 words)*
*(Click **Review Queue**, open the low-confidence case.)*

> "Now the one it *wasn't* sure about. Below the confidence line — so instead of guessing, it handed
> the case to a person.
>
> Note we gate on **how sure it is**, not how bad the score is. A confident middling score needs
> nobody; a shaky one needs a human. And the reviewer sees everything — where the specialists
> disagreed, every step, its own notes.
>
> When I correct this, it becomes a worked example, a lesson injected into every future case, and a
> note on this customer's file. And it only ever learns from cases a **person** checked — so its
> mistakes can't quietly become the house rule."

*(If you have three spare seconds: actually submit the correction.)*

---

### 2:28 – 2:52 · The deliverable  *(59 words)*
*(**SAR Drafts** → open one. Scroll once, top to bottom. End there.)*

> "Finally, a real analyst output — it drafts the Suspicious Activity Report from the case's own
> evidence. Marked draft, unsigned, with a signature block, because a person files it, not the AI.
>
> No scoring formula anywhere in the code. Memory that improves it every time a human corrects it. And
> every decision carries its own evidence. Thanks for watching."

---

## Part 4 — Rules

**Do:**
- Say your name once, at the top, and let the work carry the rest.
- Let the trace breathe. It is the most convincing thing in the video — give it a full 10 seconds.
- Point with the cursor when you say "look at what it points at". Don't just say it.
- Keep talking during the live score. Silence reads as broken; narration reads as confidence.

**Don't:**
- Don't spend 30 seconds on your background. The intro is 12 seconds, and that is deliberate.
- Don't read JSON aloud. Point at it and summarise.
- Don't apologise for latency. If it comes up: *"about eleven AI calls one after another — that's the
  cost of it actually investigating rather than pattern-matching. On dedicated infrastructure it's
  under fifteen seconds."*
- Don't tour every page. Case Comparison and Audit Trail are good; they are not worth 15 seconds of a
  2-minute video.
- Don't trigger a second live score. One is the demo; two is dead air.

**If you have 3 minutes instead of 2:** add **Case Comparison** after the trace (~20s) — the arms
dealer beside the cleared teacher: *"same agent, seventy-eight point gap, and here's exactly which
signals differ."* It is the cleanest proof the scoring discriminates on real evidence.

---

## Part 5 — Cutting to 2:00

Only if a hard 2:00 is required. These three cuts remove ~130 words (~52s) and land you at **2:00**,
in the order that costs the least:

1. **Drop the SAR section entirely** (−59 words, −24s). It is a strong closer but the weakest *argument*
   — end instead on the trace line: *"That's how you answer 'why was this escalated' six months later.
   Thanks for watching."*
2. **Cut "What it produced"** (−28 words, −11s). Go straight from the problem to the live run. The
   dashboard is visible behind you anyway.
3. **Trim the human-in-the-loop block to its first two paragraphs** (−45 words, −18s). Keep the
   confidence gate; drop the three-learning-paths detail.

**Do not cut the live investigation.** It is the reason the video exists.

---

## Part 6 — After recording

- Trim dead air at the head and tail.
- If the live score ran long, cut the middle of the wait — keep your narration, drop the spinner.
- Check the audio is louder than the typing.
- Export 1080p. Confirm the tool trace text is legible at the final resolution — that is the one shot
  that must survive compression.
