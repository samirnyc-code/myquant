"""tempo_review.py — mark-the-chart tool for CLIMAX REVERSALS (S116-tempo).

Sibling of the regime worktree's book_review.py: stdlib HTTP server + canvas
front-end at http://localhost:8642. Renders every trove day as 2000t candles
with the EXACT indicator visuals (opacity = tempo pctile quadratic, gold
climax outline + dot, state lane strip below) from tempo_engine_bars.parquet.

Click a bar -> mark it (grade A/B/C, side, note). Marks save to committed JSON:
    data/annotations/tempo_review/<date>.json
Keys: ←/→ prev/next day · g jump-to-date · c next day with climax cluster.
Purpose: user marks the BEST climax reversals across 5 years; the analysis
script then compares marked vs unmarked climax bars for commonalities.

    python tempo/scripts/tempo_review.py     # -> http://localhost:8642
"""
from __future__ import annotations
import json
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
ENG = ROOT / "tempo" / "outputs" / "tempo_engine_bars.parquet"
NOTES = ROOT / "data" / "annotations" / "tempo_review"
NOTES.mkdir(parents=True, exist_ok=True)
PORT = 8642

print("loading engine bars...")
DF = pd.read_parquet(ENG)
DATES = sorted(DF["date"].unique())
BYDAY = {d: g.reset_index(drop=True) for d, g in DF.groupby("date")}
LEVELS = {}
_LV = ROOT / "tempo" / "outputs" / "levels_by_day.json"
if _LV.exists():
    LEVELS = json.loads(_LV.read_text(encoding="utf-8"))
print(f"{len(DATES)} days ready, levels for {len(LEVELS)}")


def day_payload(date: str) -> dict:
    g = BYDAY[date]
    bars = []
    for r in g.itertuples():
        bars.append([int(r.bar), str(pd.Timestamp(r.start).strftime("%H:%M:%S")),
                     float(r.open), float(r.high), float(r.low), float(r.close),
                     None if pd.isna(r.tpct) else round(float(r.tpct)),
                     None if pd.isna(r.apct) else round(float(r.apct)),
                     None if pd.isna(r.epct) else round(float(r.epct)),
                     None if pd.isna(r.amp_abr8) else round(float(r.amp_abr8)),
                     int(r.state), int(r.dir), bool(r.climax),
                     None if pd.isna(r.tempo) else round(float(r.tempo), 1),
                     round(float(r.duration_s), 1), int(r.vol)])
    i = DATES.index(date)
    notes = {}
    nf = NOTES / f"{date}.json"
    if nf.exists():
        try:
            notes = json.loads(nf.read_text(encoding="utf-8"))
        except Exception:
            notes = {}
    return {"date": date, "bars": bars, "prev": DATES[i - 1] if i > 0 else None,
            "next": DATES[i + 1] if i < len(DATES) - 1 else None,
            "notes": notes, "ndays": len(DATES), "idx": i,
            "levels": LEVELS.get(date, {})}


def marked_summary() -> dict:
    out = {}
    for f in sorted(NOTES.glob("2*.json")):
        try:
            j = json.loads(f.read_text(encoding="utf-8"))
            if j.get("marks"):
                out[f.stem] = len(j["marks"])
        except Exception:
            pass
    return out


class H(BaseHTTPRequestHandler):
    def log_message(self, *a):
        pass

    def _json(self, obj, code=200):
        b = json.dumps(obj).encode()
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(b)))
        self.end_headers()
        self.wfile.write(b)

    def do_GET(self):
        if self.path in ("/", "/index.html"):
            b = HTML.encode()
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Content-Length", str(len(b)))
            self.end_headers()
            self.wfile.write(b)
        elif self.path.startswith("/day/"):
            d = self.path.split("/day/")[1][:10]
            if d in BYDAY:
                self._json(day_payload(d))
            else:
                self._json({"err": "no such day"}, 404)
        elif self.path == "/dates":
            self._json({"dates": DATES, "marked": marked_summary()})
        else:
            self._json({"err": "?"}, 404)

    def do_POST(self):
        if self.path.startswith("/save/"):
            d = self.path.split("/save/")[1][:10]
            ln = int(self.headers.get("Content-Length", "0"))
            body = self.rfile.read(ln).decode()
            try:
                j = json.loads(body)
                (NOTES / f"{d}.json").write_text(json.dumps(j, indent=1), encoding="utf-8")
                self._json({"ok": True})
            except Exception as e:
                self._json({"err": str(e)}, 400)
        else:
            self._json({"err": "?"}, 404)


HTML = r"""<!DOCTYPE html>
<html><head><meta charset="utf-8"><title>Tempo Review — climax reversals</title>
<style>
:root{--bg:#16181d;--panel:#1d2026;--ink:#e8e8e6;--ink2:#a5a8ad;--line:#2c3038}
*{box-sizing:border-box}body{margin:0;background:var(--bg);color:var(--ink);font:13px Consolas,monospace;overflow:hidden}
#top{display:flex;gap:10px;align-items:center;padding:6px 12px;border-bottom:1px solid var(--line)}
#lvbar{display:flex;gap:10px;align-items:center;padding:4px 12px;border-bottom:1px solid var(--line);flex-wrap:wrap;color:var(--ink2)}
#lvbar label{cursor:pointer;white-space:nowrap}
button,input,select{background:var(--panel);color:var(--ink);border:1px solid var(--line);border-radius:4px;padding:4px 8px;font:inherit}
#cv{display:block;cursor:crosshair}
#tip{position:fixed;pointer-events:none;display:none;background:#000d;border:1px solid var(--line);padding:5px 8px;border-radius:4px;z-index:9;white-space:pre}
#dlg{position:fixed;display:none;background:var(--panel);border:1px solid #555;border-radius:8px;z-index:10;width:320px}
#dlghdr{cursor:move;background:#262a31;border-radius:8px 8px 0 0;padding:7px 12px}
#dlgbody{padding:10px 12px}
#dlg textarea{width:100%;background:var(--bg);color:var(--ink);border:1px solid var(--line);border-radius:4px;font:inherit;margin-bottom:6px}
.g{padding:4px 12px;cursor:pointer;border-radius:4px;border:1px solid var(--line);display:inline-block;margin-right:6px}
.g.on{background:#c98500;color:#000}
#marks{color:var(--ink2)}
#help{color:var(--ink2);margin-left:auto}
</style></head><body>
<div id=top>
 <button onclick="nav(D.prev)">&larr;</button>
 <b id=date></b> <span id=pos style="color:var(--ink2)"></span>
 <button onclick="nav(D.next)">&rarr;</button>
 <input id=goto placeholder="YYYY-MM-DD" size=11 onkeydown="if(event.key==='Enter')nav(this.value)">
 <button onclick="nextClimaxDay()">next climax-heavy day (c)</button>
 <span id=marks></span>
 <span id=help>wheel=zoom &middot; drag=pan &middot; dblclick/r=reset &middot; click bar, SHIFT+click extend = multi-bar setup</span>
</div>
<div id=lvbar><b style="color:var(--ink)">levels:</b></div>
<canvas id=cv></canvas>
<div id=tip></div>
<div id=dlg>
 <div id=dlghdr><b id=dlgbar></b></div>
 <div id=dlgbody>
 <div style="margin-bottom:6px">grade:
  <span class=g data-g=A onclick="setG('A')">A</span><span class=g data-g=B onclick="setG('B')">B</span><span class=g data-g=C onclick="setG('C')">C</span>
  &nbsp;side:
  <select id=side><option value="short">top/short</option><option value="long">bottom/long</option></select>
 </div>
 <textarea id=note rows=2 placeholder="what makes this one good?"></textarea>
 <textarea id=cons rows=2 placeholder="what is NOT so good about it?"></textarea>
 <div>
  <button onclick="saveMark()">save</button>
  <button onclick="delMark()">remove</button>
  <button onclick="closeDlg()">close</button>
 </div>
 </div>
</div>
<script>
const LANE=["#ffd700","#199e70","#d95926","#d55181","#8fd0bc","#3987e5","#9aa0a6"];
const SNAME=["CLIMAX","EXPAND","CHURN","ACTIVITY","GRIND","BALANCE","MIXED"];
const LANEH=13,TAXIS=16,X0=64,RGUT=78;
const LVLINES=[["hoy","HOY","#e6b45a"],["loy","LOY","#e6b45a"],["coy","COY","#d98f5a"],
 ["pmid","PDmid","#b58a5a"],["ood","OOD","#5ac8e6"],["oow","OOW","#5aa0e6"],
 ["oom","OOM","#7a8ae6"],["ooq","OOQ","#8a7ae6"],["ooy","OOY","#9a7ae6"],["hod","HOD","#8b8f96"],["lod","LOD","#8b8f96"]];
const LVZONES=[["ib","IB","56,130,229"],["vay","VA-Y","230,180,90"],["vaw","VA-W","120,200,150"],
 ["vam","VA-M","170,140,220"],["vaq","VA-Q","220,120,160"],["vayr","VA-YR","150,150,150"]];
let LV={};try{LV=JSON.parse(localStorage.getItem('tlv')||'{}')}catch(e){}
const LVDEF={hoy:1,loy:1,coy:1,ood:1,hod:1,lod:1,ib:1,vay:1,vwap:1};
function lvOn(k){return LV[k]!==undefined?!!LV[k]:!!LVDEF[k];}
let D=null,ALL=[],MARKED={},curG='A';
let V={i0:0,n:0},selA=-1,selB=-1,dragX=null,dragI0=null,panning=false;
const cv=document.getElementById('cv'),cx=cv.getContext('2d');
// levels toggle bar
(function(){const bar=document.getElementById('lvbar');
 LVLINES.concat(LVZONES).concat([["vwap","VWAP","#e0e0e0"]]).forEach(([k,nm,c])=>{
  const l=document.createElement('label');
  l.innerHTML='<input type=checkbox '+(lvOn(k)?'checked':'')+' data-k='+k+'> <span style="color:'+(c.includes(',')?'rgb('+c+')':c)+'">'+nm+'</span>';
  l.querySelector('input').onchange=e=>{LV[k]=e.target.checked?1:0;localStorage.setItem('tlv',JSON.stringify(LV));render();};
  bar.appendChild(l);});})();
function topH(){return document.getElementById('top').offsetHeight+document.getElementById('lvbar').offsetHeight;}
function fit(){cv.width=innerWidth;cv.height=innerHeight-topH();render();}
onresize=fit;
function nav(d){if(!d)return;fetch('/day/'+d).then(r=>r.json()).then(j=>{if(j.err)return;
 D=j;V={i0:0,n:D.bars.length};selA=selB=-1;closeDlg();fit();
 document.getElementById('date').textContent=D.date;
 document.getElementById('pos').textContent=(D.idx+1)+'/'+D.ndays;refreshMarks();});}
function refreshMarks(){fetch('/dates').then(r=>r.json()).then(j=>{ALL=j.dates;MARKED=j.marked;
 const n=Object.values(MARKED).reduce((a,b)=>a+b,0);
 document.getElementById('marks').textContent=Object.keys(MARKED).length+' days / '+n+' marks';});}
function geom(){return{bw:Math.max(2,(cv.width-X0-RGUT)/V.n)};}
function render(){
 if(!D)return;const B=D.bars,W=cv.width,H=cv.height;
 cx.fillStyle='#16181d';cx.fillRect(0,0,W,H);
 const laneBlock=7*LANEH,chartH=H-laneBlock-TAXIS-8,laneY=H-TAXIS-laneBlock;
 const s=Math.max(0,V.i0),e=Math.min(B.length,V.i0+V.n);
 let lo=1e9,hi=-1e9;
 for(let i=s;i<e;i++){lo=Math.min(lo,B[i][4]);hi=Math.max(hi,B[i][3]);}
 if(lo>hi)return;const pad=(hi-lo)*0.05+0.25;lo-=pad;hi+=pad;
 const {bw}=geom(),xR=W-RGUT;
 const Y=p=>14+(hi-p)/(hi-lo)*(chartH-22);
 const lbls=[];
 // ---- zones first (behind everything)
 LVZONES.forEach(([k,nm,rgb])=>{if(!lvOn(k))return;const z=D.levels[k];if(!z)return;
  const a=z[0],b2=z[z.length-1];if(b2<lo||a>hi)return;
  cx.fillStyle='rgba('+rgb+',0.10)';
  cx.fillRect(X0,Y(Math.min(b2,hi)),xR-X0,Math.max(1,Y(Math.max(a,lo))-Y(Math.min(b2,hi))));
  if(z.length===3&&z[1]>=lo&&z[1]<=hi){cx.strokeStyle='rgba('+rgb+',0.75)';cx.setLineDash([5,4]);
   cx.beginPath();cx.moveTo(X0,Y(z[1]));cx.lineTo(xR,Y(z[1]));cx.stroke();cx.setLineDash([]);
   lbls.push({y:Y(z[1]),t:nm+' POC',c:'rgb('+rgb+')'});}
  [a,b2].forEach((p,ix)=>{if(p>=lo&&p<=hi){cx.strokeStyle='rgba('+rgb+',0.45)';
   cx.beginPath();cx.moveTo(X0,Y(p));cx.lineTo(xR,Y(p));cx.stroke();
   lbls.push({y:Y(p),t:nm+(z.length===3?(ix?' VAH':' VAL'):(ix?' H':' L')),c:'rgb('+rgb+')'});}});});
 // ---- level lines
 LVLINES.forEach(([k,nm,c])=>{if(!lvOn(k))return;const p=D.levels[k];
  if(p===undefined||p<lo||p>hi)return;
  cx.strokeStyle=c;cx.globalAlpha=0.8;cx.beginPath();cx.moveTo(X0,Y(p));cx.lineTo(xR,Y(p));cx.stroke();cx.globalAlpha=1;
  lbls.push({y:Y(p),t:nm+' '+p.toFixed(2),c:c});});
 // ---- candles + lane
 for(let i=s;i<e;i++){
  const b=B[i],x=X0+(i-s)*bw,up=b[5]>=b[2],tp=b[6];
  let al=0.25;if(tp!=null){const f=tp/100;al=0.10+0.90*f*f;}
  const col=up?'38,166,154':'239,83,80';
  cx.strokeStyle=b[12]?'#ffd700':'rgba('+col+','+Math.max(al,0.35)+')';
  cx.fillStyle='rgba('+col+','+(b[12]?1:al)+')';
  cx.beginPath();cx.moveTo(x+bw/2,Y(b[3]));cx.lineTo(x+bw/2,Y(b[4]));cx.stroke();
  const yA=Y(Math.max(b[2],b[5])),yB=Y(Math.min(b[2],b[5]));
  cx.fillRect(x+1,yA,Math.max(1,bw-2),Math.max(1,yB-yA));
  if(b[12]){cx.strokeRect(x+1,yA,Math.max(1,bw-2),Math.max(1,yB-yA));
   cx.fillStyle='#ffd700';cx.beginPath();cx.arc(x+bw/2,Y(b[3])-6,3,0,7);cx.fill();}
  if(b[10]>=0){cx.fillStyle=(b[10]==1||b[10]==4)?(b[11]>0?LANE[b[10]]:(b[10]==1?'#e34948':'#f0a29b')):LANE[b[10]];
   cx.fillRect(x+1,laneY+b[10]*LANEH+2,Math.max(1,bw-1),LANEH-4);}
 }
 // ---- developing VWAP
 if(lvOn('vwap')){let cv_=0,cpv=0;cx.strokeStyle='#e0e0e0';cx.globalAlpha=.7;cx.setLineDash([2,3]);cx.beginPath();let started=false;
  for(let i=0;i<e;i++){const b=B[i];const typ=(b[3]+b[4]+b[5])/3,v=b[15]||0;cpv+=typ*v;cv_+=v;
   if(i>=s&&cv_>0){const y=Y(cpv/cv_);if(y>10&&y<chartH){const x=X0+(i-s)*bw+bw/2;
    if(!started){cx.moveTo(x,y);started=true;}else cx.lineTo(x,y);}}}
  cx.stroke();cx.setLineDash([]);cx.globalAlpha=1;
  if(cv_>0){const vy=Y(cpv/cv_);if(vy>0&&vy<chartH)lbls.push({y:vy,t:'VWAP',c:'#e0e0e0'});}}
 // ---- selection + marks
 if(selA>=0){const a=Math.min(selA,selB<0?selA:selB),b2=Math.max(selA,selB<0?selA:selB);
  cx.fillStyle='rgba(255,255,255,0.08)';cx.fillRect(X0+(a-s)*bw,0,(b2-a+1)*bw,laneY-4);
  cx.strokeStyle='#fff';cx.strokeRect(X0+(a-s)*bw,10,(b2-a+1)*bw,chartH-14);}
 ((D.notes.marks)||[]).forEach(m=>{
  const b0=m.b0!==undefined?m.b0:m.bar,b1=m.b1!==undefined?m.b1:m.bar;
  const i0=B.findIndex(b=>b[0]==b0),i1=B.findIndex(b=>b[0]==b1);
  if(i0<0||i1<0||i1<s||i0>=e)return;
  let yTop=1e9;for(let k=Math.max(i0,s);k<=Math.min(i1,e-1);k++)yTop=Math.min(yTop,Y(B[k][3]));
  const xA=X0+(i0-s)*bw,xB=X0+(i1-s)*bw+bw;
  cx.strokeStyle=m.side==='long'?'#4dd0a1':'#ff8a80';cx.lineWidth=2;
  cx.beginPath();cx.moveTo(xA,yTop-16);cx.lineTo(xA,yTop-10);cx.lineTo(xB,yTop-10);cx.lineTo(xB,yTop-16);cx.stroke();
  cx.lineWidth=1;cx.fillStyle=cx.strokeStyle;cx.font='12px Consolas';
  cx.fillText(m.grade,(xA+xB)/2-4,yTop-18);});
 // ---- right-gutter labels, de-collided (no overlap; leader if shifted)
 cx.font='10px Consolas';lbls.sort((a,b)=>a.y-b.y);let last=-99;
 lbls.forEach(L=>{const y=Math.max(L.y,last+11);last=y;
  if(Math.abs(y-L.y)>3){cx.strokeStyle=L.c;cx.globalAlpha=.5;cx.beginPath();
   cx.moveTo(xR+2,L.y);cx.lineTo(xR+12,y);cx.stroke();cx.globalAlpha=1;}
  cx.fillStyle=L.c;cx.fillText(L.t,xR+14,y+3);});
 // lane labels + time axis
 cx.fillStyle='#8b8f96';cx.font='10px Consolas';
 SNAME.forEach((nm,i)=>cx.fillText(nm,4,laneY+i*LANEH+LANEH-3));
 cx.fillStyle='#6b6f76';
 const step=Math.max(1,Math.floor((e-s)/12));
 for(let i=s;i<e;i+=step)cx.fillText(B[i][1].slice(0,5),X0+(i-s)*bw,H-4);
}
function barAt(ev){const r=cv.getBoundingClientRect();
 const {bw}=geom();const i=V.i0+Math.floor((ev.clientX-r.left-X0)/bw);
 return (i>=0&&i<D.bars.length)?i:-1;}
cv.onwheel=ev=>{ev.preventDefault();if(!D)return;
 const i=barAt(ev);const frac=i<0?0.5:(i-V.i0)/V.n;
 const f=ev.deltaY<0?1/1.25:1.25;
 let n=Math.round(Math.max(20,Math.min(D.bars.length,V.n*f)));
 let i0=Math.round((i<0?V.i0+V.n/2:i)-frac*n);
 V.n=n;V.i0=Math.max(0,Math.min(D.bars.length-n,i0));render();};
cv.onmousedown=ev=>{dragX=ev.clientX;dragI0=V.i0;panning=false;};
cv.onmousemove=ev=>{
 if(dragX!==null&&(ev.buttons&1)){
  const {bw}=geom();const di=Math.round((dragX-ev.clientX)/bw);
  if(Math.abs(ev.clientX-dragX)>4){panning=true;
   V.i0=Math.max(0,Math.min(D.bars.length-V.n,dragI0+di));render();}
  return;}
 const i=barAt(ev);const tip=document.getElementById('tip');
 if(i<0||!D){tip.style.display='none';return;}
 const b=D.bars[i];
 tip.textContent=b[1]+'  '+SNAME[Math.max(0,b[10])]+(b[12]?' ★':'')+'\nT p'+b[6]+'  A p'+b[7]+' ('+(b[9]==null?'—':b[9]+'% ABR8')+')\nE p'+b[8]+'  '+(b[13]==null?'—':b[13]+' t/s')+'  '+b[14]+'s  vol '+(b[15]||0);
 tip.style.display='block';tip.style.left=(ev.clientX+14)+'px';tip.style.top=(ev.clientY+12)+'px';};
cv.onmouseleave=()=>{document.getElementById('tip').style.display='none';dragX=null;};
cv.onmouseup=ev=>{
 const wasPan=panning;dragX=null;panning=false;
 if(wasPan)return;
 const i=barAt(ev);if(i<0)return;
 if(ev.shiftKey&&selA>=0){selB=i;}else{selA=i;selB=i;}
 render();openDlg(ev);};
cv.ondblclick=()=>{if(D){V={i0:0,n:D.bars.length};render();}};
function openDlg(ev){const a=Math.min(selA,selB),b2=Math.max(selA,selB);
 const BA=D.bars[a],BB=D.bars[b2],dlg=document.getElementById('dlg');
 document.getElementById('dlgbar').textContent=D.date+'  bars '+BA[0]+(b2>a?'–'+BB[0]:'')+'  '+BA[1]+(b2>a?' → '+BB[1]:'')+((BA[12]||BB[12])?' ★CLIMAX':'');
 const m=(D.notes.marks||[]).find(m=>(m.b0!==undefined?m.b0:m.bar)==BA[0]);
 setG(m?m.grade:'A');document.getElementById('side').value=m?m.side:'short';
 document.getElementById('note').value=m?m.note:'';
 document.getElementById('cons').value=m&&m.cons?m.cons:'';
 dlg.style.display='block';dlg.style.left=Math.min(ev.clientX,innerWidth-340)+'px';
 dlg.style.top=Math.min(ev.clientY+10,innerHeight-260)+'px';}
// draggable dialog
(function(){const dlg=document.getElementById('dlg'),h=document.getElementById('dlghdr');
 let ox=0,oy=0,on=false;
 h.onmousedown=e=>{on=true;ox=e.clientX-dlg.offsetLeft;oy=e.clientY-dlg.offsetTop;e.preventDefault();};
 document.addEventListener('mousemove',e=>{if(on){dlg.style.left=(e.clientX-ox)+'px';dlg.style.top=(e.clientY-oy)+'px';}});
 document.addEventListener('mouseup',()=>on=false);})();
function setG(g){curG=g;document.querySelectorAll('.g').forEach(el=>el.classList.toggle('on',el.dataset.g==g));}
function closeDlg(){document.getElementById('dlg').style.display='none';}
function saveMark(){if(selA<0)return;
 const a=Math.min(selA,selB),b2=Math.max(selA,selB);
 const BA=D.bars[a],BB=D.bars[b2];
 D.notes.marks=(D.notes.marks||[]).filter(m=>(m.b0!==undefined?m.b0:m.bar)!=BA[0]);
 D.notes.marks.push({b0:BA[0],b1:BB[0],t0:BA[1],t1:BB[1],grade:curG,
  side:document.getElementById('side').value,note:document.getElementById('note').value,
  cons:document.getElementById('cons').value,
  states:D.bars.slice(a,b2+1).map(b=>b[10]),climax:D.bars.slice(a,b2+1).some(b=>b[12])});
 push();closeDlg();render();}
function delMark(){if(selA<0)return;const BA=D.bars[Math.min(selA,selB)];
 D.notes.marks=(D.notes.marks||[]).filter(m=>(m.b0!==undefined?m.b0:m.bar)!=BA[0]);
 push();closeDlg();render();}
function push(){fetch('/save/'+D.date,{method:'POST',body:JSON.stringify(D.notes)}).then(refreshMarks);}
function nextClimaxDay(){if(!ALL.length||!D)return;let i=ALL.indexOf(D.date);
 const step=()=>{i++;if(i>=ALL.length)return;
  fetch('/day/'+ALL[i]).then(r=>r.json()).then(j=>{
   if(j.bars.filter(b=>b[12]).length>=8){D=j;V={i0:0,n:D.bars.length};selA=selB=-1;fit();
    document.getElementById('date').textContent=D.date;
    document.getElementById('pos').textContent=(D.idx+1)+'/'+D.ndays;}
   else step();});};step();}
document.onkeydown=e=>{if(e.target.tagName==='TEXTAREA'||e.target.tagName==='INPUT')return;
 if(e.key==='ArrowLeft')nav(D.prev);if(e.key==='ArrowRight')nav(D.next);
 if(e.key==='c')nextClimaxDay();if(e.key==='r'&&D){V={i0:0,n:D.bars.length};render();}
 if(e.key==='g')document.getElementById('goto').focus();};
fetch('/dates').then(r=>r.json()).then(j=>{ALL=j.dates;MARKED=j.marked;nav(ALL[ALL.length-1]);});
</script></body></html>
"""


if __name__ == "__main__":
    print(f"tempo review -> http://localhost:{PORT}")
    ThreadingHTTPServer(("127.0.0.1", PORT), H).serve_forever()
