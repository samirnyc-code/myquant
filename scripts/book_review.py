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
 <select id=filt onchange=render()><option value=all>all</option><option value=book>in-book</option><option value=fade>fades (f2E)</option><option value=L>long</option><option value=S>short</option><option value=win>winners</option><option value=loss>losers</option></select>
 <span class=tog><input type=checkbox id=t_reg checked onchange=render()>regime</span>
 <span class=tog><input type=checkbox id=t_sma checked onchange=render()>SMA20</span>
 <span class=tog><input type=checkbox id=t_hlc checked onchange=render()>prior HLC</span>
 <span class=tog><input type=checkbox id=t_pb checked onchange=render()>prior bar</span>
 <span class=tog><input type=checkbox id=t_gap checked onchange=render()>gap</span>
 <span class=tog><input type=checkbox id=t_ib checked onchange=render()>IB</span>
 <span class=tog><input type=checkbox id=t_ema checked onchange=render()>EMA20</span>
 <span class=tog><input type=checkbox id=t_tr checked onchange=render()>trades</span>
 <span class=tog><input type=checkbox id=t_num checked onchange=render()>bar#</span>
 <span class=tog><input type=checkbox id=t_lbl checked onchange=render()>labels</span>
 <button onclick=toggleSettings() title="colors & opacity">⚙</button>
</div>
<div id=settings style="display:none;position:absolute;top:80px;right:314px;z-index:8;background:#1a1f26;border:1px solid #2b333d;border-radius:8px;padding:10px;width:230px;box-shadow:0 6px 24px #000a">
 <b style="color:#4a9eff">colors &amp; opacity</b><div id=setbody style="margin-top:6px"></div>
 <button style="margin-top:8px;width:100%" onclick=resetCfg()>reset defaults</button>
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
const CFG_DEF={cUp:'#26a65b',cDn:'#d64541',cEma:'#3aa0ff',cSma:'#f1c40f',cBull:'#2ecc71',cBear:'#e74c3c',
 cIb:'#4a9eff',cEntry:'#ffffff',cStop:'#ff5a5a',cTrig:'#f1c40f',regOp:0.10,ibOp:0.06,bg:'#0c0f13'};
let CFG=Object.assign({},CFG_DEF,JSON.parse(localStorage.getItem('brcfg')||'{}'));
function saveCfg(){localStorage.setItem('brcfg',JSON.stringify(CFG))}
function resetCfg(){CFG=Object.assign({},CFG_DEF);saveCfg();buildSettings();render()}
function hexa(hex,a){let h=hex.replace('#','');let r=parseInt(h.slice(0,2),16),g=parseInt(h.slice(2,4),16),b=parseInt(h.slice(4,6),16);return`rgba(${r},${g},${b},${a})`}
let CH={on:false,x:0,y:0};
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
function visTrades(){let f=$('filt').value;return D.trades.filter(t=>{if(f=='book')return t.in_book;if(f=='fade')return !t.with_trend;if(f=='L')return t.dir=='L';if(f=='S')return t.dir=='S';if(f=='win')return t.net>0;if(f=='loss')return t.net<0;return true})}
function hline(a,b,yy){ctx.beginPath();ctx.moveTo(a,yy);ctx.lineTo(b,yy);ctx.stroke()}
function dot(a,b,r){ctx.beginPath();ctx.arc(a,b,r,0,7);ctx.fill()}
function candle(i,o,h,l,c,x,y,bw,dim){let up=c>=o,col=dim?'#39424d':(up?CFG.cUp:CFG.cDn),xx=x(i);ctx.globalAlpha=dim?.55:1;ctx.strokeStyle=col;ctx.fillStyle=col;ctx.lineWidth=1;ctx.beginPath();ctx.moveTo(xx,y(h));ctx.lineTo(xx,y(l));ctx.stroke();let yo=y(o),yc=y(c);ctx.fillRect(xx-bw*.32,Math.min(yo,yc),Math.max(1,bw*.64),Math.max(1,Math.abs(yo-yc)));ctx.globalAlpha=1}
function setupLbl(t){return (t.with_trend?'':'f')+'2E'+t.dir}
function setupCol(t){return t.in_book?(t.dir=='L'?CFG.cBull:CFG.cBear):(t.dir=='L'?'#e67e22':'#9b59b6')}
function render(){if(!D)return;$('dt').textContent=D.date;$('rev').textContent=revIdx+1;$('nb').textContent=D.bars.length;
 let bars=D.bars,pt=D.prior_tail||[],P=pt.length,W=cv.width,H=cv.height,pad=VX,bot=H-26,lbl=$('t_lbl').checked;
 let lo=1e9,hi=-1e9;
 for(let b of pt){lo=Math.min(lo,b[2]);hi=Math.max(hi,b[1])}
 for(let i=0;i<=revIdx;i++){lo=Math.min(lo,bars[i][4]);hi=Math.max(hi,bars[i][3])}
 if($('t_sma').checked&&D.sma20){lo=Math.min(lo,D.sma20);hi=Math.max(hi,D.sma20)}
 if($('t_hlc').checked&&D.prior.H){lo=Math.min(lo,D.prior.L);hi=Math.max(hi,D.prior.H)}
 if($('t_ib').checked&&D.ib){lo=Math.min(lo,D.ib.lo);hi=Math.max(hi,D.ib.hi)}
 let rng=(hi-lo)||1;lo-=rng*.06;hi+=rng*.06;rng=hi-lo;
 let tot=P+bars.length,bw=(W-pad.x0-12)/tot,x=i=>pad.x0+(i+P)*bw+bw/2,y=p=>pad.y0+(hi-p)/rng*(bot-pad.y0);
 cv.style.background=CFG.bg;ctx.clearRect(0,0,W,H);
 // regime shading (RTH)
 if($('t_reg').checked)for(let s of D.regime){if(s.from>revIdx)continue;let to=Math.min(s.to,revIdx);let c=s.mode=='BULL'?hexa(CFG.cBull,CFG.regOp):s.mode=='BEAR'?hexa(CFG.cBear,CFG.regOp):hexa('#8b93a0',CFG.regOp*.5);ctx.fillStyle=c;ctx.fillRect(x(s.from)-bw/2,pad.y0,(to-s.from+1)*bw,bot-pad.y0)}
 // IB band to EOD
 if($('t_ib').checked&&D.ib){let y1=y(D.ib.hi),y2=y(D.ib.lo),xl=x(0)-bw/2;ctx.fillStyle=hexa(CFG.cIb,CFG.ibOp);ctx.fillRect(xl,y1,W-10-xl,y2-y1);ctx.strokeStyle=hexa(CFG.cIb,.55);ctx.setLineDash([4,3]);hline(xl,W-10,y1);hline(xl,W-10,y2);ctx.setLineDash([]);if(lbl){ctx.fillStyle=hexa(CFG.cIb,.9);ctx.font='10px sans-serif';ctx.textAlign='left';ctx.fillText('IBH',x(0),y1-2);ctx.fillText('IBL',x(0),y2+10)}}
 // racing stripes: highlight each setup's bar-span (behind candles)
 if($('t_tr').checked)for(let t of visTrades()){if(t.sig_bar>revIdx)continue;let endB=Math.max(Math.min(t.exit_bar,revIdx),t.sig_bar);let xa=x(t.sig_bar)-bw/2,ww=(endB-t.sig_bar+1)*bw,col=setupCol(t);ctx.fillStyle=hexa(col,t.in_book?.07:.05);ctx.fillRect(xa,pad.y0,ww,bot-pad.y0);ctx.fillStyle=hexa(col,.9);ctx.fillRect(xa,pad.y0,ww,3)}
 // grid + price axis
 ctx.font='10px sans-serif';ctx.textAlign='right';for(let k=0;k<=6;k++){let p=lo+rng*k/6,yy=y(p);ctx.strokeStyle='#161c23';hline(pad.x0,W-10,yy);ctx.fillStyle='#6b7480';ctx.fillText(p.toFixed(0),pad.x0-4,yy+3)}
 // prior HLC
 if($('t_hlc').checked)for(let [p,c,l] of [[D.prior.H,'#c0392b','pH'],[D.prior.L,'#2980b9','pL'],[D.prior.C,'#8e44ad','pC']]){if(!p)continue;let yy=y(p);ctx.strokeStyle=c;ctx.setLineDash([2,3]);hline(pad.x0,W-10,yy);ctx.setLineDash([]);if(lbl){ctx.fillStyle=c;ctx.textAlign='left';ctx.fillText(l,W-26,yy-2)}}
 // SMA20 dotted
 if($('t_sma').checked&&D.sma20){let yy=y(D.sma20);ctx.strokeStyle=CFG.cSma;ctx.lineWidth=1.4;ctx.setLineDash([2,4]);hline(pad.x0,W-10,yy);ctx.setLineDash([]);ctx.lineWidth=1;if(lbl){ctx.fillStyle=CFG.cSma;ctx.textAlign='left';ctx.fillText('SMA20',W-44,yy-2)}}
 // prior-session tail candles (dim; fully known)
 for(let j=0;j<P;j++){let b=pt[j];candle(-(P-j),b[0],b[1],b[2],b[3],x,y,bw,true)}
 // divider between prior session and RTH
 ctx.strokeStyle='#2b333d';ctx.setLineDash([3,3]);hline2(x(-0.5),pad.y0,x(-0.5),bot);ctx.setLineDash([]);
 // RTH candles + bar numbers
 for(let i=0;i<=revIdx;i++){let b=bars[i];candle(i,b[2],b[3],b[4],b[5],x,y,bw,false);if($('t_num').checked&&bw>7){ctx.fillStyle='#4b5560';ctx.font='8px sans-serif';ctx.textAlign='center';ctx.fillText(i+1,x(i),bot+12)}}
 // intraday EMA20 (prior tail -> revealed RTH)
 if($('t_ema').checked){ctx.strokeStyle=CFG.cEma;ctx.lineWidth=1.6;ctx.beginPath();let st=false;for(let j=0;j<P;j++){let xx=x(-(P-j)),yy=y(pt[j][4]);st?ctx.lineTo(xx,yy):ctx.moveTo(xx,yy);st=true}for(let i=0;i<=revIdx;i++){let xx=x(i),yy=y(bars[i][6]);st?ctx.lineTo(xx,yy):ctx.moveTo(xx,yy);st=true}ctx.stroke();ctx.lineWidth=1;if(lbl&&revIdx>=0){ctx.fillStyle=CFG.cEma;ctx.textAlign='left';ctx.fillText('EMA20',x(revIdx)+3,y(bars[revIdx][6]))}}
 // gap tick (open vs prior close)
 if($('t_gap').checked&&D.prior.C){ctx.strokeStyle='#f39c12';ctx.lineWidth=2;hline2(x(0),y(D.prior.C),x(0),y(bars[0][2]));ctx.lineWidth=1}
 // trades: trigger/entry/stop levels from signal bar -> exit(or reveal), no triangles
 if($('t_tr').checked)for(let t of visTrades()){if(t.sig_bar>revIdx)continue;let endB=Math.min(t.exit_bar,revIdx);let x0=x(t.sig_bar)-bw*.45,x1=x(Math.max(endB,t.sig_bar))+bw*.45,book=t.in_book;ctx.globalAlpha=book?1:.5;
  ctx.strokeStyle=CFG.cTrig;ctx.lineWidth=1;ctx.setLineDash([1,3]);hline(x0,x1,y(t.trigger));
  ctx.strokeStyle=CFG.cEntry;ctx.lineWidth=book?1.8:1;ctx.setLineDash([]);hline(x0,x1,y(t.entry_px));
  ctx.strokeStyle=CFG.cStop;ctx.lineWidth=1.3;ctx.setLineDash([5,3]);hline(x0,x1,y(t.stop));ctx.setLineDash([]);
  if(t.entry_bar<=revIdx){ctx.fillStyle=CFG.cEntry;dot(x(t.entry_bar),y(t.entry_px),3.2)}
  if(t.exit_bar<=revIdx){ctx.fillStyle='#dfe4e8';dot(x(t.exit_bar),y(t.exit_px),3.2)}
  // signal-bar marker (small caret in gutter, not over the bar)
  ctx.fillStyle=book?CFG.cEntry:'#8b93a0';ctx.font='9px sans-serif';ctx.textAlign='center';ctx.fillText(t.dir=='L'?'▲':'▼',x(t.sig_bar),t.dir=='L'?bot-2:pad.y0+9);
  if(lbl){ctx.textAlign='left';ctx.font='9px sans-serif';ctx.fillStyle=setupCol(t);ctx.fillText(setupLbl(t)+' '+t.entry_px,x0,y(t.entry_px)-3);ctx.fillStyle=CFG.cStop;ctx.fillText('stp '+t.stop,x0,y(t.stop)+(t.dir=='L'?11:-3));ctx.fillStyle=CFG.cTrig;ctx.fillText('trg '+t.trigger,x1+2,y(t.trigger)+3)}
  if(sel&&sel.entry_bar==t.entry_bar&&sel.dir==t.dir){let ys=[y(t.entry_px),y(t.stop),y(t.trigger)];ctx.strokeStyle='#fff';ctx.lineWidth=1;ctx.setLineDash([]);ctx.strokeRect(x0-2,Math.min(...ys)-3,(x1-x0)+4,Math.max(...ys)-Math.min(...ys)+6)}
  ctx.globalAlpha=1;ctx.lineWidth=1}
 // reveal edge
 ctx.strokeStyle='#333c47';hline2(x(revIdx)+bw*.5,pad.y0,x(revIdx)+bw*.5,bot);
 // crosshair + hover readout
 if(CH.on){let bi=Math.round((CH.x-pad.x0)/bw-P);ctx.strokeStyle='#5a6470';ctx.setLineDash([2,3]);ctx.lineWidth=1;hline2(CH.x,pad.y0,CH.x,bot);hline(pad.x0,W-10,CH.y);ctx.setLineDash([]);
  let pcur=hi-(CH.y-pad.y0)/(bot-pad.y0)*rng;ctx.fillStyle='#2c3440';ctx.fillRect(W-56,CH.y-8,50,16);ctx.fillStyle='#e6e9ec';ctx.textAlign='left';ctx.font='10px sans-serif';ctx.fillText(pcur.toFixed(2),W-54,CH.y+3);
  let o,h,l,c,tm,tag;if(bi>=0&&bi<=revIdx){let b=bars[bi];o=b[2];h=b[3];l=b[4];c=b[5];tm=b[1];tag='bar '+(bi+1);}else if(bi<0&&bi>=-P){let b=pt[bi+P];o=b[0];h=b[1];l=b[2];c=b[3];tm=b[5];tag='prior';}
  if(tm){let txt=`${tag} ${tm}  O${o} H${h} L${l} C${c}  (${(c-o>=0?'+':'')}${(c-o).toFixed(2)})`;ctx.font='11px sans-serif';let tw=ctx.measureText(txt).width+14;ctx.fillStyle='rgba(16,20,26,.96)';ctx.fillRect(pad.x0+4,pad.y0+3,tw,18);ctx.fillStyle='#e6e9ec';ctx.fillText(txt,pad.x0+11,pad.y0+16)}}
 renderStats();renderDayInfo();window._x=x;window._y=y;window._bw=bw;window._P=P}
function hline2(a,b,c,d){ctx.beginPath();ctx.moveTo(a,b);ctx.lineTo(c,d);ctx.stroke()}
function renderDayInfo(){let p=D.prior;$('dayinfo').innerHTML=`<div class=stat>gap<span>${p.gap_pts} (${p.gap_pct}%)</span></div><div class=stat>ADR10<span>${D.adr10}</span></div><div class=stat>SMA20<span>${D.sma20}</span></div><div class=stat>skip-after-TD<span>${D.skipTD?'<span class=loss>YES (skipped)</span>':'no'}</span></div><div class=stat>trades<span>${D.trades.length} (${D.trades.filter(t=>t.in_book).length} in-book)</span></div>`}
function renderStats(){let ts=visTrades().filter(t=>t.in_book);let w=ts.filter(t=>t.net>0),l=ts.filter(t=>t.net<0);let gp=w.reduce((a,b)=>a+b.net,0),gl=-l.reduce((a,b)=>a+b.net,0);let net=ts.reduce((a,b)=>a+b.net,0);
 $('stats').innerHTML=`<div class=stat>n<span>${ts.length}</span></div><div class=stat>PF<span>${gl?(gp/gl).toFixed(2):'∞'}</span></div><div class=stat>win%<span>${ts.length?(100*w.length/ts.length).toFixed(0):0}</span></div><div class=stat>net<span class=${net>=0?'win':'loss'}>${net>=0?'+':''}${net.toFixed(0)}</span></div>`}
cv.onclick=e=>{if(!D)return;let r=cv.getBoundingClientRect(),mx=e.clientX-r.left,my=e.clientY-r.top;let best=null,bd=1e9;
 for(let t of visTrades()){if(t.sig_bar>revIdx)continue;let xa=window._x(t.sig_bar),xb=window._x(Math.min(t.exit_bar,revIdx));if(mx<xa-window._bw||mx>xb+window._bw)continue;let dy=Math.min(Math.abs(window._y(t.entry_px)-my),Math.abs(window._y(t.stop)-my),Math.abs(window._y(t.trigger)-my));if(dy<bd&&dy<16){bd=dy;best=t}}
 if(best)selectTrade(best)}
cv.onmousemove=e=>{if(!D)return;let r=cv.getBoundingClientRect();CH={on:true,x:e.clientX-r.left,y:e.clientY-r.top};if(!CH._raf){CH._raf=requestAnimationFrame(()=>{CH._raf=0;render()})}}
cv.onmouseleave=()=>{CH.on=false;render()}
function selectTrade(t){sel=t;$('selpanel').style.display='block';let k=tkey(t);let nt=(notes.setups||{})[k]||{};
 let why=t.in_book?'':' — excluded: '+[!t.with_trend?'countertrend (WT✕)':'',!t.pass_sma20?'wrong side of SMA20':'',!t.pass_skipTD?'day-after-trend-day':'',!t.pass_gap?'gap>0.54%':'',!t.pass_window?'outside 09-13':''].filter(Boolean).join(', ');
 let tag=t.in_book?'IN BOOK':(t.with_trend?'EXCLUDED':'FADE '+setupLbl(t));
 $('selinfo').innerHTML=`<b style="color:${setupCol(t)}">${setupLbl(t)}</b> sig bar ${t.sig_bar+1} · fill bar ${t.entry_bar+1}<br>trigger ${t.trigger} · entry ${t.entry_px} · stop ${t.stop} · exit ${t.exit_px} (bar ${t.exit_bar+1})<br>net <span class=${t.net>0?'win':'loss'}>${t.net>0?'+':''}${t.net}</span> &nbsp;<span class=pill>SMA20 ${t.pass_sma20?'✓':'✕'}</span> <span class=pill>skipTD ${t.pass_skipTD?'✓':'✕'}</span> <span class=pill>WT ${t.with_trend?'✓':'✕'}</span> <span class=pill style="border-color:${t.in_book?'#2ecc71':(t.with_trend?'#e74c3c':'#e67e22')}">${tag}</span><span style="color:#e67e22">${why}</span>`;
 $('note').value=nt.note||'';render()}
function toggleSettings(){let s=$('settings');s.style.display=s.style.display=='none'?'block':'none';if(s.style.display=='block')buildSettings()}
function buildSettings(){let rows=[['cUp','up candle','color'],['cDn','down candle','color'],['cEma','EMA20','color'],['cSma','SMA20','color'],['cEntry','entry line','color'],['cStop','stop line','color'],['cTrig','trigger line','color'],['cBull','bull shade','color'],['cBear','bear shade','color'],['cIb','IB','color'],['bg','background','color'],['regOp','regime opacity','range'],['ibOp','IB opacity','range']];
 $('setbody').innerHTML=rows.map(([k,lab,ty])=>ty=='color'?`<div class=stat><span>${lab}</span><input type=color value="${CFG[k]}" oninput="CFG['${k}']=this.value;saveCfg();render()"></div>`:`<div class=stat><span>${lab}</span><input type=range min=0 max=0.4 step=0.01 value="${CFG[k]}" oninput="CFG['${k}']=+this.value;saveCfg();render()"></div>`).join('')}
function tkey(t){return t.entry_bar+t.dir}
function grade(g){if(!sel)return;setNote({grade:g})}
function takeskip(v){if(!sel)return;setNote({takeskip:v})}
function saveSel(){if(!sel)return;setNote({note:$('note').value})}
function setNote(o){let k=tkey(sel);notes.setups=notes.setups||{};notes.setups[k]=Object.assign({setup:setupLbl(sel),entry_bar:sel.entry_bar,sig_bar:sel.sig_bar,dir:sel.dir,with_trend:sel.with_trend,in_book:sel.in_book,net:sel.net,reveal_idx:revIdx},notes.setups[k]||{},o);save()}
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
