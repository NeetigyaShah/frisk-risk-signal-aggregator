# Demo Video — Script

**Presenter: Neetigya Shah** · screen recording with voiceover · **516 words ≈ 3:45**

**The whole idea:** start a real score, then *use the 60 seconds it takes* to walk the rest of the
product. The wait stops being dead air and becomes the tour. Come back at the end and the answer is
sitting there waiting for you.

This works because a running score now survives you leaving the page — there is a ⏳ badge on
**Ingest / Upload** while it runs, and a ✓ when it lands.

---

## Before you record

```bash
docker ps                       # frisk-redis must say "Up"
python -m frisk.cli demo        # writes data/demo_samples/ (already done)
frisk serve                     # then LOAD THE DASHBOARD ONCE and let it finish
```

1. **Load the dashboard once and let it finish.** First load scores 20 customers (1–2 min). Not on camera.
2. **Do not restart the server after that** — a restart clears the cache and you get the warm-up screen.
3. Browser **~1400px**, zoom 100%, devtools closed, bookmarks hidden.
4. Have `data/demo_samples/DEMO_000/` open in a file picker, ready to select all 6 files.
5. Check OpenRouter credit. A live score is a few cents; zero credit is dead air.

**Watch the badge, not the clock.** Everything after the upload is paced by the ⏳ on the sidebar.
When it turns ✓, wrap up whatever page you are on and go back.

---

## Shot list

| Time | Section | Page | Words |
|---|---|---|---|
| 0:00–0:15 | Intro | Dashboard | 33 |
| 0:15–0:40 | The problem | Dashboard | 57 |
| 0:40–0:55 | **Start the score** | Ingest / Upload | 37 |
| 0:55–1:30 | How the agents work *(over the wait)* | Ingest — live feed | 79 |
| 1:30–2:10 | Review Queue | Review Queue | 95 |
| 2:10–2:30 | Case Comparison | Case Comparison | 46 |
| 2:30–2:55 | SAR Drafts | SAR Drafts | 53 |
| 2:55–3:10 | Audit Trail | Audit Trail | 33 |
| **3:10–3:45** | **Back to the result** | Ingest → case drawer | 83 |

Timings assume ~150 wpm plus a couple of seconds per page change.

**The margin you're working with:** you start the score at 0:55 and it takes 50–90s, so it lands
somewhere between **1:45 and 2:25** — during Review Queue or Case Comparison. You then have at least
45 seconds of tour left before the payoff at 3:10. There is no version of this where you arrive back
and it isn't ready.

---

## The script

### 0:00 – 0:15 · Intro  *(33 words)*
*(Dashboard on screen. Don't click yet.)*

> "Hi, I'm **Neetigya Shah**, and this is **Frisk** — a financial risk signal aggregator I built.
> It reviews bank customers the way an analyst would, and shows you the evidence behind every call."

---

### 0:15 – 0:40 · The problem  *(57 words)*
*(Still on the dashboard. Slow scroll down the page.)*

> "A reviewer opens one customer and finds five files that don't talk to each other — their payments,
> their banker's notes, an ID scan. Nine out of ten alarms turn out to be nothing, and six months
> later nobody can explain why a customer was cleared.
>
> Here's twenty-two, already ranked worst-first. Let's score a fresh one, live."

---

### 0:40 – 0:55 · Start the score ← **do this early, it buys you the whole tour**  *(37 words)*
*(Click **Ingest / Upload**. Select all six files from `DEMO_000`. Click **Score uploaded files**.)*

> "This customer has never been scored. Six raw files, straight in.
>
> That's running now. It takes about a minute — so while it works, let me show you what it's doing,
> and the rest of the product."

**Once you click, don't wait.** Talk straight through into the next section.

---

### 0:55 – 1:30 · How the agents work — narrate over the live feed  *(79 words)*
*(Stay on Ingest. The step feed is filling in — point at it as you talk.)*

> "You can watch it think. Three specialists went first, **at the same time** — background, money,
> documents. Each only sees its own slice, so they can't talk each other into anything.
>
> Now a **lead investigator** has their three opinions and works **one step at a time**. That's the
> important bit — you can't know which document matters until you've seen the payments.
>
> Every step there is recorded. And it keeps running if I walk away — watch the badge."

*(Point at the ⏳ on **Ingest / Upload**, then click away to Review Queue.)*

---

### 1:30 – 2:10 · Review Queue — when it isn't sure  *(95 words)*
*(**Review Queue** → open the case. Badge still shows ⏳.)*

> "While that runs — here's what happens when it *isn't* confident. Instead of guessing, it handed the
> case to a person.
>
> Note we gate on **how sure it is**, not how bad the score is. A confident middling score needs
> nobody; a shaky one needs a human.
>
> The reviewer sees everything — where the specialists disagreed, every step, its own notes. And when
> I correct it, that becomes a worked example, a lesson it reads before every future case, and a note
> on this customer's file. It only ever learns from cases a person checked."

---

### 2:10 – 2:30 · Case Comparison — proof it discriminates  *(46 words)*
*(**Case Comparison** → pick the arms dealer and a cleared customer.)*

> "Same agent, two customers, side by side — you can see exactly which signals differ.
>
> That matters more than it looks. It's how you show the scoring runs on evidence and not on a vibe —
> a reviewer can point at the gap and explain it."

---

### 2:30 – 2:55 · SAR Drafts — the real deliverable  *(53 words)*
*(**SAR Drafts** → open one. Scroll it once.)*

> "This is the output an analyst actually needs — a Suspicious Activity Report drafted straight from
> the case's own evidence. What happened, with amounts and dates, the supporting evidence, the
> recommendation.
>
> Marked draft, unsigned, with a signature block — because a person files it, not the AI. That's
> normally an hour of writing."

---

### 2:55 – 3:10 · Audit Trail  *(33 words)*
*(**Audit Trail**. Check the badge — should be ✓ or close.)*

> "And every decision lands here — cleared as well as escalated, permanently, and it can't be edited
> afterwards. That's the difference between a tool a bank can actually use and a clever demo."

---

### 3:10 – 3:45 · Back to the result ← **the payoff**  *(83 words)*
*(Badge now shows ✓. Click **Ingest / Upload** — the finished result is waiting.)*

> "And there it is — finished while we were talking. Escalate.
>
> Look what it points at: four cash deposits, each just under the ten-thousand reporting limit, all
> within six days. It had to name the exact rows to claim that — every reference is checked against
> what the tools actually returned, so it can't invent evidence.
>
> No scoring formula anywhere in the code. Memory that improves it every time a human corrects it.
> And every decision carries its own evidence.
>
> Thanks for watching."

*(Click the result to open the case drawer. Land on the tool trace and stop there.)*

---

## Rules

**Do:**
- **Click upload early.** Everything else is paced by that badge.
- Point with the cursor when you say "look at what it points at".
- If the badge turns ✓ early, cut whichever section you're on short and go to the payoff.
- If it's still running when you reach the end, spend 15 more seconds on Audit Trail — the score is worth waiting for.

**Don't:**
- Don't read JSON aloud. Point and summarise.
- Don't restart the server before recording. You'll get the warm-up screen.
- Don't trigger a second score. One is the demo; two is dead air.
- Don't apologise for latency. If asked: *"about ten AI calls one after another — that's the cost of
  it actually investigating. On dedicated infrastructure it's under fifteen seconds."*

**If the score fails mid-record:** keep going to the end, then open any already-scored case
(`CUST_018` is the same profile) and deliver the closing lines over that instead. Don't restart.

---

## After recording

- Trim dead air at the head and tail.
- Check the audio is louder than the typing.
- Export 1080p, and confirm the **tool trace** text is legible — that's the one shot that must survive
  compression.
