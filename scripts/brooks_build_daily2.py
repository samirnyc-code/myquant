"""Rebuild daily.html from the CORRECTED blog re-scrape (S71 daily2 set).

Replaces the old daily.html whose images were mis-scraped and whose
'lesson' commentary was AI filler. This build uses:
  - charts: docs/living/brooks_codex/daily2/<id>.jpg (1,221 verified EOD charts)
  - text:   Al's real typed analysis from rescrape_full.json
Favorites/hidden localStorage keys are kept, so the user's stars survive.

  python scripts/brooks_build_daily2.py
"""
import json, re, statistics
from pathlib import Path
from PIL import Image

ROOT = Path(r'c:\Users\Admin\myquant')
HUB = ROOT / 'docs' / 'living' / 'brooks_codex'
SRC = Path(r'C:\Users\Admin\AppData\Local\Temp\claude\c--Users-Admin-myquant'
           r'\f04593f3-53f8-4ab9-9690-dd0509e339a3\scratchpad\rescrape_full.json')

items = json.load(open(SRC, encoding='utf-8'))
have = {p.stem for p in (HUB / 'daily2').glob('*.jpg')}
# permanent exclusions (user-purged non-charts) — never resurrected
EXC = ROOT / 'docs' / 'living' / 'brooks_daily_excluded.json'
excluded = set(json.load(open(EXC, encoding='utf-8'))) if EXC.exists() else set()
have -= excluded

TYPES = [
    ('trend from open', 'Trend From Open'), ('trend resumption', 'Trend Resumption'),
    ('trend reversal', 'Trend Reversal'), ('trading range', 'Trading Range'),
    ('bull trend', 'Bull Trend'), ('bear trend', 'Bear Trend'),
    ('bull breakout', 'Bull Breakout'), ('bear breakout', 'Bear Breakout'),
    ('wedge', 'Wedge'), ('double top', 'Double Top'), ('double bottom', 'Double Bottom'),
    ('buy climax', 'Buy Climax'), ('sell climax', 'Sell Climax'),
    ('gap up', 'Gap Up'), ('gap down', 'Gap Down'),
]

def day_type(title):
    t = title.lower()
    for k, v in TYPES:
        if k in t:
            return v
    return 'Other'

# recurring blog boilerplate — any paragraph starting with one of these is dropped
BOILER = [
    "yesterday's e-mini setups", 'jed created the', 'here are reasonable stop entry setups',
    'the goal with these charts is to present an always in',
    'it is important to understand that most swing setups',
    'if the risk is too big for your account',
    "summary of today's s&p e-mini price action", 'summary of today',
    'periodic end of day review videos', 'see the weekly update for a discussion',
    'trading room', 'al brooks and other presenters talk',
    'charts use pacific time', 'when times are mentioned, it is usa pacific',
    'you can read background information', 'e-mini end of day video review',
    's&p e-mini market analysis', 'we offer a 2 day free trial',
]
SECTION_HDR = re.compile(
    r'^(?:e-?mini|emini|sp500|s&p)?\s*(?:s&p\s*)?(weekly|daily|monthly|yearly|5[\s-]*min(?:ute)?s?|intraday)'
    r'[\s-]*chart\b[^\n]{0,60}$', re.I)

def norm_para(p):
    return re.sub(r'[‘’]', "'", re.sub(r'\s+', ' ', p)).strip().lower()

def clean_sections(text):
    """Drop boilerplate paragraphs; split into (preamble, [[header, body], ...])."""
    paras = [p.strip() for p in re.split(r'\n\s*\n?', text) if p.strip()]
    keep = [p for p in paras if not any(norm_para(p).startswith(b) for b in BOILER)]
    pre, secs, cur = [], [], None
    for p in keep:
        m = SECTION_HDR.match(p.strip()) if len(p.strip()) <= 90 else None
        if m:
            kind = re.sub(r'[\s-]+', '', m.group(1).lower())
            title = ("Today's Chart" if kind.startswith('5') or kind == 'intraday'
                     else m.group(1).strip().capitalize() + ' chart')
            cur = [title, []]
            secs.append(cur)
        elif cur is not None:
            cur[1].append(p)
        else:
            pre.append(p)
    return '\n\n'.join(pre), [[t, '\n\n'.join(b)] for t, b in secs if b]

def detect_bars(path):
    """Best-effort candle-column detection for blog charts (no URL geometry).
    Returns bar-center fractions when a confident, regular series is found."""
    try:
        img = Image.open(path).convert('L')
    except Exception:
        return None
    W, H = img.size
    px = img.load()
    Y0, Y1 = int(H * 0.14), int(H * 0.88)
    need = max(6, int((Y1 - Y0) * 0.035))
    dark = [sum(1 for y in range(Y0, Y1) if px[x, y] < 80) >= need for x in range(W)]
    centers, x = [], 0
    while x < W:
        if dark[x]:
            x0 = x
            while x < W and dark[x]:
                x += 1
            if x - x0 <= max(10, W // 60):     # candle-width run, not a box/axis
                centers.append((x0 + x - 1) / 2)
        else:
            x += 1
    if not 40 <= len(centers) <= 100:
        return None
    sp = [b - a for a, b in zip(centers, centers[1:])]
    med = statistics.median(sp)
    if med < 3 or statistics.pstdev(sp) / med > 0.35:
        return None
    # reject if the series has gaps (numbering would shift)
    span_bars = (centers[-1] - centers[0]) / med + 1
    if abs(span_bars - len(centers)) > 2:
        return None
    return {'x': [round(c / W, 5) for c in centers], 'w': round(med / W, 5)}

cards = []
for x in items:
    if x['id'] not in have or not x.get('text'):
        continue
    pre, secs = clean_sections(x['text'].strip())
    # drop the "Trading Update: <date>" line (date is already on the card)
    pre = '\n\n'.join(p for p in pre.split('\n\n')
                      if not re.match(r'\s*trading update\b', p, re.I)).strip()
    # Today's Chart first, Daily chart and the rest after
    secs.sort(key=lambda s: 0 if s[0].startswith("Today") else 1)
    txt = (pre + ' ' + ' '.join(b for _, b in secs)).strip()
    rec = {'id': x['id'], 'title': x.get('title', ''), 'date': x.get('date', ''),
           'dt': day_type(x.get('title', '')), 'pre': pre[:4000],
           'secs': [[t, b[:12000]] for t, b in secs]}
    if re.search(r'\bbar\s+\d', txt, re.I):     # only detect when text refs bars
        f = detect_bars(HUB / 'daily2' / f"{x['id']}.jpg")
        if f:
            rec['fit'] = f
    cards.append(rec)
cards.sort(key=lambda c: c['date'], reverse=True)

TMPL = r'''<!doctype html><html><head><meta charset=utf-8><title>Brooks Codex — Daily Charts</title><style>
:root{--bg:#0c1016;--panel:#141b24;--panel2:#1b2430;--ink:#e8eef6;--dim:#93a2b4;--line:#25303d;--gold:#e6b23a;--mono:ui-monospace,Menlo,Consolas,monospace}
*{box-sizing:border-box}body{margin:0;background:var(--bg);color:var(--ink);font-family:system-ui}
header{border-bottom:1px solid var(--line);padding:10px 18px;display:flex;gap:10px;align-items:center;position:sticky;top:0;background:var(--bg);z-index:5;flex-wrap:wrap}
header b{font-size:16px;letter-spacing:.12em;text-transform:uppercase}header b span{color:var(--gold)}
header a{color:var(--dim);font-family:var(--mono);font-size:12px;text-decoration:none;margin-left:auto}
input,select{font-family:var(--mono);font-size:13px;background:var(--panel);color:var(--ink);border:1px solid var(--line);border-radius:8px;padding:8px 12px}
button{font-family:var(--mono);font-size:12.5px;background:var(--panel);color:var(--ink);border:1px solid var(--line);border-radius:8px;padding:8px 13px;cursor:pointer}
button.on{background:var(--gold);color:#0c1016;font-weight:700}
.wrap{height:calc(100vh - 57px);overflow-y:auto;scroll-snap-type:y mandatory;padding:0 48px}
.snap{min-height:calc(100vh - 57px);display:flex;align-items:center;justify-content:center;scroll-snap-align:start;scroll-snap-stop:always}
.card{width:100%;max-width:min(100%,148vh);margin:0 auto}
.snap .card:not(.open){display:flex;flex-direction:column;max-height:calc(100vh - 80px)}
.card:not(.open) .cimg{flex:0 0 auto}
.card:not(.open) .cimg img{max-height:calc(100vh - 300px);object-fit:contain}
.card:not(.open) .cright{flex:1 1 auto;min-height:0;display:flex;flex-direction:column;overflow:hidden}
.card:not(.open) .chead,.card:not(.open) .more{flex:0 0 auto}
body.focus .wrap{scroll-snap-type:none;padding:0 14px}
body.focus .snap{display:none}
body.focus .snap.cur{display:flex}
body.focus .card.open{max-width:none}
body[data-fs=s]{--fs:13.5px}body[data-fs=m]{--fs:15.5px}body[data-fs=l]{--fs:18.5px}
.card{border:1px solid var(--line);border-radius:12px;background:var(--panel);margin:16px 0;overflow:hidden}
.cimg{position:relative;background:#fff}
.cimg img{width:100%;display:block;cursor:pointer}
.zbtn2{position:absolute;right:8px;bottom:8px;font-family:var(--mono);background:rgba(20,27,36,.8);color:#e8eef6;border:1px solid var(--line);border-radius:7px;width:34px;height:34px;cursor:zoom-in;font-size:15px}
.dstripe{position:absolute;top:0;bottom:0;display:none;background:rgba(255,238,0,.22);border-left:1.5px solid #ffe600;border-right:1.5px solid #ffe600;pointer-events:none}
.chead{display:flex;gap:10px;align-items:baseline;padding:12px 16px 0;flex-wrap:wrap}
.chead .dt{font-family:var(--mono);font-size:11px;background:var(--panel2);border:1px solid var(--line);color:var(--gold);border-radius:14px;padding:2px 10px}
.chead h3{margin:0;font-size:16px}
.chead .date{font-family:var(--mono);font-size:12px;color:var(--dim)}
.chead .act{margin-left:auto;display:flex;gap:6px}
.ctext{padding:8px 16px 14px;color:var(--dim);font-size:var(--fs,15.5px);line-height:1.65;white-space:pre-line;max-height:120px;overflow:hidden;cursor:pointer}
.card:not(.open) .ctext.preview{max-height:none;flex:1 1 auto;min-height:40px;overflow-y:auto;overscroll-behavior:contain}
.more{font-family:var(--mono);font-size:11px;color:var(--gold);padding:0 16px 12px;cursor:pointer}
.bref{color:var(--gold);font-weight:600}
details.sec{border:1px solid var(--line);border-radius:9px;margin:10px 16px;background:var(--panel2)}
details.sec summary{font-family:var(--mono);font-size:12.5px;color:var(--gold);padding:9px 14px;cursor:pointer;list-style:none}
details.sec summary::before{content:"▸ "}details.sec[open] summary::before{content:"▾ "}
details.sec .secbody{padding:2px 16px 12px;font-size:var(--fs,15.5px);line-height:1.65;white-space:pre-line;color:var(--ink)}
body.focus .card:not(.open){display:none}
.card.open{display:grid;grid-template-columns:minmax(0,1.65fr) minmax(320px,1fr);gap:6px;align-items:start;height:calc(100vh - 88px);overflow:hidden;margin:16px 0}
.card.open .cimg{background:transparent;padding:54px 8px 8px}
.card.open .cimg img{max-height:calc(100vh - 160px);width:100%;object-fit:contain}
.card.open .chead{padding-top:14px}
.card .full{display:none}
.card.open .full{display:block}
.card.open .ctext.preview{display:none}
.card.open .full .ctext{max-height:none;color:var(--ink);cursor:auto}
.card.open .cright{height:100%;overflow-y:auto;padding:0 10px 20px 0}
@media(max-width:900px){.card.open{display:block;height:auto;overflow:visible}.card.open .cright{height:auto}}
.zov{position:fixed;inset:0;z-index:60;background:rgba(4,7,11,.94);display:none;overflow:hidden}
.zov.on{display:block}.zov img{position:absolute;top:0;left:0;transform-origin:0 0;cursor:grab;user-select:none;max-width:none}
.zbar{position:fixed;top:14px;right:16px;z-index:61;display:none;gap:8px}.zbar.on{display:flex}
.zbtn{font-family:var(--mono);background:var(--panel);color:var(--ink);border:1px solid var(--line);border-radius:9px;width:42px;height:42px;cursor:pointer}
.count{font-family:var(--mono);font-size:12px;color:var(--dim)}
.lens{position:fixed;z-index:50;width:364px;height:364px;border-radius:50%;border:2px solid var(--gold);box-shadow:0 6px 28px rgba(0,0,0,.55);background-repeat:no-repeat;background-color:#fff;pointer-events:none;display:none}
</style></head><body>
<header><b>Brooks <span>Daily Charts</span></b>
<input id=q placeholder="search title / text / date..." style="width:240px">
<select id=tf><option value="">— all day types —</option></select>
<button id=favb>★ Favorites</button><button id=trash>🗑 <span id=tn>0</span></button><button id=exportdel title="Download the delete list, then run brooks_purge_daily.py to remove these files permanently">⤓ Export delete list</button>
<select id=fsz title="Commentary font size"><option value=s>A small</option><option value=m selected>A medium</option><option value=l>A large</option></select>
<button id=lensb title="Hover a chart to magnify a few bars; mouse wheel changes magnification">🔎 Lens</button>
<span class=count id=cnt></span>
<a href="index.html">← Codex hub</a></header>
<div class=wrap id=lst></div>
<div class=zov id=zov><img id=zimg></div>
<div class=zbar id=zbar><button class=zbtn id=zout>−</button><button class=zbtn id=zin>+</button><button class=zbtn id=zfit>⤢</button><button class=zbtn id=zx>×</button></div>
<script>
const CARDS=__CARDS__;
const FLS="brooks_daily_favs",HLS="brooks_daily_hidden";
let favs=new Set(JSON.parse(localStorage.getItem(FLS)||"[]"));
let hidden=new Set(JSON.parse(localStorage.getItem(HLS)||"[]"));
let favOnly=false,showTrash=false;
const lst=document.getElementById("lst"),q=document.getElementById("q"),tf=document.getElementById("tf");
let lensOn=false,lz=2.5;
const lens=document.createElement("div");lens.className="lens";document.body.appendChild(lens);
document.getElementById("lensb").onclick=function(){lensOn=!lensOn;this.classList.toggle("on",lensOn);if(!lensOn)lens.style.display="none";};
function lensMove(e,img){
 if(!lensOn||!img.naturalWidth){lens.style.display="none";return;}
 const r=img.getBoundingClientRect();
 const s=Math.min(r.width/img.naturalWidth,r.height/img.naturalHeight);
 const dw=img.naturalWidth*s,dh=img.naturalHeight*s;
 const ox=r.left+(r.width-dw)/2,oy=r.top+(r.height-dh)/2;
 const x=e.clientX-ox,y=e.clientY-oy;
 if(x<0||y<0||x>dw||y>dh){lens.style.display="none";return;}
 const R=182;
 lens.style.display="block";
 lens.style.left=(e.clientX-R)+"px";lens.style.top=(e.clientY-R)+"px";
 lens.style.backgroundImage='url("'+img.src+'")';
 lens.style.backgroundSize=(dw*lz)+"px "+(dh*lz)+"px";
 lens.style.backgroundPosition=(R-x*lz)+"px "+(R-y*lz)+"px";
}
function lensBind(img){
 img.addEventListener("mousemove",e=>lensMove(e,img));
 img.addEventListener("mouseleave",()=>{lens.style.display="none";});
 img.addEventListener("wheel",e=>{if(!lensOn)return;e.preventDefault();
  lz=Math.min(6,Math.max(1.5,lz*(e.deltaY<0?1.15:1/1.15)));lensMove(e,img);},{passive:false});
}
[...new Set(CARDS.map(c=>c.dt))].sort().forEach(t=>{const o=document.createElement("option");o.value=t;o.textContent=t;tf.appendChild(o);});
function esc(s){return s.replace(/&/g,"&amp;").replace(/</g,"&lt;");}
function saveF(){localStorage.setItem(FLS,JSON.stringify([...favs]));}
function saveH(){localStorage.setItem(HLS,JSON.stringify([...hidden]));document.getElementById("tn").textContent=hidden.size;}
function render(){
 const term=q.value.toLowerCase();
 let a=showTrash?CARDS.filter(c=>hidden.has(c.id)):CARDS.filter(c=>!hidden.has(c.id));
 if(favOnly&&!showTrash)a=a.filter(c=>favs.has(c.id));
 if(tf.value)a=a.filter(c=>c.dt===tf.value);
 if(term)a=a.filter(c=>c.title.toLowerCase().includes(term)||c.date.includes(term)||c.pre.toLowerCase().includes(term)||c.secs.some(s=>s[1].toLowerCase().includes(term)));
 document.getElementById("cnt").textContent=a.length+" / "+CARDS.length;
 lst.innerHTML="";
 a.slice(0,120).forEach(c=>{
  const el=document.createElement("div");el.className="card";
  const mk=s=>esc(s).replace(/\b([Bb]ars?)\s+(\d{1,3})\b/g,'<span class=bref>$1 $2</span>');
  const tod=c.secs.find(s=>s[0].startsWith("Today"));
  const preview=((c.pre?c.pre+"\n\n":"")+(tod?tod[1]:(c.secs[0]?c.secs[0][1]:""))).slice(0,6000);
  let full=c.pre?'<div class=ctext>'+mk(c.pre)+'</div>':"";
  c.secs.forEach(s=>{const today=s[0].startsWith("Today");const ttl=today?s[0]+" — "+c.date:s[0];
   full+='<details class=sec'+(today?' open':'')+'><summary>'+esc(ttl)+'</summary><div class=secbody>'+mk(s[1])+'</div></details>';});
  if(!full)full='<div class=ctext>(no commentary)</div>';
  el.innerHTML='<div class=cimg><img loading=lazy src="daily2/'+c.id+'.jpg"><div class=dstripe></div></div>'
   +'<div class=cright><div class=chead><span class=dt>'+c.dt+'</span><h3>'+esc(c.title)+'</h3><span class=date>'+c.date+'</span>'
   +'<span class=act><button class=fv>'+(favs.has(c.id)?"★":"☆")+'</button><button class=hd>'+(showTrash?"↩":"🗑")+'</button></span></div>'
   +'<div class="ctext preview">'+mk(preview)+'</div><div class=full>'+full+'</div>'
   +'<div class=more>▾ full analysis</div></div>';
  const img=el.querySelector("img"),stripe=el.querySelector(".dstripe");
  lensBind(img);
  img.onclick=()=>{if(!lensOn)tgl();};
  el.querySelector(".fv").onclick=()=>{favs.has(c.id)?favs.delete(c.id):favs.add(c.id);saveF();render();};
  el.querySelector(".hd").onclick=()=>{showTrash?hidden.delete(c.id):hidden.add(c.id);saveH();render();};
  const tgl=()=>{const opening=!el.classList.contains("open");
   if(opening)lst._sy=lst.scrollTop;
   el.classList.toggle("open",opening);el.parentElement.classList.toggle("cur",opening);
   document.body.classList.toggle("focus",opening);
   el.querySelector(".more").textContent=opening?"▴ collapse":"▾ full analysis";
   lst.scrollTop=opening?0:(lst._sy||0);};
  el.querySelector(".more").onclick=tgl;
  el.querySelector(".ctext").onclick=e=>{if(e.target.classList.contains("bref"))return;if(!el.classList.contains("open"))tgl();};
  const sec=document.createElement("div");sec.className="snap";sec.appendChild(el);lst.appendChild(sec);});
 if(a.length>120)lst.insertAdjacentHTML("beforeend","<p class=count>Showing first 120 — narrow the search.</p>");
}
document.getElementById("favb").onclick=function(){favOnly=!favOnly;this.classList.toggle("on",favOnly);render();};
document.getElementById("exportdel").onclick=()=>{
 if(!hidden.size){alert("Nothing in the trash — 🗑 some charts first.");return;}
 const blob=new Blob([JSON.stringify([...hidden])],{type:"application/json"});
 const a=document.createElement("a");a.href=URL.createObjectURL(blob);a.download="brooks_deletions.json";a.click();
 alert(hidden.size+" ids exported. Run: python scripts/brooks_purge_daily.py to delete them permanently.");};
document.getElementById("trash").onclick=function(){showTrash=!showTrash;this.classList.toggle("on",showTrash);render();};
const zov=document.getElementById("zov"),zimg=document.getElementById("zimg"),zbar=document.getElementById("zbar");
let Z={s:1,x:0,y:0,d:false,px:0,py:0};
function zap(){zimg.style.transform="translate("+Z.x+"px,"+Z.y+"px) scale("+Z.s+")";}
function zfit(){const iw=zimg.naturalWidth,ih=zimg.naturalHeight;if(!iw)return;Z.s=Math.min(innerWidth/iw,innerHeight/ih)*0.97;Z.x=(innerWidth-iw*Z.s)/2;Z.y=(innerHeight-ih*Z.s)/2;zap();}
function zat(cx,cy,f){const s2=Math.max(0.05,Math.min(9,Z.s*f));Z.x=cx-(cx-Z.x)*(s2/Z.s);Z.y=cy-(cy-Z.y)*(s2/Z.s);Z.s=s2;zap();}
function openZoom(src){zimg.src=src;zov.classList.add("on");zbar.classList.add("on");zimg.onload=zfit;if(zimg.complete)zfit();}
function closeZoom(){zov.classList.remove("on");zbar.classList.remove("on");}
zov.addEventListener("wheel",e=>{e.preventDefault();zat(e.clientX,e.clientY,e.deltaY<0?1.15:0.87);},{passive:false});
zimg.addEventListener("mousedown",e=>{Z.d=true;Z.px=e.clientX;Z.py=e.clientY;e.preventDefault();});
window.addEventListener("mousemove",e=>{if(!Z.d)return;Z.x+=e.clientX-Z.px;Z.y+=e.clientY-Z.py;Z.px=e.clientX;Z.py=e.clientY;zap();});
window.addEventListener("mouseup",()=>Z.d=false);
document.getElementById("zin").onclick=()=>zat(innerWidth/2,innerHeight/2,1.3);
document.getElementById("zout").onclick=()=>zat(innerWidth/2,innerHeight/2,0.77);
document.getElementById("zfit").onclick=zfit;document.getElementById("zx").onclick=closeZoom;
document.addEventListener("keydown",e=>{if(e.key==="Escape")closeZoom();});
const fsz=document.getElementById("fsz");
fsz.value=localStorage.brooks_daily_fs||"l";document.body.dataset.fs=fsz.value;
fsz.onchange=()=>{document.body.dataset.fs=fsz.value;localStorage.brooks_daily_fs=fsz.value;};
q.oninput=render;tf.onchange=render;saveH();render();
</script></body></html>'''

html = TMPL.replace('__CARDS__', json.dumps(cards, ensure_ascii=False))
(HUB / 'daily.html').write_text(html, encoding='utf-8')
print(f'daily.html rebuilt: {len(cards)} days with real Brooks analysis '
      f'({(HUB / "daily.html").stat().st_size/1e6:.1f} MB)')
