"""One-day interactive bar-by-bar DEMO for approval: chart + per-bar text,
click a bar # (in text or chart) -> highlight that bar on the chart; prev/next
stepping; link to the live tool. Builds a self-contained HTML and opens it.
"""
import requests, re, json, html as H, io, base64, sys
from pathlib import Path
from PIL import Image
SCR = Path(r"C:\Users\Admin\AppData\Local\Temp\claude\c--Users-Admin-myquant\f04593f3-53f8-4ab9-9690-dd0509e339a3\scratchpad")
BASE = "https://www.brookspriceaction.com"
cr = json.load(open(SCR / "bpa_login.json"))
T = "6118"   # 02-24-2023

s = requests.Session(); s.headers.update({"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) Chrome/120", "Referer": BASE + "/"})
s.get(BASE + "/login.php", timeout=25)
s.post(BASE + "/login.php", data={"username": cr["username"], "password": cr["password"], "autologin": "on", "login": "Log in", "redirect": ""}, timeout=25)

th = s.get(f"{BASE}/viewtopic.php?t={T}", timeout=25).text
date = (re.search(r'(\d{2}-\d{2}-\d{4})', th) or ["", "02-24-2023"])[1]
bb = re.search(r'(files/barbybar/brooksbars\.php\?[^"\'&]*pic_id=\d+[^"\']*)', th)
tool_url = BASE + "/" + H.unescape(bb.group(1)).replace("&amp;", "&")
q = dict(re.findall(r'(\w+)=(\d+)', tool_url))
geom = {k: int(v) for k, v in q.items() if k in ("pic_id", "bars", "left", "width", "top", "height")}
bh = s.get(tool_url, timeout=30).text

def expand(h):
    h2 = re.sub(r'<(?:abbr|acronym)[^>]*title="([^"]*)"[^>]*>(.*?)</(?:abbr|acronym)>', r'\2(\1)', h, flags=re.I | re.S)
    h2 = re.sub(r'<style.*?</style>', ' ', h2, flags=re.S | re.I); h2 = re.sub(r'<script.*?</script>', ' ', h2, flags=re.S | re.I)
    t = re.sub(r'<[^>]+>', ' ', h2); t = H.unescape(t); t = re.sub(r'[ \t]+', ' ', t); t = re.sub(r'\n\s*\n+', '\n', t)
    m = re.search(r'(?:^|\n|\s)1\s*[-–]\s+[A-Z]', t)
    if m: t = t[m.start():].lstrip()
    return re.split(r'(Powered by|Select a forum|Display posts from previous)', t)[0].strip()

text = expand(bh)
# split into per-bar chunks
parts = re.split(r'(?:(?<=\.)|\n)\s*(?=\d{1,3}\s*[-–]?\s+[A-Z])', text)
bars = []
for p in parts:
    m = re.match(r'\s*(\d{1,3})\s*[-–]?\s+(.*)', p.strip(), re.S)
    if m:
        bars.append({"n": int(m.group(1)), "t": re.sub(r'\s+', ' ', m.group(2)).strip()})
# full-size chart (no resize so geometry aligns)
pic = re.search(r'album_picm\.php\?pic_id=(\d+)', bh) or re.search(r'album_picm\.php\?pic_id=(\d+)', th)
ir = s.get(f"{BASE}/album_picm.php?pic_id={pic.group(1)}", timeout=30)
im = Image.open(io.BytesIO(ir.content)).convert("RGB")
buf = io.BytesIO(); im.save(buf, "JPEG", quality=88)
b64 = base64.b64encode(buf.getvalue()).decode()
imgw, imgh = im.size

DATA = {"date": date, "geom": geom, "tool_url": tool_url, "bars": bars, "imgw": imgw, "imgh": imgh}
print(f"date {date} | bars parsed: {len(bars)} | geom {geom} | img {imgw}x{imgh} | tool {tool_url[:70]}")

HTML = """<!doctype html><html><head><meta charset=utf-8><title>Bar-by-Bar demo</title><style>
:root{--bg:#0c1016;--panel:#141b24;--ink:#e8eef6;--dim:#93a2b4;--line:#25303d;--gold:#e6b23a;--mono:ui-monospace,Menlo,Consolas,monospace}
body{margin:0;background:var(--bg);color:var(--ink);font-family:system-ui}
.wrap{max-width:1280px;margin:0 auto;padding:18px}
h1{font-size:20px;margin:0 0 4px}h1 span{color:var(--gold)}
.sub{font-family:var(--mono);color:var(--dim);font-size:12px;margin-bottom:14px}
.tool{font-family:var(--mono);font-size:12px;color:#0c1016;background:var(--gold);padding:8px 12px;border-radius:8px;text-decoration:none}
.grid{display:grid;grid-template-columns:1fr 420px;gap:20px;align-items:start}
@media(max-width:900px){.grid{grid-template-columns:1fr}}
.chartbox{position:sticky;top:14px;border:1px solid var(--line);border-radius:12px;overflow:hidden;background:#fff}
.chartbox{position:relative}.chartbox img{width:100%;display:block}
.hl{position:absolute;top:0;bottom:0;background:rgba(230,178,58,.28);border-left:2px solid var(--gold);border-right:2px solid var(--gold);pointer-events:none;display:none}
.ctl{display:flex;gap:8px;align-items:center;margin:10px 0}
.ctl button{font-family:var(--mono);background:var(--panel);color:var(--ink);border:1px solid var(--line);border-radius:8px;padding:8px 12px;cursor:pointer}
.ctl .cur{font-family:var(--mono);color:var(--gold);font-weight:700}
.bars{display:flex;flex-direction:column;gap:8px;max-height:78vh;overflow:auto}
.bar{border:1px solid var(--line);border-left:3px solid var(--line);border-radius:9px;background:var(--panel);padding:10px 13px;cursor:pointer}
.bar:hover{border-color:var(--dim)}
.bar.on{border-left-color:var(--gold);background:#1b2430}
.bar b{font-family:var(--mono);color:var(--gold);margin-right:8px}
.bar .tx{font-size:13.5px;line-height:1.5}
</style></head><body><div class=wrap>
<h1>Al Brooks <span>Bar-by-Bar</span> — demo</h1>
<div class=sub id=sub></div>
<div class=grid>
 <div>
  <div class=chartbox id=cb><img id=chart><div class=hl id=hl></div></div>
  <div class=ctl><button id=prev>◀ Prev bar</button><span class=cur id=cur>Bar —</span><button id=next>Next bar ▶</button>
   <a class=tool id=tool target=_blank>▶ Practice on the live tool</a></div>
 </div>
 <div class=bars id=list></div>
</div></div>
<script>
const D=__DATA__;
document.getElementById('chart').src='data:image/jpeg;base64,__IMG__';
document.getElementById('sub').textContent=D.date+' \\u00b7 '+D.bars.length+' bars \\u00b7 chart '+D.imgw+'\\u00d7'+D.imgh+' \\u00b7 geometry from his tool';
document.getElementById('tool').href=D.tool_url;
const list=document.getElementById('list'),hl=document.getElementById('hl'),cur=document.getElementById('cur');
let sel=null;
function xfor(n){const g=D.geom;const span=(g.width-g.left);const bw=span/g.bars;const cx=g.left+(n-0.5)*bw;return {left:cx-bw/2,w:bw};}
function highlight(n){const cb=document.getElementById('cb');const dispW=cb.clientWidth;const scale=dispW/D.geom.width;const x=xfor(n);
 hl.style.left=(x.left*scale)+'px';hl.style.width=(x.w*scale)+'px';hl.style.display='block';
 document.querySelectorAll('.bar').forEach(b=>b.classList.toggle('on',+b.dataset.n===n));
 cur.textContent='Bar '+n;sel=n;
 const el=document.querySelector('.bar[data-n=\"'+n+'\"]');if(el)el.scrollIntoView({block:'nearest',behavior:'smooth'});}
D.bars.forEach(b=>{const d=document.createElement('div');d.className='bar';d.dataset.n=b.n;
 d.innerHTML='<b>'+b.n+'</b><span class=tx>'+b.t.replace(/[&<>]/g,m=>({'&':'&amp;','<':'&lt;','>':'&gt;'}[m]))+'</span>';
 d.onclick=()=>highlight(b.n);list.appendChild(d);});
document.getElementById('cb').onclick=e=>{const cb=document.getElementById('cb');const rel=(e.offsetX)/cb.clientWidth*D.geom.width;
 const g=D.geom;const bw=(g.width-g.left)/g.bars;let n=Math.round((rel-g.left)/bw+0.5);n=Math.max(1,Math.min(g.bars,n));highlight(n);};
const ns=D.bars.map(b=>b.n);
document.getElementById('next').onclick=()=>{let i=ns.indexOf(sel);highlight(ns[Math.min(ns.length-1,i+1)]||ns[0]);};
document.getElementById('prev').onclick=()=>{let i=ns.indexOf(sel);highlight(ns[Math.max(0,i-1)]||ns[0]);};
document.addEventListener('keydown',e=>{if(e.key==='ArrowRight')document.getElementById('next').click();if(e.key==='ArrowLeft')document.getElementById('prev').click();});
if(D.bars.length)highlight(D.bars[0].n);
</script></body></html>"""
out = SCR / "forum_bbb_demo.html"
out.write_text(HTML.replace("__DATA__", json.dumps(DATA, ensure_ascii=False)).replace("__IMG__", b64), encoding="utf-8")
print("wrote", out)
