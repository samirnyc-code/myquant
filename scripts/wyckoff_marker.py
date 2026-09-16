"""wyckoff_marker.py — interactive click-to-mark box tool (AR, TR, springs, phases).

You click the START and END of a move; the tool SNAPS each click to the nearest of that bar's
{high, low, open, close} (extreme or body, whichever is closer to where you clicked) and draws
the box. Read the exact levels off the panel, or send me a screenshot — I set the tools to your
marks. Multiple boxes; switch timeframe; toggle snap; undo/reset.

Generates a self-contained HTML with the bar data embedded (opens in your browser, no server).

    python scripts/wyckoff_marker.py --day 2026-09-15
    python scripts/wyckoff_marker.py --day 2026-09-15 --tfs eth:2000t,eth:5min,rth:2000t,rth:5min
"""
from __future__ import annotations

import argparse
import json
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
import sys
sys.path.insert(0, str(ROOT))
import tickdata as td
from wyckoff_ar import hilo_bars

OUT = ROOT / "data" / "l1_tape" / "_analysis"

HTML = r"""<!doctype html><html><head><meta charset="utf-8"><title>Wyckoff Marker __DAY__</title>
<style>
 body{margin:0;font:13px system-ui,Arial;background:#0f1216;color:#e6e6e6}
 #bar{padding:8px 12px;background:#171b21;display:flex;gap:8px;align-items:center;flex-wrap:wrap;position:sticky;top:0}
 button,select{background:#232a33;color:#e6e6e6;border:1px solid #3a4552;border-radius:5px;padding:5px 10px;cursor:pointer}
 button:hover{background:#2c3742}
 button.on{background:#1e88e5;border-color:#1e88e5}
 #read{margin-left:auto;font-family:ui-monospace,Consolas,monospace;font-size:12px;white-space:pre;color:#9fd0ff}
 #wrap{position:relative}
 canvas{display:block;cursor:crosshair}
 #hint{color:#8ea1b5;font-size:12px}
</style></head><body>
<div id="bar">
  <span id="hint">click START then END of a move → snapped box. </span>
  <span>TF:</span><select id="tf"></select>
  <button id="snap" class="on">snap: ON</button>
  <button id="undo">undo box</button>
  <button id="reset">reset</button>
  <button id="copy">copy levels</button>
  <span id="read"></span>
</div>
<div id="wrap"><canvas id="c"></canvas></div>
<script>
const DATA = __DATA__;
const TFS = Object.keys(DATA);
let cur = TFS[0], snap = true, pending = null, boxes = [];
const cv = document.getElementById('c'), ctx = cv.getContext('2d');
const tfSel = document.getElementById('tf');
TFS.forEach(t=>{const o=document.createElement('option');o.value=t;o.textContent=t;tfSel.appendChild(o)});
const padL=64, padR=16, padT=16, padB=28;
let W,H,bars,pmin,pmax;

function layout(){
  bars = DATA[cur];
  W = Math.max(900, bars.length*7 + padL+padR);
  H = Math.min(820, Math.max(480, window.innerHeight-70));
  cv.width=W; cv.height=H;
  let lo=1e9,hi=-1e9; for(const b of bars){lo=Math.min(lo,b.l);hi=Math.max(hi,b.h);}
  const pad=(hi-lo)*0.04; pmin=lo-pad; pmax=hi+pad;
}
const bw = ()=> (W-padL-padR)/bars.length;
const xOf = i => padL + (i+0.5)*bw();
const yOf = p => padT + (pmax-p)/(pmax-pmin)*(H-padT-padB);
const pOf = y => pmax - (y-padT)/(H-padT-padB)*(pmax-pmin);
const iOf = x => Math.max(0, Math.min(bars.length-1, Math.round((x-padL)/bw()-0.5)));

function draw(){
  ctx.clearRect(0,0,W,H); ctx.fillStyle='#0f1216'; ctx.fillRect(0,0,W,H);
  // price grid
  ctx.strokeStyle='#1e2732'; ctx.fillStyle='#6b7c8f'; ctx.font='11px monospace'; ctx.textAlign='right';
  const step = niceStep((pmax-pmin)/8);
  for(let p=Math.ceil(pmin/step)*step;p<pmax;p+=step){const y=yOf(p);ctx.beginPath();ctx.moveTo(padL,y);ctx.lineTo(W-padR,y);ctx.stroke();ctx.fillText(p.toFixed(2),padL-6,y+3);}
  // candles
  const w=Math.max(2,bw()*0.6);
  for(let i=0;i<bars.length;i++){const b=bars[i],x=xOf(i),up=b.c>=b.o;ctx.strokeStyle=up?'#26a69a':'#ef5350';ctx.fillStyle=up?'#26a69a':'#ef5350';
    ctx.beginPath();ctx.moveTo(x,yOf(b.h));ctx.lineTo(x,yOf(b.l));ctx.stroke();
    const y0=yOf(Math.max(b.o,b.c)),y1=yOf(Math.min(b.o,b.c));ctx.fillRect(x-w/2,y0,w,Math.max(1,y1-y0));}
  // boxes
  boxes.forEach((bx,k)=>drawBox(bx,k+1));
  if(pending){const x=xOf(pending.i),y=yOf(pending.p);ctx.fillStyle='#ffd54f';ctx.beginPath();ctx.arc(x,y,4,0,7);ctx.fill();}
}
function drawBox(bx,n){
  const x0=xOf(bx.a.i),x1=xOf(bx.b.i),y0=yOf(bx.a.p),y1=yOf(bx.b.p);
  const L=Math.min(x0,x1),R=Math.max(x0,x1),T=Math.min(y0,y1),B=Math.max(y0,y1);
  ctx.fillStyle='rgba(30,136,229,0.14)';ctx.fillRect(L,T,R-L,B-T);
  ctx.strokeStyle='#1e88e5';ctx.lineWidth=1.5;ctx.strokeRect(L,T,R-L,B-T);
  ctx.fillStyle='#9fd0ff';ctx.font='12px monospace';ctx.textAlign='left';
  ctx.fillText('box'+n+'  '+Math.abs(bx.a.p-bx.b.p).toFixed(2)+'pt',L+4,T-4);
  [bx.a,bx.b].forEach(pt=>{ctx.fillStyle='#ffd54f';ctx.beginPath();ctx.arc(xOf(pt.i),yOf(pt.p),3,0,7);ctx.fill();});
}
function niceStep(x){const p=Math.pow(10,Math.floor(Math.log10(x)));const m=x/p;return (m<1.5?1:m<3?2:m<7?5:10)*p;}

function snapClick(x,y){
  const i=iOf(x); const b=bars[i]; const pc=pOf(y);
  if(!snap) return {i, p:+pc.toFixed(2), k:'raw'};
  const cand=[['H',b.h],['L',b.l],['O',b.o],['C',b.c]];
  cand.sort((u,v)=>Math.abs(u[1]-pc)-Math.abs(v[1]-pc));
  return {i, p:cand[0][1], k:cand[0][0]};
}
cv.addEventListener('click',e=>{
  const r=cv.getBoundingClientRect();const pt=snapClick(e.clientX-r.left,e.clientY-r.top);
  if(!pending){pending=pt;} else {boxes.push({a:pending,b:pt});pending=null;} draw();readout();
});
function fmt(pt){return bars[pt.i].t+' '+pt.p.toFixed(2)+'('+pt.k+')';}
function readout(){
  let s=boxes.map((b,k)=>'box'+(k+1)+': '+fmt(b.a)+' -> '+fmt(b.b)+'  ='+Math.abs(b.a.p-b.b.p).toFixed(2)+'pt').join('\n');
  if(pending) s+=(s?'\n':'')+'start: '+fmt(pending)+'  (click END)';
  document.getElementById('read').textContent=s||'no boxes yet';
}
document.getElementById('snap').onclick=e=>{snap=!snap;e.target.textContent='snap: '+(snap?'ON':'OFF');e.target.classList.toggle('on',snap);};
document.getElementById('undo').onclick=()=>{boxes.pop();draw();readout();};
document.getElementById('reset').onclick=()=>{boxes=[];pending=null;draw();readout();};
document.getElementById('copy').onclick=()=>{navigator.clipboard.writeText(document.getElementById('read').textContent);};
tfSel.onchange=e=>{cur=e.target.value;boxes=[];pending=null;layout();draw();readout();};
window.onresize=()=>{layout();draw();};
layout();draw();readout();
</script></body></html>"""


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--day", default="2026-09-15")
    ap.add_argument("--tfs", default="eth:2000t,eth:5min,rth:2000t,rth:5min")
    a = ap.parse_args()

    data = {}
    for spec in a.tfs.split(","):
        sess, tf = spec.split(":")
        raw = td.load_eth(a.day) if sess == "eth" else td.load_rth(a.day)
        b = hilo_bars(raw, tf)
        rows = []
        for t, r in b.iterrows():
            rows.append({"t": __import__("pandas").Timestamp(t).strftime("%H:%M"),
                         "o": round(float(r["open"]), 2), "h": round(float(r["high"]), 2),
                         "l": round(float(r["low"]), 2), "c": round(float(r["close"]), 2)})
        data[spec] = rows

    OUT.mkdir(parents=True, exist_ok=True)
    html = HTML.replace("__DATA__", json.dumps(data)).replace("__DAY__", a.day)
    path = OUT / f"marker_{a.day}.html"
    path.write_text(html, encoding="utf-8")
    print(f"marker: {path}")
    print("Opening in your browser — click AR start then AR end; it snaps to the nearest")
    print("extreme/body. Read the levels off the top-right, or screenshot it back to me.")
    try:
        subprocess.Popen(["cmd", "/c", "start", "", str(path)], shell=False)
    except Exception:
        pass
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
