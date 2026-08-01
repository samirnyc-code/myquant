"""Interactive Halsey Fib tool (standalone). Draw measured-move fibs on ES by clicking
the two swing anchors; all levels (100/61.8/50/38.2/0/123.6) draw with consistent colors.
Fibs are stored as price levels + a time anchor, so they PERSIST across reloads and show
on every timeframe (a Daily fib shows on 15M/5M). Each fib's status (in play / target hit /
failed) is auto-tracked from 5-minute price since it was drawn.

Run:  python eminiaddict/scripts/fib_tool.py   ->  http://localhost:8641
All timeframes derive from one 5m RTH source so price scales align across TFs.
"""
import json
import pathlib
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import pandas as pd

ROOT = pathlib.Path(__file__).resolve().parents[2]
PORT = 8641
FIBS_FILE = ROOT / "eminiaddict" / "data" / "fibs.json"
_SRC = pd.read_parquet(ROOT / "data" / "bars" / "_db_es_5m_rth.parquet")

# derive all timeframes from the 5m RTH source (consistent price scale)
def _resample(rule):
    if rule == "5m":
        d = _SRC.copy()
    else:
        d = (_SRC.set_index("DateTime").resample(rule)
             .agg({"Open": "first", "High": "max", "Low": "min",
                   "Close": "last", "Volume": "sum"}).dropna().reset_index())
    d["t"] = (d["DateTime"].astype("int64") // 1_000_000)  # ms epoch
    return d

TF = {"5m": _resample("5m"), "15m": _resample("15min"), "1D": _resample("1D")}
for k, d in TF.items():
    print(f"{k}: {len(d)} bars {d.DateTime.iloc[0].date()}..{d.DateTime.iloc[-1].date()}")

_5 = TF["5m"]
_5t = _5["t"].values
_5H = _5["High"].values
_5L = _5["Low"].values


def levels(a, b):
    """a=100% anchor price, b=0% anchor price. Returns dict of level->price."""
    d = b - a
    return {"100": a, "61.8": a + 0.382 * d, "50": a + 0.5 * d,
            "38.2": a + 0.618 * d, "0": b, "123.6": b + 0.236 * d}


def status(fib):
    """in_play / target / failed, from 5m bars after the fib's 0% anchor time."""
    lv = levels(fib["a"], fib["b"])
    up = fib["b"] > fib["a"]
    fail, tgt = lv["61.8"], lv["123.6"]
    t0 = fib.get("t", 0)
    import numpy as np
    idx = np.searchsorted(_5t, t0, side="right")
    for j in range(idx, len(_5t)):
        if up:
            if _5L[j] < fail:
                return "failed"
            if _5H[j] >= tgt:
                return "target"
        else:
            if _5H[j] > fail:
                return "failed"
            if _5L[j] <= tgt:
                return "target"
    return "in_play"


def load_fibs():
    if FIBS_FILE.exists():
        try:
            return json.loads(FIBS_FILE.read_text())
        except Exception:
            return []
    return []


def save_fibs(fibs):
    FIBS_FILE.parent.mkdir(parents=True, exist_ok=True)
    FIBS_FILE.write_text(json.dumps(fibs, indent=1))


def bars_json(tf, off, n):
    d = TF[tf]
    end = len(d) - off
    start = max(0, end - n)
    sl = d.iloc[start:end]
    return {"tf": tf, "off": off, "total": len(d),
            "bars": [[int(t), float(o), float(h), float(l), float(c)]
                     for t, o, h, l, c in zip(sl.t, sl.Open, sl.High, sl.Low, sl.Close)]}


HTML = r"""<!doctype html><html><head><meta charset=utf-8><title>Halsey Fib Tool</title>
<style>
:root{--bg:#0d1117;--pan:#161b22;--chip:#30363d;--fg:#e6edf3;--mut:#8b949e;--blue:#58a6ff}
*{box-sizing:border-box}html,body{margin:0;height:100%;background:var(--bg);color:var(--fg);
 font:13px -apple-system,Segoe UI,Roboto,sans-serif;overflow:hidden}
#top{display:flex;align-items:center;gap:8px;padding:7px 12px;border-bottom:1px solid var(--chip)}
.tf{padding:5px 12px;border:1px solid var(--chip);border-radius:7px;cursor:pointer;font-weight:600;
 color:var(--mut);background:var(--pan)}.tf.on{color:var(--blue);border-color:var(--blue);background:#58a6ff14}
.btn{padding:5px 11px;border:1px solid var(--chip);border-radius:7px;cursor:pointer;background:var(--pan);color:var(--fg);font-weight:600}
.btn.arm{border-color:#e3b341;color:#e3b341;background:#e3b34114}
#wrap{display:flex;height:calc(100% - 42px)}
#c{flex:1;display:block;cursor:crosshair}
#side{width:290px;border-left:1px solid var(--chip);overflow:auto;padding:10px;background:var(--pan)}
h4{margin:6px 0;font-size:12px;color:var(--mut);text-transform:uppercase;letter-spacing:.04em}
.fib{border:1px solid var(--chip);border-radius:8px;padding:7px 9px;margin:6px 0;font-size:12px}
.fib .r1{display:flex;justify-content:space-between;align-items:center;gap:6px}
.badge{font-size:10.5px;font-weight:700;padding:1px 7px;border-radius:999px}
.b-in_play{background:#58a6ff22;color:#58a6ff}.b-target{background:#3fb95022;color:#3fb950}
.b-failed{background:#f8514922;color:#f85149}
.mini{color:var(--mut);font-size:10.5px;margin-top:3px;font-family:ui-monospace,Consolas,monospace}
.x{cursor:pointer;color:var(--mut)}.x:hover{color:#f85149}
.eye{cursor:pointer}.lvrow{display:flex;align-items:center;gap:6px;font-size:11.5px;margin:2px 0}
.sw{width:11px;height:11px;border-radius:2px;display:inline-block}
.hint{color:var(--mut);font-size:11px;margin:8px 0}
</style></head><body>
<div id=top>
 <b>Halsey Fib Tool</b>
 <span class=tf data-tf=5m onclick="setTf('5m')">5M</span>
 <span class="tf on" data-tf=15m onclick="setTf('15m')">15M</span>
 <span class=tf data-tf=1D onclick="setTf('1D')">1D</span>
 <span id=draw class=btn onclick="toggleDraw()">✎ Draw fib</span>
 <span id=emabtn class="btn arm" onclick="toggleEma()">EMA 8/21</span>
 <span class=btn onclick="loadOlder()">◀ older</span>
 <span class=btn onclick="loadNewer()">newer ▶</span>
 <span id=stat style="margin-left:auto;color:var(--mut)"></span>
</div>
<div id=wrap><canvas id=c></canvas>
 <div id=side>
  <h4>Levels (consistent colors)</h4><div id=lvls></div>
  <h4>Fibs <span id=fcount class=mini></span></h4><div id=fibs></div>
  <p class=hint>Click <b>✎ Draw fib</b>, then click the <b>start</b> (100%) swing, then the
   <b>end</b> (0%) swing. Fibs persist and show on every timeframe. Drag = pan, wheel = zoom.</p>
 </div>
</div>
<script>
var TF='15m', OFF=0, N=900, BARS=[], VIEW={i0:0,i1:0}, FIBS=[], DRAW=false, pend=null, DPR=devicePixelRatio||1, EMAON=true;
function toggleEma(){EMAON=!EMAON;document.getElementById('emabtn').classList.toggle('arm',EMAON);draw();}
var LV=[['100','#8a8f98',':'],['61.8','#e2453c','-'],['50','#e3b341','-'],['38.2','#e08a2b','--'],['0','#8a8f98',':'],['123.6','#26a65b','-']];
var LVON={}; LV.forEach(function(l){LVON[l[0]]=true});
var cv=document.getElementById('c'), cx=cv.getContext('2d');
function lvlprices(a,b){var d=b-a;return {'100':a,'61.8':a+.382*d,'50':a+.5*d,'38.2':a+.618*d,'0':b,'123.6':b+.236*d};}
function fmt(t){var d=new Date(t);return (d.getMonth()+1)+'/'+d.getDate()+(TF=='1D'?'/'+String(d.getFullYear()).slice(2):' '+String(d.getHours()).padStart(2,'0')+':'+String(d.getMinutes()).padStart(2,'0'));}

function resize(){var w=cv.clientWidth,h=cv.clientHeight;cv.width=w*DPR;cv.height=h*DPR;cx.setTransform(DPR,0,0,DPR,0,0);draw();}
function setTf(tf){TF=tf;OFF=0;document.querySelectorAll('.tf').forEach(function(e){e.classList.toggle('on',e.dataset.tf==tf)});fetchBars(true);}
function toggleDraw(){DRAW=!DRAW;pend=null;document.getElementById('draw').classList.toggle('arm',DRAW);}
function loadOlder(){OFF+=Math.floor(N*0.7);fetchBars(true);}
function loadNewer(){OFF=Math.max(0,OFF-Math.floor(N*0.7));fetchBars(true);}

function fetchBars(reset){fetch('/bars?tf='+TF+'&off='+OFF+'&n='+N).then(function(r){return r.json()}).then(function(j){
 BARS=j.bars; if(reset){VIEW.i0=0;VIEW.i1=BARS.length-1;} document.getElementById('stat').textContent=TF+'  '+(j.total)+' bars  ('+BARS.length+' shown)'; draw();});}
function fetchFibs(){fetch('/fibs').then(function(r){return r.json()}).then(function(j){FIBS=j;renderSide();draw();});}
function saveFibs(){fetch('/fibs',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(FIBS)}).then(function(r){return r.json()}).then(function(j){FIBS=j;renderSide();draw();});}

var pad={l:8,r:66,t:10,b:22};
function plot(){var w=cv.clientWidth,h=cv.clientHeight;var i0=Math.max(0,Math.floor(VIEW.i0)),i1=Math.min(BARS.length-1,Math.ceil(VIEW.i1));
 var lo=1e18,hi=-1e18;for(var i=i0;i<=i1;i++){if(BARS[i][3]<lo)lo=BARS[i][3];if(BARS[i][2]>hi)hi=BARS[i][2];}
 // include on-screen fib levels in the scale a little
 var pr=hi-lo||1;lo-=pr*0.04;hi+=pr*0.05;
 var gw=w-pad.l-pad.r, gh=h-pad.t-pad.b, nb=(i1-i0+1);
 return {w:w,h:h,i0:i0,i1:i1,lo:lo,hi:hi,gw:gw,gh:gh,nb:nb,
  x:function(i){return pad.l+(i-i0+0.5)/nb*gw;}, y:function(p){return pad.t+(hi-p)/(hi-lo)*gh;},
  bw:Math.max(1.2,gw/nb*0.62), px2i:function(px){return i0+ (px-pad.l)/gw*nb -0.5;}, py2p:function(py){return hi-(py-pad.t)/gh*(hi-lo);}};}

function draw(){var w=cv.clientWidth,h=cv.clientHeight;cx.clearRect(0,0,w,h);cx.fillStyle='#0b0b0b';cx.fillRect(0,0,w,h);
 if(!BARS.length)return;var P=plot();window._P=P;
 // grid price labels
 cx.strokeStyle='#161616';cx.fillStyle='#8b949e';cx.font='10px monospace';cx.textAlign='left';
 for(var g=0;g<=5;g++){var pp=P.lo+(P.hi-P.lo)*g/5,yy=P.y(pp);cx.beginPath();cx.moveTo(pad.l,yy);cx.lineTo(w-pad.r,yy);cx.stroke();cx.fillText(pp.toFixed(2),w-pad.r+3,yy+3);}
 // candles
 for(var i=P.i0;i<=P.i1;i++){var b=BARS[i],x=P.x(i),up=b[4]>=b[1];cx.strokeStyle=up?'#26a65b':'#e2453c';cx.fillStyle=cx.strokeStyle;
  cx.beginPath();cx.moveTo(x,P.y(b[2]));cx.lineTo(x,P.y(b[3]));cx.stroke();
  var yo=P.y(b[1]),yc=P.y(b[4]);cx.fillRect(x-P.bw/2,Math.min(yo,yc),P.bw,Math.max(1,Math.abs(yc-yo)));}
 // EMA 8 (white) + EMA 21 (cyan) — Halsey's MAs
 if(EMAON){[[8,'#ededed'],[21,'#38c6d9']].forEach(function(cfg){var nn=cfg[0],k=2/(nn+1),e=null,pts=[];
   for(var i=0;i<BARS.length;i++){var c=BARS[i][4];e=(e==null)?c:c*k+e*(1-k);if(i>=P.i0&&i<=P.i1)pts.push([P.x(i),P.y(e)]);}
   cx.strokeStyle=cfg[1];cx.lineWidth=1.3;cx.beginPath();pts.forEach(function(p,j){j?cx.lineTo(p[0],p[1]):cx.moveTo(p[0],p[1]);});cx.stroke();cx.lineWidth=1;});}
 // fibs (price-based -> show on any TF)
 FIBS.forEach(function(f){if(f.hidden)return;var pr=lvlprices(f.a,f.b);
  // x-start = bar at/after the anchor time (else left edge)
  var xs=pad.l; for(var i=P.i0;i<=P.i1;i++){if(BARS[i][0]>=f.t){xs=P.x(i);break;}}
  LV.forEach(function(l){if(!LVON[l[0]])return;var p=pr[l[0]],yy=P.y(p);if(yy<pad.t-40||yy>h-pad.b+40)return;
   cx.strokeStyle=l[1];cx.lineWidth=(l[0]=='50'||l[0]=='61.8'||l[0]=='123.6')?1.6:0.9;
   cx.setLineDash(l[2]==':'?[2,3]:l[2]=='--'?[6,4]:[]);cx.beginPath();cx.moveTo(xs,yy);cx.lineTo(w-pad.r,yy);cx.stroke();cx.setLineDash([]);
   cx.fillStyle=l[1];cx.font='10px monospace';cx.textAlign='right';cx.fillText(l[0],w-pad.r-2,yy-2);});
  cx.lineWidth=1;});
 // pending anchor
 if(pend){var yy=P.y(pend.p);cx.fillStyle='#e3b341';cx.beginPath();cx.arc(pend.x,yy,4,0,7);cx.fill();}}

// interaction
var drag=null;
cv.addEventListener('mousedown',function(e){var r=cv.getBoundingClientRect();drag={x:e.clientX-r.left,y:e.clientY-r.top,i0:VIEW.i0,i1:VIEW.i1,moved:false};});
window.addEventListener('mousemove',function(e){if(!drag)return;var r=cv.getBoundingClientRect();var dx=(e.clientX-r.left)-drag.x;
 if(Math.abs(dx)>3){drag.moved=true;if(!DRAW){var P=window._P;var di=dx/P.gw*P.nb;VIEW.i0=drag.i0-di;VIEW.i1=drag.i1-di;clampView();draw();}}});
window.addEventListener('mouseup',function(e){if(!drag)return;var r=cv.getBoundingClientRect();var px=e.clientX-r.left,py=e.clientY-r.top;
 if(DRAW && !drag.moved){onDrawClick(px,py);} drag=null;});
cv.addEventListener('wheel',function(e){e.preventDefault();var P=window._P;if(!P)return;var r=cv.getBoundingClientRect();var px=e.clientX-r.left;
 var ic=P.px2i(px);var f=e.deltaY>0?1.15:0.87;VIEW.i0=ic-(ic-VIEW.i0)*f;VIEW.i1=ic+(VIEW.i1-ic)*f;clampView();draw();},{passive:false});
function clampView(){if(VIEW.i1-VIEW.i0<6)VIEW.i1=VIEW.i0+6;if(VIEW.i0<0){VIEW.i1-=VIEW.i0;VIEW.i0=0;}if(VIEW.i1>BARS.length-1){VIEW.i0-=(VIEW.i1-(BARS.length-1));VIEW.i1=BARS.length-1;if(VIEW.i0<0)VIEW.i0=0;}}
function onDrawClick(px,py){var P=window._P;var i=Math.round(P.px2i(px));i=Math.max(0,Math.min(BARS.length-1,i));var p=P.py2p(py);
 if(!pend){pend={x:P.x(i),p:p,t:BARS[i][0]};draw();}
 else{var f={a:pend.p,b:p,t:pend.t,t2:BARS[i][0],tf:TF,hidden:false};pend=null;FIBS.push(f);DRAW=false;document.getElementById('draw').classList.remove('arm');saveFibs();}}

function renderSide(){
 document.getElementById('lvls').innerHTML=LV.map(function(l){return '<div class=lvrow><span class=eye onclick="togLv(\''+l[0]+'\')">'+(LVON[l[0]]?'☑':'☐')+'</span><span class=sw style="background:'+l[1]+'"></span>'+l[0]+'%</div>';}).join('');
 document.getElementById('fcount').textContent='('+FIBS.length+')';
 document.getElementById('fibs').innerHTML=FIBS.map(function(f,k){var up=f.b>f.a,pr=lvlprices(f.a,f.b);var st=f.status||'in_play';
  return '<div class=fib><div class=r1><b>#'+(k+1)+' '+(up?'▲ long':'▼ short')+' <span class=mini>'+f.tf+'</span></b>'
   +'<span><span class="badge b-'+st+'">'+st.replace('_',' ')+'</span> <span class=eye onclick="togFib('+k+')">'+(f.hidden?'☐':'☑')+'</span> <span class=x onclick="delFib('+k+')">✕</span></span></div>'
   +'<div class=mini>50 '+pr['50'].toFixed(2)+'  ·  61.8 '+pr['61.8'].toFixed(2)+'  ·  123.6 '+pr['123.6'].toFixed(2)+'</div></div>';}).join('');}
function togLv(k){LVON[k]=!LVON[k];renderSide();draw();}
function togFib(k){FIBS[k].hidden=!FIBS[k].hidden;saveFibs();}
function delFib(k){FIBS.splice(k,1);saveFibs();}

window.addEventListener('resize',resize);
fetchFibs();fetchBars(true);setTimeout(resize,60);
</script></body></html>"""


class H(BaseHTTPRequestHandler):
    def log_message(self, *a):
        pass

    def _send(self, body, ctype="application/json", code=200):
        b = body.encode() if isinstance(body, str) else body
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(b)))
        self.end_headers()
        self.wfile.write(b)

    def do_GET(self):
        from urllib.parse import urlparse, parse_qs
        u = urlparse(self.path)
        if u.path == "/":
            return self._send(HTML, "text/html; charset=utf-8")
        if u.path == "/bars":
            q = parse_qs(u.query)
            tf = q.get("tf", ["15m"])[0]
            off = int(q.get("off", ["0"])[0])
            n = int(q.get("n", ["900"])[0])
            return self._send(json.dumps(bars_json(tf, off, min(n, 3000))))
        if u.path == "/fibs":
            fibs = load_fibs()
            for f in fibs:
                f["status"] = status(f)
            return self._send(json.dumps(fibs))
        return self._send("not found", "text/plain", 404)

    def do_POST(self):
        if self.path == "/fibs":
            n = int(self.headers.get("Content-Length", 0))
            fibs = json.loads(self.rfile.read(n) or b"[]")
            save_fibs(fibs)
            for f in fibs:
                f["status"] = status(f)
            return self._send(json.dumps(fibs))
        return self._send("not found", "text/plain", 404)


if __name__ == "__main__":
    print(f"Halsey Fib Tool  ->  http://localhost:{PORT}")
    ThreadingHTTPServer(("127.0.0.1", PORT), H).serve_forever()
