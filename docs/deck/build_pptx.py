"""Build the 5-slide submission deck (deck.pptx).

    pip install python-pptx
    python docs/deck/build_pptx.py

Design is authored here rather than parsed from SLIDES.md: the deck is table-, diagram- and
screenshot-heavy, and a markdown bullet-parser cannot lay that out well. SLIDES.md remains the
narrative source (and the speaker notes below are lifted from it).

Visual language matches the app — "Charcoal Ink": near-black canvas, neutral greys, and colour
reserved exclusively for risk semantics (green = cleared, amber = review, red = escalate).

The build asserts every shape stays inside the 16:9 canvas, so a layout regression fails loudly.
"""
from __future__ import annotations

import os

from pptx import Presentation
from pptx.dml.color import RGBColor
from pptx.enum.shapes import MSO_SHAPE
from pptx.enum.text import MSO_ANCHOR, PP_ALIGN
from pptx.util import Emu, Inches, Pt

HERE = os.path.dirname(os.path.abspath(__file__))
SHOTS = os.path.join(HERE, "screenshots")
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


def pic(slide, name, x, y, h):
    """Place a screenshot sized by HEIGHT (native aspect drives width). Returns (width, shape)."""
    p = os.path.join(SHOTS, name)
    if not os.path.exists(p):
        print(f"  ! missing screenshot: {name}")
        return Emu(0), None
    img = slide.shapes.add_picture(p, x, y, height=h)
    img.line.color.rgb = LINE
    img.line.width = Pt(1)
    return img.width, img


def caption(slide, x, y, w, txt):
    text(slide, x, y, w, Inches(0.2), txt, size=8, color=FAINT, align=PP_ALIGN.CENTER)


def stat(slide, x, y, w, label, value, color=INK, delta=None):
    rect(slide, x, y, w, Inches(1.02), fill=PANEL)
    text(slide, x + Inches(0.16), y + Inches(0.12), w - Inches(0.3), Inches(0.2),
         label.upper(), size=9, color=FAINT, bold=True)
    text(slide, x + Inches(0.16), y + Inches(0.34), w - Inches(0.3), Inches(0.45),
         value, size=24, color=color, bold=True)
    if delta:
        text(slide, x + Inches(0.16), y + Inches(0.76), w - Inches(0.3), Inches(0.2),
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


# ── slides ──────────────────────────────────────────────────────────────────
def slide1(prs):
    s = slide_base(prs, "01 · Problem & Objective",
                   "Analysts drown in fragmented signals",
                   "Five disconnected artefacts per customer — read manually, hundreds of times a day.")

    text(s, Inches(0.6), Inches(1.72), Inches(5.5), Inches(0.24),
         "WHAT ONE CUSTOMER LOOKS LIKE", size=9.5, color=FAINT, bold=True)
    rows = [
        ("kyc.json",         "structured", "identity, occupation, PEP"),
        ("account.json",     "structured", "tenure, product, jurisdiction"),
        ("transactions.csv", "structured", "the actual behaviour — 100s of rows"),
        ("rm_notes.txt",     "free text",  "the relationship manager's unease"),
        ("id_document.txt",  "free text",  "document anomalies, admissions"),
    ]
    for i, (f, kind, hides) in enumerate(rows):
        ry = Inches(2.0) + Inches(0.48 * i)
        rect(s, Inches(0.6), ry, Inches(5.5), Inches(0.4), fill=PANEL)
        text(s, Inches(0.74), ry + Inches(0.08), Inches(1.7), Inches(0.26),
             f, size=9.5, color=INK, bold=True, font=MONO)
        text(s, Inches(2.44), ry + Inches(0.09), Inches(0.92), Inches(0.24),
             kind, size=8, color=REVIEW if kind == "free text" else FAINT, bold=True)
        text(s, Inches(3.36), ry + Inches(0.09), Inches(2.66), Inches(0.24),
             hides, size=8.5, color=MUTED)

    text(s, Inches(6.45), Inches(1.72), Inches(6.28), Inches(0.24),
         "THREE FAILURES THIS CREATES", size=9.5, color=FAINT, bold=True)
    fails = [
        ("Slow", HIGH,
         "Minutes per customer — and the queue is unordered, so the riskiest case may be read last."),
        ("Inconsistent", MED,
         "Two analysts score the same file differently. There is no shared calibration."),
        ("Unauditable", REVIEW,
         "The reasoning lives in someone's head. A regulator asking “why was this cleared?” gets a shrug."),
    ]
    for i, (h, c, body) in enumerate(fails):
        fy = Inches(2.0) + Inches(0.8 * i)
        rect(s, Inches(6.45), fy, Inches(6.28), Inches(0.7), fill=PANEL)
        rect(s, Inches(6.45), fy, Pt(3), Inches(0.7), fill=c, outline=None, radius=False)
        text(s, Inches(6.66), fy + Inches(0.07), Inches(5.9), Inches(0.24),
             h, size=11.5, color=c, bold=True)
        text(s, Inches(6.66), fy + Inches(0.29), Inches(5.95), Inches(0.38),
             body, size=9, color=MUTED, line=1.15)

    oy = Inches(4.48)
    rect(s, Inches(0.6), oy, Inches(12.13), Inches(0.88), fill=PANEL2, outline=ACCENT)
    text(s, Inches(0.82), oy + Inches(0.11), Inches(11.6), Inches(0.24),
         "OBJECTIVE", size=9, color=FAINT, bold=True)
    text(s, Inches(0.82), oy + Inches(0.35), Inches(11.6), Inches(0.45),
         [[("Do the first pass: ", {"bold": True, "color": INK}),
           ("read every source, investigate like an analyst, ", {"color": MUTED}),
           ("rank the whole book by risk", {"bold": True, "color": INK}),
           (", and ", {"color": MUTED}),
           ("show the work", {"bold": True, "color": INK}),
           (" — so the human starts from evidence, not a blank page.", {"color": MUTED})]],
         size=12)

    cy = Inches(5.55)
    rect(s, Inches(0.6), cy, Inches(8.0), Inches(1.62), fill=PANEL)
    rect(s, Inches(0.6), cy, Pt(3), Inches(1.62), fill=REVIEW, outline=None, radius=False)
    text(s, Inches(0.84), cy + Inches(0.16), Inches(7.5), Inches(0.24),
         "DESIGN CONSTRAINT THAT SHAPED EVERYTHING", size=9, color=FAINT, bold=True)
    text(s, Inches(0.84), cy + Inches(0.44), Inches(7.55), Inches(1.05),
         [[("A false negative — a missed launderer — is catastrophic; a false positive is merely "
            "expensive.", {"color": INK, "size": 11.5})],
          [("So the system must ", {"color": MUTED, "size": 11.5}),
           ("know when it is unsure", {"bold": True, "color": REVIEW, "size": 11.5}),
           (" and escalate, rather than guess confidently — which is why confidence, not score, "
            "decides who sees the case.", {"color": MUTED, "size": 11.5})]],
         space_after=6, line=1.3)

    iw, _ = pic(s, "02-ranked-queue.png", Inches(8.9), Inches(5.55), Inches(1.62))
    caption(s, Inches(8.9), Inches(7.2), iw, "The output that fixes all three — a ranked, evidenced queue")
    note(s, "Lead with the analyst's desk, not the tech. The problem is fragmentation + inconsistency "
            "+ no audit trail. Everything in the next four slides answers one of those three.")
    return s


def slide2(prs):
    s = slide_base(prs, "02 · Architecture & Agent Orchestration",
                   "Parallel where independent, serial where dependent",
                   "Four stages per customer. No deterministic rules engine — the LLM judges; code supplies tools, memory and guardrails.")

    py = Inches(1.76)
    bw, bh = Inches(2.72), Inches(1.36)
    gap = Inches(0.36)
    xs = [Inches(0.6) + (bw + gap) * i for i in range(4)]
    flow_box(s, xs[0], py, bw, bh, "1 · INGEST",
             ["kyc · account · transactions", "id_document · rm_notes",
              "correspondence · screening", "→ one typed Dossier"],
             accent=CYAN, tcolor=RGBColor(0x7D, 0xD3, 0xFC))
    flow_box(s, xs[1], py, bw, bh, "2 · RETRIEVE MEMORY",
             ["per-customer history", "similar past cases", "lessons learned",
              "reference cheat-sheets"], accent=TEAL, tcolor=RGBColor(0x5E, 0xEA, 0xD4))
    flow_box(s, xs[2], py, bw, bh, "3 · INVESTIGATE",
             ["3 specialists — PARALLEL", "   KYC · transactions · docs",
              "agentic orchestrator — SERIAL", "   tools → finalize()"],
             accent=VIOLET, tcolor=RGBColor(0xC4, 0xB5, 0xFD))
    flow_box(s, xs[3], py, bw, bh, "4 · DECIDE + LEARN",
             ["conf ≥ 0.60 → auto-dispose", "conf < 0.60 → human queue",
              "correction → memory"], accent=REVIEW, tcolor=RGBColor(0xFD, 0xBA, 0x74))
    for i in range(3):
        arrow(s, xs[i] + bw + Inches(0.04), py + Inches(0.6))

    ty = Inches(3.38)
    text(s, Inches(0.6), ty, Inches(6.0), Inches(0.24),
         "WHY TWO DIFFERENT TOPOLOGIES", size=9.5, color=FAINT, bold=True)
    text(s, Inches(1.9), ty + Inches(0.26), Inches(2.1), Inches(0.22),
         "Specialists", size=9.5, color=ACCENT, bold=True)
    text(s, Inches(4.05), ty + Inches(0.26), Inches(2.4), Inches(0.22),
         "Orchestrator", size=9.5, color=ACCENT, bold=True)
    trows = [
        ("Execution", "3 parallel calls", "serial loop, one call at a time"),
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

    text(s, Inches(6.85), ty, Inches(5.88), Inches(0.24),
         "LAYERED MEMORY — 5 TIERS, 3 STORES", size=9.5, color=FAINT, bold=True)
    tiers = [
        ("Working",      "notes during this run",       "Redis scratchpad",   REVIEW, "evicted on exit"),
        ("Per-customer", "this customer's history",     "SQLite assessments", FAINT,  "permanent"),
        ("Episodic",     "similar cases + corrections", "case-bank",          TEAL,   "permanent"),
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

    iw, _ = pic(s, "03-case-specialists.png", Inches(0.6), Inches(5.05), Inches(1.5))
    caption(s, Inches(0.6), Inches(6.62), iw, "The three parallel specialist opinions, in the case drawer")

    text(s, Inches(3.5), Inches(5.62), Inches(9.23), Inches(1.1),
         [[("The key design decision", {"bold": True, "color": ACCENT, "size": 11.5})],
          [("The orchestrator is ", {"color": MUTED, "size": 10.5}),
           ("serial", {"bold": True, "color": INK, "size": 10.5}),
           (" because investigation is inherently sequential — you cannot know which document to open "
            "until you have seen the transactions. The specialists are ", {"color": MUTED, "size": 10.5}),
           ("parallel", {"bold": True, "color": INK, "size": 10.5}),
           (" because their domains are independent, so running them together costs nothing and stops "
            "them contaminating each other's reasoning.", {"color": MUTED, "size": 10.5})]],
         space_after=5, line=1.3)

    note(s, "The two-topology split is the core architectural claim — parallel where independent, serial "
            "where dependent. The memory table is what makes it a system rather than a prompt.")
    return s


def slide3(prs):
    s = slide_base(prs, "03 · Input → Agent Loop → Output",
                   "A real investigation, step by step",
                   "Trace from CUST_018 — an Iranian arms dealer. Every step recorded; the trace is the audit record.")

    text(s, Inches(0.6), Inches(1.72), Inches(6.1), Inches(0.24),
         "THE LOOP — ACTUAL TRACE", size=9.5, color=FAINT, bold=True)
    steps = [
        ("1",   "read_document",      "id_document.txt — Iranian passport, valid"),
        ("2",   "read_document",      "rm_notes.txt — RM flags poor source of funds"),
        ("3",   "query_transactions", "31 transactions, £62,174 credits"),
        ("4-9", "query_transactions", "filtered: cash deposits, counterparty, window"),
        ("10",  "find_txn_patterns",  "STRUCTURING candidate, strength 1.0, S00–S03"),
        ("11",  "note",               "“4 sub-threshold deposits in 6 days”"),
        ("12",  "finalize",           "score 83 · HIGH · ESCALATE · conf 0.85"),
    ]
    for i, (n, tool, what) in enumerate(steps):
        ry = Inches(2.0) + Inches(0.4 * i)
        last = i == len(steps) - 1
        rect(s, Inches(0.6), ry, Inches(6.1), Inches(0.34),
             fill=PANEL2 if last else PANEL, outline=HIGH if last else None)
        text(s, Inches(0.7), ry + Inches(0.06), Inches(0.4), Inches(0.22),
             n, size=8, color=FAINT, bold=True, align=PP_ALIGN.RIGHT)
        text(s, Inches(1.2), ry + Inches(0.06), Inches(1.72), Inches(0.22),
             tool, size=8.5, color=HIGH if last else RGBColor(0xC4, 0xB5, 0xFD),
             bold=True, font=MONO)
        text(s, Inches(2.96), ry + Inches(0.06), Inches(3.66), Inches(0.22),
             what, size=8.5, color=INK if last else MUTED)

    text(s, Inches(7.05), Inches(1.72), Inches(5.68), Inches(0.24),
         "OUTPUT — A DECISION THAT CARRIES ITS EVIDENCE", size=9.5, color=FAINT, bold=True)
    oy = Inches(2.0)
    rect(s, Inches(7.05), oy, Inches(5.68), Inches(1.5), fill=PANEL2, outline=HIGH)
    text(s, Inches(7.25), oy + Inches(0.09), Inches(5.3), Inches(0.42),
         [[("83", {"size": 27, "bold": True, "color": HIGH}),
           (" / 100", {"size": 11.5, "color": FAINT}),
           ("    HIGH · ESCALATE", {"size": 12, "bold": True, "color": HIGH}),
           ("   conf 0.85", {"size": 10, "color": MUTED})]])
    text(s, Inches(7.25), oy + Inches(0.56), Inches(5.32), Inches(0.85),
         [[("evidence_refs: ", {"size": 8, "color": FAINT, "font": MONO}),
           ("CUST_018-S00, S01, S02, S03, rm_notes.txt", {"size": 8, "color": LOW, "font": MONO})],
          [("key_signals: ", {"size": 8, "color": FAINT, "font": MONO}),
           ("Iran high-risk jurisdiction · arms dealer occupation · confirmed structuring "
            "($37k across 4 deposits in 6 days)", {"size": 8, "color": MUTED, "font": MONO})]],
         space_after=3, line=1.25)

    text(s, Inches(7.05), Inches(3.68), Inches(5.68), Inches(0.24),
         "GUARDRAILS THAT MAKE THE OUTPUT TRUSTWORTHY", size=9.5, color=FAINT, bold=True)
    guards = [
        ("Citation check", "evidence_refs validated against what tools actually returned; fabrications rejected"),
        ("Bounded loop", "12 steps max — exceeding it routes to a human, never loops forever"),
        ("Never blank", "any exception still produces a valid decision routed to review"),
        ("Facts, not verdicts", "find_txn_patterns yields candidates the LLM must judge and justify"),
    ]
    for i, (h, b) in enumerate(guards):
        gy = Inches(3.96) + Inches(0.58 * i)
        rect(s, Inches(7.05), gy, Inches(5.68), Inches(0.52), fill=PANEL)
        text(s, Inches(7.22), gy + Inches(0.05), Inches(5.3), Inches(0.22),
             h, size=9.5, color=LOW, bold=True)
        text(s, Inches(7.22), gy + Inches(0.25), Inches(5.36), Inches(0.24),
             b, size=8, color=MUTED)

    iw, _ = pic(s, "04-tool-trace.png", Inches(0.6), Inches(4.98), Inches(2.1))
    caption(s, Inches(0.6), Inches(7.14), iw, "The same trace in the app — the audit record analysts actually read")
    note(s, "Walk the trace line by line — this is the 'show your work' claim made concrete. Point out "
            "step 10: the tool only suggests structuring; the agent had to accept it and cite the exact rows.")
    return s


def slide4(prs):
    s = slide_base(prs, "04 · Human-in-the-Loop",
                   "The flywheel: uncertainty becomes training signal",
                   "Confidence gates the outcome. What the human corrects, the system remembers — three different ways.")

    gy = Inches(1.76)
    rect(s, Inches(0.6), gy, Inches(2.4), Inches(0.66), fill=PANEL2, outline=VIOLET)
    text(s, Inches(0.74), gy + Inches(0.09), Inches(2.15), Inches(0.5),
         [[("RiskFinding", {"size": 11, "bold": True, "color": INK})],
          [("+ self-reported confidence", {"size": 8, "color": MUTED})]], space_after=1)
    arrow(s, Inches(3.08), gy + Inches(0.25))
    rect(s, Inches(3.5), gy, Inches(2.1), Inches(0.66), fill=PANEL, outline=ACCENT)
    text(s, Inches(3.6), gy + Inches(0.18), Inches(1.9), Inches(0.32),
         "confidence ≥ 0.60 ?", size=10.5, color=ACCENT, bold=True, align=PP_ALIGN.CENTER)

    rect(s, Inches(5.92), Inches(1.64), Inches(2.66), Inches(0.55), fill=PANEL, outline=LOW)
    text(s, Inches(6.06), Inches(1.75), Inches(2.4), Inches(0.32),
         [[("YES → ", {"size": 9.5, "bold": True, "color": LOW}),
           ("auto-dispose by band", {"size": 9.5, "color": MUTED})]])
    rect(s, Inches(5.92), Inches(2.29), Inches(2.66), Inches(0.55), fill=PANEL, outline=REVIEW)
    text(s, Inches(6.06), Inches(2.40), Inches(2.4), Inches(0.32),
         [[("NO → ", {"size": 9.5, "bold": True, "color": REVIEW}),
           ("Redis review queue", {"size": 9.5, "color": MUTED})]])
    arrow(s, Inches(8.7), Inches(2.42))
    rect(s, Inches(9.1), Inches(2.2), Inches(3.63), Inches(0.66), fill=PANEL2, outline=REVIEW)
    text(s, Inches(9.26), Inches(2.31), Inches(3.35), Inches(0.5),
         [[("Human sets the correct score", {"size": 10, "bold": True, "color": INK})],
          [("sees opinions, full trace, agent notes", {"size": 8, "color": MUTED})]], space_after=1)

    wy = Inches(3.12)
    rect(s, Inches(0.6), wy, Inches(6.0), Inches(1.36), fill=PANEL)
    text(s, Inches(0.78), wy + Inches(0.11), Inches(5.6), Inches(0.22),
         "WHY GATE ON CONFIDENCE, NOT SCORE", size=9.5, color=FAINT, bold=True)
    text(s, Inches(0.78), wy + Inches(0.37), Inches(5.64), Inches(0.92),
         [[("A score of 58 is not automatically uncertain — the agent may be very confident it is a 58. "
            "What matters is whether ", {"size": 9.5, "color": MUTED}),
           ("the evidence supports the conclusion", {"size": 9.5, "color": INK, "bold": True}),
           (". Confidence is the agent's own honest self-report, and the prompt tells it that "
            "low-confidence cases go to a human — so ", {"size": 9.5, "color": MUTED}),
           ("admitting uncertainty is the rewarded behaviour", {"size": 9.5, "color": LOW, "bold": True}),
           (".", {"size": 9.5, "color": MUTED})]], line=1.22)

    text(s, Inches(6.85), wy, Inches(5.88), Inches(0.24),
         "ONE CORRECTION → THREE LEARNING PATHS", size=9.5, color=FAINT, bold=True)
    paths = [
        ("human-verified episode", "similar customers retrieve it as few-shot", TEAL),
        ("a lesson (frisk reflect)", "injected into every future orchestrator prompt", VIOLET),
        ("a row in customer history", "next assessment sees what changed", CYAN),
    ]
    for i, (h, b, c) in enumerate(paths):
        pyy = wy + Inches(0.28) + Inches(0.45 * i)
        rect(s, Inches(6.85), pyy, Inches(5.88), Inches(0.4), fill=PANEL)
        rect(s, Inches(6.85), pyy, Pt(3), Inches(0.4), fill=c, outline=None, radius=False)
        text(s, Inches(7.04), pyy + Inches(0.04), Inches(2.6), Inches(0.22),
             h, size=9, color=INK, bold=True)
        text(s, Inches(9.7), pyy + Inches(0.05), Inches(2.95), Inches(0.22),
             b, size=8, color=MUTED)

    ay = Inches(4.78)
    rect(s, Inches(6.85), ay, Inches(5.88), Inches(0.68), fill=PANEL2, outline=LOW)
    text(s, Inches(7.04), ay + Inches(0.09), Inches(5.6), Inches(0.52),
         [[("Anti-echo-chamber guard: ", {"size": 9, "bold": True, "color": LOW}),
           ("episodic few-shot draws only from human-verified cases. The system never learns from its "
            "own unreviewed output, so mistakes cannot compound into false precedent.",
            {"size": 9, "color": MUTED})]], line=1.2)

    text(s, Inches(6.85), Inches(5.62), Inches(5.88), Inches(0.5),
         [[("Every decision — cleared as well as escalated — is written to an append-only audit log, "
            "so the flywheel is inspectable, not just felt.", {"size": 9, "color": FAINT})]], line=1.2)

    iw, _ = pic(s, "07-teach-the-model.png", Inches(0.6), Inches(4.66), Inches(2.42))
    caption(s, Inches(0.6), Inches(7.14), iw,
            "“Agent proposed 45 at confidence 0.50 — below threshold.” The reviewer corrects it here.")
    note(s, "This is the slide that answers 'so it improves?'. Emphasise the three paths — most systems "
            "have one (few-shot). The anti-echo-chamber rule is the detail that shows rigour.")
    return s


def slide5(prs):
    s = slide_base(prs, "05 · Results, Trade-offs & Next Steps",
                   "It works end-to-end — and here is where it is weak",
                   "22 customers scored live by the real model. 14 tests pass with no API key required.")

    ky = Inches(1.72)
    cw = Inches(2.34)
    stat(s, Inches(0.6), ky, cw, "Customers scored", "22", INK, "one full synthetic book")
    stat(s, Inches(3.06), ky, cw, "Auto-cleared", "27%", LOW, "zero human time")
    stat(s, Inches(5.52), ky, cw, "Escalated", "3", HIGH, "to a senior reviewer")
    stat(s, Inches(7.98), ky, cw, "Sent to a human", "1", REVIEW, "below confidence gate")
    stat(s, Inches(10.44), ky, Inches(2.29), "Tests", "14 ✓", LOW, "mock provider, offline")

    wy = Inches(3.0)
    text(s, Inches(0.6), wy, Inches(6.0), Inches(0.24),
         "SAME AGENT, OPPOSITE ENDS OF THE QUEUE", size=9.5, color=FAINT, bold=True)
    rect(s, Inches(0.6), wy + Inches(0.26), Inches(6.0), Inches(0.58), fill=PANEL, outline=HIGH)
    text(s, Inches(0.78), wy + Inches(0.35), Inches(5.7), Inches(0.4),
         [[("CUST_018", {"size": 10, "bold": True, "color": INK, "font": MONO}),
           ("  arms dealer, Iran, structuring → ", {"size": 9, "color": MUTED}),
           ("83 HIGH / ESCALATE", {"size": 10, "bold": True, "color": HIGH}),
           (" @ 0.85", {"size": 9, "color": MUTED})]])
    rect(s, Inches(0.6), wy + Inches(0.92), Inches(6.0), Inches(0.58), fill=PANEL, outline=LOW)
    text(s, Inches(0.78), wy + Inches(1.01), Inches(5.7), Inches(0.4),
         [[("CUST_000", {"size": 10, "bold": True, "color": INK, "font": MONO}),
           ("  UK teacher, salary + card spend → ", {"size": 9, "color": MUTED}),
           ("5 LOW / AUTO_CLEAR", {"size": 10, "bold": True, "color": LOW}),
           (" @ 0.95", {"size": 9, "color": MUTED})]])

    text(s, Inches(6.85), wy, Inches(5.88), Inches(0.24),
         "HONEST LIMITS", size=9.5, color=FAINT, bold=True)
    limits = [
        ("Latency ~45–90s per customer",
         "~11 sequential LLM round-trips. Serial depth is the cost of a real investigation; batch mode overlaps customers."),
        ("Not byte-reproducible",
         "Mitigated: temperature=0 plus a logged trace and injected-memory record, so any decision is reconstructable."),
        ("Episodic recall is feature-match",
         "Not embeddings yet — the similar() interface is deliberately vector-pluggable."),
    ]
    for i, (h, b) in enumerate(limits):
        ly = wy + Inches(0.26) + Inches(0.68 * i)
        rect(s, Inches(6.85), ly, Inches(5.88), Inches(0.6), fill=PANEL)
        text(s, Inches(7.02), ly + Inches(0.06), Inches(5.6), Inches(0.22),
             h, size=9.5, color=MED, bold=True)
        text(s, Inches(7.02), ly + Inches(0.26), Inches(5.64), Inches(0.34),
             b, size=8, color=MUTED, line=1.15)

    ny = Inches(5.18)
    text(s, Inches(0.6), ny, Inches(12.13), Inches(0.24),
         "NEXT STEPS — EACH MAPS TO A LIMIT ABOVE", size=9.5, color=FAINT, bold=True)
    nexts = [
        ("Vector episodic memory", "swap feature-match for embeddings as the case bank grows"),
        ("Live watchlist feeds", "re-add sanctions / adverse-media as tools the agent queries"),
        ("Confidence calibration", "measure agreement vs human corrections, auto-tune the gate"),
        ("Case management", "assignment, SLAs, escalation workflow, reviewer analytics"),
    ]
    for i, (h, b) in enumerate(nexts):
        nx = Inches(0.6) + Inches(3.06) * i
        rect(s, nx, ny + Inches(0.26), Inches(2.9), Inches(0.78), fill=PANEL)
        text(s, nx + Inches(0.14), ny + Inches(0.34), Inches(2.62), Inches(0.22),
             f"{i+1}. {h}", size=9.5, color=ACCENT, bold=True)
        text(s, nx + Inches(0.14), ny + Inches(0.55), Inches(2.64), Inches(0.4),
             b, size=8, color=MUTED, line=1.15)

    ey = Inches(6.24)
    rect(s, Inches(0.6), ey, Inches(12.13), Inches(0.82), fill=PANEL2, outline=ACCENT)
    text(s, Inches(0.82), ey + Inches(0.1), Inches(11.7), Inches(0.24),
         "ENGINEERING DECISIONS WORTH DEFENDING", size=9, color=FAINT, bold=True)
    text(s, Inches(0.82), ey + Inches(0.34), Inches(11.7), Inches(0.4),
         [[("No deterministic scoring · sanctions deliberately scoped out (the brief said “external "
            "alerts”) · Decimal money · seeded byte-identical data generation · append-only audit of "
            "clears as well as escalations · working-memory scratchpad evicted on every exit path",
            {"size": 9.5, "color": MUTED})]], line=1.2)

    note(s, "Close on the trade-offs, not the wins — showing you know where it is weak is more convincing "
            "than claiming it is finished. Each next step maps to a limit named above.")
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
