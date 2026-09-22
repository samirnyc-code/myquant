"""Build the Mission Control library of Halsey's teaching diagrams (the MM Diagram
Slideshow + the two flow charts + reference tools). Copyrighted (paying subscriber),
so the embedded-image HTML is gitignored; the generator + catalog entry are committed.

Output: docs/artifacts/eminiaddict_diagrams.html  (served :8590/artifact/eminiaddict_diagrams)
Run from repo root or eminiaddict/.
"""
import base64
import json
import pathlib
import re

ROOT = pathlib.Path(__file__).resolve().parents[2]
DIAG = ROOT / "eminiaddict" / "data" / "site" / "_diagrams"
PAGES = ROOT / "eminiaddict" / "data" / "site" / "_pages"
OUT = ROOT / "docs" / "artifacts" / "eminiaddict_diagrams.html"
CATALOG = ROOT / "data" / "_catalog" / "claude_artifacts.json"
TITLE = "EminiAddict Diagrams"          # slug -> eminiaddict_diagrams
DATE = "2026-08-01"

FLOW = {"5", "8"}                        # the two flow charts
PAGE_LABELS = [
    ("traderschecklist.png", "Signal Alignment Checklist (VX / Indices / TICK / BANK / USD)", "Reference"),
    ("gapfillsats.png", "Gap Fill Statistics (by weekday, 30/90/180d, pro-gap by size)", "Reference"),
    ("dollarcor.png", "Dollar / Indices Correlation", "Reference"),
    ("calczgalq.png", "Position Sizing Calculator", "Reference"),
]


def b64(p):
    return "data:image/png;base64," + base64.b64encode(p.read_bytes()).decode()


items = []
# core MM diagrams, ordered by numeric prefix
diag = []
for p in DIAG.glob("*.png"):
    m = re.match(r"(\d+)", p.name)
    num = int(m.group(1)) if m else 999
    label = re.sub(r"^\d+[-_ ]+", "", p.stem).replace("_", " ").replace("plus", " + ").strip()
    diag.append((num, label, p))
for num, label, p in sorted(diag):
    star = " ⭐" if str(num) in FLOW else ""
    items.append({"n": num, "label": f"{num}. {label}{star}", "cat": "MM Diagrams",
                  "flow": str(num) in FLOW, "src": b64(p)})
# reference tools
for fn, label, cat in PAGE_LABELS:
    p = PAGES / fn
    if p.exists():
        items.append({"n": 100, "label": label, "cat": cat, "flow": False, "src": b64(p)})

DATA = json.dumps(items)
n = len(items)

HTML = f"""<!doctype html><html lang=en><head><meta charset=utf-8>
<meta name=viewport content="width=device-width,initial-scale=1"><title>{TITLE}</title>
<style>
:root{{--bg:#0d1117;--pan:#161b22;--chip:#30363d;--fg:#e6edf3;--mut:#8b949e;--blue:#58a6ff;--gold:#e3b341}}
*{{box-sizing:border-box}}body{{margin:0;background:var(--bg);color:var(--fg);
 font:14px -apple-system,Segoe UI,Roboto,sans-serif;height:100vh;display:flex;flex-direction:column}}
header{{display:flex;align-items:center;gap:12px;padding:11px 18px;border-bottom:1px solid var(--chip)}}
header h1{{font-size:16px;margin:0}}a{{color:var(--blue);text-decoration:none}}
#main{{flex:1;display:flex;min-height:0}}
#list{{width:270px;border-right:1px solid var(--chip);overflow:auto;padding:8px;background:var(--pan)}}
.cat{{font-size:11px;color:var(--mut);text-transform:uppercase;letter-spacing:.05em;margin:10px 6px 4px}}
.it{{padding:6px 9px;border-radius:7px;cursor:pointer;font-size:12.5px;color:var(--fg);border:1px solid transparent}}
.it:hover{{background:#ffffff08}}.it.on{{background:#58a6ff1c;border-color:#58a6ff55;color:var(--blue)}}
.it.flow{{color:var(--gold);font-weight:700}}.it.flow.on{{color:var(--gold)}}
#view{{flex:1;display:flex;flex-direction:column;min-width:0;align-items:center;justify-content:center;padding:14px;overflow:auto}}
#cap{{font-size:14px;font-weight:600;margin-bottom:8px;text-align:center}}
#img{{max-width:100%;max-height:calc(100vh - 130px);border:1px solid var(--chip);border-radius:8px;background:#fff}}
.nav{{display:flex;gap:12px;align-items:center;margin-top:10px}}
.btn{{padding:6px 14px;border:1px solid var(--blue);border-radius:7px;background:#58a6ff12;color:var(--blue);font-weight:600;cursor:pointer}}
.count{{color:var(--mut);font-family:ui-monospace,Consolas,monospace;font-size:12px}}
</style></head><body>
<header><h1>Halsey Teaching Diagrams</h1>
 <span class=count>{n} diagrams · ⭐ = flow chart</span>
 <span style="margin-left:auto"></span>
 <a href="/artifact/eminiaddict_measured_move_method">Method reference →</a></header>
<div id=main>
 <div id=list></div>
 <div id=view>
  <div id=cap></div>
  <img id=img alt="diagram">
  <div class=nav><button class=btn onclick="go(-1)">← Prev</button>
   <span class=count id=cnt></span>
   <button class=btn onclick="go(1)">Next →</button></div>
 </div>
</div>
<script>
var D={DATA}, i=0;
function render(){{var d=D[i];document.getElementById('img').src=d.src;
 document.getElementById('cap').textContent=d.label;
 document.getElementById('cnt').textContent=(i+1)+' / '+D.length;
 var els=document.querySelectorAll('.it');for(var k=0;k<els.length;k++)els[k].classList.toggle('on',k==i);
 var on=document.querySelector('.it.on');if(on)on.scrollIntoView({{block:'nearest'}});}}
function go(d){{i=(i+d+D.length)%D.length;render();}}
function sel(k){{i=k;render();}}
(function(){{var h='',cur=null;D.forEach(function(d,k){{if(d.cat!=cur){{cur=d.cat;h+='<div class=cat>'+cur+'</div>';}}
 h+='<div class="it'+(d.flow?' flow':'')+'" onclick="sel('+k+')">'+d.label+'</div>';}});
 document.getElementById('list').innerHTML=h;render();}})();
document.addEventListener('keydown',function(e){{if(e.key=='ArrowRight')go(1);if(e.key=='ArrowLeft')go(-1);}});
</script></body></html>"""

OUT.write_text(HTML, encoding="utf-8")
print(f"wrote {OUT} ({round(len(HTML)/1024/1024,2)} MB, {n} diagrams)")

cat = json.loads(CATALOG.read_text(encoding="utf-8"))
its = cat["artifacts"]
info = ("David Halsey's own teaching diagrams (the Measured Move Diagram Slideshow) + the "
        "two flow charts — the Measured Move decision tree (basic→extended→next-extended, "
        "trend-break→ATW-HWB→reverse) and the Market Analysis flow (Daily→series→active MM→"
        "phase→larger opposing MM→15M entry) — plus reference tools (signal-alignment checklist, "
        "gap-fill stats, dollar correlation, position sizing). Scrollable, keyboard nav.")
its[:] = [a for a in its if a.get("title") != TITLE]
its.insert(0, {"title": TITLE, "url": "", "updated": DATE, "group": "EminiAddict", "info": info})
CATALOG.write_text(json.dumps(cat, indent=1, ensure_ascii=False), encoding="utf-8")
print(f"registered '{TITLE}'")
