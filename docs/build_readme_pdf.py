"""Render README.md to a print-ready docs/README.pdf.

    python docs/build_readme_pdf.py

Mermaid blocks are swapped for the pre-rendered PNGs in docs/diagrams/ (regenerate those with
mermaid-cli if the README diagrams change), screenshots are inlined as base64 so the PDF is a single
self-contained file, and headless Chrome does the actual printing.
"""
from __future__ import annotations

import base64
import mimetypes
import os
import re
import shutil
import subprocess
import sys
import tempfile

from markdown_it import MarkdownIt

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
README = os.path.join(ROOT, "README.md")
OUT = os.path.join(HERE, "README.pdf")

# README mermaid blocks, in order → pre-rendered PNG (repo-root relative, like README image paths)
DIAGRAMS = ["docs/diagrams/pipeline.png", "docs/diagrams/request-flow.png"]

CHROME_CANDIDATES = [
    r"C:\Program Files\Google\Chrome\Application\chrome.exe",
    r"C:\Program Files (x86)\Google\Chrome\Application\chrome.exe",
    "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome",
    "google-chrome", "chromium", "chromium-browser",
]

CSS = """
@page { size: A4; margin: 16mm 14mm; }
* { box-sizing: border-box; }
body {
  font-family: -apple-system, "Segoe UI", Inter, Helvetica, Arial, sans-serif;
  font-size: 10.5pt; line-height: 1.55; color: #1a1a1f; margin: 0;
  -webkit-print-color-adjust: exact; print-color-adjust: exact;
}
h1 { font-size: 25pt; margin: 0 0 4pt; letter-spacing: -.4pt; }
h2 { font-size: 16pt; margin: 22pt 0 8pt; padding-bottom: 4pt;
     border-bottom: 1.5px solid #d4d4d8; break-after: avoid; }
h3 { font-size: 12pt; margin: 15pt 0 5pt; break-after: avoid; }
h4 { font-size: 10.5pt; margin: 12pt 0 4pt; break-after: avoid; }
p { margin: 0 0 8pt; }
a { color: #0f766e; text-decoration: none; }
code { font-family: Consolas, "SF Mono", Menlo, monospace; font-size: 9pt;
       background: #f4f4f5; padding: 1px 4px; border-radius: 3px; }
pre { background: #18181b; color: #e4e4e7; padding: 10pt 12pt; border-radius: 6px;
      overflow: hidden; break-inside: avoid; margin: 0 0 10pt; }
pre code { background: none; color: inherit; font-size: 8.5pt; padding: 0; line-height: 1.45; }
table { border-collapse: collapse; width: 100%; margin: 0 0 10pt;
        font-size: 9pt; break-inside: avoid; }
th { background: #f4f4f5; text-align: left; font-weight: 600; }
th, td { border: 1px solid #e4e4e7; padding: 5pt 7pt; vertical-align: top; }
tr:nth-child(even) td { background: #fafafa; }
img { max-width: 100%; height: auto; display: block; margin: 8pt auto 12pt;
      border: 1px solid #e4e4e7; border-radius: 5px; }
img.diagram { border: none; max-height: 215mm; }
blockquote { border-left: 3px solid #0f766e; background: #f0fdfa; margin: 0 0 10pt;
             padding: 7pt 12pt; break-inside: avoid; }
blockquote p:last-child { margin-bottom: 0; }
ul, ol { margin: 0 0 10pt; padding-left: 18pt; }
li { margin-bottom: 3pt; }
hr { border: 0; border-top: 1px solid #e4e4e7; margin: 16pt 0; }
details { margin: 0 0 10pt; }
summary { font-weight: 600; margin-bottom: 5pt; }
.subtitle { font-size: 12pt; color: #52525b; margin: 0 0 4pt; }
.meta { font-size: 8.5pt; color: #71717a; margin: 0 0 14pt;
        padding-bottom: 10pt; border-bottom: 2px solid #18181b; }
h2, h3, table, pre, blockquote, img { break-inside: avoid; }
"""


def find_chrome() -> str:
    for c in CHROME_CANDIDATES:
        if os.path.isfile(c):
            return c
        w = shutil.which(c)
        if w:
            return w
    sys.exit("Chrome/Chromium not found — install it or edit CHROME_CANDIDATES.")


def data_uri(path: str) -> str:
    """Inline a local image so the PDF is one self-contained file."""
    full = path if os.path.isabs(path) else os.path.join(ROOT, path)
    if not os.path.exists(full):
        print(f"  ! missing image: {path}")
        return ""
    mime = mimetypes.guess_type(full)[0] or "image/png"
    return f"data:{mime};base64," + base64.b64encode(open(full, "rb").read()).decode()


def preprocess(md: str) -> str:
    # mermaid fences → the pre-rendered PNG for that position
    idx = [0]

    def swap(_m):
        i = idx[0]
        idx[0] += 1
        if i >= len(DIAGRAMS):
            print(f"  ! no pre-rendered diagram for mermaid block {i + 1}")
            return ""
        return f"\n![diagram]({DIAGRAMS[i]})\n"

    md = re.sub(r"```mermaid\n.*?```", swap, md, flags=re.S)
    print(f"  swapped {idx[0]} mermaid block(s) for rendered images")

    # strip the centred HTML header/footer wrappers — the PDF gets its own title block
    md = re.sub(r"</?div[^>]*>", "", md)
    # drop the README's own H1 + tagline + badge line: the PDF title block already says all three
    md = re.sub(r"^# .*?\n+(\*\*.*?\*\*\n+)?", "", md, count=1, flags=re.S | re.M)
    md = re.sub(r"^`Python 3\.11\+`.*?\n", "", md, count=1, flags=re.M)
    # the ToC is navigation, useless on paper
    md = re.sub(r"## Table of contents.*?\n---\n", "", md, flags=re.S)
    # <details> renders collapsed in Chrome; open it so the content prints
    return md.replace("<details>", "<details open>")


def main() -> None:
    md_src = preprocess(open(README, encoding="utf-8").read())
    html_body = MarkdownIt("commonmark", {"html": True}).enable("table").render(md_src)

    # inline every local image
    def inline(m):
        src = m.group(2)
        if src.startswith(("http", "data:")):
            return m.group(0)
        cls = ' class="diagram"' if "diagrams/" in src else ""
        return f'{m.group(1)}"{data_uri(src)}"{cls}'

    html_body = re.sub(r'(<img[^>]*?src=)"([^"]+)"', inline, html_body)

    html = f"""<!doctype html><html><head><meta charset="utf-8">
<title>Frisk — Financial Risk Signal Aggregator</title><style>{CSS}</style></head><body>
<h1>Frisk — Financial Risk Signal Aggregator</h1>
<p class="subtitle">An AI that reviews customers the way a good analyst would —
and hands you the evidence for every call it makes.</p>
<p class="meta">Supporting documentation · setup, architecture and key design decisions</p>
{html_body}
</body></html>"""

    tmp = os.path.join(tempfile.gettempdir(), "frisk_readme.html")
    open(tmp, "w", encoding="utf-8").write(html)

    subprocess.run([
        find_chrome(), "--headless", "--disable-gpu", "--no-sandbox",
        "--no-pdf-header-footer", f"--print-to-pdf={OUT}",
        "--virtual-time-budget=12000", f"file:///{tmp.replace(os.sep, '/')}",
    ], check=True, capture_output=True, timeout=180)

    print(f"built {OUT}  ({os.path.getsize(OUT) / 1024:.0f} KB)")


if __name__ == "__main__":
    main()
