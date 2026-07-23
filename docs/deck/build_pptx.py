"""Render SLIDES.md into deck.pptx.

    pip install python-pptx      # <-- run this first
    python docs/deck/build_pptx.py

Parses the `## Slide N — Title` sections of SLIDES.md (bullets, one code/diagram
block, and the `> Speaker note:` line) so the deck stays a single source of truth.
"""
from __future__ import annotations

import os
import re

from pptx import Presentation
from pptx.util import Inches, Pt

HERE = os.path.dirname(os.path.abspath(__file__))
SRC = os.path.join(HERE, "SLIDES.md")
OUT = os.path.join(HERE, "deck.pptx")


def parse_slides(md: str):
    """-> list of {title, bullets:[(text, level)], code:str, note:str}."""
    slides = []
    for block in re.split(r"^## Slide .*?— ", md, flags=re.M)[1:]:
        lines = block.splitlines()
        title = lines[0].strip()
        bullets, code, note, in_code = [], [], "", False
        for ln in lines[1:]:
            if ln.strip().startswith("```"):
                in_code = not in_code
                continue
            if in_code:
                code.append(ln)
            elif ln.startswith("> "):
                note = ln[2:].strip()
                note = re.sub(r"^Speaker note:\s*", "", note)
            elif ln.lstrip().startswith("- "):
                level = 1 if ln.startswith("  ") else 0
                text = re.sub(r"\*\*(.*?)\*\*", r"\1", ln.lstrip()[2:]).replace("`", "")
                bullets.append((text, level))
        slides.append({"title": title, "bullets": bullets,
                       "code": "\n".join(code).strip("\n"), "note": note})
    return slides


def build(slides):
    prs = Presentation()
    prs.slide_width, prs.slide_height = Inches(13.333), Inches(7.5)  # 16:9
    blank = prs.slide_layouts[6]

    for s in slides:
        slide = prs.slides.add_slide(blank)

        tb = slide.shapes.add_textbox(Inches(0.5), Inches(0.3), Inches(12.3), Inches(0.9))
        p = tb.text_frame.paragraphs[0]
        p.text = s["title"]
        p.font.size, p.font.bold = Pt(28), True

        body = slide.shapes.add_textbox(Inches(0.5), Inches(1.3), Inches(12.3), Inches(5.4))
        tf = body.text_frame
        tf.word_wrap = True
        first = True
        for text, level in s["bullets"]:
            para = tf.paragraphs[0] if first else tf.add_paragraph()
            first = False
            para.text = ("- " if level == 0 else "    - ") + text
            para.level = level
            para.font.size = Pt(15 if level == 0 else 13)

        if s["code"]:
            cb = slide.shapes.add_textbox(Inches(0.5), Inches(1.3), Inches(12.3), Inches(5.0))
            cp = cb.text_frame.paragraphs[0]
            cp.text = s["code"]
            cp.font.size, cp.font.name = Pt(10), "Consolas"

        if s["note"]:
            nb = slide.shapes.add_textbox(Inches(0.5), Inches(6.8), Inches(12.3), Inches(0.6))
            np_ = nb.text_frame.paragraphs[0]
            np_.text = "Note: " + s["note"]
            np_.font.size, np_.font.italic = Pt(11), True
            # also put it in the real speaker-notes pane
            slide.notes_slide.notes_text_frame.text = s["note"]

    prs.save(OUT)
    return OUT


if __name__ == "__main__":
    with open(SRC, encoding="utf-8") as f:
        slides = parse_slides(f.read())
    assert len(slides) == 5, f"expected 5 slides, parsed {len(slides)}"
    assert all(s["title"] and s["bullets"] for s in slides), "a slide has no title/bullets"
    assert any(s["code"] for s in slides), "architecture diagram slide lost its code block"
    print(f"parsed {len(slides)} slides ->", build(slides))
