"""wyckoff_marker.py — interactive click-to-mark box tool (AR, TR, springs, phases).

Click the START and END of a move; each click SNAPS to the nearest of that bar's extremes/
bodies (candles: high/low/open/close; renko: brick top/bottom + wick hi/lo) and draws a box
that EXTENDS RIGHT to EOD. Three stacked panels on one clock: PRICE (+ Weis zigzag skeleton),
per-bar VOLUME, and the WEIS WAVE (per-swing cumulative volume) — so you can see where effort
fades and place the AR end there. Candle AND renko views; multiple boxes; snap toggle; undo/reset.

Self-contained HTML with the data embedded (opens in your browser, no server).

    python scripts/wyckoff_marker.py --day 2026-09-15
"""
from __future__ import annotations

import argparse
import json
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
import sys
sys.path.insert(0, str(ROOT))
import pandas as pd
import tickdata as td
from wyckoff_ar import hilo_bars
from weis_wave import zigzag
from renko import build_renko

OUT = ROOT / "data" / "l1_tape" / "_analysis"

HTML = r"""<!doctype html><html><head><meta charset="utf-8"><title>Wyckoff Marker __DAY__</title>
<style>
 body{margin:0;font:13px system-ui,Arial;background:#0f1216;color:#e6e6e6}
 #bar{padding:8px 12px;background:#171b21;display:flex;gap:8px;align-items:center;flex-wrap:wrap;position:sticky;top:0;z-index:5}
 button,select{background:#232a33;color:#e6e6e6;border:1px solid #3a4552;border-radius:5px;padding:5px 10px;cursor:pointer}
 button:hover{background:#2c3742}
 button.on{background:#1e88e5;border-color:#1e88e5}
 #read{margin-left:auto;font-family:ui-monospace,Consolas,monospace;font-size:12px;white-space:pre;color:#9fd0ff}
 #wrap{position:relative;overflow-x:auto}
 canvas{display:block;cursor:crosshair}
 #hint{color:#8ea1b5;font-size:12px}
</style></head><body>
<div id="bar">
  <span id="hint">click START then END on the PRICE panel → box snaps + extends to EOD. </span>
  <span>view:</span><select id="tf"></select>
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
let cur=TFS[0], snap=true, pending=null, boxes=[];
const cv=document.getElementById('c'), ctx=cv.getContext('2d');
const tfSel=document.getElementById('tf');
TFS.forEach(t=>{const o=document.createElement('option');o.value=t;o.textContent=t;tfSel.appendChild(o)});
const padL=64,padR=16,padT=14,padB=24;
let W,H,ds,bars,sw,pmin,pmax,isRenko,brick,volMax,swMax;
let pTop,pBot,vTop,vBot,wTop,wBot;

function layout(){
  ds=DATA[cur]; bars=ds.bars; sw=ds.swings; isRenko=ds.type==='renko'; brick=ds.brick||0;
  W=Math.max(1000, bars.length*(isRenko?10:7)+padL+padR);
  H=Math.min(880,Math.max(560,window.innerHeight-70)); cv.width=W; cv.height=H;
  let lo=1e9,hi=-1e9,vm=0;
  for(const b of bars){ if(isRenko){lo=Math.min(lo,b.wlo,b.bottom);hi=Math.max(hi,b.whi,b.top);}else{lo=Math.min(lo,b.l);hi=Math.max(hi,b.h);} vm=Math.max(vm,b.v);}
  const pad=(hi-lo)*0.04; pmin=lo-pad; pmax=hi+pad; volMax=vm||1; swMax=Math.max(1,...sw.map(s=>s.vol));
  const gTop=padT,gBot=H-padB,gH=gBot-gTop,gap=gH*0.03;
  pTop=gTop; pBot=gTop+gH*0.55; vTop=pBot+gap; vBot=vTop+gH*0.17; wTop=vBot+gap; wBot=gBot;
}
const bw=()=>(W-padL-padR)/bars.length;
const xOf=i=>padL+(i+0.5)*bw();
const yOf=p=>pTop+(pmax-p)/(pmax-pmin)*(pBot-pTop);
const pOf=y=>pmax-(y-pTop)/(pBot-pTop)*(pmax-pmin);
const iOf=x=>Math.max(0,Math.min(bars.length-1,Math.round((x-padL)/bw()-0.5)));

function draw(){
  ctx.clearRect(0,0,W,H);ctx.fillStyle='#0f1216';ctx.fillRect(0,0,W,H);
  // price grid + labels
  ctx.strokeStyle='#1e2732';ctx.fillStyle='#6b7c8f';ctx.font='11px monospace';ctx.textAlign='right';
  const step=niceStep((pmax-pmin)/8);
  for(let p=Math.ceil(pmin/step)*step;p<pmax;p+=step){const y=yOf(p);ctx.beginPath();ctx.moveTo(padL,y);ctx.lineTo(W-padR,y);ctx.stroke();ctx.fillText(p.toFixed(2),padL-6,y+3);}
  const w=Math.max(2,bw()*0.6);
  // candles/renko
  for(let i=0;i<bars.length;i++){const b=bars[i],x=xOf(i);
    if(isRenko){const up=b.dir==='up';ctx.strokeStyle='#455a64';ctx.beginPath();ctx.moveTo(x,yOf(b.whi));ctx.lineTo(x,yOf(b.wlo));ctx.stroke();
      ctx.fillStyle=up?'#26a69a':'#ef5350';ctx.fillRect(x-w/2,yOf(b.top),w,yOf(b.bottom)-yOf(b.top));}
    else{const up=b.c>=b.o;ctx.strokeStyle=up?'#26a69a':'#ef5350';ctx.fillStyle=up?'#26a69a':'#ef5350';
      ctx.beginPath();ctx.moveTo(x,yOf(b.h));ctx.lineTo(x,yOf(b.l));ctx.stroke();
      const y0=yOf(Math.max(b.o,b.c)),y1=yOf(Math.min(b.o,b.c));ctx.fillRect(x-w/2,y0,w,Math.max(1,y1-y0));}}
  // Weis zigzag skeleton on price
  ctx.strokeStyle='#5b8def';ctx.lineWidth=1.3;ctx.beginPath();
  sw.forEach((s,k)=>{const x0=xOf(s.i0),y0=yOf(pAt(s.i0,s.dir==='up'?'lo':'hi'));if(k===0)ctx.moveTo(x0,y0);const x1=xOf(s.i1),y1=yOf(pAt(s.i1,s.dir==='up'?'hi':'lo'));ctx.lineTo(x1,y1);});
  ctx.stroke();ctx.lineWidth=1;
  // per-bar volume panel
  panelLabel('volume',vTop);
  for(let i=0;i<bars.length;i++){const b=bars[i],x=xOf(i),h=(b.v/volMax)*(vBot-vTop);const up=isRenko?b.dir==='up':b.c>=b.o;ctx.fillStyle=up?'#2e7d6b':'#b5514f';ctx.fillRect(x-w/2,vBot-h,w,h);}
  // Weis wave panel (per-swing cumulative volume)
  panelLabel('weis wave',wTop);
  sw.forEach((s,k)=>{const x0=xOf(s.i0),x1=xOf(s.i1),h=(s.vol/swMax)*(wBot-wTop);ctx.fillStyle=s.dir==='up'?'rgba(38,166,154,0.8)':'rgba(239,83,80,0.8)';ctx.fillRect(Math.min(x0,x1)-w/2,wBot-h,Math.max(w,Math.abs(x1-x0)+w),h);
    if(bw()>6){ctx.fillStyle='#cfd8dc';ctx.font='9px monospace';ctx.textAlign='center';ctx.fillText((s.vol/1000).toFixed(0)+'k',(x0+x1)/2,wBot-h-2);}});
  // boxes
  boxes.forEach((bx,k)=>drawBox(bx,k+1));
  if(pending){const x=xOf(pending.i),y=yOf(pending.p);ctx.fillStyle='#ffd54f';ctx.beginPath();ctx.arc(x,y,4,0,7);ctx.fill();}
}
function pAt(i,which){const b=bars[i];if(isRenko)return which==='hi'?b.whi:b.wlo;return which==='hi'?b.h:b.l;}
function panelLabel(t,y){ctx.fillStyle='#5c6b7a';ctx.font='10px monospace';ctx.textAlign='left';ctx.fillText(t,padL+2,y+10);}
function drawBox(bx,n){
  const L=xOf(Math.min(bx.a.i,bx.b.i)),R=W-padR,T=yOf(Math.max(bx.a.p,bx.b.p)),B=yOf(Math.min(bx.a.p,bx.b.p));
  ctx.fillStyle='rgba(30,136,229,0.14)';ctx.fillRect(L,T,R-L,B-T);
  ctx.strokeStyle='#1e88e5';ctx.lineWidth=1.5;ctx.strokeRect(L,T,R-L,B-T);
  ctx.setLineDash([5,4]);ctx.beginPath();ctx.moveTo(L,T);ctx.lineTo(R,T);ctx.moveTo(L,B);ctx.lineTo(R,B);ctx.stroke();ctx.setLineDash([]);
  ctx.fillStyle='#9fd0ff';ctx.font='12px monospace';ctx.textAlign='left';ctx.fillText('box'+n+'  '+Math.abs(bx.a.p-bx.b.p).toFixed(2)+'pt',L+4,T-4);
  [bx.a,bx.b].forEach(pt=>{ctx.fillStyle='#ffd54f';ctx.beginPath();ctx.arc(xOf(pt.i),yOf(pt.p),3,0,7);ctx.fill();});
}
function niceStep(x){const p=Math.pow(10,Math.floor(Math.log10(x)));const m=x/p;return (m<1.5?1:m<3?2:m<7?5:10)*p;}
function snapClick(x,y){const i=iOf(x),b=bars[i],pc=pOf(y);
  if(!snap)return{i,p:+pc.toFixed(2),k:'raw'};
  const cand=isRenko?[['T',b.top],['B',b.bottom],['wH',b.whi],['wL',b.wlo]]:[['H',b.h],['L',b.l],['O',b.o],['C',b.c]];
  cand.sort((u,v)=>Math.abs(u[1]-pc)-Math.abs(v[1]-pc));return{i,p:cand[0][1],k:cand[0][0]};}
cv.addEventListener('click',e=>{const r=cv.getBoundingClientRect();const y=e.clientY-r.top;if(y>pBot)return;
  const pt=snapClick(e.clientX-r.left,y);if(!pending){pending=pt;}else{boxes.push({a:pending,b:pt});pending=null;}draw();readout();});
function fmt(pt){return bars[pt.i].t+' '+pt.p.toFixed(2)+'('+pt.k+')';}
function readout(){let s=boxes.map((b,k)=>'box'+(k+1)+': '+fmt(b.a)+' -> '+fmt(b.b)+'  ='+Math.abs(b.a.p-b.b.p).toFixed(2)+'pt').join('\n');
  if(pending)s+=(s?'\n':'')+'start: '+fmt(pending)+'  (click END)';document.getElementById('read').textContent=s||'no boxes yet';}
document.getElementById('snap').onclick=e=>{snap=!snap;e.target.textContent='snap: '+(snap?'ON':'OFF');e.target.classList.toggle('on',snap);};
document.getElementById('undo').onclick=()=>{boxes.pop();draw();readout();};
document.getElementById('reset').onclick=()=>{boxes=[];pending=null;draw();readout();};
document.getElementById('copy').onclick=()=>{navigator.clipboard.writeText(document.getElementById('read').textContent);};
tfSel.onchange=e=>{cur=e.target.value;boxes=[];pending=null;layout();draw();readout();};
window.onresize=()=>{layout();draw();};
layout();draw();readout();
</script></body></html>"""


def make_swings(bars_df, is_renko, reversal=2.5):
    if is_renko:
        R = bars_df.reset_index(drop=True).copy()
        R["grp"] = (R["dir"] != R["dir"].shift()).cumsum()
        return [{"i0": int(seg.index[0]), "i1": int(seg.index[-1]), "dir": seg["dir"].iloc[0],
                 "vol": int(seg["vol"].sum())} for _, seg in R.groupby("grp")]
    prices = bars_df["close"].to_numpy()
    piv = zigzag(prices, reversal)
    out = []
    for s, e in zip(piv[:-1], piv[1:]):
        seg = bars_df.iloc[s:e + 1]
        out.append({"i0": int(s), "i1": int(e), "dir": "up" if prices[e] >= prices[s] else "dn",
                    "vol": int(seg["vol"].sum())})
    return out


def dataset(day, spec):
    sess, tf = spec.split(":")
    raw = td.load_eth(day) if sess == "eth" else td.load_rth(day)
    if tf.startswith("renko"):
        brick = float(tf.replace("renko", ""))
        R = build_renko(raw, brick)
        rows = [{"t": pd.Timestamp(r["t"]).strftime("%H:%M"), "dir": r["dir"],
                 "bottom": round(float(r["bottom"]), 2), "top": round(float(r["top"]), 2),
                 "wlo": round(float(r["wlo"]), 2), "whi": round(float(r["whi"]), 2),
                 "v": int(r["vol"])} for _, r in R.iterrows()]
        return {"type": "renko", "brick": brick, "bars": rows, "swings": make_swings(R, True)}
    b = hilo_bars(raw, tf)
    rows = [{"t": pd.Timestamp(t).strftime("%H:%M"), "o": round(float(r["open"]), 2),
             "h": round(float(r["high"]), 2), "l": round(float(r["low"]), 2),
             "c": round(float(r["close"]), 2), "v": int(r["vol"])} for t, r in b.iterrows()]
    return {"type": "candle", "bars": rows, "swings": make_swings(b, False)}


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--day", default="2026-09-15")
    ap.add_argument("--tfs", default="eth:2000t,eth:5min,eth:renko5,rth:2000t,rth:5min,rth:renko5")
    a = ap.parse_args()

    data = {spec: dataset(a.day, spec) for spec in a.tfs.split(",")}
    OUT.mkdir(parents=True, exist_ok=True)
    html = HTML.replace("__DATA__", json.dumps(data)).replace("__DAY__", a.day)
    path = OUT / f"marker_{a.day}.html"
    path.write_text(html, encoding="utf-8")
    print(f"marker: {path}  ({len(data)} views: price + volume + weis, incl. renko5)")
    for spec, d in data.items():
        print(f"  {spec}: {len(d['bars'])} {d['type']} bars, {len(d['swings'])} swings")
    try:
        subprocess.Popen(["cmd", "/c", "start", "", str(path)], shell=False)
    except Exception:
        pass
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
