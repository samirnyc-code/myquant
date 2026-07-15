"""Build codex_portable.html — the one-file travel Codex.

Embeds (no external references, works from a bare download):
  - Setups & Rules Trainer (app.html, self-contained) as an iframe srcdoc
  - Desk cheat-sheet (cheatsheet.html) as an iframe srcdoc
  - Real Days: all forum day texts + tags + abbreviation dictionary (no images;
    each day links to the live tool and to the chart in the Drive folder)
  - The official Encyclopedia index (596 sections), searchable

  python scripts/brooks_build_portable.py
"""
import json, html as H
from pathlib import Path

ROOT = Path(r'c:\Users\Admin\myquant')
HUB = ROOT / 'docs' / 'living' / 'brooks_codex'

app = (HUB / 'app.html').read_text(encoding='utf-8')
cheat = (HUB / 'cheatsheet.html').read_text(encoding='utf-8')
fd = json.load(open(HUB / 'forum_days.json', encoding='utf-8'))
enc = json.load(open(ROOT / 'docs' / 'living' / 'brooks_encyc_index.json', encoding='utf-8'))

# keep only text days for the portable file (charts live in the Drive folder)
days = [d for d in fd['days'] if d.get('bars')]

TMPL = r'''<!doctype html><html><head><meta charset=utf-8><meta name=viewport content="width=device-width,initial-scale=1">
<title>Brooks Codex — Portable</title><style>
:root{--bg:#0c1016;--panel:#141b24;--panel2:#1b2430;--ink:#e8eef6;--dim:#93a2b4;--line:#25303d;--gold:#e6b23a;--mono:ui-monospace,Menlo,Consolas,monospace}
@media(prefers-color-scheme:light){:root{--bg:#eef1f5;--panel:#fff;--panel2:#f4f6f9;--ink:#141b24;--dim:#54636f;--line:#dbe2ea;--gold:#b1810c}}
*{box-sizing:border-box}body{margin:0;background:var(--bg);color:var(--ink);font-family:system-ui}
header{display:flex;gap:6px;align-items:center;padding:10px 16px;border-bottom:1px solid var(--line);position:sticky;top:0;background:var(--bg);z-index:9;flex-wrap:wrap}
header b{letter-spacing:.12em;text-transform:uppercase;font-size:15px;margin-right:10px}header b span{color:var(--gold)}
.tab{font-family:var(--mono);font-size:13px;background:var(--panel);color:var(--ink);border:1px solid var(--line);border-radius:8px;padding:8px 14px;cursor:pointer}
.tab.on{background:var(--gold);color:#0c1016;font-weight:700}
.pane{display:none}.pane.on{display:block}
iframe{width:100%;height:calc(100vh - 60px);border:0;background:#fff}
.wrap{max-width:1100px;margin:0 auto;padding:16px 20px 60px}
input,select{font-family:var(--mono);font-size:13px;background:var(--panel);color:var(--ink);border:1px solid var(--line);border-radius:8px;padding:8px 12px}
.day{border:1px solid var(--line);border-radius:10px;background:var(--panel);margin:10px 0;padding:12px 16px}
.day h3{margin:0;font-family:var(--mono);font-size:14px;color:var(--gold);cursor:pointer}
.day .tags{font-family:var(--mono);font-size:11px;color:var(--dim);margin:4px 0}
.day .bars{display:none;margin-top:8px}.day.open .bars{display:block}
.bar{padding:6px 0;border-top:1px solid var(--line);font-size:14.5px;line-height:1.55}
.bar b{font-family:var(--mono);color:var(--gold);font-size:12px}
abbr{text-decoration:underline dotted rgba(230,178,58,.5);cursor:help}
table{border-collapse:collapse;width:100%;font-size:14px}
th,td{border:1px solid var(--line);padding:7px 10px;text-align:left}
th{background:var(--panel2);font-family:var(--mono);font-size:11px;text-transform:uppercase}
.note{color:var(--dim);font-size:13px}
</style></head><body>
<header><b>Brooks <span>Codex</span> · portable</b>
<button class="tab on" data-p=trainer>Trainer</button>
<button class=tab data-p=days>Real Days</button>
<button class=tab data-p=encyc>Encyclopedia</button>
<button class=tab data-p=cheat>Cheat sheet</button>
</header>
<div class="pane on" id=trainer><iframe id=iftrainer></iframe></div>
<div class=pane id=cheat><iframe id=ifcheat></iframe></div>
<div class=pane id=days><div class=wrap>
 <p class=note>All of Al's bar-by-bar day reads, text-only (charts live in the Drive folder / live tool). Hover any abbreviation for its definition.</p>
 <input id=dq placeholder="search date / tag / text..." style="width:260px"> <select id=dt><option value="">— all tags —</option></select> <span id=dc class=note></span>
 <div id=dlist></div></div></div>
<div class=pane id=encyc><div class=wrap>
 <p class=note>The official Brooks Encyclopedia of Chart Patterns index (Oct 2025, Parts 1–16).</p>
 <input id=eq placeholder="search sections..." style="width:260px">
 <table><thead><tr><th>Part</th><th>Abbreviation</th><th>Section</th></tr></thead><tbody id=etb></tbody></table></div></div>
<script>
const DAYS=__DAYS__,DICT=__DICT__,ENC=__ENC__;
const APP=__APP__,CHEAT=__CHEAT__;
let loaded={};
document.querySelectorAll(".tab").forEach(t=>t.onclick=()=>{
 document.querySelectorAll(".tab").forEach(x=>x.classList.toggle("on",x===t));
 document.querySelectorAll(".pane").forEach(p=>p.classList.toggle("on",p.id===t.dataset.p));
 if(t.dataset.p==="trainer"&&!loaded.t){document.getElementById("iftrainer").srcdoc=APP;loaded.t=1;}
 if(t.dataset.p==="cheat"&&!loaded.c){document.getElementById("ifcheat").srcdoc=CHEAT;loaded.c=1;}});
document.getElementById("iftrainer").srcdoc=APP;loaded.t=1;
function esc(s){return s.replace(/&/g,"&amp;").replace(/</g,"&lt;");}
function markup(s){return esc(s).replace(/\b([A-Za-z][A-Za-z0-9']{0,30})\b/g,(m,w)=>DICT[w]?'<abbr title="'+esc(DICT[w]).replace(/"/g,"&quot;")+'">'+w+"</abbr>":m);}
const tags={};DAYS.forEach(d=>Object.keys(d.tags||{}).forEach(t=>tags[t]=(tags[t]||0)+1));
const dt=document.getElementById("dt");
Object.entries(tags).sort((a,b)=>b[1]-a[1]).forEach(([t,n])=>{const o=document.createElement("option");o.value=t;o.textContent=t+" ("+n+")";dt.appendChild(o);});
function renderDays(){
 const q=document.getElementById("dq").value.toLowerCase(),tg=dt.value;
 const hits=DAYS.filter(d=>{if(tg&&!(d.tags&&d.tags[tg]))return false;
  if(!q)return true;
  return d.date.includes(q)||Object.keys(d.tags||{}).some(t=>t.toLowerCase().includes(q))||d.bars.some(b=>b.t.toLowerCase().includes(q));});
 document.getElementById("dc").textContent=hits.length+" / "+DAYS.length+" days";
 const dl=document.getElementById("dlist");dl.innerHTML="";
 hits.slice(0,400).forEach(d=>{const el=document.createElement("div");el.className="day";
  el.innerHTML="<h3>"+d.date+" ▸</h3><div class=tags>"+Object.keys(d.tags||{}).join(" · ")+"</div><div class=bars>"+
   d.bars.map(b=>"<div class=bar><b>Bar "+b.n+"</b> "+markup(b.t)+"</div>").join("")+
   (d.tool?'<div class=bar><a style="color:var(--gold)" href="'+d.tool+'" target=_blank>▶ open live tool (chart)</a></div>':"")+"</div>";
  el.querySelector("h3").onclick=()=>el.classList.toggle("open");dl.appendChild(el);});
 if(hits.length>400)dl.insertAdjacentHTML("beforeend","<p class=note>Showing first 400 — narrow the search.</p>");
}
document.getElementById("dq").oninput=renderDays;dt.onchange=renderDays;renderDays();
function renderEnc(){const q=document.getElementById("eq").value.toLowerCase();
 document.getElementById("etb").innerHTML=ENC.filter(e=>!q||e.section.toLowerCase().includes(q)||e.abbr.toLowerCase().includes(q))
 .map(e=>"<tr><td>"+e.part+"</td><td style='font-family:var(--mono)'>"+esc(e.abbr)+"</td><td>"+esc(e.section)+"</td></tr>").join("");}
document.getElementById("eq").oninput=renderEnc;renderEnc();
</script></body></html>'''

def js(v, **kw):
    # JSON destined for an inline <script>: a literal </script> (or <!--) inside
    # the string ends the script element and spills everything after it into the
    # page as text. <\/ and <\!-- are the same strings to the JS engine.
    return json.dumps(v, **kw).replace('</', r'<\/').replace('<!--', r'<\!--')

out = (TMPL.replace('__DAYS__', js(days, ensure_ascii=False))
           .replace('__DICT__', js(fd['dict'], ensure_ascii=False))
           .replace('__ENC__', js(enc, ensure_ascii=False))
           .replace('__APP__', js(app))
           .replace('__CHEAT__', js(cheat)))
dst = HUB / 'codex_portable.html'
dst.write_text(out, encoding='utf-8')
print(f'codex_portable.html: {len(days)} text days, {dst.stat().st_size/1e6:.1f} MB')
