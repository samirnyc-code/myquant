"""book_review.py — interactive forward-reveal REVIEW tool for THE BOOK (2E + SMA20 + skip-TD).
Self-contained: stdlib HTTP server + canvas front-end. Run it, open the browser, review 5 years
of trade-days bar-by-bar, toggle every overlay, grade/comment setups, label day-types, and it
saves everything to committed JSON so I can learn from your annotations.

  python scripts/book_review.py           # -> http://localhost:8640
Data:  data/annotations/book_review/<date>.json   (from book_review_prep.py)
Notes: data/annotations/book_review_notes/<date>.json   (your grades/comments/day-types)

Features: forward reveal (space/step/show-all) · jump next-setup / next-ungraded · toggles
(regime shading, SMA20, prior HLC, prior last-bar, gap, IB, bar#s, book-only vs all) · click a
bar or setup to grade(A/B/C)+comment+take/skip · intermediate & final day-type · setup filter
(all/long/short/win/loss/in-book) · live stats · no-lookahead (annotations keyed to reveal bar).
"""
import json
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DAYS = ROOT / "data" / "annotations" / "book_review"
NOTES = ROOT / "data" / "annotations" / "book_review_notes"
NOTES.mkdir(parents=True, exist_ok=True)
PORT = 8640

DAYTYPES = ["Trend", "Trend-from-open", "Trend reversal", "Tight channel", "Broad channel",
            "Trading range", "TR breakout", "Double-distribution trend", "Normal (Dalton)",
            "Normal-variation", "Neutral (Dalton)", "Non-trend", "Other"]

_PATHS = None


def build_paths():
    """R-multiple price path (entry->exit, per bar close) for every in-book trade, from disk.
    R = (px-entry)/risk, sign-adjusted for direction; risk = |entry-stop|. Cached."""
    global _PATHS
    if _PATHS is not None:
        return _PATHS
    win, loss = [], []
    for f in sorted(DAYS.glob("2*.json")):
        try:
            d = json.loads(f.read_text())
        except Exception:
            continue
        closes = [b[5] for b in d["bars"]]
        for t in d["trades"]:
            if not t.get("in_book"):
                continue
            risk = abs(t["entry_px"] - t["stop"]) or 0.25
            sgn = 1.0 if t["dir"] == "L" else -1.0
            eb, xb = t["entry_bar"], min(t["exit_bar"], len(closes) - 1)
            path = [round(sgn * (closes[i] - t["entry_px"]) / risk, 3) for i in range(eb, xb + 1)]
            path = [0.0] + path if not path or path[0] != 0.0 else path
            (win if t["net"] > 0 else loss).append({"date": d["date"], "dir": t["dir"], "net": t["net"], "r": path})
    _PATHS = {"win": win, "loss": loss}
    return _PATHS

HTML = r"""<!doctype html><html><head><meta charset=utf-8><title>Book Review</title>
<style>
:root{--bg:#0f1216;--sf:#1a1f26;--ln:#2b333d;--tx:#e6e9ec;--mut:#8b93a0;--grn:#2ecc71;--red:#e74c3c;--blu:#4a9eff;--yel:#f1c40f}
*{box-sizing:border-box}body{margin:0;background:var(--bg);color:var(--tx);font:13px/1.4 system-ui,sans-serif}
#top{display:flex;gap:10px;align-items:center;flex-wrap:wrap;padding:6px 10px;background:var(--sf);border-bottom:1px solid var(--ln)}
#top b{color:var(--blu)} button,select{background:#232a33;color:var(--tx);border:1px solid var(--ln);border-radius:5px;padding:4px 8px;cursor:pointer;font-size:12px}
button:hover{background:#2c3440} button.on{background:#204a2e;border-color:var(--grn)}
.tog{display:inline-flex;align-items:center;gap:3px} .tog input{accent-color:var(--grn)}
#wrap{display:flex;height:calc(100vh - 44px)} #chart{flex:1;position:relative}
canvas{display:block;background:#0c0f13}
#side{width:300px;background:var(--sf);border-left:1px solid var(--ln);padding:10px;overflow:auto}
.pill{background:#232a33;border:1px solid var(--ln);border-radius:10px;padding:2px 8px;font-size:11px}
h4{margin:10px 0 5px;color:var(--mut);font-weight:600;font-size:11px;text-transform:uppercase;letter-spacing:.4px}
textarea{width:100%;background:#0c0f13;color:var(--tx);border:1px solid var(--ln);border-radius:5px;padding:5px;resize:vertical;font:12px sans-serif}
.gr{display:flex;gap:4px}.gr button{flex:1}
.stat{display:flex;justify-content:space-between;padding:2px 0;border-bottom:1px solid #222}
.win{color:var(--grn)}.loss{color:var(--red)}
</style></head><body>
<div id=top>
 <b id=dt>—</b>
 <button onclick=nav(-1)>◀ prev</button><button onclick=nav(1)>next ▶</button>
 <button onclick=jumpUngraded()>next ungraded</button>
 <select id=daysel onchange=goDay(this.value)></select>
 <span class=pill>reveal <b id=rev>0</b>/<b id=nb>0</b></span>
 <button onclick=play()><span id=playlbl>▶ play</span></button>
 <button onclick=step(-1)>◀</button><button onclick=step(1)>▶</button>
 <button onclick=showAll()>show all</button><button onclick=nextSetup()>next setup ⤼</button>
 <button onclick=openPaths()>W/L paths 📈</button>
 <select id=spd><option value=350>slow</option><option value=150 selected>med</option><option value=50>fast</option></select>
 <span style=color:var(--mut)>filter</span>
 <select id=filt onchange=render()><option value=all>all</option><option value=book>in-book</option><option value=L>long</option><option value=S>short</option><option value=win>winners</option><option value=loss>losers</option></select>
 <span class=tog><input type=checkbox id=t_reg checked onchange=render()>regime</span>
 <span class=tog><input type=checkbox id=t_sma checked onchange=render()>SMA20</span>
 <span class=tog><input type=checkbox id=t_hlc checked onchange=render()>prior HLC</span>
 <span class=tog><input type=checkbox id=t_pb checked onchange=render()>prior bar</span>
 <span class=tog><input type=checkbox id=t_gap checked onchange=render()>gap</span>
 <span class=tog><input type=checkbox id=t_ib checked onchange=render()>IB</span>
 <span class=tog><input type=checkbox id=t_tr checked onchange=render()>trades</span>
 <span class=tog><input type=checkbox id=t_num checked onchange=render()>bar#</span>
</div>
<div id=wrap><div id=chart><canvas id=cv></canvas></div>
<div id=side>
 <h4>day</h4><div id=dayinfo></div>
 <h4>day type</h4>
 <div class=stat>intermediate @bar <b id=ibar>—</b> <select id=dti onchange=saveDay()></select></div>
 <div class=stat>final <select id=dtf onchange=saveDay()></select></div>
 <h4>selected setup</h4><div id=selinfo style=color:var(--mut)>click a setup or bar</div>
 <div id=selpanel style=display:none>
  <div class=gr><button onclick=grade('A')>A</button><button onclick=grade('B')>B</button><button onclick=grade('C')>C</button><button onclick=grade('F')>F</button></div>
  <div class=gr style=margin-top:4px><button onclick=takeskip('take')>take ✓</button><button onclick=takeskip('skip')>skip ✕</button></div>
  <textarea id=note rows=3 placeholder="why? (your read)" oninput=saveSel()></textarea>
 </div>
 <h4>stats (filter)</h4><div id=stats></div>
</div></div>
<div id=modal style="display:none;position:fixed;inset:0;background:rgba(0,0,0,.8);z-index:9">
 <div style="position:absolute;top:3%;left:3%;right:3%;bottom:3%;background:#1a1f26;border:1px solid #2b333d;border-radius:8px;padding:12px;display:flex;flex-direction:column">
  <div style="display:flex;justify-content:space-between;align-items:center">
   <b style="color:#4a9eff">Winner vs Loser price paths — R-multiple by bars-since-entry (in-book trades)</b>
   <span>
    <span class=tog><input type=checkbox id=p_win checked onchange=drawPaths()>winners</span>
    <span class=tog><input type=checkbox id=p_loss checked onchange=drawPaths()>losers</span>
    <span class=tog><input type=checkbox id=p_med checked onchange=drawPaths()>medians</span>
    <select id=p_dir onchange=drawPaths()><option value=all>both dirs</option><option value=L>long</option><option value=S>short</option></select>
    <button onclick="document.getElementById('modal').style.display='none'">✕ close</button>
   </span></div>
  <canvas id=pcv style="flex:1;background:#0c0f13;margin-top:8px;border-radius:5px"></canvas>
  <div id=pstats style="color:#8b93a0;margin-top:6px;font-size:12px"></div>
 </div></div>
<script>
const DTS=__DTS__;
let PATHS=null;
let D=null,notes={},idx=[],curDate=null,revIdx=0,playT=null,sel=null,VX={x0:60,y0:20};
const $=id=>document.getElementById(id);
for(const s of ['dti','dtf']){const e=$(s);e.innerHTML='<option value="">—</option>'+DTS.map(d=>`<option>${d}</option>`).join('')}
fetch('/index').then(r=>r.json()).then(j=>{idx=j;$('daysel').innerHTML=idx.map(d=>`<option value=${d.date}>${d.date} (${d.n_in_book}tr ${d.net>=0?'+':''}${d.net})</option>`).join('');goDay(idx[0].date)});
function goDay(dt){curDate=dt;$('daysel').value=dt;fetch('/day/'+dt).then(r=>r.json()).then(j=>{D=j;revIdx=D.bars.length-1;loadNotes(dt)})}
function loadNotes(dt){fetch('/notes/'+dt).then(r=>r.json()).then(n=>{notes=n||{};$('dti').value=notes.daytype_inter||'';$('dtf').value=notes.daytype_final||'';$('ibar').textContent=notes.daytype_inter_bar??'—';sel=null;$('selpanel').style.display='none';$('selinfo').textContent='click a setup or bar';fit();render()})}
function nav(d){let i=idx.findIndex(x=>x.date==curDate)+d;if(i>=0&&i<idx.length)goDay(idx[i].date)}
function jumpUngraded(){let start=idx.findIndex(x=>x.date==curDate);
 (function tryNext(k){if(k>=idx.length)return;let i=(start+1+k)%idx.length;fetch('/notes/'+idx[i].date).then(r=>r.json()).then(n=>{if(!n||!n.daytype_final)goDay(idx[i].date);else tryNext(k+1)})})(0)}
function play(){if(playT){clearInterval(playT);playT=null;$('playlbl').textContent='▶ play';return}$('playlbl').textContent='⏸ pause';playT=setInterval(()=>{if(revIdx<D.bars.length-1){revIdx++;render()}else play()},+$('spd').value)}
function step(d){revIdx=Math.max(0,Math.min(D.bars.length-1,revIdx+d));render()}
function showAll(){revIdx=D.bars.length-1;render()}
function nextSetup(){if(!D)return;let t=D.trades.filter(x=>x.entry_bar>revIdx).sort((a,b)=>a.entry_bar-b.entry_bar)[0];if(t){revIdx=t.entry_bar;render()}}
window.onkeydown=e=>{if(e.target.tagName=='TEXTAREA')return;if(e.key==' '){e.preventDefault();play()}else if(e.key=='ArrowRight')step(1);else if(e.key=='ArrowLeft')step(-1);else if(e.key=='a'||e.key=='s'&&0)showAll();else if(e.key=='n')nextSetup();else if(['A','B','C','F'].includes(e.key.toUpperCase())&&sel)grade(e.key.toUpperCase())}
let cv=$('cv'),ctx=cv.getContext('2d');
function fit(){cv.width=$('chart').clientWidth;cv.height=$('chart').clientHeight}
window.onresize=()=>{fit();render()};
function visTrades(){let f=$('filt').value;return D.trades.filter(t=>{if(f=='book')return t.in_book;if(f=='L')return t.dir=='L';if(f=='S')return t.dir=='S';if(f=='win')return t.net>0;if(f=='loss')return t.net<0;return true})}
function render(){if(!D)return;$('dt').textContent=D.date;$('rev').textContent=revIdx;$('nb').textContent=D.bars.length-1;
 let bars=D.bars,W=cv.width,H=cv.height,pad=VX;let shown=bars.slice(0,revIdx+1);
 let lows=shown.map(b=>b[4]),his=shown.map(b=>b[3]);let lo=Math.min(...lows),hi=Math.max(...his);
 // include overlays in scale
 if($('t_sma').checked&&D.sma20){lo=Math.min(lo,D.sma20);hi=Math.max(hi,D.sma20)}
 if($('t_hlc').checked&&D.prior.H){lo=Math.min(lo,D.prior.L);hi=Math.max(hi,D.prior.H)}
 let rng=(hi-lo)||1;lo-=rng*.05;hi+=rng*.05;rng=hi-lo;
 let n=bars.length,bw=(W-pad.x0-10)/n,x=i=>pad.x0+i*bw+bw/2,y=p=>pad.y0+(hi-p)/rng*(H-pad.y0-24);
 ctx.clearRect(0,0,W,H);
 // regime shading
 if($('t_reg').checked)for(let s of D.regime){if(s.from>revIdx)continue;let to=Math.min(s.to,revIdx);let c=s.mode=='BULL'?'rgba(46,204,113,.09)':s.mode=='BEAR'?'rgba(231,76,60,.09)':'rgba(139,147,160,.06)';ctx.fillStyle=c;ctx.fillRect(pad.x0+s.from*bw,pad.y0,(to-s.from+1)*bw,H-pad.y0-24)}
 // y grid + labels
 ctx.strokeStyle='#1a2028';ctx.fillStyle='#6b7480';ctx.font='10px sans-serif';ctx.textAlign='right';
 for(let k=0;k<=5;k++){let p=lo+rng*k/5,yy=y(p);ctx.beginPath();ctx.moveTo(pad.x0,yy);ctx.lineTo(W-10,yy);ctx.stroke();ctx.fillText(p.toFixed(0),pad.x0-4,yy+3)}
 // prior HLC
 if($('t_hlc').checked)for(let [p,c,l] of [[D.prior.H,'#c0392b','pH'],[D.prior.L,'#2980b9','pL'],[D.prior.C,'#8e44ad','pC']]){if(!p)continue;let yy=y(p);ctx.strokeStyle=c;ctx.setLineDash([2,3]);ctx.beginPath();ctx.moveTo(pad.x0,yy);ctx.lineTo(W-10,yy);ctx.stroke();ctx.setLineDash([]);ctx.fillStyle=c;ctx.textAlign='left';ctx.fillText(l,W-28,yy-2)}
 // SMA20
 if($('t_sma').checked&&D.sma20){let yy=y(D.sma20);ctx.strokeStyle='#f1c40f';ctx.lineWidth=1.4;ctx.beginPath();ctx.moveTo(pad.x0,yy);ctx.lineTo(W-10,yy);ctx.stroke();ctx.lineWidth=1;ctx.fillStyle='#f1c40f';ctx.fillText('SMA20',W-46,yy-2)}
 // IB box
 if($('t_ib').checked&&D.ib){let y1=y(D.ib.hi),y2=y(D.ib.lo);ctx.strokeStyle='rgba(74,158,255,.5)';ctx.setLineDash([4,3]);ctx.strokeRect(pad.x0,y1,12*bw,y2-y1);ctx.setLineDash([])}
 // candles + bar numbers
 for(let i=0;i<=revIdx;i++){let b=bars[i],up=b[5]>=b[2],col=up?'#26a65b':'#d64541';ctx.strokeStyle=col;ctx.fillStyle=col;let xx=x(i);ctx.beginPath();ctx.moveTo(xx,y(b[3]));ctx.lineTo(xx,y(b[4]));ctx.stroke();let o=y(b[2]),c=y(b[5]);ctx.fillRect(xx-bw*.32,Math.min(o,c),bw*.64,Math.max(1,Math.abs(o-c)));
  if($('t_num').checked&&bw>7){ctx.fillStyle='#4b5560';ctx.font='8px sans-serif';ctx.textAlign='center';ctx.fillText(i,xx,H-14)}}
 // gap marker (open vs prior close)
 if($('t_gap').checked&&D.prior.C){let yy=y(D.prior.C),yo=y(bars[0][2]);ctx.strokeStyle='#f39c12';ctx.beginPath();ctx.moveTo(x(0),yy);ctx.lineTo(x(0),yo);ctx.stroke()}
 // prior last bar marker (at x=-1 region, draw a small tag at left)
 // trades
 if($('t_tr').checked)for(let t of visTrades()){if(t.entry_bar>revIdx)continue;let xe=x(t.entry_bar),ye=y(t.entry_px),ys=y(t.stop);let long=t.dir=='L';let col=t.in_book?(t.net>0?'#2ecc71':'#e74c3c'):'#7f8c8d';
  ctx.strokeStyle=col;ctx.lineWidth=t.in_book?2:1;ctx.beginPath();ctx.moveTo(xe,ye);ctx.lineTo(xe,ys);ctx.stroke();
  // entry arrow
  ctx.fillStyle=col;ctx.beginPath();if(long){ctx.moveTo(xe-4,ye+6);ctx.lineTo(xe+4,ye+6);ctx.lineTo(xe,ye)}else{ctx.moveTo(xe-4,ye-6);ctx.lineTo(xe+4,ye-6);ctx.lineTo(xe,ye)}ctx.fill();
  // exit dotted to exit bar if revealed
  if(t.exit_bar<=revIdx){let xx2=x(t.exit_bar),yy2=y(t.exit_px);ctx.setLineDash([2,2]);ctx.strokeStyle=col;ctx.lineWidth=1;ctx.beginPath();ctx.moveTo(xe,ye);ctx.lineTo(xx2,yy2);ctx.stroke();ctx.setLineDash([])}
  if(sel&&sel.entry_bar==t.entry_bar&&sel.dir==t.dir){ctx.strokeStyle='#fff';ctx.lineWidth=1;ctx.strokeRect(xe-bw*.5,Math.min(ye,ys)-4,bw,Math.abs(ye-ys)+8)}
  ctx.lineWidth=1}
 // reveal edge
 ctx.strokeStyle='#333c47';ctx.beginPath();ctx.moveTo(x(revIdx)+bw*.5,pad.y0);ctx.lineTo(x(revIdx)+bw*.5,H-24);ctx.stroke();
 renderStats();renderDayInfo();window._x=x;window._y=y;window._bw=bw}
function renderDayInfo(){let p=D.prior;$('dayinfo').innerHTML=`<div class=stat>gap<span>${p.gap_pts} (${p.gap_pct}%)</span></div><div class=stat>ADR10<span>${D.adr10}</span></div><div class=stat>SMA20<span>${D.sma20}</span></div><div class=stat>skip-after-TD<span>${D.skipTD?'<span class=loss>YES (skipped)</span>':'no'}</span></div><div class=stat>trades<span>${D.trades.length} (${D.trades.filter(t=>t.in_book).length} in-book)</span></div>`}
function renderStats(){let ts=visTrades().filter(t=>t.in_book);let w=ts.filter(t=>t.net>0),l=ts.filter(t=>t.net<0);let gp=w.reduce((a,b)=>a+b.net,0),gl=-l.reduce((a,b)=>a+b.net,0);let net=ts.reduce((a,b)=>a+b.net,0);
 $('stats').innerHTML=`<div class=stat>n<span>${ts.length}</span></div><div class=stat>PF<span>${gl?(gp/gl).toFixed(2):'∞'}</span></div><div class=stat>win%<span>${ts.length?(100*w.length/ts.length).toFixed(0):0}</span></div><div class=stat>net<span class=${net>=0?'win':'loss'}>${net>=0?'+':''}${net.toFixed(0)}</span></div>`}
cv.onclick=e=>{if(!D)return;let r=cv.getBoundingClientRect(),mx=e.clientX-r.left,my=e.clientY-r.top;let best=null,bd=1e9;for(let t of visTrades()){if(t.entry_bar>revIdx)continue;let dx=Math.abs(window._x(t.entry_bar)-mx),dy=Math.abs(window._y(t.entry_px)-my);let d=dx+dy*.3;if(d<bd&&dx<window._bw*2){bd=d;best=t}}if(best){selectTrade(best)}}
function selectTrade(t){sel=t;$('selpanel').style.display='block';let k=tkey(t);let nt=(notes.setups||{})[k]||{};
 $('selinfo').innerHTML=`<b>2E${t.dir}</b> @bar ${t.entry_bar} · entry ${t.entry_px} stop ${t.stop} · net <span class=${t.net>0?'win':'loss'}>${t.net>0?'+':''}${t.net}</span><br><span class=pill>SMA20 ${t.pass_sma20?'✓':'✕'}</span> <span class=pill>skipTD ${t.pass_skipTD?'✓':'✕'}</span> <span class=pill>WT ${t.with_trend?'✓':'✕'}</span> <span class=pill>${t.in_book?'IN BOOK':'excluded'}</span>`;
 $('note').value=nt.note||'';render()}
function tkey(t){return t.entry_bar+t.dir}
function grade(g){if(!sel)return;setNote({grade:g})}
function takeskip(v){if(!sel)return;setNote({takeskip:v})}
function saveSel(){if(!sel)return;setNote({note:$('note').value})}
function setNote(o){let k=tkey(sel);notes.setups=notes.setups||{};notes.setups[k]=Object.assign({entry_bar:sel.entry_bar,dir:sel.dir,in_book:sel.in_book,net:sel.net,reveal_idx:revIdx},notes.setups[k]||{},o);save()}
function saveDay(){notes.daytype_inter=$('dti').value;notes.daytype_inter_bar=revIdx;notes.daytype_final=$('dtf').value;$('ibar').textContent=revIdx;save()}
function save(){fetch('/save/'+curDate,{method:'POST',body:JSON.stringify(notes)})}
function openPaths(){$('modal').style.display='block';if(PATHS){drawPaths();return}fetch('/allpaths').then(r=>r.json()).then(j=>{PATHS=j;drawPaths()})}
function median(a){if(!a.length)return 0;let s=[...a].sort((x,y)=>x-y),m=s.length>>1;return s.length%2?s[m]:(s[m-1]+s[m])/2}
function drawPaths(){if(!PATHS)return;let dir=$('p_dir').value;
 let win=PATHS.win.filter(t=>dir=='all'||t.dir==dir),loss=PATHS.loss.filter(t=>dir=='all'||t.dir==dir);
 let c=$('pcv');c.width=c.clientWidth;c.height=c.clientHeight;let g=c.getContext('2d'),W=c.width,H=c.height,pl=44,pb=24;
 let all=[...win,...loss];if(!all.length)return;let maxL=Math.max(...all.map(t=>t.r.length));
 let rmax=Math.max(1.5,...all.flatMap(t=>t.r.map(Math.abs)));
 let X=i=>pl+i/(maxL-1)*(W-pl-10),Y=r=>10+(rmax-r)/(2*rmax)*(H-10-pb);
 g.clearRect(0,0,W,H);g.strokeStyle='#1a2028';g.fillStyle='#6b7480';g.font='10px sans-serif';g.textAlign='right';
 for(let r=-Math.floor(rmax);r<=rmax;r++){let yy=Y(r);g.strokeStyle=r==0?'#3a444f':'#161c23';g.beginPath();g.moveTo(pl,yy);g.lineTo(W-10,yy);g.stroke();g.fillStyle='#6b7480';g.fillText(r+'R',pl-4,yy+3)}
 g.textAlign='center';for(let k=0;k<maxL;k+=Math.ceil(maxL/12)){g.fillText(k,X(k),H-8)}
 function drawSet(set,col){g.strokeStyle=col;g.lineWidth=1;for(let t of set){g.globalAlpha=.10;g.beginPath();t.r.forEach((r,i)=>i?g.lineTo(X(i),Y(r)):g.moveTo(X(i),Y(r)));g.stroke()}g.globalAlpha=1}
 function drawMed(set,col){if(!set.length)return;g.strokeStyle=col;g.lineWidth=2.4;g.beginPath();for(let i=0;i<maxL;i++){let v=set.filter(t=>i<t.r.length).map(t=>t.r[i]);if(!v.length)break;let m=median(v);i?g.lineTo(X(i),Y(m)):g.moveTo(X(i),Y(m))}g.stroke();g.lineWidth=1}
 if($('p_win').checked)drawSet(win,'#2ecc71');if($('p_loss').checked)drawSet(loss,'#e74c3c');
 if($('p_med').checked){if($('p_win').checked)drawMed(win,'#2ecc71');if($('p_loss').checked)drawMed(loss,'#e74c3c')}
 let mfeW=median(win.map(t=>Math.max(...t.r))),maeW=median(win.map(t=>Math.min(...t.r))),mfeL=median(loss.map(t=>Math.max(...t.r))),maeL=median(loss.map(t=>Math.min(...t.r)));
 $('pstats').innerHTML=`<span class=win>winners n=${win.length}</span> · med MFE ${mfeW.toFixed(2)}R · med MAE ${maeW.toFixed(2)}R &nbsp;|&nbsp; <span class=loss>losers n=${loss.length}</span> · med MFE ${mfeL.toFixed(2)}R · med MAE ${maeL.toFixed(2)}R &nbsp;→&nbsp; losers that first ran ≥+0.5R: ${(100*loss.filter(t=>Math.max(...t.r)>=.5).length/(loss.length||1)).toFixed(0)}% (giveback signal)`}
</script></body></html>"""


class H(BaseHTTPRequestHandler):
    def log_message(self, *a): pass

    def _send(self, body, ctype="application/json", code=200):
        self.send_response(code); self.send_header("Content-Type", ctype)
        b = body if isinstance(body, bytes) else body.encode()
        self.send_header("Content-Length", str(len(b))); self.end_headers(); self.wfile.write(b)

    def do_GET(self):
        p = self.path
        if p == "/" or p.startswith("/index.html"):
            page = HTML.replace("__DTS__", json.dumps(DAYTYPES))
            return self._send(page, "text/html")
        if p == "/index":
            f = DAYS / "index.json"
            return self._send(f.read_bytes() if f.exists() else b"[]")
        if p == "/allpaths":
            return self._send(json.dumps(build_paths()))
        if p.startswith("/day/"):
            f = DAYS / (p[5:] + ".json")
            return self._send(f.read_bytes() if f.exists() else b"{}")
        if p.startswith("/notes/"):
            f = NOTES / (p[7:] + ".json")
            return self._send(f.read_bytes() if f.exists() else b"{}")
        self._send(b"not found", "text/plain", 404)

    def do_POST(self):
        if self.path.startswith("/save/"):
            ln = int(self.headers.get("Content-Length", 0))
            (NOTES / (self.path[6:] + ".json")).write_bytes(self.rfile.read(ln))
            return self._send(b'{"ok":1}')
        self._send(b"not found", "text/plain", 404)


if __name__ == "__main__":
    print(f"Book Review  ->  http://localhost:{PORT}   (Ctrl-C to stop)")
    HTTPServer(("127.0.0.1", PORT), H).serve_forever()
