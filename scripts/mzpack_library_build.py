"""Build the MZpack Insights Library page (S75N).

Reads the per-article study notes in docs/mzpack_insights/notes/*.md (frontmatter +
fixed sections, scraped from https://www.mzpack.pro/category/mzpack-insights/) and
renders ONE self-contained HTML page, docs/mzpack_insights/library.html, organized
by topic with search + relevance filters. Mission Control serves it at /library.

Run after adding/editing notes:
  .venv/Scripts/python.exe scripts/mzpack_library_build.py
"""
import datetime as dt
import html
import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
NOTES = ROOT / "docs" / "mzpack_insights" / "notes"
OUT = ROOT / "docs" / "mzpack_insights" / "library.html"
INDEX = ROOT / "docs" / "mzpack_insights" / "index.json"

TOPICS = [  # display order + labels
    ("core-concepts", "🧠 Core Order-Flow Concepts",
     "Market mechanics: icebergs, DOM pressure, order types, liquidity migration, "
     "defended & mirror levels, delta rate."),
    ("footprint", "👣 Footprint Techniques",
     "Reading the footprint: reversal patterns, delta divergence, imbalances, "
     "left/right footprint."),
    ("volume-profile-tpo", "📊 Volume Profile & TPO",
     "POC retests, value area, TPO profile splitting/merging, RTH vs ETH sessions."),
    ("strategies-backtesting", "🧪 Strategies & Backtesting",
     "Rule-based setups, the MZpack API, and how MZpack thinks about validating an edge."),
    ("trade-examples", "📈 Annotated Trade Examples",
     "Dated walk-throughs (ES/NQ/GC/CL/6E/ZN): which signals confirmed, entries, exits."),
    ("platform-misc", "🔧 Platform & Misc",
     "Settings, templates, market-specific configs, COT, general background."),
]
REL_BADGE = {"high": ("REL-HIGH", "relevant to our level/absorption research"),
             "medium": ("rel-med", ""), "low": ("rel-low", "")}


def parse_note(p: Path):
    txt = p.read_text(encoding="utf-8")
    m = re.match(r"\s*---\s*\n(.*?)\n---\s*\n(.*)", txt, re.S)
    if not m:
        return None
    meta = {}
    for line in m.group(1).splitlines():
        if ":" in line:
            k, v = line.split(":", 1)
            meta[k.strip()] = v.split("#")[0].strip().strip('"')
    body = m.group(2).strip()
    secs = {}
    cur = None
    for line in body.splitlines():
        h = re.match(r"##\s+(.*)", line)
        if h:
            cur = h.group(1).strip().lower()
            secs[cur] = []
        elif cur:
            secs[cur].append(line)
    secs = {k: "\n".join(v).strip() for k, v in secs.items()}
    return {"slug": p.stem, "title": meta.get("title", p.stem),
            "url": meta.get("url", ""), "date": meta.get("date", ""),
            "topic": meta.get("topic", "platform-misc"),
            "relevance": meta.get("research_relevance", "low"),
            "sections": secs}


def md_inline(s):
    s = html.escape(s)
    s = re.sub(r"\*\*(.+?)\*\*", r"<b>\1</b>", s)
    s = re.sub(r"\*(.+?)\*", r"<i>\1</i>", s)
    s = re.sub(r"`(.+?)`", r"<code>\1</code>", s)
    return s


def md_block(s):
    outp, in_ul = [], False
    for line in s.splitlines():
        li = re.match(r"\s*[-*]\s+(.*)", line)
        if li:
            if not in_ul:
                outp.append("<ul>")
                in_ul = True
            outp.append(f"<li>{md_inline(li.group(1))}</li>")
        else:
            if in_ul:
                outp.append("</ul>")
                in_ul = False
            if line.strip():
                outp.append(f"<p>{md_inline(line.strip())}</p>")
    if in_ul:
        outp.append("</ul>")
    return "\n".join(outp)


def card(n):
    rel = n["relevance"]
    badge = {"high": '<span class="badge hi">★ research-relevant</span>',
             "medium": '<span class="badge md">relevant</span>',
             "low": ""}.get(rel, "")
    sec_html = ""
    for label, key in [("Summary", "summary"),
                       ("Key concepts", "key concepts & definitions"),
                       ("Rules / thresholds", "rules / thresholds / settings"),
                       ("Order-flow signature", "order-flow signature described"),
                       ("Why we care", "relevance to our research")]:
        body = n["sections"].get(key, "")
        if body and body.lower() not in ("none given", "none given."):
            sec_html += f'<div class="sec"><div class="sl">{label}</div>{md_block(body)}</div>'
    date = html.escape(n["date"])
    return f"""<details class="note" data-rel="{rel}" data-search="{html.escape((n['title'] + ' ' + n['sections'].get('summary', '')).lower())}">
<summary><span class="nt">{html.escape(n['title'])}</span>{badge}<span class="nd">{date}</span></summary>
<div class="body">{sec_html}
<p class="src"><a href="{html.escape(n['url'])}" target="_blank" rel="noopener">source article ↗</a></p>
</div></details>"""


def build():
    notes = [n for n in (parse_note(p) for p in sorted(NOTES.glob("*.md"))) if n]
    order = {"high": 0, "medium": 1, "low": 2}
    by_topic = {k: [] for k, _, _ in TOPICS}
    for n in notes:
        by_topic.setdefault(n["topic"], []).append(n)
    body = ""
    toc = ""
    for key, label, blurb in TOPICS:
        items = sorted(by_topic.get(key, []),
                       key=lambda n: (order.get(n["relevance"], 3), n["title"]))
        if not items:
            continue
        nhigh = sum(1 for n in items if n["relevance"] == "high")
        toc += (f'<a class="tocitem" href="#t-{key}">{label} '
                f'<span class="cnt">{len(items)}</span></a>')
        body += (f'<section id="t-{key}"><h2>{label} '
                 f'<span class="cnt">{len(items)} articles'
                 f'{f" · {nhigh} research-relevant" if nhigh else ""}</span></h2>'
                 f'<p class="blurb">{blurb}</p>'
                 + "\n".join(card(n) for n in items) + "</section>")
    generated = dt.datetime.now().strftime("%Y-%m-%d %H:%M")
    page = TEMPLATE.replace("__BODY__", body).replace("__TOC__", toc) \
                   .replace("__N__", str(len(notes))).replace("__GEN__", generated)
    OUT.write_text(page, encoding="utf-8")
    INDEX.write_text(json.dumps(
        {"generated": generated, "count": len(notes),
         "articles": [{k: n[k] for k in ("slug", "title", "url", "date", "topic",
                                         "relevance")} for n in notes]},
        indent=1), encoding="utf-8")
    print(f"library.html: {len(notes)} notes -> {OUT}")


TEMPLATE = r"""<!doctype html><html lang="en"><head>
<meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1">
<title>MZpack Insights Library</title>
<style>
:root{--plane:#f9f9f7;--surface:#fff;--ink:#0b0b0b;--ink2:#52514e;--muted:#898781;
  --border:rgba(11,11,11,.10);--pos:#2a78d6;--chip:#f0efea;--hi:#b45309;--hibg:#fef3c7}
@media(prefers-color-scheme:dark){:root{--plane:#0d0d0d;--surface:#1f1f1e;--ink:#fff;
  --ink2:#c3c2b7;--muted:#898781;--border:rgba(255,255,255,.10);--pos:#3987e5;
  --chip:#26261f;--hi:#fbbf24;--hibg:#3a2e10}}
*{box-sizing:border-box}
body{margin:0;background:var(--plane);color:var(--ink);
  font-family:system-ui,-apple-system,"Segoe UI",sans-serif;font-size:14px;line-height:1.5}
header{position:sticky;top:0;z-index:5;background:var(--surface);
  border-bottom:1px solid var(--border);padding:12px 20px;display:flex;gap:12px;
  align-items:center;flex-wrap:wrap}
h1{font-size:16px;margin:0;font-weight:650}
#q{padding:6px 12px;border:1px solid var(--border);border-radius:8px;
  background:var(--plane);color:var(--ink);font:inherit;width:230px}
.pill{font-size:12px;padding:3px 10px;border-radius:20px;background:var(--chip);color:var(--muted)}
label.f{font-size:12.5px;color:var(--ink2);display:flex;gap:5px;align-items:center;cursor:pointer}
.wrap{max-width:980px;margin:0 auto;padding:16px 20px 90px}
.toc{display:flex;gap:8px;flex-wrap:wrap;margin:10px 0 4px}
.tocitem{font-size:12.5px;text-decoration:none;color:var(--ink2);background:var(--surface);
  border:1px solid var(--border);border-radius:20px;padding:5px 12px}
.tocitem:hover{border-color:var(--pos);color:var(--pos)}
.cnt{color:var(--muted);font-weight:400;font-size:12px}
h2{font-size:15px;margin:34px 0 4px;padding-bottom:6px;border-bottom:1px solid var(--border)}
.blurb{color:var(--ink2);font-size:12.5px;margin:4px 0 12px}
.note{background:var(--surface);border:1px solid var(--border);border-radius:10px;
  margin:8px 0;overflow:hidden}
.note summary{cursor:pointer;padding:10px 14px;display:flex;gap:10px;align-items:center;
  flex-wrap:wrap;list-style:none}
.note summary::-webkit-details-marker{display:none}
.note[open] summary{border-bottom:1px solid var(--border)}
.nt{font-weight:600;font-size:13.5px}
.nd{margin-left:auto;color:var(--muted);font-size:11.5px;font-variant-numeric:tabular-nums}
.badge{font-size:10.5px;font-weight:600;padding:2px 8px;border-radius:12px}
.badge.hi{background:var(--hibg);color:var(--hi)}
.badge.md{background:var(--chip);color:var(--muted)}
.body{padding:6px 16px 12px}
.sec{margin:10px 0}
.sl{font-size:10.5px;font-weight:700;letter-spacing:.05em;text-transform:uppercase;
  color:var(--muted);margin-bottom:3px}
.sec p{margin:4px 0}.sec ul{margin:4px 0;padding-left:20px}.sec li{margin:2px 0}
code{background:var(--chip);border-radius:4px;padding:1px 5px;font-size:12px}
.src{font-size:12px}.src a{color:var(--pos)}
.hidden{display:none}
</style></head><body>
<header>
  <h1>📚 MZpack Insights Library</h1>
  <span class="pill">__N__ articles · built __GEN__</span>
  <span style="margin-left:auto"></span>
  <input id="q" placeholder="search titles &amp; summaries…" autocomplete="off">
  <label class="f"><input type="checkbox" id="onlyhi"> ★ research-relevant only</label>
</header>
<div class="wrap">
  <div class="toc">__TOC__</div>
  __BODY__
</div>
<script>
const q=document.getElementById('q'),hi=document.getElementById('onlyhi');
function apply(){
  const t=q.value.trim().toLowerCase(),oh=hi.checked;
  document.querySelectorAll('.note').forEach(n=>{
    const okT=!t||n.dataset.search.includes(t);
    const okR=!oh||n.dataset.rel==='high';
    n.classList.toggle('hidden',!(okT&&okR));
    if(t&&okT&&okR)n.open=true;
  });
  document.querySelectorAll('section').forEach(s=>{
    s.classList.toggle('hidden',![...s.querySelectorAll('.note')].some(n=>!n.classList.contains('hidden')));
  });
}
q.oninput=apply;hi.onchange=apply;
</script>
</body></html>"""


if __name__ == "__main__":
    build()
