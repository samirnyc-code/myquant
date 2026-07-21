"""Build the Brooks Codex HUB landing page (index.html) — one home for everything,
with a sectioned Table of Contents linking to each local tool. Also wraps the
cheat-sheet fragment into a standalone cheatsheet.html.
Folder: docs/living/brooks_codex/  (open index.html; deploy the folder to Streamlit)
"""
import json
from pathlib import Path
ROOT = Path(__file__).resolve().parent.parent
LIVE = ROOT / "docs" / "living"
HUB = LIVE / "brooks_codex"
idx = json.load(open(HUB / "figure_index.json", encoding="utf-8"))
try:
    ad = json.load(open(ROOT / "scratchpad" / "brooks_app_data.json", encoding="utf-8"))
    c = ad["counts"]
except Exception:
    c = {"setups": 15, "rules": 78, "core": 15, "teachings": 1390, "quiz": 28}
nfig = len(idx)
from collections import Counter
fbybook = Counter(f["book"] for f in idx)
try:
    ndaily = len(json.load(open(HUB / "daily_index.json", encoding="utf-8")))
except Exception:
    ndaily = 0

# wrap the cheat-sheet fragment into a standalone doc
cheat_frag = (LIVE / "brooks_cheatsheet.html").read_text(encoding="utf-8")
cheat_full = ('<!doctype html><html lang="en"><head><meta charset="utf-8">'
              '<meta name="viewport" content="width=device-width, initial-scale=1">'
              '<title>Brooks Codex — Desk Cheat-Sheet</title><style>html,body{margin:0;padding:0}</style>'
              '</head><body>\n' + cheat_frag + '\n</body></html>')
(HUB / "cheatsheet.html").write_text(cheat_full, encoding="utf-8")

SECTIONS = [
    ("01", "📈", "Setups &amp; Rules Trainer", "app.html",
     f"The core study app: <b>{c['setups']} setups</b> with Brooks' matched charts, <b>{c['rules']} golden rules</b> (Core-{c['core']} first), the <b>When-NOT-to-Trade</b> deck, a <b>{c['teachings']:,}-teaching</b> library, and quizzes (name-that-chart, recall, core-15).",
     "Open the trainer", True),
    ("02", "🗺", "Figure Explorer", "explorer.html",
     f"Every one of Brooks' <b>{nfig} book charts</b> across all four books, with the full bar-by-bar text, deep zoom (scroll / drag / pinch), ★ favorites, and a 📖 jump straight to that page in the book PDF. Contents sidebar to jump, not scroll.",
     "Open the explorer →", True),
    ("03", "📅", "Daily Charts", "daily.html",
     f"<b>{ndaily:,} of Brooks' real end-of-day charts</b> from his blog — his numbered annotations, day-type label, and written analysis for each. Filter by day-type, search, deep zoom, ★ favorites. This is where you study real days.",
     "Open the daily charts →", ndaily > 0),
    ("04", "🃏", "Desk Cheat-Sheet", "cheatsheet.html",
     "The printable one-pager: the 10 to memorize, When-NOT-to-Trade, and the golden rules. Ctrl/Cmd-P prints clean for beside your screen.",
     "Open the cheat-sheet →", True),
    ("05", "📚", "The Books", "books/trends.pdf",
     "The four source books as PDFs — Trends, Trading Ranges, Reversals, and Reading Price Charts Bar by Bar. Every figure in the Explorer deep-links into these.",
     "", True),
    ("06", "🎞", "Encyclopedia &amp; Video Nuggets", "",
     "Reserved: the 7,000-chart encyclopedia (annotated / unannotated drills) and mined nuggets from the 200 hrs of course video — when you have the files.",
     "", False),
]

def book_links():
    names = [("trends.pdf", "Trends"), ("ranges.pdf", "Trading Ranges"),
             ("reversals.pdf", "Reversals"), ("rpcbb.pdf", "Reading Price Charts")]
    return "".join(f'<a class="pdf" href="books/{fn}" target="_blank">📖 {nm}'
                   f'<span>{fbybook.get(nm,0) if nm!="Reading Price Charts" else fbybook.get("Reading Price Charts",0)} figs</span></a>'
                   for fn, nm in names)

cards = ""
for num, icon, title, href, desc, lbl, live in SECTIONS:
    is_books = href.startswith("books/")
    head = f'<div class="cnum">{num}</div><div class="cicon">{icon}</div>'
    if is_books:   # div (contains its own pdf links) — no nested anchors
        cards += (f'<div class="card live">{head}<div class="cbody"><h2>{title}</h2>'
                  f'<p>{desc}</p><div class="pdfs">{book_links()}</div></div></div>')
    elif live:     # whole card is one link
        cards += (f'<a class="card live" href="{href}">{head}<div class="cbody"><h2>{title}</h2>'
                  f'<p>{desc}</p><span class="go">{lbl or "Open →"}</span></div></a>')
    else:
        cards += (f'<div class="card soon">{head}<div class="cbody"><h2>{title}</h2>'
                  f'<p>{desc}</p><span class="soon">coming later</span></div></div>')

HTML = f"""<!doctype html><html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>The Brooks Codex — Home</title>
<style>
:root{{--bg:#0b0f15;--panel:#141b24;--panel2:#1b2430;--ink:#e8eef6;--dim:#93a2b4;--faint:#6b7a8c;--line:#25303d;
 --gold:#e6b23a;--blue:#5aa0ff;--green:#45c26a;--mono:ui-monospace,Menlo,Consolas,monospace;--sans:system-ui,-apple-system,"Segoe UI",Roboto,sans-serif;}}
@media(prefers-color-scheme:light){{:root{{--bg:#eef1f5;--panel:#fff;--panel2:#f4f6f9;--ink:#141b24;--dim:#54636f;--faint:#8593a1;--line:#dbe2ea;--gold:#b1810c;--blue:#2f6fd6;}}}}
:root[data-theme=light]{{--bg:#eef1f5;--panel:#fff;--panel2:#f4f6f9;--ink:#141b24;--dim:#54636f;--faint:#8593a1;--line:#dbe2ea;--gold:#b1810c;--blue:#2f6fd6;}}
:root[data-theme=dark]{{--bg:#0b0f15;--panel:#141b24;--panel2:#1b2430;--ink:#e8eef6;--dim:#93a2b4;--faint:#6b7a8c;--line:#25303d;--gold:#e6b23a;--blue:#5aa0ff;}}
*{{box-sizing:border-box}}html,body{{margin:0;padding:0}}
body{{font-family:var(--sans);background:var(--bg);color:var(--ink);line-height:1.55;min-height:100vh}}
.hero{{max-width:960px;margin:0 auto;padding:54px 22px 20px;text-align:center}}
.kick{{font-family:var(--mono);font-size:12px;letter-spacing:.22em;text-transform:uppercase;color:var(--gold)}}
h1{{font-size:44px;letter-spacing:-.02em;margin:12px 0 6px;font-weight:850}}
h1 span{{color:var(--gold)}}
.sub{{color:var(--dim);font-size:16px;max-width:60ch;margin:0 auto}}
.stats{{display:flex;gap:26px;justify-content:center;flex-wrap:wrap;margin:22px 0 6px;font-family:var(--mono);font-size:12.5px;color:var(--faint)}}
.stats b{{color:var(--ink);font-size:19px;display:block}}
.toc{{max-width:960px;margin:26px auto 0;padding:0 22px}}
.toclabel{{font-family:var(--mono);font-size:11px;letter-spacing:.14em;text-transform:uppercase;color:var(--faint);border-bottom:1px solid var(--line);padding-bottom:8px;margin-bottom:16px}}
.cards{{display:flex;flex-direction:column;gap:14px;padding-bottom:60px}}
.card{{display:grid;grid-template-columns:52px 56px 1fr;gap:6px 14px;align-items:start;border:1px solid var(--line);border-radius:16px;background:var(--panel);padding:20px 22px;text-decoration:none;color:inherit;transition:.16s}}
.card.live{{cursor:pointer}}
.card.live:hover{{border-color:var(--gold);transform:translateY(-2px);background:var(--panel2)}}
.card.soon{{opacity:.55}}
.cnum{{font-family:var(--mono);font-size:13px;color:var(--faint);padding-top:6px}}
.cicon{{font-size:34px;line-height:1}}
.cbody h2{{margin:0 0 6px;font-size:20px}}
.cbody p{{margin:0 0 12px;color:var(--dim);font-size:14.5px;max-width:66ch}}
.cbody p b{{color:var(--ink)}}
.go{{display:inline-block;font-family:var(--mono);font-size:12.5px;font-weight:700;color:var(--bg);background:var(--gold);padding:9px 15px;border-radius:9px;text-decoration:none}}
.soon{{font-family:var(--mono);font-size:12px;color:var(--faint)}}
.pdfs{{display:flex;gap:10px;flex-wrap:wrap}}
.pdf{{font-family:var(--mono);font-size:12.5px;color:var(--blue);text-decoration:none;border:1px solid var(--line);border-radius:9px;padding:9px 12px;display:flex;gap:8px;align-items:center}}
.pdf:hover{{border-color:var(--blue)}}
.pdf span{{color:var(--faint);font-size:11px}}
.foot{{font-family:var(--mono);font-size:11px;color:var(--faint);text-align:center;padding:20px;border-top:1px solid var(--line);max-width:960px;margin:0 auto;line-height:1.7}}
.theme{{position:fixed;top:16px;right:18px;font-family:var(--mono);background:var(--panel);color:var(--ink);border:1px solid var(--line);border-radius:9px;padding:8px 11px;cursor:pointer}}
@media(max-width:640px){{h1{{font-size:32px}}.card{{grid-template-columns:1fr;gap:8px}}.cnum,.cicon{{display:inline-block}}}}
</style></head><body>
<button class="theme" onclick="var c=document.documentElement.getAttribute('data-theme');document.documentElement.setAttribute('data-theme',c==='dark'?'light':c==='light'?'dark':(matchMedia('(prefers-color-scheme:dark)').matches?'light':'dark'))">◑</button>
<div class="hero">
 <div class="kick">Al Brooks · Price Action · Study System</div>
 <h1>The Brooks <span>Codex</span></h1>
 <p class="sub">Everything from the four books — condensed, cited, and built to study. One home, four tools.</p>
 <div class="stats">
  <div><b>{c['setups']}</b>setups</div><div><b>{c['rules']}</b>rules</div>
  <div><b>{nfig}</b>book figures</div><div><b>{ndaily:,}</b>daily charts</div>
  <div><b>{c['teachings']:,}</b>teachings</div><div><b>4</b>books</div>
 </div>
</div>
<div class="toc"><div class="toclabel">Contents</div><div class="cards">{cards}</div></div>
<div class="foot">All content is condensed from Al Brooks' four books (Trends · Trading Ranges · Reversals · Reading Price Charts Bar by Bar), page-cited. A personal study aid — not trading advice, not for redistribution.</div>
</body></html>"""
(HUB / "index.html").write_text(HTML, encoding="utf-8")
print(f"wrote hub index.html ({len(HTML)} bytes) · figures by book: {dict(fbybook)}")
