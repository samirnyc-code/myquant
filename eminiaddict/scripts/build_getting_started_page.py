"""build_getting_started_page.py — render the Getting Started knowledge base into a single
self-contained Mission Control artifact (docs/artifacts/eminiaddict_getting_started.html),
structured in David Halsey's own curriculum order. Re-runnable: pulls text + slides from the
scrape and transcripts/nuggets when present (so re-running after transcription fills them in).

Serves at MC :8590 (group EminiAddict). Slides embedded as base64 -> the page is portable.

Usage: python build_getting_started_page.py
"""
import base64
import html
import json
import os
import re

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
GS = os.path.join(ROOT, "eminiaddict", "data", "site", "getting_started")
TR = os.path.join(GS, "transcripts")
NUG = os.path.join(GS, "nuggets")          # <idx>_*.md nugget files (assistant-produced)
OUT = os.path.join(ROOT, "docs", "artifacts", "eminiaddict_getting_started.html")
CATALOG = os.path.join(ROOT, "data", "_catalog", "claude_artifacts.json")

CSS = """
:root{--bg:#0d1117;--card:#161b22;--chip:#30363d;--fg:#e6edf3;--mut:#8b949e;--blue:#58a6ff;--gold:#e3b341}
*{box-sizing:border-box}body{margin:0;background:var(--bg);color:var(--fg);font:14.5px/1.65 -apple-system,Segoe UI,Roboto,sans-serif}
header{position:sticky;top:0;background:var(--bg);border-bottom:1px solid var(--chip);padding:14px 24px;z-index:10}
header h1{font-size:18px;margin:0}a{color:var(--blue);text-decoration:none}a:hover{text-decoration:underline}
.wrap{max-width:960px;margin:0 auto;padding:18px 24px 90px}
.lead{color:var(--mut);margin:6px 0 18px}
.toc{background:var(--card);border:1px solid var(--chip);border-radius:12px;padding:12px 18px;margin:0 0 22px;columns:2;column-gap:26px}
.toc a{display:block;font-size:13.5px;margin:3px 0}
.mod{background:var(--card);border:1px solid var(--chip);border-radius:12px;padding:16px 20px;margin:14px 0;border-left:3px solid var(--blue)}
.mod h3{margin:0 0 4px;font-size:16px}.mod .k{color:var(--mut);font-size:12px;text-transform:uppercase;letter-spacing:.04em}
.mod p{margin:8px 0;font-size:13.7px}
.slides{display:flex;flex-wrap:wrap;gap:8px;margin:10px 0}
.slides img{max-width:100%;width:300px;border:1px solid var(--chip);border-radius:8px;cursor:zoom-in}
.vid{margin:8px 0}.vid a{font-weight:600}
details{margin:8px 0}summary{cursor:pointer;color:var(--gold);font-weight:600}
pre{white-space:pre-wrap;background:#0b0f14;border:1px solid var(--chip);border-radius:8px;padding:10px 12px;font-size:12.5px;color:#cbd5e1;max-height:340px;overflow:auto}
.nug{background:#12261a;border:1px solid #1f5133;border-radius:8px;padding:10px 14px;margin:8px 0}
.nug h4{margin:0 0 6px;color:#3fb950}
.pending{color:var(--mut);font-style:italic}
.glossary dt{font-weight:600;color:var(--gold);margin-top:10px}.glossary dd{margin:2px 0 0;color:#cbd5e1}
"""

def b64img(path):
    try:
        ext = os.path.splitext(path)[1].lstrip(".").lower().replace("jpg", "jpeg")
        return f"data:image/{ext};base64," + base64.b64encode(open(path, "rb").read()).decode()
    except Exception:
        return ""

def esc(s):
    return html.escape(s or "")

def render_glossary(text):
    # glossary text is "Term – definition. Term2 – ..." ; split on " – " heuristically
    out = ['<dl class="glossary">']
    # split into sentences that look like "X – def"
    parts = re.split(r'(?<=[.)])\s+(?=[A-Z][A-Za-z0-9 /()\-]{2,40}\s+[–\-]\s)', text)
    for p in parts:
        m = re.match(r'\s*([A-Z][A-Za-z0-9 /()\-]{1,40}?)\s+[–\-]\s+(.+)', p)
        if m:
            out.append(f"<dt>{esc(m.group(1).strip())}</dt><dd>{esc(m.group(2).strip())}</dd>")
    out.append("</dl>")
    return "\n".join(out) if len(out) > 2 else f"<p>{esc(text)}</p>"

def main():
    man = json.load(open(os.path.join(GS, "manifest.json"), encoding="utf-8"))
    slugmap = {re.sub(r'[^a-z0-9]+', '-', r['label'].lower()).strip('-')[:40]: r for r in man}
    toc, mods = [], []
    for r in man:
        idx = r["idx"]; label = esc(r["label"]); anchor = f"m{idx}"
        toc.append(f'<a href="#{anchor}">{idx:02d}. {label}</a>')
        item_dir = os.path.join(GS, r["dir"]) if r.get("dir") else None
        item = {}
        if item_dir and os.path.exists(os.path.join(item_dir, "item.json")):
            item = json.load(open(os.path.join(item_dir, "item.json"), encoding="utf-8"))
        text = item.get("text", "")
        parts = [f'<div class="mod" id="{anchor}"><div class="k">Lesson {idx:02d}</div>'
                 f'<h3>{label}</h3>']
        # glossary special-render
        if "glossary" in r["label"].lower() and len(text) > 200:
            parts.append(render_glossary(text))
        elif text and len(text.split()) > 12:
            parts.append(f"<p>{esc(text)}</p>")
        # slides
        if item_dir:
            imgs = sorted(f for f in os.listdir(item_dir) if f.startswith("slide_"))
            if imgs:
                parts.append('<div class="slides">')
                for im in imgs:
                    d = b64img(os.path.join(item_dir, im))
                    if d:
                        parts.append(f'<img src="{d}" loading="lazy">')
                parts.append("</div>")
        # video link
        for v in r.get("videos", []):
            if v.endswith(".mp4"):
                parts.append(f'<div class="vid">🎬 <a href="{esc(v)}" target="_blank">'
                             f'Lesson video (public)</a></div>')
        # nuggets (assistant-produced .md)
        nf = os.path.join(NUG, f"{idx:02d}.md")
        if os.path.exists(nf):
            parts.append(f'<div class="nug"><h4>Nuggets</h4>{md_to_html(open(nf,encoding="utf-8").read())}</div>')
        # transcript (collapsible) if present
        tname = f"{idx:02d}_" + re.sub(r'[^a-z0-9]+', '-', r['label'].lower()).strip('-')[:40]
        tf = os.path.join(TR, tname + ".txt")
        if os.path.exists(tf):
            tx = open(tf, encoding="utf-8").read()
            parts.append(f'<details><summary>Transcript ({len(tx.splitlines())} lines)</summary>'
                         f'<pre>{esc(tx)}</pre></details>')
        elif r.get("videos"):
            parts.append('<p class="pending">Transcript + nuggets pending transcription…</p>')
        parts.append("</div>")
        mods.append("\n".join(parts))

    page = (f'<!doctype html><html lang="en"><head><meta charset="utf-8">'
            f'<meta name="viewport" content="width=device-width,initial-scale=1">'
            f'<title>EminiAddict Getting Started</title><style>{CSS}</style></head><body>'
            f'<header><h1>EminiAddict — Getting Started</h1></header><div class="wrap">'
            f'<p class="lead">David Halsey\'s Getting Started curriculum, in his order — '
            f'sections, glossary, slides, lesson videos, transcripts &amp; nuggets. '
            f'(Study notes from a paid subscription; source is copyrighted.)</p>'
            f'<div class="toc">{"".join(toc)}</div>'
            f'{"".join(mods)}</div>'
            f'<script>document.querySelectorAll(".slides img").forEach(i=>i.onclick=()=>'
            f'window.open(i.src))</script></body></html>')
    os.makedirs(os.path.dirname(OUT), exist_ok=True)
    open(OUT, "w", encoding="utf-8").write(page)
    print(f"wrote {os.path.relpath(OUT, ROOT)}  ({len(page)//1024} KB, {len(man)} lessons)")
    register_mc()

def md_to_html(md):
    md = esc(md)
    md = re.sub(r'^\- (.+)$', r'<li>\1</li>', md, flags=re.M)
    md = re.sub(r'(<li>.*</li>)', r'<ul>\1</ul>', md, flags=re.S)
    return md.replace("\n", "<br>")

def register_mc():
    """Add/refresh the MC catalog entry so the page groups under EminiAddict at :8590."""
    try:
        cat = json.load(open(CATALOG, encoding="utf-8"))
    except Exception:
        cat = []
    items = cat if isinstance(cat, list) else cat.get("items", cat.get("artifacts", []))
    entry = {"title": "EminiAddict Getting Started", "group": "EminiAddict", "url": "",
             "info": "DH Getting Started curriculum: sections, glossary, slides, transcripts, nuggets."}
    items = [i for i in items if i.get("title") != entry["title"]]
    items.append(entry)
    if isinstance(cat, list):
        cat = items
    else:
        key = "artifacts" if "artifacts" in cat else "items"
        cat[key] = items
    os.makedirs(os.path.dirname(CATALOG), exist_ok=True)
    json.dump(cat, open(CATALOG, "w", encoding="utf-8"), indent=1)
    print("registered MC catalog entry (group EminiAddict)")

if __name__ == "__main__":
    main()
