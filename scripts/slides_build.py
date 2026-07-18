"""Build the Slide Library gallery (S75N).

Scans docs/slides/<topic>/NN_*.png (+ optional NN_*.md sidecar captions and
_topic.md topic blurbs) and writes docs/slides/index.html. Mission Control
serves it at /slides and the images at /slides/<topic>/<file>.

Run after adding slides:
  .venv/Scripts/python.exe scripts/slides_build.py
"""
import datetime as dt
import html
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SLIDES = ROOT / "docs" / "slides"
OUT = SLIDES / "index.html"


def title_of(slug):
    return slug.replace("-", " ").replace("_", " ").title()


def build():
    sections, total = "", 0
    for topic in sorted(p for p in SLIDES.iterdir() if p.is_dir()):
        pngs = sorted(topic.glob("*.png"))
        if not pngs:
            continue
        blurb = ""
        tmd = topic / "_topic.md"
        if tmd.exists():
            blurb = f'<p class="blurb">{html.escape(tmd.read_text(encoding="utf-8").strip())}</p>'
        cards = ""
        for png in pngs:
            total += 1
            side = png.with_suffix(".md")
            title, notes = png.stem.split("_", 1)[-1].replace("_", " "), ""
            if side.exists():
                lines = side.read_text(encoding="utf-8").strip().splitlines()
                title = lines[0].strip()
                notes = " ".join(x.strip() for x in lines[1:]).strip()
            rel = f"{topic.name}/{png.name}"
            notes_html = (f"<details><summary>notes</summary><p>{html.escape(notes)}</p></details>"
                          if notes else "")
            cards += f"""<figure class="slide">
<a href="{rel}" target="_blank" rel="noopener"><img src="{rel}" loading="lazy" alt="{html.escape(title)}"></a>
<figcaption><b>{html.escape(title)}</b>{notes_html}</figcaption>
</figure>"""
        sections += (f'<section><h2>{html.escape(title_of(topic.name))} '
                     f'<span class="cnt">{len(pngs)}</span></h2>{blurb}'
                     f'<div class="grid">{cards}</div></section>')
    gen = dt.datetime.now().strftime("%Y-%m-%d %H:%M")
    OUT.write_text(TEMPLATE.replace("__BODY__", sections)
                   .replace("__N__", str(total)).replace("__GEN__", gen),
                   encoding="utf-8")
    print(f"slide gallery: {total} slides -> {OUT}")


TEMPLATE = r"""<!doctype html><html lang="en"><head>
<meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1">
<title>Slide Library</title>
<style>
:root{--plane:#f9f9f7;--surface:#fff;--ink:#0b0b0b;--ink2:#52514e;--muted:#898781;
  --border:rgba(11,11,11,.10);--pos:#2a78d6;--chip:#f0efea}
@media(prefers-color-scheme:dark){:root{--plane:#0d0d0d;--surface:#1f1f1e;--ink:#fff;
  --ink2:#c3c2b7;--border:rgba(255,255,255,.10);--pos:#3987e5;--chip:#26261f}}
*{box-sizing:border-box}
body{margin:0;background:var(--plane);color:var(--ink);
  font-family:system-ui,-apple-system,"Segoe UI",sans-serif;font-size:14px;line-height:1.5}
header{position:sticky;top:0;z-index:5;background:var(--surface);
  border-bottom:1px solid var(--border);padding:12px 20px;display:flex;gap:12px;align-items:center}
h1{font-size:16px;margin:0;font-weight:650}
.pill{font-size:12px;padding:3px 10px;border-radius:20px;background:var(--chip);color:var(--muted)}
.wrap{max-width:1200px;margin:0 auto;padding:16px 20px 90px}
h2{font-size:15px;margin:30px 0 6px;padding-bottom:6px;border-bottom:1px solid var(--border)}
.cnt{color:var(--muted);font-weight:400;font-size:12px}
.blurb{color:var(--ink2);font-size:12.5px;margin:4px 0 10px;max-width:75ch}
.grid{display:grid;grid-template-columns:repeat(auto-fill,minmax(340px,1fr));gap:14px}
.slide{margin:0;background:var(--surface);border:1px solid var(--border);border-radius:10px;
  padding:10px;display:flex;flex-direction:column;gap:8px}
.slide img{width:100%;height:auto;border-radius:6px;display:block}
.slide a:hover img{outline:2px solid var(--pos)}
figcaption{font-size:12.5px;color:var(--ink2)}
figcaption b{color:var(--ink);font-size:13px}
details{margin-top:3px}summary{cursor:pointer;font-size:11.5px;color:var(--muted)}
details p{margin:4px 0 0;font-size:12px}
.hint{color:var(--muted);font-size:12px;margin-left:auto}
</style></head><body>
<header><h1>🎞 Slide Library</h1><span class="pill">__N__ slides · built __GEN__</span>
<span class="hint">click a slide to open full-size · add slides: docs/slides/README.md</span></header>
<div class="wrap">__BODY__</div>
</body></html>"""


if __name__ == "__main__":
    build()
