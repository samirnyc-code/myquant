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
#side{width:236px;background:var(--sf);border-left:1px solid var(--ln);padding:9px;overflow:auto;font-size:12px}
#side.hidden{display:none}
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
 <span class=tog><input type=checkbox id=t_ema checked onchange=render()>EMA20</span>
 <span class=tog><input type=checkbox id=t_gap checked onchange=render()>gap</span>
 <span class=tog><input type=checkbox id=t_tr checked onchange=render()>trades</span>
 <span class=tog><input type=checkbox id=t_num checked onchange=render()>bar#</span>
 <span class=tog><input type=checkbox id=t_lbl checked onchange=render()>labels</span>
 <span class=tog><input type=checkbox id=t_piv onchange=render()>pivots</span>
 <span class=tog><input type=checkbox id=t_ob onchange=render()>OB</span>
 <span style=color:var(--mut)>levels→⚙</span>
 <span style=color:var(--mut)>Y</span><input type=range id=yzoom min=0.5 max=3.5 step=0.1 value=1 oninput=render() style="width:56px" title="Y compress/expand">
 <span style=color:var(--mut)>X</span><input type=range id=xzoom min=0.5 max=7 step=0.1 value=1 oninput=render() style="width:56px" title="X compress/expand">
 <span style=color:var(--mut)>pan</span><input type=range id=panx min=0 max=1 step=0.01 value=1 oninput=render() style="width:56px" title="horizontal pan">
 <button onclick="document.getElementById('yzoom').value=1;document.getElementById('xzoom').value=1;document.getElementById('panx').value=1;render()" title="reset zoom">⟲</button>
 <button id=lensbtn onclick=toggleLens() title="movable magnifier">🔍 lens</button>
 <button onclick=toggleSettings() title="colors & opacity">⚙</button>
</div>
<button id=sidebtn onclick=toggleSide() title="show/hide panel" style="position:fixed;top:48px;right:8px;z-index:130;background:#2c3440;border:1px solid #4a9eff;padding:4px 7px">⇥ panel</button>
<canvas id=lenscv width=200 height=200 style="position:fixed;border-radius:50%;border:2px solid #4a9eff;box-shadow:0 6px 28px rgba(0,0,0,.6);pointer-events:none;display:none;z-index:120"></canvas>
<div id=settings style="display:none;position:absolute;top:80px;right:250px;z-index:8;background:#1a1f26;border:1px solid #2b333d;border-radius:8px;padding:10px;width:224px;box-shadow:0 6px 24px #000a">
 <b style="color:#4a9eff">colors &amp; opacity</b><div id=setbody style="margin-top:6px"></div>
 <button style="margin-top:8px;width:100%" onclick=resetCfg()>reset defaults</button>
</div>
<div id=wrap><div id=chart><canvas id=cv></canvas></div>
<div id=side>
 <h4>day</h4><div id=dayinfo></div>
 <h4>levels (● on-screen ○ off)</h4><div id=levels></div>
 <h4>day type</h4>
 <div class=stat>intermediate @bar <b id=ibar>—</b> <select id=dti onchange=saveDay()></select></div>
 <div class=stat>final <select id=dtf onchange=saveDay()></select></div>
 <h4>selected setup</h4><div id=selinfo style=color:var(--mut)>click a setup or bar</div>
 <div id=selpanel style=display:none>
  <div class=gr><button onclick=grade('A')>A</button><button onclick=grade('B')>B</button><button onclick=grade('C')>C</button><button onclick=grade('F')>F</button></div>
  <div class=gr style=margin-top:4px><button onclick=takeskip('take')>take ✓</button><button onclick=takeskip('skip')>skip ✕</button></div>
  <textarea id=note rows=3 placeholder="why? (your read)" oninput=saveSel()></textarea>
  <button style="width:100%;margin-top:4px" onclick=openLens()>🔍 zoom this setup</button>
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
<div id=lens style="display:none;position:fixed;inset:0;background:rgba(0,0,0,.82);z-index:9">
 <div style="position:absolute;top:6%;left:8%;right:8%;bottom:6%;background:#12161b;border:1px solid #2b333d;border-radius:8px;padding:10px;display:flex;flex-direction:column">
  <div style="display:flex;justify-content:space-between;align-items:center">
   <b id=lenstitle style="color:#4a9eff">setup lens</b>
   <span>pad <input type=range id=lpad min=3 max=25 value=8 oninput=drawLens() style="vertical-align:middle"> <button onclick="document.getElementById('lens').style.display='none'">✕ close</button></span></div>
  <canvas id=lcv style="flex:1;background:#0c0f13;margin-top:8px;border-radius:5px"></canvas>
 </div></div>
<script>
const DTS=__DTS__;
let PATHS=null;
const CFG_DEF={cUp:'#26a65b',cDn:'#d64541',cEma:'#3aa0ff',cBull:'#2ecc71',cBear:'#e74c3c',
 cIb:'#4a9eff',cEntry:'#ffffff',cStop:'#ff5a5a',cTrig:'#f1c40f',regOp:0.10,ibOp:0.06,ibFill:1,bg:'#0c0f13',
 tl:{entry:{w:1,d:'solid'},stop:{w:1,d:'dash'},trig:{w:1,d:'dot'}},
 lv:{pH:{on:1,c:'#c0392b',w:1,d:'dash',a:1},pL:{on:1,c:'#2980b9',w:1,d:'dash',a:1},pC:{on:1,c:'#8e44ad',w:1,d:'dash',a:1},
     sma:{on:1,c:'#f1c40f',w:1,d:'dot',a:1},open:{on:1,c:'#dfe4e8',w:1,d:'dash',a:1},
     ibh:{on:1,c:'#4a9eff',w:1,d:'dash',a:1},ibl:{on:1,c:'#4a9eff',w:1,d:'dash',a:1}}};
let CFG=Object.assign({},CFG_DEF,JSON.parse(localStorage.getItem('brcfg')||'{}'));
CFG.lv=CFG.lv||{};for(let k in CFG_DEF.lv)CFG.lv[k]=Object.assign({},CFG_DEF.lv[k],CFG.lv[k]||{});
CFG.tl=CFG.tl||{};for(let k in CFG_DEF.tl)CFG.tl[k]=Object.assign({},CFG_DEF.tl[k],CFG.tl[k]||{});
if(CFG.ibFill==null)CFG.ibFill=1;
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
function visTrades(){let f=$('filt').value;return D.trades.filter(t=>{if(f=='book')return t.in_book;if(f=='fade')return t.is_fade;if(f=='L')return t.dir=='L';if(f=='S')return t.dir=='S';if(f=='win')return t.net>0;if(f=='loss')return t.net<0;return true})}
function toggleSide(){let h=$('side').classList.toggle('hidden');$('sidebtn').textContent=h?'‹ panel':'⇥ panel';fit();render()}
function hline(a,b,yy){ctx.beginPath();ctx.moveTo(a,yy);ctx.lineTo(b,yy);ctx.stroke()}
function dot(a,b,r){ctx.beginPath();ctx.arc(a,b,r,0,7);ctx.fill()}
function candle(i,o,h,l,c,x,y,bw,dim){let up=c>=o,col=dim?'#39424d':(up?CFG.cUp:CFG.cDn),xx=x(i);ctx.globalAlpha=dim?.55:1;ctx.strokeStyle=col;ctx.fillStyle=col;ctx.lineWidth=1;ctx.beginPath();ctx.moveTo(xx,y(h));ctx.lineTo(xx,y(l));ctx.stroke();let yo=y(o),yc=y(c);ctx.fillRect(xx-bw*.32,Math.min(yo,yc),Math.max(1,bw*.64),Math.max(1,Math.abs(yo-yc)));ctx.globalAlpha=1}
function setupLbl(t){return t.setup||((t.with_trend?'':'f')+'2E'+t.dir)}
function setupCol(t){if(t.is_fade)return t.dir=='L'?'#e67e22':'#9b59b6';if(t.in_book)return t.dir=='L'?CFG.cBull:CFG.cBear;return '#7f8c8d'}
function render(){if(!D)return;$('dt').textContent=D.date;$('rev').textContent=revIdx+1;$('nb').textContent=D.bars.length;
 let bars=D.bars,ptA=D.prior_tail||[],pt=ptA.length?[ptA[ptA.length-1]]:[],P=pt.length,W=cv.width,H=cv.height,pad=VX,bot=H-26,lbl=$('t_lbl').checked;
 let lo=1e9,hi=-1e9;                              // scale to PRICE ACTION only (bars); far levels listed in panel
 for(let b of pt){lo=Math.min(lo,b[2]);hi=Math.max(hi,b[1])}
 for(let i=0;i<=revIdx;i++){lo=Math.min(lo,bars[i][4]);hi=Math.max(hi,bars[i][3])}
 let rng=(hi-lo)||1;lo-=rng*.06;hi+=rng*.06;rng=hi-lo;
 let yZoom=+$('yzoom').value,mid=(lo+hi)/2,half=rng/2/yZoom;lo=mid-half;hi=mid+half;rng=hi-lo;let onS=p=>p!=null&&p>=lo&&p<=hi;
 let tot=P+bars.length,vw=W-pad.x0-12,xZoom=+$('xzoom').value,bw=vw/tot*xZoom,offX=(+$('panx').value)*Math.max(0,tot*bw-vw);
 let x=i=>pad.x0+(i+P)*bw+bw/2-offX,y=p=>pad.y0+(hi-p)/rng*(bot-pad.y0);
 cv.style.background=CFG.bg;ctx.clearRect(0,0,W,H);
 // regime shading (RTH)
 if($('t_reg').checked)for(let s of D.regime){if(s.from>revIdx)continue;let to=Math.min(s.to,revIdx);let c=s.mode=='BULL'?hexa(CFG.cBull,CFG.regOp):s.mode=='BEAR'?hexa(CFG.cBear,CFG.regOp):hexa('#8b93a0',CFG.regOp*.5);ctx.fillStyle=c;ctx.fillRect(x(s.from)-bw/2,pad.y0,(to-s.from+1)*bw,bot-pad.y0)}
 // per-level style/toggle from settings
 let dashOf=d=>d=='solid'?[]:d=='dot'?[2,3]:[6,4];
 let drawLevel=(p,k,label)=>{let s=CFG.lv[k];if(!s||!s.on||!onS(p))return;let yy=y(p),al=s.a==null?1:s.a;ctx.strokeStyle=hexa(s.c,al);ctx.lineWidth=s.w;ctx.setLineDash(dashOf(s.d));hline(pad.x0,W-10,yy);ctx.setLineDash([]);ctx.lineWidth=1;if(lbl){ctx.fillStyle=hexa(s.c,al);ctx.textAlign='left';ctx.fillText(label,W-26,yy-2)}};
 // IB band fill (own toggle, independent of the IBH/IBL line toggles)
 if(D.ib&&CFG.ibFill&&D.ib.lo<=hi&&D.ib.hi>=lo){let y1=y(Math.min(D.ib.hi,hi)),y2=y(Math.max(D.ib.lo,lo)),xl=x(0)-bw/2;ctx.fillStyle=hexa(CFG.cIb,CFG.ibOp);ctx.fillRect(xl,y1,W-10-xl,y2-y1)}
 // grid + price axis
 ctx.font='10px sans-serif';ctx.textAlign='right';for(let k=0;k<=6;k++){let p=lo+rng*k/6,yy=y(p);ctx.strokeStyle='#161c23';hline(pad.x0,W-10,yy);ctx.fillStyle='#6b7480';ctx.fillText(p.toFixed(0),pad.x0-4,yy+3)}
 // horizontal levels
 drawLevel(D.prior.H,'pH','pH');drawLevel(D.prior.L,'pL','pL');drawLevel(D.prior.C,'pC','pC');
 drawLevel(D.sma20,'sma','SMA');drawLevel(D.today_open,'open','O');
 if(D.ib){drawLevel(D.ib.hi,'ibh','IBH');drawLevel(D.ib.lo,'ibl','IBL')}
 // prior-session LAST bar only (normal colors), + divider
 for(let j=0;j<P;j++){let b=pt[j];candle(-(P-j),b[0],b[1],b[2],b[3],x,y,bw,false);if(lbl){ctx.fillStyle='#8b93a0';ctx.font='8px sans-serif';ctx.textAlign='center';ctx.fillText('prev',x(-(P-j)),bot+12)}}
 if(P){ctx.strokeStyle='#2b333d';ctx.setLineDash([3,3]);hline2(x(-0.5),pad.y0,x(-0.5),bot);ctx.setLineDash([])}
 // RTH candles + bar numbers (b1, then every 3rd)
 for(let i=0;i<=revIdx;i++){let b=bars[i];candle(i,b[2],b[3],b[4],b[5],x,y,bw,false);if($('t_num').checked&&i%3==0){ctx.fillStyle='#5a6470';ctx.font='9px sans-serif';ctx.textAlign='center';ctx.fillText(i+1,x(i),bot+12)}}
 // pivots (swing H/L from phase machine): opening=gold, major=bold, minor=dim
 if($('t_piv').checked&&D.pivots)for(let p of D.pivots){if(p.b>revIdx)continue;let b=bars[p.b],hiP=p.side=='H',py=hiP?b[3]:b[4],big=p.major||p.open;let col=p.open?'#f1c40f':(hiP?'#e59866':'#5dade2');ctx.fillStyle=big?col:hexa(col,.8);dot(x(p.b),y(py),big?3.4:2.4);ctx.font=(big?'9px':'8px')+' sans-serif';ctx.textAlign='center';ctx.fillStyle=big?col:hexa(col,.75);ctx.fillText(p.lab,x(p.b),hiP?y(py)-6:y(py)+13)}
 // OB dots
 if($('t_ob').checked&&D.obs)for(let i of D.obs){if(i>revIdx)continue;ctx.fillStyle='#c39bd3';dot(x(i),y(bars[i][4])+9,2.2)}
 // intraday EMA20 (prior tail -> revealed RTH)
 if($('t_ema').checked){ctx.strokeStyle=CFG.cEma;ctx.lineWidth=1.6;ctx.beginPath();let st=false;for(let j=0;j<P;j++){let xx=x(-(P-j)),yy=y(pt[j][4]);st?ctx.lineTo(xx,yy):ctx.moveTo(xx,yy);st=true}for(let i=0;i<=revIdx;i++){let xx=x(i),yy=y(bars[i][6]);st?ctx.lineTo(xx,yy):ctx.moveTo(xx,yy);st=true}ctx.stroke();ctx.lineWidth=1;if(lbl&&revIdx>=0){ctx.fillStyle=CFG.cEma;ctx.textAlign='left';ctx.fillText('EMA20',x(revIdx)+3,y(bars[revIdx][6]))}}
 // gap tick (open vs prior close)
 if($('t_gap').checked&&D.prior.C){ctx.strokeStyle='#f39c12';ctx.lineWidth=2;hline2(x(0),y(D.prior.C),x(0),y(bars[0][2]));ctx.lineWidth=1}
 // racing stripe on the SIGNAL BAR only
 if($('t_tr').checked)for(let t of visTrades()){if(t.sig_bar>revIdx)continue;let col=setupCol(t),xs=x(t.sig_bar)-bw/2;ctx.globalAlpha=t.in_book?1:.55;ctx.fillStyle=hexa(col,.11);ctx.fillRect(xs,pad.y0,bw,bot-pad.y0);ctx.fillStyle=hexa(col,.9);ctx.fillRect(xs,pad.y0,bw,3);ctx.globalAlpha=1}
 // trades: trigger/entry/stop level lines from signal bar -> exit(or reveal)
 if($('t_tr').checked)for(let t of visTrades()){if(t.sig_bar>revIdx)continue;let endB=Math.min(t.exit_bar,revIdx);let x0=x(t.sig_bar)-bw*.45,x1=x(Math.max(endB,t.sig_bar))+bw*.45,book=t.in_book,TL=CFG.tl;ctx.globalAlpha=book?1:.55;
  ctx.strokeStyle=CFG.cTrig;ctx.lineWidth=TL.trig.w;ctx.setLineDash(dashOf(TL.trig.d));hline(x0,x1,y(t.trigger));
  ctx.strokeStyle=CFG.cEntry;ctx.lineWidth=TL.entry.w;ctx.setLineDash(dashOf(TL.entry.d));hline(x0,x1,y(t.entry_px));
  ctx.strokeStyle=CFG.cStop;ctx.lineWidth=TL.stop.w;ctx.setLineDash(dashOf(TL.stop.d));hline(x0,x1,y(t.stop));ctx.setLineDash([]);ctx.lineWidth=1;
  if(t.entry_bar<=revIdx){ctx.fillStyle=CFG.cEntry;dot(x(t.entry_bar),y(t.entry_px),3)}
  if(t.exit_bar<=revIdx){ctx.fillStyle='#dfe4e8';dot(x(t.exit_bar),y(t.exit_px),3)}
  if(lbl){ctx.textAlign='left';ctx.font='9px sans-serif';ctx.fillStyle=setupCol(t);ctx.fillText(setupLbl(t)+' '+t.entry_px,x0,y(t.entry_px)-3);ctx.fillStyle=CFG.cStop;ctx.fillText('stop '+t.stop,x0,y(t.stop)+(t.dir=='L'?11:-3));if(Math.abs(t.trigger-t.entry_px)>1){ctx.fillStyle=CFG.cTrig;ctx.fillText('trig '+t.trigger,x1+2,y(t.trigger)+3)}}
  if(sel&&sel.entry_bar==t.entry_bar&&sel.dir==t.dir){ctx.strokeStyle='#fff';ctx.lineWidth=1.5;ctx.setLineDash([]);ctx.beginPath();ctx.arc(x(t.entry_bar),y(t.entry_px),6,0,7);ctx.stroke()}
  ctx.globalAlpha=1;ctx.lineWidth=1}
 // reveal edge
 ctx.strokeStyle='#333c47';hline2(x(revIdx)+bw*.5,pad.y0,x(revIdx)+bw*.5,bot);
 // crosshair + hover readout
 if(CH.on){let bi=Math.round((CH.x-pad.x0+offX)/bw-P);ctx.strokeStyle='#5a6470';ctx.setLineDash([2,3]);ctx.lineWidth=1;hline2(CH.x,pad.y0,CH.x,bot);hline(pad.x0,W-10,CH.y);ctx.setLineDash([]);
  let pcur=Math.round((hi-(CH.y-pad.y0)/(bot-pad.y0)*rng)/0.25)*0.25;ctx.fillStyle='#2c3440';ctx.fillRect(W-56,CH.y-8,50,16);ctx.fillStyle='#e6e9ec';ctx.textAlign='left';ctx.font='10px sans-serif';ctx.fillText(pcur.toFixed(2),W-54,CH.y+3);
  let o,h,l,c,tm,tag;if(bi>=0&&bi<=revIdx){let b=bars[bi];o=b[2];h=b[3];l=b[4];c=b[5];tm=b[1];tag='b'+(bi+1);}else if(bi<0&&bi>=-P){let b=pt[bi+P];o=b[0];h=b[1];l=b[2];c=b[3];tm=b[5];tag='prev';}
  if(tm){let cls=[];if(bi>=0){if(D.obs&&D.obs.includes(bi))cls.push('OB');if(D.ibs&&D.ibs.includes(bi))cls.push('IB');let pv=D.pivots&&D.pivots.find(p=>p.b==bi);if(pv)cls.push((pv.side=='H'?'swingH':'swingL')+' '+pv.lab);cls.push(c>=o?'up':'dn');let rg=D.regime&&D.regime.find(s=>bi>=s.from&&bi<=s.to);if(rg)cls.push(rg.mode)}
    let txt=`${tag} ${tm}  O${o} H${h} L${l} C${c}  Δ${(c-o>=0?'+':'')}${(c-o).toFixed(2)}${cls.length?'  ['+cls.join(', ')+']':''}`;ctx.font='11px sans-serif';let tw=ctx.measureText(txt).width+14;ctx.fillStyle='rgba(16,20,26,.96)';ctx.fillRect(pad.x0+4,pad.y0+3,tw,18);ctx.fillStyle='#e6e9ec';ctx.fillText(txt,pad.x0+11,pad.y0+16)}}
 window._lo=lo;window._hi=hi;renderStats();renderDayInfo();renderLevels();window._x=x;window._y=y;window._bw=bw;window._P=P}
function renderLevels(){if(!D)return;let last=D.bars[revIdx][5],lo=window._lo,hi=window._hi;
 let L=CFG.lv,rows=[['last',last,'#e6e9ec'],['OPEN',D.today_open,L.open.c],['SMA20',D.sma20,L.sma.c],['pH',D.prior.H,L.pH.c],['pC',D.prior.C,L.pC.c],['pL',D.prior.L,L.pL.c]];
 if(D.ib){rows.push(['IBH',D.ib.hi,L.ibh.c],['IBL',D.ib.lo,L.ibl.c])}
 $('levels').innerHTML=rows.filter(r=>r[1]!=null).map(([k,v,c])=>{let on=v>=lo&&v<=hi,d=k=='last'?'':((v-last>=0?'+':'')+(v-last).toFixed(2)+'pt');return`<div class=stat><span style="color:${c}">${on?'●':'○'} ${k}</span><span>${v} <span style="color:#6b7480">${d}</span></span></div>`}).join('')}
function hline2(a,b,c,d){ctx.beginPath();ctx.moveTo(a,b);ctx.lineTo(c,d);ctx.stroke()}
function renderDayInfo(){let p=D.prior;$('dayinfo').innerHTML=`<div class=stat>gap<span>${p.gap_pts} (${p.gap_pct}%)</span></div><div class=stat>ADR10<span>${D.adr10}</span></div><div class=stat>SMA20<span>${D.sma20}</span></div><div class=stat>skip-after-TD<span>${D.skipTD?'<span class=loss>YES (skipped)</span>':'no'}</span></div><div class=stat>trades<span>${D.trades.length} (${D.trades.filter(t=>t.in_book).length} in-book)</span></div>`}
function renderStats(){let ts=visTrades().filter(t=>t.in_book);let w=ts.filter(t=>t.net>0),l=ts.filter(t=>t.net<0);let gp=w.reduce((a,b)=>a+b.net,0),gl=-l.reduce((a,b)=>a+b.net,0);let net=ts.reduce((a,b)=>a+b.net,0);
 $('stats').innerHTML=`<div class=stat>n<span>${ts.length}</span></div><div class=stat>PF<span>${gl?(gp/gl).toFixed(2):'∞'}</span></div><div class=stat>win%<span>${ts.length?(100*w.length/ts.length).toFixed(0):0}</span></div><div class=stat>net<span class=${net>=0?'win':'loss'}>${net>=0?'+':''}${net.toFixed(0)}</span></div>`}
cv.onclick=e=>{if(!D)return;let r=cv.getBoundingClientRect(),mx=e.clientX-r.left,my=e.clientY-r.top;let best=null,bd=1e9;
 for(let t of visTrades()){if(t.sig_bar>revIdx)continue;let xa=window._x(t.sig_bar),xb=window._x(Math.min(t.exit_bar,revIdx));if(mx<xa-window._bw||mx>xb+window._bw)continue;let dy=Math.min(Math.abs(window._y(t.entry_px)-my),Math.abs(window._y(t.stop)-my),Math.abs(window._y(t.trigger)-my));if(dy<bd&&dy<16){bd=dy;best=t}}
 if(best)selectTrade(best);else{sel=null;$('selpanel').style.display='none';$('selinfo').textContent='click a setup or bar';render()}}
let LENS_ON=false;
function toggleLens(){LENS_ON=!LENS_ON;$('lensbtn').classList.toggle('on',LENS_ON);$('lenscv').style.display=LENS_ON?'block':'none'}
function drawLensMag(){let lc=$('lenscv'),g=lc.getContext('2d'),S=lc.width,Z=2.8,sw=S/Z;
 g.clearRect(0,0,S,S);g.save();g.beginPath();g.arc(S/2,S/2,S/2-2,0,7);g.clip();g.fillStyle=CFG.bg;g.fillRect(0,0,S,S);
 g.imageSmoothingEnabled=false;g.drawImage(cv,CH.x-sw/2,CH.y-sw/2,sw,sw,0,0,S,S);
 g.strokeStyle='rgba(255,255,255,.22)';g.lineWidth=1;g.beginPath();g.moveTo(S/2,0);g.lineTo(S/2,S);g.moveTo(0,S/2);g.lineTo(S,S/2);g.stroke();g.restore();
 lc.style.left=(CH.cx-S/2)+'px';lc.style.top=(CH.cy-S/2)+'px'}
cv.onmousemove=e=>{if(!D)return;let r=cv.getBoundingClientRect();CH={on:true,x:e.clientX-r.left,y:e.clientY-r.top,cx:e.clientX,cy:e.clientY};if(!CH._raf){CH._raf=requestAnimationFrame(()=>{CH._raf=0;render();if(LENS_ON)drawLensMag()})}}
cv.onmouseleave=()=>{CH.on=false;$('lenscv').style.display='none';render()}
cv.onmouseenter=()=>{if(LENS_ON)$('lenscv').style.display='block'}
function selectTrade(t){sel=t;$('selpanel').style.display='block';let k=tkey(t);let nt=(notes.setups||{})[k]||{};
 let pills,tag,why='';
 if(t.is_fade){tag=t.fade_tradeable?'FADE (tradeable)':'FADE (DEAD)';pills=`<span class=pill>4pt stop</span> <span class=pill>${t.dir=='S'?'BEAR-gated':'BULL-gated'}</span> <span class=pill>gap ${t.pass_gap?'✓':'✕'}</span> <span class=pill>09-13 ${t.pass_window?'✓':'✕'}</span> <span class=pill style="border-color:${t.fade_tradeable?'#e67e22':'#7f8c8d'}">${tag}</span>`;if(!t.fade_tradeable)why=' — f2ES-long is DEAD (PF 0.71), do not trade';}
 else{tag=t.in_book?'IN BOOK':'EXCLUDED';why=t.in_book?'':' — excluded: '+[!t.pass_sma20?'wrong side of SMA20':'',!t.pass_skipTD?'day-after-trend-day':'',!t.pass_gap?'gap>0.54%':'',!t.pass_window?'outside 09-13':''].filter(Boolean).join(', ');pills=`<span class=pill>SMA20 ${t.pass_sma20?'✓':'✕'}</span> <span class=pill>skipTD ${t.pass_skipTD?'✓':'✕'}</span> <span class=pill>WT ${t.with_trend?'✓':'✕'}</span> <span class=pill style="border-color:${t.in_book?'#2ecc71':'#e74c3c'}">${tag}</span>`;}
 $('selinfo').innerHTML=`<b style="color:${setupCol(t)}">${setupLbl(t)}</b> ${t.dir=='S'?'short':'long'} · sig b${t.sig_bar+1} · fill b${t.entry_bar+1}<br>trigger ${t.trigger} · entry ${t.entry_px} · stop ${t.stop} · exit ${t.exit_px} (b${t.exit_bar+1})<br>net <span class=${t.net>0?'win':'loss'}>${t.net>0?'+':''}${t.net}</span> ${pills}<span style="color:#e67e22">${why}</span>`;
 $('note').value=nt.note||'';render()}
function toggleSettings(){let s=$('settings');s.style.display=s.style.display=='none'?'block':'none';if(s.style.display=='block')buildSettings()}
function buildSettings(){
 let LV=[['pH','prior high'],['pL','prior low'],['pC','prior close'],['sma','SMA20'],['open','open'],['ibh','IB high'],['ibl','IB low']];
 let dopt=d=>['solid','dash','dot'].map(o=>`<option ${o==d?'selected':''}>${o}</option>`).join('');
 let lvHtml=LV.map(([k,lab])=>{let s=CFG.lv[k];return `<div style="display:flex;align-items:center;gap:3px;margin:2px 0;font-size:11px">
   <input type=checkbox ${s.on?'checked':''} onchange="CFG.lv['${k}'].on=this.checked?1:0;saveCfg();render()">
   <span style="width:58px">${lab}</span>
   <input type=color value="${s.c}" oninput="CFG.lv['${k}'].c=this.value;saveCfg();render()">
   <input type=range min=1 max=4 step=1 value="${s.w}" title=width style="width:38px" oninput="CFG.lv['${k}'].w=+this.value;saveCfg();render()">
   <select onchange="CFG.lv['${k}'].d=this.value;saveCfg();render()" style="font-size:10px">${dopt(s.d)}</select>
   <input type=range min=0 max=1 step=0.05 value="${s.a==null?1:s.a}" title="opacity (0=transparent)" style="width:36px" oninput="CFG.lv['${k}'].a=+this.value;saveCfg();render()"></div>`}).join('');
 let TL=[['entry','entry'],['stop','stop'],['trig','trigger']];
 let tlHtml=TL.map(([k,lab])=>{let s=CFG.tl[k];return `<div style="display:flex;align-items:center;gap:3px;margin:2px 0;font-size:11px"><span style="width:58px">${lab}</span><input type=range min=1 max=4 step=1 value="${s.w}" title=width style="width:38px" oninput="CFG.tl['${k}'].w=+this.value;saveCfg();render()"><select onchange="CFG.tl['${k}'].d=this.value;saveCfg();render()" style="font-size:10px">${dopt(s.d)}</select></div>`}).join('');
 let rows=[['cUp','up candle'],['cDn','down candle'],['cEma','EMA20 line'],['cEntry','entry line'],['cStop','stop line'],['cTrig','trigger line'],['cBull','bull shade'],['cBear','bear shade'],['cIb','IB fill'],['bg','background']];
 let colHtml=rows.map(([k,lab])=>`<div class=stat><span>${lab}</span><input type=color value="${CFG[k]}" oninput="CFG['${k}']=this.value;saveCfg();render()"></div>`).join('');
 let ibFillHtml=`<div class=stat><span>IB fill shade</span><input type=checkbox ${CFG.ibFill?'checked':''} onchange="CFG.ibFill=this.checked?1:0;saveCfg();render()"></div>`;
 let opHtml=[['regOp','regime opacity'],['ibOp','IB opacity']].map(([k,lab])=>`<div class=stat><span>${lab}</span><input type=range min=0 max=0.4 step=0.01 value="${CFG[k]}" oninput="CFG['${k}']=+this.value;saveCfg();render()"></div>`).join('');
 $('setbody').innerHTML=`<div style="color:#8b93a0;font-size:10px;margin:4px 0">LEVELS (on·color·width·style·opacity)</div>${lvHtml}<div style="color:#8b93a0;font-size:10px;margin:6px 0 2px">TRADE LINES (width·style)</div>${tlHtml}<div style="color:#8b93a0;font-size:10px;margin:6px 0 2px">CHART</div>${colHtml}${ibFillHtml}${opHtml}`}
function tkey(t){return t.entry_bar+t.dir}
function grade(g){if(!sel)return;setNote({grade:g})}
function takeskip(v){if(!sel)return;setNote({takeskip:v})}
function saveSel(){if(!sel)return;setNote({note:$('note').value})}
function setNote(o){let k=tkey(sel);notes.setups=notes.setups||{};notes.setups[k]=Object.assign({setup:setupLbl(sel),entry_bar:sel.entry_bar,sig_bar:sel.sig_bar,dir:sel.dir,with_trend:sel.with_trend,in_book:sel.in_book,net:sel.net,reveal_idx:revIdx},notes.setups[k]||{},o);save()}
function saveDay(){notes.daytype_inter=$('dti').value;notes.daytype_inter_bar=revIdx;notes.daytype_final=$('dtf').value;$('ibar').textContent=revIdx;save()}
function save(){fetch('/save/'+curDate,{method:'POST',body:JSON.stringify(notes)})}
function openLens(){if(!sel){return}$('lens').style.display='block';drawLens()}
function drawLens(){if(!sel||!D)return;let t=sel,bars=D.bars,padN=+$('lpad').value;
 let i0=Math.max(0,t.sig_bar-padN),i1=Math.min(bars.length-1,Math.min(t.exit_bar,revIdx)+padN);
 $('lenstitle').textContent=`${setupLbl(t)} — bars ${i0+1}..${i1+1}  ·  entry ${t.entry_px} · stop ${t.stop} · trig ${t.trigger} · net ${t.net>0?'+':''}${t.net}`;
 let c=$('lcv');c.width=c.clientWidth;c.height=c.clientHeight;let g=c.getContext('2d'),W=c.width,H=c.height,pl=52,bot=H-24;
 let lo=1e9,hi=-1e9;for(let i=i0;i<=i1;i++){lo=Math.min(lo,bars[i][4]);hi=Math.max(hi,bars[i][3])}
 for(let v of [t.entry_px,t.stop,t.trigger]){lo=Math.min(lo,v);hi=Math.max(hi,v)}
 let rng=(hi-lo)||1;lo-=rng*.08;hi+=rng*.08;rng=hi-lo;let n=i1-i0+1,bw=(W-pl-14)/n;
 let x=i=>pl+(i-i0)*bw+bw/2,y=p=>10+(hi-p)/rng*(bot-10);
 g.clearRect(0,0,W,H);g.font='11px sans-serif';g.textAlign='right';
 for(let k=0;k<=8;k++){let p=lo+rng*k/8,yy=y(p);g.strokeStyle='#161c23';g.beginPath();g.moveTo(pl,yy);g.lineTo(W-14,yy);g.stroke();g.fillStyle='#6b7480';g.fillText((Math.round(p/0.25)*0.25).toFixed(2),pl-4,yy+3)}
 // EMA
 g.strokeStyle=CFG.cEma;g.lineWidth=1.6;g.beginPath();for(let i=i0;i<=i1;i++){let xx=x(i),yy=y(bars[i][6]);i==i0?g.moveTo(xx,yy):g.lineTo(xx,yy)}g.stroke();g.lineWidth=1;
 // level lines
 for(let [v,col,dash,lab] of [[t.trigger,CFG.cTrig,[1,3],'trigger'],[t.entry_px,CFG.cEntry,[],'entry'],[t.stop,CFG.cStop,[5,3],'stop']]){g.strokeStyle=col;g.setLineDash(dash);g.beginPath();g.moveTo(pl,y(v));g.lineTo(W-14,y(v));g.stroke();g.setLineDash([]);g.fillStyle=col;g.textAlign='left';g.fillText(lab+' '+v,pl+3,y(v)-3)}
 // candles + bar#
 for(let i=i0;i<=i1;i++){let b=bars[i],up=b[5]>=b[2],col=up?CFG.cUp:CFG.cDn,xx=x(i);g.strokeStyle=col;g.fillStyle=col;g.beginPath();g.moveTo(xx,y(b[3]));g.lineTo(xx,y(b[4]));g.stroke();let yo=y(b[2]),yc=y(b[5]);g.fillRect(xx-bw*.34,Math.min(yo,yc),Math.max(1.5,bw*.68),Math.max(1,Math.abs(yo-yc)));
  g.fillStyle=(i==t.sig_bar)?'#4a9eff':(i==t.entry_bar?'#fff':'#5a6470');g.font='9px sans-serif';g.textAlign='center';g.fillText(i+1,xx,bot+12);
  if(i==t.sig_bar){g.fillStyle='#4a9eff';g.fillText('sig',xx,10)}if(i==t.entry_bar){g.fillStyle='#fff';g.fillText('fill',xx,20)}if(i==t.exit_bar&&t.exit_bar<=revIdx){g.fillStyle='#dfe4e8';g.fillText('exit',xx,10)}}
 // entry/exit dots
 g.fillStyle=CFG.cEntry;if(t.entry_bar<=i1){g.beginPath();g.arc(x(t.entry_bar),y(t.entry_px),4,0,7);g.fill()}if(t.exit_bar<=revIdx&&t.exit_bar<=i1){g.fillStyle='#dfe4e8';g.beginPath();g.arc(x(t.exit_bar),y(t.exit_px),4,0,7);g.fill()}}
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
