"""Build the 5-slide summary deck (deck.pptx).

    pip install python-pptx
    python docs/deck/build_pptx.py

Structure maps 1:1 onto the five required elements:
    1 Problem understanding · 2 Solution approach · 3 Key highlights ·
    4 Human-in-the-loop · 5 Challenges & learnings

Layout is authored here rather than parsed from SLIDES.md — the deck is table- and diagram-heavy,
which a markdown bullet-parser cannot lay out. SLIDES.md stays the narrative source and the speaker
notes below are lifted from it.

No screenshots: the deck carries the argument, the demo video carries the evidence.

Visual language matches the app — "Charcoal Ink": near-black canvas, neutral greys, and colour
reserved exclusively for risk semantics (green = cleared, amber = review, red = escalate).

The build asserts every shape stays inside the 16:9 canvas, so a layout regression fails loudly.
"""
from __future__ import annotations

import os

from pptx import Presentation
from pptx.dml.color import RGBColor
from pptx.enum.shapes import MSO_SHAPE
from pptx.enum.text import PP_ALIGN
from pptx.util import Emu, Inches, Pt

HERE = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.join(HERE, "deck.pptx")

# ── palette (mirrors frontend/styles.css) ───────────────────────────────────
BG      = RGBColor(0x0B, 0x0B, 0x0C)
PANEL   = RGBColor(0x14, 0x14, 0x16)
PANEL2  = RGBColor(0x1A, 0x1A, 0x1D)
LINE    = RGBColor(0x32, 0x32, 0x36)
INK     = RGBColor(0xED, 0xED, 0xF0)
MUTED   = RGBColor(0xA1, 0xA1, 0xAA)
FAINT   = RGBColor(0x71, 0x71, 0x7A)
LOW     = RGBColor(0x22, 0xC5, 0x5E)
MED     = RGBColor(0xF5, 0x9E, 0x0B)
HIGH    = RGBColor(0xEF, 0x44, 0x44)
REVIEW  = RGBColor(0xF9, 0x73, 0x16)
ACCENT  = RGBColor(0xE4, 0xE4, 0xE7)
CYAN    = RGBColor(0x0E, 0xA5, 0xE9)
TEAL    = RGBColor(0x14, 0xB8, 0xA6)
VIOLET  = RGBColor(0x8B, 0x5C, 0xF6)

W, H = Inches(13.333), Inches(7.5)          # 16:9
FONT = "Inter"
MONO = "Consolas"


# ── primitives ──────────────────────────────────────────────────────────────
def text(slide, x, y, w, h, runs, *, size=14, color=INK, bold=False, align=PP_ALIGN.LEFT,
         space_after=6, line=1.25, font=FONT):
    """runs: str, or list of paragraphs; each paragraph is str or list of (text, {opts})."""
    tf = slide.shapes.add_textbox(x, y, w, h).text_frame
    tf.word_wrap = True
    tf.margin_left = tf.margin_right = tf.margin_top = tf.margin_bottom = Emu(0)
    for i, para in enumerate(runs if isinstance(runs, list) else [runs]):
        p = tf.paragraphs[0] if i == 0 else tf.add_paragraph()
        p.alignment = align
        p.space_after = Pt(space_after)
        p.line_spacing = line
        for t, o in (para if isinstance(para, list) else [(para, {})]):
            r = p.add_run()
            r.text = t
            r.font.name = o.get("font", font)
            r.font.size = Pt(o.get("size", size))
            r.font.bold = o.get("bold", bold)
            r.font.color.rgb = o.get("color", color)
    return tf


def rect(slide, x, y, w, h, fill=PANEL, outline=LINE, radius=True):
    shp = slide.shapes.add_shape(
        MSO_SHAPE.ROUNDED_RECTANGLE if radius else MSO_SHAPE.RECTANGLE, x, y, w, h)
    shp.fill.solid()
    shp.fill.fore_color.rgb = fill
    if outline is None:
        shp.line.fill.background()
    else:
        shp.line.color.rgb = outline
        shp.line.width = Pt(0.75)
    if radius:
        try:
            shp.adjustments[0] = 0.06
        except Exception:
            pass
    shp.shadow.inherit = False
    return shp


def slide_base(prs, kicker, title, subtitle=None):
    s = prs.slides.add_slide(prs.slide_layouts[6])
    s.background.fill.solid()
    s.background.fill.fore_color.rgb = BG
    rect(s, 0, 0, W, Pt(3), fill=ACCENT, outline=None, radius=False)
    text(s, Inches(0.6), Inches(0.38), Inches(11), Inches(0.28),
         kicker.upper(), size=11, color=FAINT, bold=True)
    text(s, Inches(0.6), Inches(0.68), Inches(12.2), Inches(0.55),
         title, size=28, color=INK, bold=True)
    if subtitle:
        text(s, Inches(0.6), Inches(1.22), Inches(12.2), Inches(0.4),
             subtitle, size=12.5, color=MUTED)
    return s


def note(slide, txt):
    slide.notes_slide.notes_text_frame.text = txt


def label(slide, x, y, w, txt):
    text(slide, x, y, w, Inches(0.22), txt.upper(), size=9.5, color=FAINT, bold=True)


def stat(slide, x, y, w, lbl, value, color=INK, delta=None, h=Inches(1.0)):
    rect(slide, x, y, w, h, fill=PANEL)
    text(slide, x + Inches(0.16), y + Inches(0.11), w - Inches(0.3), Inches(0.2),
         lbl.upper(), size=8.5, color=FAINT, bold=True)
    text(slide, x + Inches(0.16), y + Inches(0.32), w - Inches(0.3), Inches(0.45),
         value, size=23, color=color, bold=True)
    if delta:
        text(slide, x + Inches(0.16), y + Inches(0.73), w - Inches(0.3), Inches(0.2),
             delta, size=8.5, color=MUTED)


def flow_box(slide, x, y, w, h, title, lines, *, accent=LINE, tcolor=INK):
    rect(slide, x, y, w, h, fill=PANEL, outline=accent)
    text(slide, x + Inches(0.14), y + Inches(0.11), w - Inches(0.28), Inches(0.24),
         title, size=10.5, color=tcolor, bold=True)
    text(slide, x + Inches(0.14), y + Inches(0.38), w - Inches(0.28), h - Inches(0.48),
         lines, size=8.5, color=MUTED, space_after=2, line=1.15)


def arrow(slide, x, y, w=Inches(0.28)):
    a = slide.shapes.add_shape(MSO_SHAPE.RIGHT_ARROW, x, y, w, Inches(0.16))
    a.fill.solid(); a.fill.fore_color.rgb = LINE
    a.line.fill.background(); a.shadow.inherit = False
    return a


def card(slide, x, y, w, h, head, body, *, accent=None, hsize=10.5, bsize=8.5,
         hcolor=INK, fill=PANEL, bar=False):
    rect(slide, x, y, w, h, fill=fill, outline=accent if (accent and not bar) else LINE)
    if bar and accent:
        rect(slide, x, y, Pt(3), h, fill=accent, outline=None, radius=False)
    pad = Inches(0.2) if bar else Inches(0.15)
    text(slide, x + pad, y + Inches(0.07), w - pad - Inches(0.14), Inches(0.24),
         head, size=hsize, color=hcolor, bold=True)
    text(slide, x + pad, y + Inches(0.29), w - pad - Inches(0.12), h - Inches(0.36),
         body, size=bsize, color=MUTED, line=1.16, space_after=2)


# ── slide 1 · problem understanding ─────────────────────────────────────────
def slide1(prs):
    s = slide_base(prs, "01 · Problem Understanding",
                   "Compliance drowns in signals it generated itself",
                   "The bottleneck is not detecting suspicious activity — it is triaging the noise, and explaining the call afterwards.")

    label(s, Inches(0.6), Inches(1.72), Inches(6.0), "the domain, in numbers")
    facts = [
        ("~90–95%", "of AML alerts are false positives", "the bottleneck is triage, not detection", HIGH),
        ("2–4%", "of alerts are actionable", "96%+ of analyst effort produces nothing", MED),
        ("70–80%", "of analyst time goes to false positives", "the scarce resource is attention", REVIEW),
        ("2–5%", "of global GDP laundered annually (UNODC)", "the false negatives are the costly ones", MUTED),
    ]
    for i, (n, what, why, c) in enumerate(facts):
        ry = Inches(2.0) + Inches(0.55 * i)
        rect(s, Inches(0.6), ry, Inches(6.0), Inches(0.47), fill=PANEL)
        text(s, Inches(0.74), ry + Inches(0.08), Inches(1.05), Inches(0.3),
             n, size=13, color=c, bold=True)
        text(s, Inches(1.88), ry + Inches(0.05), Inches(4.6), Inches(0.2),
             what, size=9, color=INK)
        text(s, Inches(1.88), ry + Inches(0.24), Inches(4.6), Inches(0.2),
             why, size=8, color=FAINT)
    text(s, Inches(0.6), Inches(4.24), Inches(6.0), Inches(0.36),
         "Directional industry estimates, not audited statistics — but the shape is consistent.",
         size=8.5, color=FAINT)

    label(s, Inches(6.9), Inches(1.72), Inches(5.83), "one customer = five disconnected artefacts")
    rows = [
        ("kyc.json",         "structured", "identity, occupation, PEP"),
        ("account.json",     "structured", "tenure, product, jurisdiction"),
        ("transactions.csv", "structured", "the behaviour — 100s of rows"),
        ("rm_notes.txt",     "free text",  "the RM's unease, in prose"),
        ("id_document.txt",  "free text",  "document anomalies, admissions"),
    ]
    for i, (f, kind, hides) in enumerate(rows):
        ry = Inches(2.0) + Inches(0.44 * i)
        rect(s, Inches(6.9), ry, Inches(5.83), Inches(0.38), fill=PANEL)
        text(s, Inches(7.04), ry + Inches(0.07), Inches(1.7), Inches(0.24),
             f, size=9.5, color=INK, bold=True, font=MONO)
        text(s, Inches(8.76), ry + Inches(0.08), Inches(0.92), Inches(0.22),
             kind, size=8, color=REVIEW if kind == "free text" else FAINT, bold=True)
        text(s, Inches(9.72), ry + Inches(0.08), Inches(2.9), Inches(0.22),
             hides, size=8.5, color=MUTED)
    text(s, Inches(6.9), Inches(4.24), Inches(5.83), Inches(0.36),
         [[("The two most incriminating sources are unstructured. ", {"size": 9, "color": MUTED}),
           ("No rules engine reads them.", {"size": 9, "color": REVIEW, "bold": True})]])

    label(s, Inches(0.6), Inches(4.76), Inches(12.13), "three failures this creates")
    fails = [
        ("Slow", HIGH, "Minutes per customer — and the queue is unordered, so the riskiest case may be read last."),
        ("Inconsistent", MED, "Two analysts score the same file differently. There is no shared calibration."),
        ("Unauditable", REVIEW, "A regulator asking “why was this cleared?” six months later gets a shrug."),
    ]
    for i, (h, c, b) in enumerate(fails):
        card(s, Inches(0.6) + Inches(4.09) * i, Inches(5.02), Inches(3.93), Inches(0.78),
             h, b, accent=c, bar=True, hcolor=c, hsize=11.5, bsize=8.5)

    cy = Inches(5.98)
    rect(s, Inches(0.6), cy, Inches(12.13), Inches(1.06), fill=PANEL2, outline=ACCENT)
    text(s, Inches(0.84), cy + Inches(0.11), Inches(11.6), Inches(0.22),
         "OBJECTIVE, AND THE CONSTRAINT THAT SHAPED EVERYTHING", size=9, color=FAINT, bold=True)
    text(s, Inches(0.84), cy + Inches(0.34), Inches(11.65), Inches(0.66),
         [[("Do the first pass: ", {"bold": True, "color": INK, "size": 11}),
           ("read every source, investigate like an analyst, rank the whole book by risk, and show "
            "the work — so the human starts from evidence, not a blank page.",
            {"color": MUTED, "size": 11})],
          [("A false negative is catastrophic; a false positive is merely expensive — so the system "
            "must ", {"color": MUTED, "size": 11}),
           ("know when it is unsure and escalate", {"bold": True, "color": REVIEW, "size": 11}),
           (". That is why confidence, not score, decides who sees a case.",
            {"color": MUTED, "size": 11})]], space_after=4, line=1.25)

    note(s, "Lead with the analyst's desk, not the tech. The numbers establish this is a triage and "
            "explainability problem, not a detection problem. Everything in the next four slides "
            "answers one of the three failures.")
    return s


# ── slide 2 · solution approach ─────────────────────────────────────────────
def slide2(prs):
    s = slide_base(prs, "02 · Solution Approach",
                   "Parallel where independent, serial where dependent",
                   "Four stages per customer. No deterministic rules engine — the LLM produces the score; code supplies tools, memory and guardrails.")

    py = Inches(1.76)
    bw, bh = Inches(2.72), Inches(1.42)
    gap = Inches(0.36)
    xs = [Inches(0.6) + (bw + gap) * i for i in range(4)]
    flow_box(s, xs[0], py, bw, bh, "1 · INGEST",
             ["kyc · account · transactions", "id_document · rm_notes",
              "correspondence", "", "→ one typed Dossier"],
             accent=CYAN, tcolor=RGBColor(0x7D, 0xD3, 0xFC))
    flow_box(s, xs[1], py, bw, bh, "2 · RETRIEVE MEMORY",
             ["per-customer history", "similar past cases", "lessons learned",
              "", "reference cheat-sheets"], accent=TEAL, tcolor=RGBColor(0x5E, 0xEA, 0xD4))
    flow_box(s, xs[2], py, bw, bh, "3 · INVESTIGATE",
             ["3 specialists — PARALLEL", "   KYC · transactions · docs", "",
              "orchestrator — SERIAL", "   tools → finalize()"],
             accent=VIOLET, tcolor=RGBColor(0xC4, 0xB5, 0xFD))
    flow_box(s, xs[3], py, bw, bh, "4 · DECIDE + LEARN",
             ["conf ≥ 0.60 → auto-dispose", "conf < 0.60 → human queue", "",
              "correction → memory"], accent=REVIEW, tcolor=RGBColor(0xFD, 0xBA, 0x74))
    for i in range(3):
        arrow(s, xs[i] + bw + Inches(0.04), py + Inches(0.63))

    ty = Inches(3.44)
    label(s, Inches(0.6), ty, Inches(6.0), "why two different topologies")
    text(s, Inches(1.9), ty + Inches(0.26), Inches(2.1), Inches(0.22),
         "3 Specialists", size=9.5, color=ACCENT, bold=True)
    text(s, Inches(4.05), ty + Inches(0.26), Inches(2.4), Inches(0.22),
         "1 Orchestrator", size=9.5, color=ACCENT, bold=True)
    trows = [
        ("Execution", "3 calls in parallel", "serial loop, one call at a time"),
        ("Sees", "only its own slice", "all 3 opinions + dossier + tools"),
        ("Returns", "SpecialistOpinion", "RiskFinding via finalize()"),
        ("Why", "speed, no cross-talk", "each result informs the next question"),
    ]
    for i, (a, b, c) in enumerate(trows):
        ry = ty + Inches(0.52) + Inches(0.31 * i)
        if i % 2 == 0:
            rect(s, Inches(0.6), ry - Inches(0.03), Inches(5.86), Inches(0.29),
                 fill=PANEL, outline=None)
        text(s, Inches(0.72), ry, Inches(1.15), Inches(0.24), a, size=8.5, color=FAINT, bold=True)
        text(s, Inches(1.9), ry, Inches(2.1), Inches(0.24), b, size=8.5, color=MUTED)
        text(s, Inches(4.05), ry, Inches(2.35), Inches(0.24), c, size=8.5, color=MUTED)

    label(s, Inches(6.85), ty, Inches(5.88), "layered memory — 5 tiers, 3 stores")
    tiers = [
        ("Working",      "notes during this run",       "Redis scratchpad",   REVIEW, "evicted on exit"),
        ("Per-customer", "this customer's history",     "SQLite assessments", FAINT,  "permanent"),
        ("Episodic",     "similar cases + corrections", "case bank",          TEAL,   "permanent"),
        ("Semantic",     "typology defs, risk lists",   "static files",       CYAN,   "static"),
        ("Procedural",   "lessons from corrections",    "lessons table",      VIOLET, "grows with use"),
    ]
    for i, (name, what, store, col, life) in enumerate(tiers):
        ry = ty + Inches(0.28) + Inches(0.37 * i)
        rect(s, Inches(6.85), ry, Inches(5.88), Inches(0.33),
             fill=PANEL if i % 2 == 0 else BG, outline=None)
        rect(s, Inches(6.97), ry + Inches(0.11), Inches(0.1), Inches(0.1), fill=col, outline=None)
        text(s, Inches(7.18), ry + Inches(0.05), Inches(1.3), Inches(0.24), name, size=9, color=INK, bold=True)
        text(s, Inches(8.45), ry + Inches(0.05), Inches(1.95), Inches(0.24), what, size=8.5, color=MUTED)
        text(s, Inches(10.42), ry + Inches(0.05), Inches(1.4), Inches(0.24), store, size=8, color=MUTED, font=MONO)
        text(s, Inches(11.86), ry + Inches(0.05), Inches(0.85), Inches(0.24), life, size=7.5, color=FAINT)

    ky = Inches(5.44)
    rect(s, Inches(0.6), ky, Inches(6.0), Inches(1.06), fill=PANEL2, outline=VIOLET)
    text(s, Inches(0.82), ky + Inches(0.11), Inches(5.6), Inches(0.22),
         "THE KEY DESIGN DECISION", size=9, color=FAINT, bold=True)
    text(s, Inches(0.82), ky + Inches(0.34), Inches(5.62), Inches(0.66),
         [[("The orchestrator is ", {"size": 9.5, "color": MUTED}),
           ("serial", {"size": 9.5, "color": INK, "bold": True}),
           (" because investigation is inherently sequential — you cannot know which document to "
            "open until you have seen the transactions. The specialists are ",
            {"size": 9.5, "color": MUTED}),
           ("parallel", {"size": 9.5, "color": INK, "bold": True}),
           (" because their domains are independent.", {"size": 9.5, "color": MUTED})]], line=1.2)

    rect(s, Inches(6.85), ky, Inches(5.88), Inches(1.06), fill=PANEL2, outline=TEAL)
    text(s, Inches(7.07), ky + Inches(0.11), Inches(5.5), Inches(0.22),
         "WHY MEMORY IS RETRIEVED FIRST", size=9, color=FAINT, bold=True)
    text(s, Inches(7.07), ky + Inches(0.34), Inches(5.5), Inches(0.66),
         [[("Memory is loaded ", {"size": 9.5, "color": MUTED}),
           ("before", {"size": 9.5, "color": INK, "bold": True}),
           (" the specialists run, so every LLM call in the pipeline sees the same context — past "
            "assessments, verified precedents, and lessons from corrections. That is what makes "
            "this a system rather than a prompt.", {"size": 9.5, "color": MUTED})]], line=1.2)

    note(s, "The two-topology split is the core architectural claim — parallel where independent, "
            "serial where dependent. The memory table is the second claim: state outlives the request.")
    return s


# ── slide 3 · key highlights ────────────────────────────────────────────────
def slide3(prs):
    s = slide_base(prs, "03 · Key Highlights",
                   "It investigates, cites its evidence, and shows the work",
                   "A real trace from CUST_018 — an Iranian arms dealer. Every step is recorded; the trace is the audit record.")

    label(s, Inches(0.6), Inches(1.72), Inches(6.2), "the loop — actual trace, 12 steps")
    steps = [
        ("1",   "read_document",      "id_document.txt — Iranian passport, valid"),
        ("2",   "read_document",      "rm_notes.txt — RM flags poor source of funds"),
        ("3",   "query_transactions", "31 transactions, £62,174 in credits"),
        ("4-9", "query_transactions", "filtered 6 ways: cash, counterparty, window"),
        ("10",  "find_txn_patterns",  "STRUCTURING candidate, strength 1.0, S00–S03"),
        ("11",  "note",               "“4 sub-threshold deposits in 6 days”"),
        ("12",  "finalize",           "score 83 · HIGH · ESCALATE · conf 0.85"),
    ]
    for i, (n, tool, what) in enumerate(steps):
        ry = Inches(2.0) + Inches(0.38 * i)
        last = i == len(steps) - 1
        rect(s, Inches(0.6), ry, Inches(6.2), Inches(0.32),
             fill=PANEL2 if last else PANEL, outline=HIGH if last else None)
        text(s, Inches(0.7), ry + Inches(0.05), Inches(0.4), Inches(0.22),
             n, size=8, color=FAINT, bold=True, align=PP_ALIGN.RIGHT)
        text(s, Inches(1.2), ry + Inches(0.05), Inches(1.72), Inches(0.22),
             tool, size=8.5, color=HIGH if last else RGBColor(0xC4, 0xB5, 0xFD),
             bold=True, font=MONO)
        text(s, Inches(2.96), ry + Inches(0.05), Inches(3.76), Inches(0.22),
             what, size=8.5, color=INK if last else MUTED)

    label(s, Inches(7.15), Inches(1.72), Inches(5.58), "output — a decision that carries its evidence")
    oy = Inches(2.0)
    rect(s, Inches(7.15), oy, Inches(5.58), Inches(1.4), fill=PANEL2, outline=HIGH)
    text(s, Inches(7.35), oy + Inches(0.08), Inches(5.2), Inches(0.4),
         [[("83", {"size": 26, "bold": True, "color": HIGH}),
           (" / 100", {"size": 11, "color": FAINT}),
           ("    HIGH · ESCALATE", {"size": 12, "bold": True, "color": HIGH}),
           ("   conf 0.85", {"size": 10, "color": MUTED})]])
    text(s, Inches(7.35), oy + Inches(0.52), Inches(5.22), Inches(0.82),
         [[("evidence_refs: ", {"size": 8, "color": FAINT, "font": MONO}),
           ("CUST_018-S00, S01, S02, S03, rm_notes.txt", {"size": 8, "color": LOW, "font": MONO})],
          [("key_signals: ", {"size": 8, "color": FAINT, "font": MONO}),
           ("Iran high-risk jurisdiction · arms dealer occupation · confirmed structuring "
            "($37k across 4 deposits in 6 days)", {"size": 8, "color": MUTED, "font": MONO})]],
         space_after=3, line=1.25)

    label(s, Inches(7.15), Inches(3.58), Inches(5.58), "four guardrails that make it trustworthy")
    guards = [
        ("Citation check", "evidence_refs validated against what the tools actually returned — fabrications rejected"),
        ("Bounded loop", "12 steps max; exceeding it routes to a human, never loops forever"),
        ("Never blank", "any exception still produces a valid decision, routed to review"),
        ("Facts, not verdicts", "find_txn_patterns returns candidates the agent must judge and cite"),
    ]
    for i, (h, b) in enumerate(guards):
        card(s, Inches(7.15), Inches(3.86) + Inches(0.55 * i), Inches(5.58), Inches(0.5),
             h, b, hsize=9.5, bsize=8, hcolor=LOW)

    ry = Inches(4.86)
    label(s, Inches(0.6), ry, Inches(6.2), "it works end-to-end")
    cw = Inches(1.19)
    kpis = [("scored", "22", INK), ("auto-cleared", "27%", LOW), ("escalated", "3", HIGH),
            ("to a human", "1", REVIEW), ("tests", "14 ✓", LOW)]
    for i, (l, v, c) in enumerate(kpis):
        x = Inches(0.6) + (cw + Inches(0.06)) * i
        rect(s, x, ry + Inches(0.26), cw, Inches(0.62), fill=PANEL)
        text(s, x + Inches(0.1), ry + Inches(0.32), cw - Inches(0.2), Inches(0.2),
             l.upper(), size=7, color=FAINT, bold=True)
        text(s, x + Inches(0.1), ry + Inches(0.5), cw - Inches(0.2), Inches(0.3),
             v, size=15, color=c, bold=True)

    label(s, Inches(0.6), Inches(6.0), Inches(6.2), "same agent, opposite ends of the queue")
    rect(s, Inches(0.6), Inches(6.26), Inches(6.2), Inches(0.42), fill=PANEL, outline=HIGH)
    text(s, Inches(0.76), Inches(6.34), Inches(5.9), Inches(0.26),
         [[("CUST_018", {"size": 9.5, "bold": True, "color": INK, "font": MONO}),
           ("  arms dealer, Iran → ", {"size": 8.5, "color": MUTED}),
           ("83 HIGH / ESCALATE", {"size": 9.5, "bold": True, "color": HIGH}),
           (" @ 0.85", {"size": 8.5, "color": MUTED})]])
    rect(s, Inches(0.6), Inches(6.76), Inches(6.2), Inches(0.42), fill=PANEL, outline=LOW)
    text(s, Inches(0.76), Inches(6.84), Inches(5.9), Inches(0.26),
         [[("CUST_000", {"size": 9.5, "bold": True, "color": INK, "font": MONO}),
           ("  UK teacher, salary → ", {"size": 8.5, "color": MUTED}),
           ("5 LOW / AUTO_CLEAR", {"size": 9.5, "bold": True, "color": LOW}),
           (" @ 0.95", {"size": 8.5, "color": MUTED})]])

    note(s, "Walk the trace. This is 'show your work' made concrete. Point at step 10 — the tool "
            "only suggests structuring; the agent had to accept it and cite the exact rows to claim it.")
    return s


# ── slide 4 · human-in-the-loop ─────────────────────────────────────────────
def slide4(prs):
    s = slide_base(prs, "04 · Human-in-the-Loop",
                   "The flywheel: uncertainty becomes training signal",
                   "Confidence gates the outcome. What the human corrects, the system remembers — three different ways.")

    gy = Inches(1.78)
    rect(s, Inches(0.6), gy, Inches(2.4), Inches(0.66), fill=PANEL2, outline=VIOLET)
    text(s, Inches(0.74), gy + Inches(0.09), Inches(2.15), Inches(0.5),
         [[("RiskFinding", {"size": 11, "bold": True, "color": INK})],
          [("+ self-reported confidence", {"size": 8, "color": MUTED})]], space_after=1)
    arrow(s, Inches(3.08), gy + Inches(0.25))
    rect(s, Inches(3.5), gy, Inches(2.1), Inches(0.66), fill=PANEL, outline=ACCENT)
    text(s, Inches(3.6), gy + Inches(0.18), Inches(1.9), Inches(0.32),
         "confidence ≥ 0.60 ?", size=10.5, color=ACCENT, bold=True, align=PP_ALIGN.CENTER)

    rect(s, Inches(5.92), Inches(1.66), Inches(2.66), Inches(0.55), fill=PANEL, outline=LOW)
    text(s, Inches(6.06), Inches(1.77), Inches(2.4), Inches(0.32),
         [[("YES → ", {"size": 9.5, "bold": True, "color": LOW}),
           ("auto-dispose by band", {"size": 9.5, "color": MUTED})]])
    rect(s, Inches(5.92), Inches(2.31), Inches(2.66), Inches(0.55), fill=PANEL, outline=REVIEW)
    text(s, Inches(6.06), Inches(2.42), Inches(2.4), Inches(0.32),
         [[("NO → ", {"size": 9.5, "bold": True, "color": REVIEW}),
           ("Redis review queue", {"size": 9.5, "color": MUTED})]])
    arrow(s, Inches(8.7), Inches(2.44))
    rect(s, Inches(9.1), Inches(2.22), Inches(3.63), Inches(0.66), fill=PANEL2, outline=REVIEW)
    text(s, Inches(9.26), Inches(2.33), Inches(3.35), Inches(0.5),
         [[("Human sets the correct score", {"size": 10, "bold": True, "color": INK})],
          [("nothing is hidden from the reviewer", {"size": 8, "color": MUTED})]], space_after=1)

    wy = Inches(3.16)
    rect(s, Inches(0.6), wy, Inches(6.0), Inches(1.34), fill=PANEL)
    text(s, Inches(0.78), wy + Inches(0.11), Inches(5.6), Inches(0.22),
         "WHY GATE ON CONFIDENCE, NOT SCORE", size=9, color=FAINT, bold=True)
    text(s, Inches(0.78), wy + Inches(0.36), Inches(5.64), Inches(0.92),
         [[("A score of 58 is not automatically uncertain — the agent may be very confident it is a "
            "58. What matters is whether ", {"size": 9.5, "color": MUTED}),
           ("the evidence supports the conclusion", {"size": 9.5, "color": INK, "bold": True}),
           (". Confidence is the agent's own self-report, and the prompt tells it that low-confidence "
            "cases go to a human — so ", {"size": 9.5, "color": MUTED}),
           ("admitting uncertainty is the rewarded behaviour", {"size": 9.5, "color": LOW, "bold": True}),
           (".", {"size": 9.5, "color": MUTED})]], line=1.2)

    ry2 = Inches(4.68)
    rect(s, Inches(0.6), ry2, Inches(6.0), Inches(1.06), fill=PANEL)
    text(s, Inches(0.78), ry2 + Inches(0.11), Inches(5.6), Inches(0.22),
         "WHAT THE REVIEWER SEES — NOTHING IS HIDDEN", size=9, color=FAINT, bold=True)
    text(s, Inches(0.78), ry2 + Inches(0.35), Inches(5.64), Inches(0.64),
         "The proposed score and confidence · all three specialist opinions, including where they "
         "disagreed · the complete tool-call trace · the agent's own working notes · the memory that "
         "was injected into the prompt.", size=9.5, color=MUTED, line=1.2)

    label(s, Inches(6.85), Inches(3.16), Inches(5.88), "one correction → three learning paths")
    paths = [
        ("1 · human-verified episode", "future similar customers retrieve it as a few-shot example", TEAL),
        ("2 · a lesson (frisk reflect)", "distilled and injected into every future orchestrator prompt", VIOLET),
        ("3 · a row in customer history", "the next assessment of that customer sees what changed", CYAN),
    ]
    for i, (h, b, c) in enumerate(paths):
        card(s, Inches(6.85), Inches(3.44) + Inches(0.6 * i), Inches(5.88), Inches(0.54),
             h, b, accent=c, bar=True, hsize=9.5, bsize=8.5)
    text(s, Inches(6.85), Inches(5.24), Inches(5.88), Inches(0.24),
         [[("Most systems have one of these. Three means one correction improves ",
            {"size": 8.5, "color": FAINT}),
           ("similar cases, all cases, and this case", {"size": 8.5, "color": MUTED, "bold": True}),
           (" at once.", {"size": 8.5, "color": FAINT})]])

    ay = Inches(5.62)
    rect(s, Inches(6.85), ay, Inches(5.88), Inches(1.16), fill=PANEL2, outline=LOW)
    text(s, Inches(7.05), ay + Inches(0.11), Inches(5.6), Inches(0.22),
         "ANTI-ECHO-CHAMBER GUARD", size=9, color=LOW, bold=True)
    text(s, Inches(7.05), ay + Inches(0.35), Inches(5.6), Inches(0.74),
         "Episodic few-shot draws only from human-verified cases. The system never learns from its "
         "own unreviewed output, so its mistakes cannot compound into false precedent. Every "
         "decision — cleared as well as escalated — is written to an append-only audit log.",
         size=9.5, color=MUTED, line=1.2)

    note(s, "This is the slide that answers 'does it improve?'. Emphasise the three paths, then the "
            "anti-echo-chamber rule — that is the detail showing the failure mode was anticipated.")
    return s


# ── slide 5 · challenges & learnings ────────────────────────────────────────
def slide5(prs):
    s = slide_base(prs, "05 · Challenges & Learnings",
                   "Four things that broke, and what they taught",
                   "Each challenge below changed the design — these are not hypotheticals, they are bugs that shipped and were fixed.")

    label(s, Inches(0.6), Inches(1.72), Inches(6.6), "challenges that changed the design")
    chals = [
        ("1 · The agent that never finished", HIGH,
         "Runs hit the 12-step cap mid-investigation and returned score 0 at confidence 0 — which the "
         "router read as a legitimate “uncertain” case. A silent failure disguised as a valid decision.",
         "Fix: in the final two turns, finalize is the only bound tool. A bounded loop needs a "
         "forced exit, not just a cap."),
        ("2 · A deleted feature that would not die", REVIEW,
         "Sanctions screening was cut from scope but kept appearing in output — three ghosts: a {} "
         "default in the loader, a stray phrase in a reference file, and a stale LLM cache.",
         "Fix: purge data, not just code. Added a scope guard to every prompt, then re-scored all 22 "
         "customers to verify zero mentions."),
        ("3 · “It must be rate limiting”", MED,
         "Parallel scoring took 76–90s and I assumed throttling. The data disagreed — no request cap, "
         "and 4 concurrent calls took 1.55s vs 1.48s for one. Real cause: serial depth, plus a tool "
         "factory rebuilt every call (375ms vs 0.9ms).",
         "Fix: cache the detectors. That path went from 7500ms to 5ms."),
        ("4 · Learning from its own homework", VIOLET,
         "Episodic retrieval would have surfaced the agent's own unreviewed decisions as precedent, "
         "compounding any early error into permanent bias.",
         "Fix: restrict episodic retrieval to human-verified cases only."),
    ]
    for i, (h, c, problem, fix) in enumerate(chals):
        cy = Inches(2.0) + Inches(1.26 * i)
        rect(s, Inches(0.6), cy, Inches(6.6), Inches(1.14), fill=PANEL)
        rect(s, Inches(0.6), cy, Pt(3), Inches(1.14), fill=c, outline=None, radius=False)
        text(s, Inches(0.82), cy + Inches(0.08), Inches(6.25), Inches(0.22),
             h, size=10, color=c, bold=True)
        text(s, Inches(0.82), cy + Inches(0.3), Inches(6.28), Inches(0.5),
             problem, size=8.5, color=MUTED, line=1.14)
        text(s, Inches(0.82), cy + Inches(0.84), Inches(6.28), Inches(0.24),
             fix, size=8.5, color=LOW, line=1.14)

    label(s, Inches(7.5), Inches(1.72), Inches(5.23), "learnings")
    lessons = [
        ("Give the model facts, not verdicts",
         "Tools returning candidates the agent must judge and cite produce better reasoning than tools "
         "returning conclusions — and the citation is auditable."),
        ("Confidence routes better than score",
         "A confident 58 needs no human; an unsure 30 does. Routing on certainty rather than severity "
         "is what makes escalation meaningful."),
        ("Measure before optimising",
         "My first latency diagnosis was wrong, and only measurement showed it. The fix I would have "
         "shipped would have addressed nothing."),
        ("In compliance, the trace is the product",
         "A correct score that cannot be explained is worthless to a regulator. Explainability is not "
         "bolted on afterwards; it is the output."),
    ]
    for i, (h, b) in enumerate(lessons):
        card(s, Inches(7.5), Inches(2.0) + Inches(0.84 * i), Inches(5.23), Inches(0.74),
             h, b, hsize=10, bsize=8.5, hcolor=ACCENT, fill=PANEL2)

    ny = Inches(5.44)
    label(s, Inches(7.5), ny, Inches(5.23), "honest limits → what comes next")
    nexts = [
        ("~45–90s per customer", "batch mode overlaps customers; fewer steps per run"),
        ("Not byte-reproducible", "pin model snapshots; store the full prompt hash"),
        ("Episodic recall is feature-match", "similar() is deliberately vector-pluggable"),
        ("Fixed 0.60 confidence gate", "calibrate against accumulated human corrections"),
    ]
    for i, (lim, nxt) in enumerate(nexts):
        ly = ny + Inches(0.26) + Inches(0.36 * i)
        rect(s, Inches(7.5), ly, Inches(5.23), Inches(0.32),
             fill=PANEL if i % 2 == 0 else BG, outline=None)
        text(s, Inches(7.62), ly + Inches(0.05), Inches(2.15), Inches(0.22),
             lim, size=8.5, color=MED, bold=True)
        text(s, Inches(9.85), ly + Inches(0.05), Inches(2.8), Inches(0.22),
             nxt, size=8.5, color=MUTED)

    note(s, "Close on the challenges and learnings, not the wins. Showing that you found the silent "
            "failure — and that you were wrong once and the data corrected you — is more convincing "
            "than claiming it is finished.\n\n"
            "If asked about engineering decisions: no deterministic scoring · sanctions deliberately "
            "scoped out (the brief said “external alerts”) · Decimal money · seeded byte-identical "
            "data generation · append-only audit of clears as well as escalations · working-memory "
            "scratchpad evicted on every exit path.")
    return s


def main():
    prs = Presentation()
    prs.slide_width, prs.slide_height = W, H
    for fn in (slide1, slide2, slide3, slide4, slide5):
        fn(prs)

    # ponytail: one assert instead of a test file — a layout regression fails the build.
    for n, s in enumerate(prs.slides, 1):
        for sh in s.shapes:
            assert sh.left >= 0 and sh.top >= 0 and sh.left + sh.width <= W \
                and sh.top + sh.height <= H, \
                f"slide {n}: shape outside canvas at ({sh.left/914400:.2f}, {sh.top/914400:.2f})"

    prs.save(OUT)
    print(f"built {len(prs.slides._sldIdLst)} slides -> {OUT}")


if __name__ == "__main__":
    main()
