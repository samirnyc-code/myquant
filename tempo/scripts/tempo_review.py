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
print(f"{len(DATES)} days ready")


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
                     round(float(r.duration_s), 1)])
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
            "notes": notes, "ndays": len(DATES), "idx": i}


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
*{box-sizing:border-box}body{margin:0;background:var(--bg);color:var(--ink);font:13px Consolas,monospace}
#top{display:flex;gap:12px;align-items:center;padding:8px 12px;border-bottom:1px solid var(--line)}
button,input,select{background:var(--panel);color:var(--ink);border:1px solid var(--line);border-radius:4px;padding:4px 8px;font:inherit}
#cv{display:block;width:100vw;cursor:crosshair}
#tip{position:fixed;pointer-events:none;display:none;background:#000d;border:1px solid var(--line);padding:5px 8px;border-radius:4px;z-index:9;white-space:pre}
#dlg{position:fixed;display:none;background:var(--panel);border:1px solid #555;border-radius:8px;padding:12px;z-index:10;width:300px}
#dlg textarea{width:100%;background:var(--bg);color:var(--ink);border:1px solid var(--line);border-radius:4px;font:inherit}
.g{padding:4px 12px;cursor:pointer;border-radius:4px;border:1px solid var(--line);display:inline-block;margin-right:6px}
.g.on{background:#c98500;color:#000}
#marks{color:var(--ink2)}
</style></head><body>
<div id=top>
 <button onclick="nav(D.prev)">&larr;</button>
 <b id=date></b> <span id=pos style="color:var(--ink2)"></span>
 <button onclick="nav(D.next)">&rarr;</button>
 <input id=goto placeholder="YYYY-MM-DD" size=11 onkeydown="if(event.key==='Enter')nav(this.value)">
 <button onclick="nextClimaxDay()">next climax-heavy day (c)</button>
 <span id=marks></span>
 <span style="margin-left:auto;color:var(--ink2)">click a bar to mark a CLIMAX REVERSAL &middot; saved to data/annotations/tempo_review/</span>
</div>
<canvas id=cv height=640></canvas>
<div id=tip></div>
<div id=dlg>
 <div style="margin-bottom:6px"><b id=dlgbar></b></div>
 <div style="margin-bottom:6px">grade:
  <span class=g data-g=A onclick="setG('A')">A</span><span class=g data-g=B onclick="setG('B')">B</span><span class=g data-g=C onclick="setG('C')">C</span>
 </div>
 <div style="margin-bottom:6px">side:
  <select id=side><option value="short">top / short reversal</option><option value="long">bottom / long reversal</option></select>
 </div>
 <textarea id=note rows=3 placeholder="what makes this one good?"></textarea>
 <div style="margin-top:8px">
  <button onclick="saveMark()">save</button>
  <button onclick="delMark()">remove</button>
  <button onclick="closeDlg()">close</button>
 </div>
</div>
<script>
const LANE=["#ffd700","#199e70","#d95926","#d55181","#8fd0bc","#3987e5","#9aa0a6"];
const SNAME=["CLIMAX","EXPAND","CHURN","ACTIVITY","GRIND","BALANCE","MIXED"];
let D=null,ALL=[],MARKED={},sel=-1,curG='A';
const cv=document.getElementById('cv'),cx=cv.getContext('2d');
function nav(d){if(!d)return;fetch('/day/'+d).then(r=>r.json()).then(j=>{if(j.err)return;D=j;sel=-1;closeDlg();render();
 document.getElementById('date').textContent=D.date;
 document.getElementById('pos').textContent=(D.idx+1)+'/'+D.ndays;refreshMarks();});}
function refreshMarks(){fetch('/dates').then(r=>r.json()).then(j=>{ALL=j.dates;MARKED=j.marked;
 const n=Object.values(MARKED).reduce((a,b)=>a+b,0);
 document.getElementById('marks').textContent=Object.keys(MARKED).length+' days marked / '+n+' marks';});}
function render(){
 if(!D)return;const B=D.bars,W=innerWidth;cv.width=W;const H=cv.height;
 cx.fillStyle='#16181d';cx.fillRect(0,0,W,H);
 const chartH=H-90,laneY=H-78;
 let lo=1e9,hi=-1e9;B.forEach(b=>{lo=Math.min(lo,b[4]);hi=Math.max(hi,b[3]);});
 const pad=(hi-lo)*0.04;lo-=pad;hi+=pad;
 const bw=Math.max(3,Math.min(14,(W-60)/B.length)),x0=30;
 const Y=p=>20+(hi-p)/(hi-lo)*(chartH-30);
 B.forEach((b,i)=>{
  const x=x0+i*bw,up=b[5]>=b[2],tp=b[6];
  let al=0.25;if(tp!=null){const f=tp/100;al=0.10+0.90*f*f;}
  const col=up?'38,166,154':'239,83,80';
  cx.strokeStyle=b[12]?'#ffd700':'rgba('+col+','+al+')';
  cx.fillStyle='rgba('+col+','+(b[12]?1:al)+')';
  cx.beginPath();cx.moveTo(x+bw/2,Y(b[3]));cx.lineTo(x+bw/2,Y(b[4]));cx.stroke();
  const yA=Y(Math.max(b[2],b[5])),yB=Y(Math.min(b[2],b[5]));
  cx.fillRect(x+1,yA,bw-2,Math.max(1,yB-yA));
  if(b[12]){cx.strokeRect(x+1,yA,bw-2,Math.max(1,yB-yA));
   cx.fillStyle='#ffd700';cx.beginPath();cx.arc(x+bw/2,Y(b[3])-6,3,0,7);cx.fill();}
  // state lane
  if(b[10]>=0){cx.fillStyle=b[10]==1||b[10]==4?(b[11]>0?LANE[b[10]]:(b[10]==1?'#e34948':'#f0a29b')):LANE[b[10]];
   cx.fillRect(x+1,laneY+ (b[10]*9),bw-1,8);}
  // user marks
  const m=(D.notes.marks||[]).find(m=>m.bar==b[0]);
  if(m){cx.strokeStyle='#fff';cx.lineWidth=2;
   cx.strokeRect(x,Y(b[3])-14,bw,10);cx.lineWidth=1;
   cx.fillStyle='#fff';cx.font='10px Consolas';cx.fillText(m.grade,x+1,Y(b[3])-16);}
 });
 cx.fillStyle='#6b6f76';cx.font='10px Consolas';
 SNAME.forEach((s,i)=>cx.fillText(s,2,laneY+i*9+7));
 for(let i=0;i<B.length;i+=20)cx.fillText(B[i][1].slice(0,5),x0+i*bw,H-2);
}
function barAt(e){const r=cv.getBoundingClientRect(),W=innerWidth;
 const bw=Math.max(3,Math.min(14,(W-60)/D.bars.length));
 const i=Math.floor((e.clientX-r.left-30)/bw);return (i>=0&&i<D.bars.length)?i:-1;}
const tip=document.getElementById('tip');
cv.onmousemove=e=>{const i=barAt(e);if(i<0||!D){tip.style.display='none';return;}
 const b=D.bars[i];
 tip.textContent=b[1]+'  '+SNAME[Math.max(0,b[10])]+ (b[12]?' ★':'')+'\nT p'+b[6]+'  A p'+b[7]+' ('+(b[9]==null?'—':b[9]+'% ABR8')+')\nE p'+b[8]+'  '+(b[13]==null?'—':b[13]+' t/s')+'  '+b[14]+'s';
 tip.style.display='block';tip.style.left=(e.clientX+14)+'px';tip.style.top=(e.clientY+12)+'px';};
cv.onmouseleave=()=>tip.style.display='none';
cv.onclick=e=>{const i=barAt(e);if(i<0)return;sel=i;openDlg(e);};
function openDlg(e){const b=D.bars[sel],dlg=document.getElementById('dlg');
 document.getElementById('dlgbar').textContent=D.date+'  bar '+b[0]+'  '+b[1]+'  '+SNAME[Math.max(0,b[10])]+(b[12]?' ★CLIMAX':'');
 const m=(D.notes.marks||[]).find(m=>m.bar==b[0]);
 setG(m?m.grade:'A');document.getElementById('side').value=m?m.side:'short';
 document.getElementById('note').value=m?m.note:'';
 dlg.style.display='block';dlg.style.left=Math.min(e.clientX,innerWidth-320)+'px';dlg.style.top=(e.clientY+10)+'px';}
function setG(g){curG=g;document.querySelectorAll('.g').forEach(el=>el.classList.toggle('on',el.dataset.g==g));}
function closeDlg(){document.getElementById('dlg').style.display='none';}
function saveMark(){if(sel<0)return;const b=D.bars[sel];
 D.notes.marks=(D.notes.marks||[]).filter(m=>m.bar!=b[0]);
 D.notes.marks.push({bar:b[0],time:b[1],grade:curG,side:document.getElementById('side').value,
  note:document.getElementById('note').value,tpct:b[6],state:b[10],climax:b[12]});
 push();closeDlg();render();}
function delMark(){if(sel<0)return;const b=D.bars[sel];
 D.notes.marks=(D.notes.marks||[]).filter(m=>m.bar!=b[0]);push();closeDlg();render();}
function push(){fetch('/save/'+D.date,{method:'POST',body:JSON.stringify(D.notes)}).then(refreshMarks);}
function nextClimaxDay(){if(!ALL.length||!D)return;
 // climax-heavy = walk forward until a day whose payload has >=8 climax bars
 let i=ALL.indexOf(D.date);
 const step=()=>{i++;if(i>=ALL.length)return;
  fetch('/day/'+ALL[i]).then(r=>r.json()).then(j=>{
   const n=j.bars.filter(b=>b[12]).length;
   if(n>=8){D=j;sel=-1;render();document.getElementById('date').textContent=D.date;
    document.getElementById('pos').textContent=(D.idx+1)+'/'+D.ndays;}
   else step();});};
 step();}
document.onkeydown=e=>{if(e.target.tagName==='TEXTAREA'||e.target.tagName==='INPUT')return;
 if(e.key==='ArrowLeft')nav(D.prev);if(e.key==='ArrowRight')nav(D.next);
 if(e.key==='c')nextClimaxDay();
 if(e.key==='g')document.getElementById('goto').focus();};
fetch('/dates').then(r=>r.json()).then(j=>{ALL=j.dates;MARKED=j.marked;nav(ALL[ALL.length-1]);});
</script></body></html>
"""

if __name__ == "__main__":
    print(f"tempo review -> http://localhost:{PORT}")
    ThreadingHTTPServer(("127.0.0.1", PORT), H).serve_forever()
