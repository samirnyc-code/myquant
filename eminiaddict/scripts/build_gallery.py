"""Build the scrollable MM-sequence gallery for Mission Control.

Reads figures/sequences/manifest.json + the PNGs, embeds them base64 into a
self-contained viewer (prev/next, arrow keys, timeframe filter, metadata) and
writes docs/artifacts/eminiaddict_mm_sequence_library.html. Registers in catalog.
Run from repo root or eminiaddict/.
"""
import base64
import json
import pathlib

ROOT = pathlib.Path(__file__).resolve().parents[2]
SEQDIR = ROOT / "eminiaddict" / "figures" / "sequences"
OUT = ROOT / "docs" / "artifacts" / "eminiaddict_mm_sequence_library.html"
CATALOG = ROOT / "data" / "_catalog" / "claude_artifacts.json"
TITLE = "EminiAddict MM Sequence Library"   # slug -> eminiaddict_mm_sequence_library
DATE = "2026-07-30"

man = json.loads((SEQDIR / "manifest.json").read_text())
# order: 15m, then 5m, then 1D; recent-first within (manifest already recent-first per tf)
order = {"15m": 0, "5m": 1, "1D": 2}
man.sort(key=lambda m: (order.get(m["tf"], 9),))
items = []
for m in man:
    p = SEQDIR / m["png"]
    if not p.exists():
        continue
    b64 = base64.b64encode(p.read_bytes()).decode()
    items.append({**m, "src": f"data:image/png;base64,{b64}"})

DATA = json.dumps(items)
n = len(items)

CSS = """
:root{--bg:#0d1117;--card:#161b22;--chip:#30363d;--fg:#e6edf3;--mut:#8b949e;--blue:#58a6ff}
*{box-sizing:border-box}body{margin:0;background:var(--bg);color:var(--fg);
 font:14px/1.5 -apple-system,Segoe UI,Roboto,sans-serif}
header{position:sticky;top:0;background:var(--bg);border-bottom:1px solid var(--chip);
 padding:11px 20px;display:flex;align-items:center;gap:12px;z-index:10;flex-wrap:wrap}
header h1{font-size:16px;margin:0}a{color:var(--blue);text-decoration:none}
.tf{padding:5px 12px;border:1px solid var(--chip);border-radius:8px;cursor:pointer;font-size:12.5px;
 font-weight:600;color:var(--mut);background:var(--card)}
.tf.on{color:var(--blue);border-color:var(--blue);background:#58a6ff14}
.btn{padding:7px 15px;border:1px solid var(--blue);border-radius:8px;background:#58a6ff12;color:var(--blue);
 font-weight:600;cursor:pointer;font-size:14px}.btn:hover{background:#58a6ff26}
.wrap{max-width:1500px;margin:0 auto;padding:14px 20px 60px;text-align:center}
.meta{display:flex;gap:14px;justify-content:center;flex-wrap:wrap;margin:6px 0 10px;
 font-size:13px;color:var(--mut)}
.meta b{color:var(--fg)}.pill{background:var(--card);border:1px solid var(--chip);border-radius:6px;padding:2px 9px}
img{max-width:100%;border:1px solid var(--chip);border-radius:10px}
.count{font-family:ui-monospace,Consolas,monospace;color:var(--mut);font-size:13px}
.hint{color:var(--mut);font-size:12px;margin:10px 0}
</style>"""

JS = """
var ALL=__DATA__, tf='all', i=0, view=ALL;
function setTf(t){tf=t;var b=document.querySelectorAll('.tf');for(var k=0;k<b.length;k++)b[k].classList.toggle('on',b[k].dataset.t===t);
 view=(t==='all')?ALL:ALL.filter(function(x){return x.tf===t});i=0;render();}
function go(d){if(!view.length)return;i=(i+d+view.length)%view.length;render();}
function render(){if(!view.length){document.getElementById('img').src='';document.getElementById('meta').innerHTML='none';return;}
 var m=view[i];document.getElementById('img').src=m.src;
 document.getElementById('count').textContent=(i+1)+' / '+view.length;
 document.getElementById('meta').innerHTML=
  '<span class="pill">'+m.tf+'</span>'+
  '<span class="pill">'+m.dir+'</span>'+
  '<span>leg <b>'+m.leg+'</b></span>'+
  '<span><b>'+m.n_with+'</b> with-trend MMs</span>'+
  '<span><b>'+m.n_counter+'</b> counter</span>'+
  '<span>R <b>'+m.R+'</b></span>'+
  '<span>ATWHWB '+(m.atw?'<b style="color:#3fb950">reached ✓</b>':'<span style="color:#8b949e">not in window</span>')+'</span>';}
document.addEventListener('keydown',function(e){if(e.key==='ArrowRight')go(1);if(e.key==='ArrowLeft')go(-1);});
setTf('all');
"""

HTML = f"""<!doctype html><html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1"><title>{TITLE}</title>
<style>{CSS}</style></head><body>
<header><h1>MM Sequence Library</h1>
 <span class="tf on" data-t="all" onclick="setTf('all')">All</span>
 <span class="tf" data-t="15m" onclick="setTf('15m')">15M</span>
 <span class="tf" data-t="5m" onclick="setTf('5m')">5M</span>
 <span class="tf" data-t="1D" onclick="setTf('1D')">1D</span>
 <span style="margin-left:auto"></span>
 <a href="/artifact/eminiaddict_measured_move_method">Method reference →</a></header>
<div class="wrap">
 <div class="meta" id="meta"></div>
 <div style="display:flex;gap:14px;align-items:center;justify-content:center;margin-bottom:10px">
  <button class="btn" onclick="go(-1)">← Prev</button>
  <span class="count" id="count"></span>
  <button class="btn" onclick="go(1)">Next →</button>
 </div>
 <img id="img" alt="MM sequence">
 <p class="hint">Each chart: the initial (macro) leg + its 123.6% target and the
  <b style="color:#4aa3ff">ATWHWB</b> (50% of the whole leg); ▲/▼ = a member MM's 50% entry,
  ★ = its 123.6% target (green=with-trend, orange=counter-trend). {n} sequences, 5-yr ES.
  Use ← → arrow keys. Prices on pre-2024 charts are continuous back-adjusted; recent = real ES.</p>
</div>
<script>{JS.replace('__DATA__', DATA)}</script>
</body></html>"""

OUT.write_text(HTML, encoding="utf-8")
print(f"wrote {OUT}  ({round(len(HTML)/1024/1024,2)} MB, {n} sequences)")

cat = json.loads(CATALOG.read_text(encoding="utf-8"))
its = cat["artifacts"]
info = (f"Scrollable library of {n} Halsey measured-move SEQUENCES auto-detected across "
        "5 years of ES (5M/15M/1D). Each shows the initial leg, its with-trend series of "
        "traditional MMs riding to the 123.6% target, counter-trend MMs after the break, and "
        "the ATWHWB (50% of the initial move) that price retraces to. Filter by timeframe, "
        "arrow-key scroll.")
its[:] = [a for a in its if a.get("title") != TITLE]
its.insert(0, {"title": TITLE, "url": "", "updated": DATE, "group": "EminiAddict", "info": info})
CATALOG.write_text(json.dumps(cat, indent=1, ensure_ascii=False), encoding="utf-8")
print(f"registered '{TITLE}'")
