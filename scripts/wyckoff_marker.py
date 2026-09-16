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
from renko import build_renko, flex_renko

OUT = ROOT / "data" / "l1_tape" / "_analysis"

HTML = r"""<!doctype html><html><head><meta charset="utf-8"><title>Wyckoff Marker __DAY__</title>
<style>
 body{margin:0;font:13px system-ui,Arial;background:#0f1216;color:#e6e6e6}
 #bar{padding:8px 12px;background:#171b21;display:flex;gap:8px;align-items:center;flex-wrap:wrap;position:sticky;top:0;z-index:5}
 button,select{background:#232a33;color:#e6e6e6;border:1px solid #3a4552;border-radius:5px;padding:5px 10px;cursor:pointer}
 button:hover{background:#2c3742}
 button.on{background:#1e88e5;border-color:#1e88e5}
 #readpanel{position:fixed;top:52px;right:10px;width:300px;background:rgba(23,27,33,0.97);border:1px solid #3a4552;border-radius:6px;z-index:6;box-shadow:0 4px 16px rgba(0,0,0,.5)}
 #readhead{padding:5px 9px;cursor:pointer;font-size:12px;color:#bcd;display:flex;justify-content:space-between;user-select:none}
 #readbody{max-height:44vh;overflow-y:auto;padding:4px 9px 8px;font:12px ui-monospace,Consolas,monospace;white-space:pre;color:#9fd0ff;border-top:1px solid #3a4552}
 #readpanel.collapsed #readbody{display:none}
 #wrap{position:relative;overflow-x:auto}
 canvas{display:block;cursor:crosshair}
 #hint{color:#8ea1b5;font-size:12px}
</style></head><body>
<div id="bar">
  <span id="hint">box = 2 clicks; spring/upthrust = 1 click. </span>
  <span>mode:</span>
  <button id="m_box" class="on">box</button>
  <button id="m_spring">spring</button>
  <button id="m_ut">upthrust</button>
  <button id="auto" class="on">auto events: ON</button>
  <span>view:</span><select id="tf"></select>
  <button id="snap" class="on">snap: ON</button>
  <span>zoom:</span><button id="xm">x&minus;</button><button id="xp">x+</button><button id="ym">y&minus;</button><button id="yp">y+</button>
  <button id="ww">WW: OFF</button>
  <button id="trend">trend: OFF</button>
  <span>pb:</span><button id="pbm">&minus;</button><span id="pbv" style="min-width:24px;text-align:center;display:inline-block">2.5</span><button id="pbp">+</button>
  <button id="undo">undo box</button>
  <button id="reset">reset</button>
  <button id="copy">copy levels</button>
</div>
<div id="readpanel" class="collapsed"><div id="readhead"><span>levels (<span id="cnt">0</span>)</span><span id="rtoggle">▸ show</span></div><div id="readbody"></div></div>
<div id="wrap"><canvas id="c"></canvas></div>
<script>
const DATA = __DATA__;
const TFS = Object.keys(DATA);
let cur=TFS[0], snap=true, pending=null, boxes=[], marks=[], hist=[], mode='box', autoOn=true;
let bwPx=7, yZoom=1, showWW=false, reversal=2.5, showTrend=false;
const cv=document.getElementById('c'), ctx=cv.getContext('2d');
const tfSel=document.getElementById('tf');
TFS.forEach(t=>{const o=document.createElement('option');o.value=t;o.textContent=t;tfSel.appendChild(o)});
const padL=64,padR=16,padT=14,padB=24;
let W,H,ds,bars,sw,pmin,pmax,isRenko,brick,volMax,swMax;
let pTop,pBot,vTop,vBot,wTop,wBot;

function zzz(pr,rev){const n=pr.length;if(n<2)return n?[0]:[];let piv=[0],trend=0,hi=pr[0],lo=pr[0],hib=0,lob=0;
  for(let i=1;i<n;i++){const p=pr[i];if(p>hi){hi=p;hib=i;}if(p<lo){lo=p;lob=i;}
    if(trend<=0&&p>=lo+rev){if(piv[piv.length-1]!==lob)piv.push(lob);trend=1;hi=p;hib=i;}
    else if(trend>=0&&p<=hi-rev){if(piv[piv.length-1]!==hib)piv.push(hib);trend=-1;lo=p;lob=i;}}
  piv.push(trend>=0?hib:lob);let out=[];for(const x of piv)if(!out.length||x>out[out.length-1])out.push(x);return out;}
function computeSwings(){
  if(isRenko){let out=[],i=0;while(i<bars.length){let j=i;while(j+1<bars.length&&bars[j+1].dir===bars[i].dir)j++;let v=0;for(let k=i;k<=j;k++)v+=bars[k].v;out.push({i0:i,i1:j,dir:bars[i].dir,vol:v});i=j+1;}sw=out;}
  else{const cl=bars.map(b=>b.c),piv=zzz(cl,reversal);let out=[];for(let k=0;k+1<piv.length;k++){const s=piv[k],e=piv[k+1];let v=0;for(let m=s;m<=e;m++)v+=bars[m].v;out.push({i0:s,i1:e,dir:cl[e]>=cl[s]?'up':'dn',vol:v});}sw=out;}}
function fitX(){const n=(DATA[cur].bars||[]).length||1;bwPx=Math.min(40,Math.max(1.1,(window.innerWidth-padL-padR-4)/n));}
function layout(){
  ds=DATA[cur]; bars=ds.bars; isRenko=ds.type==='renko'; brick=ds.brick||0; computeSwings();
  W=Math.max(300, bars.length*bwPx+padL+padR);
  H=Math.max(360, window.innerHeight-52); cv.width=W; cv.height=H;   // fill the screen height
  let lo=1e9,hi=-1e9,vm=0;
  for(const b of bars){ if(isRenko){lo=Math.min(lo,b.wlo,b.bottom);hi=Math.max(hi,b.whi,b.top);}else{lo=Math.min(lo,b.l);hi=Math.max(hi,b.h);} vm=Math.max(vm,b.v);}
  const pad=(hi-lo)*0.04, mid=(lo+hi)/2, half=((hi-lo)/2+pad)/yZoom;
  pmin=mid-half; pmax=mid+half; volMax=vm||1; swMax=Math.max(1,...sw.map(s=>s.vol));
  const gTop=padT,gBot=H-padB,gH=gBot-gTop,gap=gH*0.03;
  if(showWW){pTop=gTop;pBot=gTop+gH*0.55;vTop=pBot+gap;vBot=vTop+gH*0.17;wTop=vBot+gap;wBot=gBot;}
  else{pTop=gTop;pBot=gTop+gH*0.74;vTop=pBot+gap;vBot=gBot;wTop=wBot=gBot;}
}
const bw=()=>(W-padL-padR)/bars.length;
const xOf=i=>padL+(i+0.5)*bw();
const yOf=p=>pTop+(pmax-p)/(pmax-pmin)*(pBot-pTop);
const pOf=y=>pmax-(y-pTop)/(pBot-pTop)*(pmax-pmin);
const iOf=x=>Math.max(0,Math.min(bars.length-1,Math.round((x-padL)/bw()-0.5)));

function draw(){
  ctx.clearRect(0,0,W,H);ctx.fillStyle='#0f1216';ctx.fillRect(0,0,W,H);
  const st=showTrend?structure():null;
  if(st){st.segs.forEach(sg=>{ctx.fillStyle=SEGCOL[sg.state]||SEGCOL.na;const x0=xOf(sg.i0)-bw()/2,x1=xOf(sg.i1)+bw()/2;ctx.fillRect(x0,pTop,x1-x0,pBot-pTop);});}
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
  // Weis wave panel (per-swing cumulative volume) — toggleable
  if(showWW){panelLabel('weis wave (pb '+reversal+')',wTop);
  sw.forEach((s,k)=>{const x0=xOf(s.i0),x1=xOf(s.i1),h=(s.vol/swMax)*(wBot-wTop);ctx.fillStyle=s.dir==='up'?'rgba(38,166,154,0.8)':'rgba(239,83,80,0.8)';ctx.fillRect(Math.min(x0,x1)-w/2,wBot-h,Math.max(w,Math.abs(x1-x0)+w),h);
    if(bw()>6){ctx.fillStyle='#cfd8dc';ctx.font='9px monospace';ctx.textAlign='center';ctx.fillText((s.vol/1000).toFixed(0)+'k',(x0+x1)/2,wBot-h-2);}});}
  // boxes
  boxes.forEach((bx,k)=>drawBox(bx,k+1));
  if(st){ctx.font='9px monospace';ctx.textAlign='center';
    st.piv.forEach(p=>{ctx.fillStyle=p.up?'#7fd3c8':'#f0a0a0';ctx.fillText(p.lbl,xOf(p.i),yOf(p.p)+(p.up?-6:12));});
    st.brk.forEach(m=>{const s=EVSTYLE[m.type];ctx.fillStyle=s[0];ctx.beginPath();ctx.arc(xOf(m.i),yOf(m.p),2.5,0,7);ctx.fill();ctx.fillText(s[1],xOf(m.i),yOf(m.p)+s[2]);});}
  drawEvents();        // box-relative candidates: spring/UT/test/SOS/SOW
  drawMarks();
  if(pending){const x=xOf(pending.i),y=yOf(pending.p);ctx.fillStyle='#ffd54f';ctx.beginPath();ctx.arc(x,y,4,0,7);ctx.fill();}
}
const EPS=0.01;
function barLoHiCl(b){const lo=isRenko?Math.min(b.wlo,b.bottom):b.l,hi=isRenko?Math.max(b.whi,b.top):b.h,cl=isRenko?(b.dir==='up'?b.top:b.bottom):b.c;return[lo,hi,cl];}
function barOpen(b){return isRenko?(b.dir==='up'?b.bottom:b.top):b.o;}
function events(){                    // box-relative candidates only; nothing before the AR bar
  if(!autoOn||boxes.length===0) return [];
  const ev=[];
  boxes.forEach(bx=>{const sup=Math.min(bx.a.p,bx.b.p),res=Math.max(bx.a.p,bx.b.p);
    const arBar=Math.max(bx.a.i,bx.b.i);           // the bar that DEFINES the AR high — nothing before it
    const third=sup+(res-sup)/3;
    for(let i=arBar+1;i<bars.length;i++){const [lo,hi,cl]=barLoHiCl(bars[i]);const o=barOpen(bars[i]);
      const openIn=o>=sup-EPS&&o<=res+EPS;         // spring/UT MUST originate INSIDE the range
      if(openIn&&lo<sup-EPS&&cl>=sup-EPS) ev.push({type:'spring',i,p:lo});   // opens inside, probe below, reclaim
      if(openIn&&hi>res+EPS&&cl<=res+EPS) ev.push({type:'ut',i,p:hi});       // opens inside, probe above, fail back
      if(o<=res+EPS&&cl>res+EPS) ev.push({type:'SOS',i,p:hi});              // from inside, close breaks out up
      if(o>=sup-EPS&&cl<sup-EPS) ev.push({type:'SOW',i,p:lo});              // from inside, close breaks out down
    }
    // tests: down-swing bottoming in the lower third but holding above support — only AFTER the AR bar.
    // On renko the true test low (the dip wick) lands on the NEXT (reversal) brick, so mark it there.
    sw.forEach(s=>{if(s.dir==='dn'&&s.i1>arBar){
      let lb=s.i1;
      if(isRenko&&s.i1+1<bars.length&&bars[s.i1+1].wlo<bars[lb].wlo) lb=s.i1+1;
      const lo=isRenko?bars[lb].wlo:pAt(s.i1,'lo');
      if(lo>sup-EPS&&lo<=third) ev.push({type:'test',i:lb,p:lo});}});
  });
  return ev;
}
// BOX-FREE trend engine from the swing structure: HH/HL/LH/LL, BoS=continuation, ChoCH=flip.
// State machine: bull / bear / trans(ition). ChoCH -> transition; next same-side BoS -> bull/bear.
function structure(){
  const piv=[],brk=[],segs=[];let trend=0,prevHigh=null,prevLow=null,state='na',segStart=0;
  // BACKDATE the colour to the move's ORIGIN: a HH break -> bull FROM the low the rally began at;
  // a LL break -> bear FROM the high the drop began at. So up-moves read green, down-moves red.
  function setState(s,startBar){if(s!==state){segs.push({i0:segStart,i1:startBar,state});state=s;segStart=startBar;}}
  sw.forEach(s=>{if(s.dir==='up'){const hi=pAt(s.i1,'hi');
      piv.push({lbl:prevHigh==null?'H':(hi>prevHigh?'HH':'LH'),i:s.i1,p:hi,up:true});
      if(prevHigh!=null&&hi>prevHigh+EPS){brk.push({type:trend<0?'ChoCH':'BoS',i:s.i1,p:hi});trend=1;setState('bull',s.i0);}
      prevHigh=hi;}
    else{const lo=pAt(s.i1,'lo');
      piv.push({lbl:prevLow==null?'L':(lo<prevLow?'LL':'HL'),i:s.i1,p:lo,up:false});
      if(prevLow!=null&&lo<prevLow-EPS){brk.push({type:trend>0?'ChoCH':'BoS',i:s.i1,p:lo});trend=-1;setState('bear',s.i0);}
      prevLow=lo;}});
  segs.push({i0:segStart,i1:bars.length-1,state});
  return {piv,brk,segs,state};
}
const SEGCOL={bull:'rgba(0,230,118,0.42)',bear:'rgba(255,60,60,0.30)',trans:'rgba(150,150,150,0.24)',na:'rgba(90,90,90,0.06)'};
const EVSTYLE={spring:['#26a69a','spring',13],ut:['#ef5350','UT',-13],SOS:['#2e7d32','SOS',-13],
  SOW:['#c62828','SOW',13],test:['#00acc1','test',13],BoS:['#1e88e5','BoS',-13],ChoCH:['#f9a825','ChoCH',-13]};
function drawEvents(){events().forEach(m=>{const s=EVSTYLE[m.type],x=xOf(m.i),y=yOf(m.p);
  ctx.fillStyle=s[0];ctx.beginPath();ctx.arc(x,y,2.5,0,7);ctx.fill();
  ctx.font='9px monospace';ctx.textAlign='center';ctx.fillText(s[1],x,y+s[2]);});}
function drawMarks(){marks.forEach(m=>{const x=xOf(m.i),y=yOf(m.p);ctx.font='10px monospace';ctx.textAlign='center';
  if(m.type==='spring'){ctx.strokeStyle=ctx.fillStyle='#26a69a';const yb=y+16;ctx.beginPath();ctx.moveTo(x,yb);ctx.lineTo(x,y+3);ctx.stroke();
    ctx.beginPath();ctx.moveTo(x-4,y+9);ctx.lineTo(x,y+2);ctx.lineTo(x+4,y+9);ctx.closePath();ctx.fill();ctx.fillText('SP '+m.p.toFixed(2),x,yb+11);}
  else{ctx.strokeStyle=ctx.fillStyle='#ef5350';const yt=y-16;ctx.beginPath();ctx.moveTo(x,yt);ctx.lineTo(x,y-3);ctx.stroke();
    ctx.beginPath();ctx.moveTo(x-4,y-9);ctx.lineTo(x,y-2);ctx.lineTo(x+4,y-9);ctx.closePath();ctx.fill();ctx.fillText('UT '+m.p.toFixed(2),x,yt-4);}});}
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
function snapClick(x,y,force){const i=iOf(x),b=bars[i],pc=pOf(y);
  if(force){const p=force==='lo'?(isRenko?Math.min(b.wlo,b.bottom):b.l):(isRenko?Math.max(b.whi,b.top):b.h);return{i,p,k:force==='lo'?'L':'H'};}
  if(!snap)return{i,p:+pc.toFixed(2),k:'raw'};
  const cand=isRenko?[['T',b.top],['B',b.bottom],['wH',b.whi],['wL',b.wlo]]:[['H',b.h],['L',b.l],['O',b.o],['C',b.c]];
  cand.sort((u,v)=>Math.abs(u[1]-pc)-Math.abs(v[1]-pc));return{i,p:cand[0][1],k:cand[0][0]};}
cv.addEventListener('click',e=>{const r=cv.getBoundingClientRect();const y=e.clientY-r.top;if(y>pBot)return;const x=e.clientX-r.left;
  if(mode==='spring'){const pt=snapClick(x,y,'lo');marks.push({type:'spring',i:pt.i,p:pt.p});hist.push({t:'mark'});draw();readout();return;}
  if(mode==='ut'){const pt=snapClick(x,y,'hi');marks.push({type:'ut',i:pt.i,p:pt.p});hist.push({t:'mark'});draw();readout();return;}
  const pt=snapClick(x,y);if(!pending){pending=pt;}else{boxes.push({a:pending,b:pt});pending=null;hist.push({t:'box'});}draw();readout();});
function fmt(pt){return bars[pt.i].t+' '+pt.p.toFixed(2)+'('+pt.k+')';}
function readout(){let parts=[];
  if(showTrend){const st=structure();parts.push('TREND: '+st.state.toUpperCase()+'   ('+st.brk.length+' BoS/ChoCH)');}
  parts=parts.concat(boxes.map((b,k)=>'box'+(k+1)+': '+fmt(b.a)+' -> '+fmt(b.b)+'  ='+Math.abs(b.a.p-b.b.p).toFixed(2)+'pt'));
  events().forEach(m=>parts.push('  '+(EVSTYLE[m.type]?EVSTYLE[m.type][1]:m.type)+' '+bars[m.i].t+' '+m.p.toFixed(2)));
  marks.forEach(m=>parts.push((m.type==='spring'?'SPRING':'UPTHRUST')+': '+bars[m.i].t+' '+m.p.toFixed(2)));
  if(pending)parts.push('start: '+fmt(pending)+'  (click END)');
  document.getElementById('readbody').textContent=parts.join('\n')||'no marks yet';
  document.getElementById('cnt').textContent=parts.length;}
document.getElementById('readhead').onclick=()=>{const p=document.getElementById('readpanel');p.classList.toggle('collapsed');document.getElementById('rtoggle').textContent=p.classList.contains('collapsed')?'▸ show':'▾ hide';};
document.getElementById('auto').onclick=e=>{autoOn=!autoOn;e.target.textContent='auto events: '+(autoOn?'ON':'OFF');e.target.classList.toggle('on',autoOn);draw();readout();};
function setMode(m){mode=m;pending=null;['box','spring','ut'].forEach(x=>document.getElementById('m_'+x).classList.toggle('on',x===m));readout();}
document.getElementById('m_box').onclick=()=>setMode('box');
document.getElementById('m_spring').onclick=()=>setMode('spring');
document.getElementById('m_ut').onclick=()=>setMode('ut');
document.getElementById('snap').onclick=e=>{snap=!snap;e.target.textContent='snap: '+(snap?'ON':'OFF');e.target.classList.toggle('on',snap);};
document.getElementById('undo').onclick=()=>{const h=hist.pop();if(!h)return;if(h.t==='box')boxes.pop();else marks.pop();draw();readout();};
document.getElementById('reset').onclick=()=>{boxes=[];marks=[];hist=[];pending=null;draw();readout();};
document.getElementById('copy').onclick=()=>{navigator.clipboard.writeText(document.getElementById('readbody').textContent);};
tfSel.onchange=e=>{cur=e.target.value;boxes=[];marks=[];hist=[];pending=null;fitX();layout();draw();readout();};
function relayout(){layout();draw();readout();}
// MOUSE: wheel = time-zoom centered on cursor · Ctrl+wheel = price-zoom · Shift+wheel = pan
const wrapEl=document.getElementById('wrap');
cv.addEventListener('wheel',e=>{e.preventDefault();const f=e.deltaY<0?1.15:0.87;
  if(e.shiftKey){wrapEl.scrollLeft+=e.deltaY;return;}
  if(e.ctrlKey){yZoom=Math.max(0.3,Math.min(8,yZoom*f));relayout();return;}
  const r=cv.getBoundingClientRect();const mx=e.clientX-r.left;const barAt=(mx-padL)/bw()-0.5;
  bwPx=Math.max(1,Math.min(40,bwPx*f));layout();draw();
  wrapEl.scrollLeft=(padL+(barAt+0.5)*bw())-(e.clientX-wrapEl.getBoundingClientRect().left);
},{passive:false});
document.getElementById('xm').onclick=()=>{bwPx=Math.max(2,bwPx*0.8);relayout();};
document.getElementById('xp').onclick=()=>{bwPx=Math.min(28,bwPx*1.25);relayout();};
document.getElementById('ym').onclick=()=>{yZoom=Math.max(0.3,yZoom*0.8);relayout();};
document.getElementById('yp').onclick=()=>{yZoom=Math.min(6,yZoom*1.25);relayout();};
document.getElementById('ww').onclick=e=>{showWW=!showWW;e.target.textContent='WW: '+(showWW?'ON':'OFF');e.target.classList.toggle('on',showWW);relayout();};
document.getElementById('trend').onclick=e=>{showTrend=!showTrend;e.target.textContent='trend: '+(showTrend?'ON':'OFF');e.target.classList.toggle('on',showTrend);relayout();};
document.getElementById('pbm').onclick=()=>{reversal=Math.max(0.5,+(reversal-0.5).toFixed(1));document.getElementById('pbv').textContent=reversal;relayout();};
document.getElementById('pbp').onclick=()=>{reversal=+(reversal+0.5).toFixed(1);document.getElementById('pbv').textContent=reversal;relayout();};
window.onresize=()=>{layout();draw();};
fitX();layout();draw();readout();
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


def _renko_rows(R):
    return [{"t": pd.Timestamp(r["t"]).strftime("%H:%M"), "dir": r["dir"],
             "bottom": round(float(r["bottom"]), 2), "top": round(float(r["top"]), 2),
             "wlo": round(float(r["wlo"]), 2), "whi": round(float(r["whi"]), 2),
             "v": int(r["vol"])} for _, r in R.iterrows()]


def dataset(day, spec):
    sess, tf = spec.split(":")
    raw = td.load_eth(day) if sess == "eth" else td.load_rth(day)
    if tf.startswith("flex"):                       # flexBOX-TREND-REV (ticks), e.g. flex16-8-4
        box, tr, rv = [int(x) for x in tf.replace("flex", "").split("-")]
        R = flex_renko(raw, box, tr, rv)
        return {"type": "renko", "brick": box * 0.25, "bars": _renko_rows(R), "swings": make_swings(R, True)}
    if tf.startswith("renko"):
        brick = float(tf.replace("renko", ""))
        R = build_renko(raw, brick)
        return {"type": "renko", "brick": brick, "bars": _renko_rows(R), "swings": make_swings(R, True)}
    b = hilo_bars(raw, tf)
    rows = [{"t": pd.Timestamp(t).strftime("%H:%M"), "o": round(float(r["open"]), 2),
             "h": round(float(r["high"]), 2), "l": round(float(r["low"]), 2),
             "c": round(float(r["close"]), 2), "v": int(r["vol"])} for t, r in b.iterrows()]
    return {"type": "candle", "bars": rows, "swings": make_swings(b, False)}


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--day", default="2026-09-15")
    ap.add_argument("--tfs", default="eth:flex16-8-4,eth:flex8-4-2,rth:flex16-8-4,rth:flex8-4-2,eth:2000t,rth:2000t")
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
