# Demo Video — Script

**Presenter: Neetigya Shah** · screen recording with voiceover · **391 words ≈ 2:54** *(hard cap 3:00)*

**The idea:** start a real score early, then use the 60 seconds it takes to walk the rest of the
product. The wait becomes the tour. Come back at the end and the answer is waiting.

That works because a running score survives you leaving the page — a ⏳ badge sits on
**Ingest / Upload** while it runs, and turns ✓ when it lands.

---

## Before you record

```bash
docker ps                       # frisk-redis must say "Up"
frisk serve                     # then LOAD THE DASHBOARD ONCE and let it finish
```

1. **Load the dashboard once and let it finish.** First load scores 20 customers (1–2 min). Not on camera.
2. **Don't restart the server after that** — a restart clears the cache and you get the warm-up screen.
3. Browser **~1400px**, zoom 100%, devtools closed, bookmarks hidden.
4. Have `data/demo_samples/DEMO_000/` open in a file picker, all 6 files ready to select.
5. Check OpenRouter credit — a live score is a few cents; zero credit is dead air.

**Pace on the badge, not the clock.** When ⏳ turns ✓, wrap up whatever page you're on and go back.

---

## Shot list

| Time | Section | Page | Words |
|---|---|---|---|
| 0:00–0:13 | Intro | Dashboard | 28 |
| 0:13–0:33 | The problem | Dashboard | 46 |
| **0:33–0:46** | Start the score ← | Ingest / Upload | 27 |
| 0:46–1:18 | How the agents work — narrate over the live feed | Ingest — live feed | 75 |
| 1:18–1:50 | Review Queue — when it isn't sure | Review Queue | 76 |
| 1:50–2:04 | Case Comparison | Case Comparison | 28 |
| 2:04–2:20 | SAR Drafts — the real deliverable | SAR Drafts | 37 |
| 2:20–2:32 | Audit Trail | Audit Trail | 25 |
| **2:32–2:54** | Back to the result ← | Ingest → case drawer | 49 |

Assumes ~150 wpm plus ~2s per page change.

**Your margin:** you start the score at 0:33; it takes 50–90s, so it lands between **1:23 and 2:03** —
during Review Queue or Case Comparison. Even in the slowest case you still have ~29 seconds of tour
left before the payoff, so there's no version where you get back too early.

---

## The script

### 0:00 – 0:13 · Intro  *(28 words)*
*(Dashboard on screen. Don't click yet.)*

> "Hi, I'm **Neetigya Shah**. This is **Frisk** — it reviews bank customers for financial crime the way
> an analyst would, and shows you the evidence behind every call."

---

### 0:13 – 0:33 · The problem  *(46 words)*
*(Still on the dashboard. Slow scroll.)*

> "A reviewer opens one customer and finds five files that don't talk to each other. Nine out of ten
> alarms turn out to be nothing — and months later, nobody can explain why a customer was cleared.
>
> Here's twenty-two, ranked worst-first. Let's score a fresh one."

---

### 0:33 – 0:46 · Start the score ← **do this early; it buys the whole tour**  *(27 words)*
*(Click **Ingest / Upload**. Select all six files from `DEMO_000`. Click **Score uploaded files**.)*

> "This customer's never been scored. Six raw files, straight in.
>
> That takes about a minute — so while it runs, let me show you what it's doing."

**Don't wait after clicking.** Talk straight into the next section.

---

### 0:46 – 1:18 · How the agents work — narrate over the live feed  *(75 words)*
*(Stay on Ingest. Point at the step feed as it fills.)*

> "You can watch it think. Three specialists went first, **at the same time** — background, money,
> documents. Each sees only its own slice, so they can't talk each other into anything.
>
> Now a **lead investigator** has all three opinions, and works **one step at a time** — because you
> can't know which document matters until you've seen the payments.
>
> Every step is recorded. And it keeps running if I walk away — watch the badge."

*(Point at the ⏳ on **Ingest / Upload**, then click to Review Queue.)*

---

### 1:18 – 1:50 · Review Queue — when it isn't sure  *(76 words)*
*(**Review Queue** → open the case. Badge still ⏳.)*

> "Here's what happens when it *isn't* confident — instead of guessing, it hands the case to a person.
>
> We gate on **how sure it is**, not how bad the score is. A confident middling score needs nobody; a
> shaky one needs a human.
>
> And when I correct it, that becomes a worked example, a lesson it reads before every future case, and
> a note on this customer's file. It only learns from cases a person checked."

---

### 1:50 – 2:04 · Case Comparison  *(28 words)*
*(**Case Comparison** → the arms dealer beside a cleared customer.)*

> "Same agent, two customers, side by side — you can see exactly which signals differ.
>
> That's how you show the scoring runs on evidence, not on a vibe."

---

### 2:04 – 2:20 · SAR Drafts — the real deliverable  *(37 words)*
*(**SAR Drafts** → open one. Scroll it once.)*

> "This is what an analyst actually needs — a Suspicious Activity Report drafted from the case's own
> evidence. Amounts, dates, reasoning, recommendation.
>
> Marked draft, unsigned, with a signature block, because a person files it, not the AI."

---

### 2:20 – 2:32 · Audit Trail  *(25 words)*
*(**Audit Trail**. Badge should be ✓ by now.)*

> "Every decision lands here — cleared as well as escalated, permanently, and it can't be edited
> afterwards. That's what makes it usable in a bank."

---

### 2:32 – 2:54 · Back to the result ← **the payoff**  *(49 words)*
*(Badge shows ✓. Click **Ingest / Upload** — the result is waiting.)*

> "And there it is, finished while we talked. Escalate.
>
> Four cash deposits, each just under the ten-thousand reporting limit, inside six days. It had to name
> the exact rows — every reference is checked, so it can't invent evidence.
>
> No scoring formula anywhere in the code. Thanks for watching."

*(Click the result to open the case drawer. Land on the tool trace and stop.)*

---

## Rules

**Do:**
- **Click upload early.** Everything else is paced by that badge.
- Point with the cursor when you say "four cash deposits".
- If the badge turns ✓ early, cut the current section short and go to the payoff.

**Don't:**
- Don't read JSON aloud. Point and summarise.
- Don't restart the server before recording — you'll get the warm-up screen.
- Don't trigger a second score. One is the demo; two is dead air.
- Don't apologise for latency. If asked: *"about ten AI calls one after another — the cost of it
  actually investigating. On dedicated infrastructure it's under fifteen seconds."*

**If the score fails mid-record:** carry on to the end, then open `CUST_018` (same profile) and deliver
the closing lines over that. Don't restart.

**If you're running long:** cut Case Comparison (−28 words, ~13s) — it's the least load-bearing
section. Never cut the live investigation or the payoff.

---

## After recording

- Trim dead air at head and tail.
- Check the audio is louder than the typing.
- Export 1080p, and confirm the **tool trace** text is legible — that's the shot that must survive
  compression.
