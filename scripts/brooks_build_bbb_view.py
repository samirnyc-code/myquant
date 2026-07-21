"""Build the interactive bar-by-bar day view (Brooks Codex).

STRIPE CALIBRATION — SOLVED (S72). The live tool (brooksbars.php) displays the
album_picm.php image stretched to CSS height 780px, so its URL coordinates
(left/width/bars) live in a space scaled by s = 780/naturalHeight. Its JS
`the_left = left + (N-1)*width/(bars-1)` is the RIGHT edge of bar N (it is a
cover-the-future replay tool). Therefore, as fractions of the image width:

    s      = 780 / naturalHeight
    incF   = (width/(bars-1)) / s / naturalWidth
    rightF(N) = (left + (N-1)*width/(bars-1)) / s / naturalWidth
    stripe(N) = [rightF(N) - incF, rightF(N)]

Verified pixel-exact on pic 7160 (07-26-2022, bars=81 left=80 width=1131) at
bars 1, 2, 10..80, 62, 81. No hand-tuned constants; per-day URL params +
image natural size fully determine the geometry.
"""
import base64, re, json, sys, os
from pathlib import Path
from PIL import Image

SCR = sys.argv[1] if len(sys.argv) > 1 else '.'
OLD = str(Path(__file__).resolve().parent.parent / 'scratchpad')

IMG_PATH = OLD + r'\diag_7160.jpg'
GEOM = {'bars': 81, 'left': 80, 'width': 1131}

b64 = base64.b64encode(open(IMG_PATH, 'rb').read()).decode()
raw = open(OLD + r'\bbb_6042_text.txt', encoding='utf-8').read()

# --- parse notes, enforcing monotone bar numbers -------------------------
# Al's shorthand sometimes starts with a number ("36: 20GBS...") and the
# scrape splits the wrong token off as the bar number. If an entry breaks
# strictly-increasing order, reassign it to prev+1 and flag it.
bars, prev = [], 0
for m in re.finditer(r'Bar (\d+): (.*?)(?=\nBar \d+:|\Z)', raw, re.S):
    n, t = int(m.group(1)), re.sub(r'\s+', ' ', m.group(2)).strip()
    if n <= prev:
        n = prev + 1
        t = '⚠ bar # inferred (source mislabeled) — ' + t
    bars.append({'n': n, 't': t})
    prev = n

# --- calibrate bar centers: detect wicks, then robust-fit one line -------
# Per-bar wick snapping is noisy (small-body bars / dojis miss by ~3px), so
# detect wick columns inside each geometric slot, then Theil-Sen fit
# x(n) = a + b*n through them. Uniform spacing, pixel-true position.
import itertools, statistics
img = Image.open(IMG_PATH).convert('L')
W, H = img.size
px = img.load()
s = 780.0 / H
inc_nat = GEOM['width'] / (GEOM['bars'] - 1) / s
Y0, Y1 = 30, H - 30
dark = lambda x: sum(1 for y in range(Y0, Y1) if px[x, y] < 90) if 0 <= x < W else 0

pts = []
for n in range(1, GEOM['bars'] + 1):
    a = (GEOM['left'] + (n - 1) * GEOM['width'] / (GEOM['bars'] - 1)) / s - inc_nat
    cand = [(dark(x), x) for x in range(int(a + 1), int(a + inc_nat - 1) + 1)]
    best, bx = max(cand)
    if best >= 8:
        pts.append((n, bx + 0.5))

if len(pts) >= 10:
    slopes = [(x2 - x1) / (n2 - n1) for (n1, x1), (n2, x2) in itertools.combinations(pts, 2)]
    fit_b = statistics.median(slopes)
    fit_a = statistics.median(x - fit_b * n for n, x in pts)
else:  # too few wicks detected — fall back to pure tool geometry
    fit_b = inc_nat
    fit_a = GEOM['left'] / s - inc_nat / 2 - fit_b

barx = [round((fit_a + fit_b * n) / W, 5) for n in range(1, GEOM['bars'] + 1)]

DATA = {'date': '07-26-2022 Tuesday',
        'geom': GEOM, 'barx': barx, 'incf': round(inc_nat / W, 5),
        'tool': 'https://www.brookspriceaction.com/files/barbybar/brooksbars.php?pic_id=7160&bars=81&left=80&width=1131&top=0&height=603',
        'bars': bars}

TMPL = r'''<!doctype html><html><head><meta charset=utf-8><title>Bar-by-Bar</title><style>
:root{--bg:#0c1016;--panel:#141b24;--panel2:#1b2430;--ink:#e8eef6;--dim:#93a2b4;--line:#25303d;--gold:#e6b23a;--mono:ui-monospace,Menlo,Consolas,monospace}
*{box-sizing:border-box}body{margin:0;background:var(--bg);color:var(--ink);font-family:system-ui}
header{border-bottom:1px solid var(--line);padding:13px 22px;background:linear-gradient(180deg,var(--panel),var(--bg));display:flex;align-items:center;gap:14px;flex-wrap:wrap}
header b{font-size:18px;letter-spacing:.13em;text-transform:uppercase}header b span{color:var(--gold)}
header small{font-family:var(--mono);color:var(--dim);font-size:12px}
.tool{margin-left:auto;font-family:var(--mono);font-size:12px;color:#0c1016;background:var(--gold);padding:9px 13px;border-radius:8px;text-decoration:none}
.wrap{max-width:1400px;margin:0 auto;padding:18px 22px 60px}
.chartbox{position:relative;border:1px solid var(--line);border-radius:12px;overflow:hidden;background:#fff;cursor:crosshair}
.chartbox img{width:100%;display:block}
.hl{position:absolute;top:0;bottom:0;background:rgba(255,238,0,.13);border-left:1.5px solid #ffe600;border-right:1.5px solid #ffe600;pointer-events:none}
.ctl{display:flex;gap:10px;align-items:center;margin:12px 0 14px;flex-wrap:wrap}
.ctl button{font-family:var(--mono);background:var(--panel);color:var(--ink);border:1px solid var(--line);border-radius:8px;padding:9px 15px;cursor:pointer;font-size:13px}
.ctl button:hover{border-color:var(--gold)}
.hint{font-family:var(--mono);font-size:12px;color:var(--faint,#6b7a8c)}
.txtpanel{border:1px solid var(--line);border-left:4px solid #ffe600;border-radius:12px;background:var(--panel);padding:18px 22px;min-height:130px}
.txtpanel .bn{font-family:var(--mono);color:var(--gold);font-weight:700;font-size:16px;margin-bottom:8px}
.txtpanel .bt{font-size:17px;line-height:1.65;max-width:95ch}
.notelist{display:none;max-height:calc(100vh - 120px);overflow-y:auto;padding-right:6px}
.card{border:1px solid var(--line);border-left:4px solid var(--line);border-radius:10px;background:var(--panel);padding:12px 16px;margin-bottom:10px;cursor:pointer}
.card .bn{font-family:var(--mono);color:var(--gold);font-weight:700;font-size:13px;margin-bottom:5px}
.card .bt{font-size:14px;line-height:1.55;color:var(--dim)}
.card.sel{border-left-color:#ffe600;background:var(--panel2)}.card.sel .bt{color:var(--ink)}
body.split .wrap{max-width:none;display:grid;grid-template-columns:minmax(0,1.55fr) minmax(340px,1fr);gap:20px;align-items:start}
body.split .chartcol{position:sticky;top:10px}
body.split .txtpanel{display:none}body.split .notelist{display:block}
.zov{position:fixed;inset:0;z-index:60;background:rgba(4,7,11,.93);display:none;overflow:hidden;touch-action:none}
.zov.on{display:block}.zov img{position:absolute;top:0;left:0;transform-origin:0 0;cursor:grab;user-select:none}
.zbar{position:fixed;top:14px;right:16px;z-index:61;display:flex;gap:8px}
.zbtn{font-family:var(--mono);background:var(--panel);color:var(--ink);border:1px solid var(--line);border-radius:9px;width:42px;height:42px;cursor:pointer;font-size:15px}
</style></head><body>
<header><b>Al Brooks <span>Bar-by-Bar</span></b><small id=sub></small><a class=tool id=toollink target=_blank>&#9654; Live interactive tool</a></header>
<div class=wrap>
 <div class=chartcol>
  <div class=chartbox id=cb><img id=chart><div class=hl id=hl></div></div>
  <div class=ctl><button id=prev>&#9664; Prev bar</button><button id=next>Next bar &#9654;</button><button id=zoom>&#9974; Zoom chart</button><button id=stripe>&#9635; Stripe: ON</button><button id=layout>&#9707; Layout: Hover</button>
   <span class=hint>Hover the chart &middot; arrows step notes &middot; S = stripe &middot; L = layout. Only the commented bars have text.</span></div>
  <div class=txtpanel id=panel><div class=bn id=bn>&mdash;</div><div class=bt id=bt>Hover a bar on the chart to read Brooks&#39; note.</div></div>
 </div>
 <aside class=notelist id=notelist></aside>
</div>
<div class=zov id=zov><div class=zbar><button class=zbtn id=zout>&minus;</button><button class=zbtn id=zin>+</button><button class=zbtn id=zfit>&#10530;</button><button class=zbtn id=zx>&times;</button></div><img id=zimg></div>
<script>
const D=__DATA__;const IMG="data:image/jpeg;base64,__IMG__";
const cb=document.getElementById("cb"),hl=document.getElementById("hl"),bn=document.getElementById("bn"),bt=document.getElementById("bt"),sub=document.getElementById("sub");
const chart=document.getElementById("chart");chart.src=IMG;
sub.textContent=D.date+" · "+D.bars.length+" commented bars of "+D.geom.bars;
document.getElementById("toollink").href=D.tool;
const map={};D.bars.forEach(b=>map[b.n]=b.t);const ns=D.bars.map(b=>b.n);let sel=null;
// D.barx[i] = measured center of bar i+1 (fraction of image width, wick-snapped).
function nearestNoted(n){return ns.reduce((a,b)=>Math.abs(b-n)<Math.abs(a-n)?b:a,ns[0]);}
let stripeOn=true;
function setStripe(on){stripeOn=on;hl.style.display=on?"":"none";
 document.getElementById("stripe").innerHTML="&#9635; Stripe: "+(on?"ON":"OFF");}
document.getElementById("stripe").onclick=()=>setStripe(!stripeOn);
let splitOn=false;
function setLayout(split){splitOn=split;document.body.classList.toggle("split",split);
 document.getElementById("layout").innerHTML="&#9707; Layout: "+(split?"Split":"Hover");}
document.getElementById("layout").onclick=()=>setLayout(!splitOn);
document.addEventListener("keydown",e=>{if(e.key=="s"||e.key=="S")setStripe(!stripeOn);
 if(e.key=="l"||e.key=="L")setLayout(!splitOn);});
const nl=document.getElementById("notelist"),cards={};
D.bars.forEach(b=>{const c=document.createElement("div");c.className="card";
 c.innerHTML="<div class=bn>Bar "+b.n+"</div><div class=bt></div>";
 c.querySelector(".bt").textContent=b.t;c.onclick=()=>show(b.n);cards[b.n]=c;nl.appendChild(c);});
function show(n){const w=cb.clientWidth,c=D.barx[n-1]*w,bw=Math.max(D.incf*w,7);
 hl.style.left=(c-bw/2)+"px";hl.style.width=bw+"px";
 const m=map[n]?n:nearestNoted(n);
 if(map[n]){bn.innerHTML="Bar "+n;bt.style.opacity=1;bt.textContent=map[n];}
 else{bn.innerHTML="Bar "+n+" &mdash; no note &middot; nearest noted: Bar "+m;
  bt.style.opacity=.55;bt.textContent=map[m];}
 nl.querySelectorAll(".card.sel").forEach(x=>x.classList.remove("sel"));
 if(cards[m]){cards[m].classList.add("sel");
  if(splitOn)cards[m].scrollIntoView({block:"nearest",behavior:"smooth"});}
 sel=n;}
cb.addEventListener("mousemove",e=>{const f=e.offsetX/cb.clientWidth;
 let best=1,bd=9;D.barx.forEach((x,i)=>{const d=Math.abs(x-f);if(d<bd){bd=d;best=i+1;}});
 show(best);});
document.getElementById("next").onclick=()=>{const c=sel??0;show(ns.find(n=>n>c)??ns[ns.length-1]);};
document.getElementById("prev").onclick=()=>{const c=sel??D.geom.bars+1;const p=[...ns].reverse().find(n=>n<c);show(p??ns[0]);};
document.addEventListener("keydown",e=>{if(e.key=="ArrowRight")next.click();if(e.key=="ArrowLeft")prev.click();});
const zov=document.getElementById("zov"),zimg=document.getElementById("zimg");let Z={s:1,x:0,y:0,d:false,px:0,py:0};
function zfit(){const iw=zimg.naturalWidth,ih=zimg.naturalHeight,W=innerWidth,H=innerHeight;Z.s=Math.min(W/iw,H/ih)*0.98;Z.x=(W-iw*Z.s)/2;Z.y=(H-ih*Z.s)/2;zap();}
function zap(){zimg.style.transform="translate("+Z.x+"px,"+Z.y+"px) scale("+Z.s+")";}
function zat(cx,cy,f){const s2=Math.max(0.1,Math.min(9,Z.s*f));Z.x=cx-(cx-Z.x)*(s2/Z.s);Z.y=cy-(cy-Z.y)*(s2/Z.s);Z.s=s2;zap();}
document.getElementById("zoom").onclick=()=>{zimg.src=IMG;zov.classList.add("on");zimg.onload=zfit;if(zimg.complete)zfit();};
zov.addEventListener("wheel",e=>{e.preventDefault();zat(e.clientX,e.clientY,e.deltaY<0?1.15:0.87);},{passive:false});
zimg.addEventListener("mousedown",e=>{Z.d=true;Z.px=e.clientX;Z.py=e.clientY;zimg.style.cursor="grabbing";});
window.addEventListener("mousemove",e=>{if(!Z.d)return;Z.x+=e.clientX-Z.px;Z.y+=e.clientY-Z.py;Z.px=e.clientX;Z.py=e.clientY;zap();});
window.addEventListener("mouseup",()=>{Z.d=false;zimg.style.cursor="grab";});
document.getElementById("zin").onclick=()=>zat(innerWidth/2,innerHeight/2,1.3);
document.getElementById("zout").onclick=()=>zat(innerWidth/2,innerHeight/2,0.77);
document.getElementById("zfit").onclick=zfit;
document.getElementById("zx").onclick=()=>zov.classList.remove("on");
document.addEventListener("keydown",e=>{if(e.key=="Escape")zov.classList.remove("on");});
show(ns[0]);
</script></body></html>'''
out = TMPL.replace('__DATA__', json.dumps(DATA, ensure_ascii=False)).replace('__IMG__', b64)
dst = os.path.join(SCR, 'codex_bbb_view.html')
open(dst, 'w', encoding='utf-8').write(out)
print('rebuilt', dst, '-', len(bars), 'bars')
