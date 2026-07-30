"""Build the interactive EminiAddict study tool for Mission Control.

Writes docs/artifacts/eminiaddict_method_study_quiz.html — a self-contained page
(no external libs) with: flashcards (definitions), a scored quiz (multiple-choice
+ numeric, drawn from RULEBOOK), a live MM-level calculator (SVG), sequence-order
drills, and a chart-reading drill. Registers in the artifact catalog.
Run from repo root or eminiaddict/.
"""
import base64
import json
import pathlib

ROOT = pathlib.Path(__file__).resolve().parents[2]
CHART = ROOT / "eminiaddict" / "figures" / "es_daily_mm_fib_dominant.png"
OUT = ROOT / "docs" / "artifacts" / "eminiaddict_method_study_quiz.html"
CATALOG = ROOT / "data" / "_catalog" / "claude_artifacts.json"
TITLE = "EminiAddict Method Study Quiz"       # slug -> eminiaddict_method_study_quiz
DATE = "2026-07-30"
chart_b64 = base64.b64encode(CHART.read_bytes()).decode() if CHART.exists() else ""

# ---- study content (accurate to notes/RULEBOOK.md) ----
FLASHCARDS = [
    ["50% / HWB", "Half-way-back. The <b>entry</b> / continuation zone of a measured move. Formula (long): L + 0.500·R."],
    ["61.8% level", "The <b>FAILURE</b> line. A breach kills the MM. Formula (long): L + 0.382·R (= H − 0.618·R)."],
    ["123% / −23.6%", "The measured-move <b>TARGET</b>; also seeds the next swing. Formula (long): H + 0.236·R."],
    ["Distance Formula", "A scalp exit = the distance between the 50% and 38.2% lines = <b>0.118·R</b>. Used as a first target."],
    ["Seed swing", "The <b>only discretionary step</b> — the 'significant high-low that jumps off the page.' Everything after is mechanical."],
    ["Traditional 50% MM", "Pull back 50% of an initial rally; buy the limit at HWB, target 123%. Strings into a series."],
    ["Extension 50% MM", "Formed when price makes new highs PAST a 123% target with no pullback (bull/bear flags). FIRST extension = observe-only."],
    ["61.8% failure (setup)", "Fails the 2nd test of the 50% and pierces 61.8% → series broken → new trend. Trade the first pullback after the break."],
    ["First test", "The first pullback into the 50% MM. Highest probability / most volume. ES: limit +2 ticks in front, stop −6→−4."],
    ["Front-run 2nd test", "Riskiest, best R:R. 4-tick total stop, all-in/all-out, smaller size. Not a reduced-risk trade."],
    ["Trend break / next MM", "Break of the OPPOSING MM confirms (a) the trend and (b) the target. Trade the next MM at first-test specs."],
    ["Professional gap", "Open ≥10 points from prior close. Tends to run away (gap-and-go), rarely fills same day (~9–26%)."],
    ["Amateur gap", "Open <10 points from prior close. Usually fills within the first hour (~77–79%)."],
    ["Gap fill", "Price reaches the prior day's 4pm cash close during RTH."],
    ["Daily Pivot (DP)", "(High + Low + Close) / 3 of the prior session. A price attractor / target."],
    ["Trend day (up)", "Professional gap up + positive breadth + positive tick divergence (all three)."],
    ["Free trade", "Trade ≥2 contracts, sell half at target 1, move stop so max loss = 0."],
    ["Tick extreme", "NYSE tick at ±1000 = reversal risk (programs take profit). Buy low ticks in long series; sell high ticks in short series."],
]

# quiz: type 'mc' {q,choices,a,ex}; type 'num' {q,fn(L,H),tol,ex} handled in JS with fixed L/H
QUIZ = [
    {"t": "mc", "q": "Which Fib level is the ENTRY in a measured move?",
     "choices": ["61.8%", "50% (HWB)", "38.2%", "123%"], "a": 1,
     "ex": "50% = half-way-back = the entry / continuation zone."},
    {"t": "mc", "q": "A breach of which level means the MM has FAILED?",
     "choices": ["50%", "38.2%", "61.8%", "0%"], "a": 2,
     "ex": "61.8% is the failure line; a pierce breaks the series."},
    {"t": "mc", "q": "The measured-move profit target sits at:",
     "choices": ["61.8% retracement", "the 0% swing extreme", "123% / −23.6% extension", "the daily pivot"], "a": 2,
     "ex": "Target = 123% (−23.6%) = H + 0.236·R for a long. It also seeds the next swing."},
    {"t": "num", "q": "Long leg L=6,420.75, H=7,699.75. Compute the 50% HWB entry.",
     "fn": "hwb", "tol": 0.5, "ex": "HWB = L + 0.5·R = 6420.75 + 0.5·1279 = 7,060.25."},
    {"t": "num", "q": "Same leg (L=6,420.75, H=7,699.75). Compute the 61.8% FAILURE level.",
     "fn": "fail", "tol": 0.5, "ex": "Fail = L + 0.382·R = 6420.75 + 0.382·1279 = 6,909.33."},
    {"t": "num", "q": "Same leg. Compute the 123% TARGET.",
     "fn": "tgt", "tol": 0.5, "ex": "Target = H + 0.236·R = 7699.75 + 0.236·1279 = 8,001.59."},
    {"t": "mc", "q": "The three entry strategies, in their fixed order, are:",
     "choices": ["Trend break → first test → second test", "First test → front-run 2nd test → trend break & next MM",
                 "Second test → first test → gap fill", "HWB → 61.8% → 123%"], "a": 1,
     "ex": "Always First Test → Front-Run 2nd Test → Trend Break & Next MM."},
    {"t": "mc", "q": "On the /ES, the first-test setup uses which stop / front-run / first target?",
     "choices": ["−12 / +4 / +6", "−6 / +2 / +2", "−8 / +4 / +4", "−4 / +2 / +6"], "a": 1,
     "ex": "ES: stop −6, front-run +2, first target +2, then move stop to −4 (reduced-risk)."},
    {"t": "mc", "q": "Which extension can you place a limit order on?",
     "choices": ["The first extension off a new anchor", "Any extension", "Only after the first extension is observed", "None — extensions aren't traded"], "a": 2,
     "ex": "HARD GATE: the FIRST extension is observe-only (it can fail). Trade subsequent ones."},
    {"t": "mc", "q": "A 61.8% failure that turns into a RETEST of the prior high/low (double top) means:",
     "choices": ["Enter aggressively", "Do NOT trust the next MM — skip it", "Double your size", "Switch to the daily chart"], "a": 1,
     "ex": "Double-top/bottom risk → skip the pullback after the retest."},
    {"t": "mc", "q": "If the ES opens LESS than 10 points from the fill, the historical fill rate is about:",
     "choices": ["9–26%", "50%", "77–79%", "100%"], "a": 2,
     "ex": "<10 pts → ~77–79% fill. >10 pts (professional gap-and-go) → ~9–26%; let it run."},
    {"t": "mc", "q": "The two US trading sessions (with the open no-trade zone) are:",
     "choices": ["09:30–16:00 straight", "08:00–11:30 and 13:30–16:00 ET (no-trade 09:30–10:00)",
                 "10:00–15:00 ET only", "24h"], "a": 1,
     "ex": "08:00–11:30 & 13:30–16:00 ET; no-trade 09:30–10:00; no new trades after 15:45."},
    {"t": "mc", "q": "The Distance Formula target distance equals:",
     "choices": ["|50% − 61.8%|", "|50% − 38.2%| = 0.118·R", "the full 123% move", "|0% − 100%|"], "a": 1,
     "ex": "Distance Formula = gap between the 50% and 38.2% lines = 0.118·R. A fast scalp / first target."},
    {"t": "mc", "q": "A professional gap on the ES is defined as an open of:",
     "choices": ["≥5 points", "≥10 points from prior close", "any gap up", "≥20 points"], "a": 1,
     "ex": "Professional gap = ≥10 pts from prior close (amateur <10 fills within the first hour)."},
    {"t": "mc", "q": "The trend order Halsey describes is:",
     "choices": ["extensions → traditionals → straight up", "traditionals → extensions → straight up (61.8% failure flips it)",
                 "random", "gap fill → trend day → close"], "a": 1,
     "ex": "Traditionals → extensions → straight up; a 61.8% failure flips the trend."},
    {"t": "mc", "q": "An up trend day requires all three of:",
     "choices": ["gap / volume / news", "professional gap up + positive breadth + positive tick divergence",
                 "high VIX + low tick + gap", "DP above open + gap + Monday"], "a": 1,
     "ex": "Pro gap up + positive breadth + positive tick divergence."},
]

SEQUENCES = [
    ["The three entry strategies (in order)",
     ["First Test", "Front-Run of the 2nd Test", "Trend Break & Next MM"]],
    ["Trend order",
     ["Traditional MMs", "Extensions", "Straight up", "61.8% failure → trend flips"]],
    ["Gap-fill workflow (all must be YES)",
     ["Not opt-ex / rollover-Thu / 1st-of-month", "Time within 08:00–09:30 ET",
      "Price inside the ±10-pt band", "A large S/R points toward the fill"]],
    ["A series of traditional MMs",
     ["Enter limit at 50% HWB", "Price runs to 123% target", "Re-anchor at the last low", "Next pullback → repeat"]],
]

CHART_IMG = (f'<img src="data:image/png;base64,{chart_b64}" alt="ES MM chart" '
             f'style="width:100%;border:1px solid #30363d;border-radius:10px">' if chart_b64 else "")

CSS = """
:root{--bg:#0d1117;--card:#161b22;--chip:#30363d;--fg:#e6edf3;--muted:#8b949e;
 --blue:#58a6ff;--green:#3fb950;--red:#f85149;--yellow:#e3b341}
*{box-sizing:border-box}body{margin:0;background:var(--bg);color:var(--fg);
 font:14px/1.55 -apple-system,Segoe UI,Roboto,sans-serif}
header{position:sticky;top:0;background:var(--bg);border-bottom:1px solid var(--chip);
 padding:12px 22px;display:flex;align-items:center;gap:10px;z-index:10;flex-wrap:wrap}
header h1{font-size:16px;margin:0}a{color:var(--blue);text-decoration:none}
.tabs{display:flex;gap:6px;flex-wrap:wrap}
.tab{padding:6px 14px;border:1px solid var(--chip);border-radius:8px;cursor:pointer;font-size:13px;
 font-weight:600;color:var(--muted);background:var(--card)}
.tab.on{color:var(--blue);border-color:var(--blue);background:#58a6ff14}
.wrap{max-width:920px;margin:0 auto;padding:20px 22px 80px}
.pane{display:none}.pane.on{display:block}
.card{background:var(--card);border:1px solid var(--chip);border-radius:12px;padding:18px 20px;margin:12px 0}
h2{font-size:16px;margin:6px 0 12px}h3{font-size:14px;color:var(--blue);margin:16px 0 6px}
.btn{display:inline-block;font-size:13px;font-weight:600;border-radius:8px;padding:7px 16px;
 border:1px solid var(--blue);color:var(--blue);background:#58a6ff12;cursor:pointer}
.btn:hover{background:#58a6ff26}.btn.sec{border-color:var(--chip);color:var(--muted);background:var(--card)}
.muted{color:var(--muted)}.big{font-size:22px;font-weight:700}
/* flashcard */
.fc{perspective:1200px;height:210px;cursor:pointer}
.fcInner{position:relative;width:100%;height:100%;transition:transform .5s;transform-style:preserve-3d}
.fc.flip .fcInner{transform:rotateY(180deg)}
.fcFace{position:absolute;inset:0;backface-visibility:hidden;border:1px solid var(--chip);
 border-radius:12px;background:var(--card);display:flex;align-items:center;justify-content:center;
 padding:26px;text-align:center}
.fcBack{transform:rotateY(180deg);font-size:14px;line-height:1.6}
.fcFront{font-size:22px;font-weight:700;color:var(--yellow)}
.row{display:flex;gap:10px;align-items:center;flex-wrap:wrap;margin-top:12px}
/* quiz */
.choice{display:block;width:100%;text-align:left;border:1px solid var(--chip);background:var(--card);
 color:var(--fg);border-radius:9px;padding:10px 14px;margin:7px 0;cursor:pointer;font-size:13.5px}
.choice:hover{border-color:var(--blue)}.choice.correct{border-color:var(--green);background:#3fb95018}
.choice.wrong{border-color:var(--red);background:#f8514918}
.ex{margin-top:10px;padding:10px 14px;border-left:3px solid var(--blue);background:#58a6ff10;
 border-radius:0 8px 8px 0;font-size:13px}
input[type=number],input[type=text]{background:#0d1117;border:1px solid var(--chip);color:var(--fg);
 border-radius:8px;padding:8px 12px;font-size:14px;width:160px}
input[type=range]{width:100%}
.progress{height:6px;background:var(--chip);border-radius:3px;overflow:hidden;margin:8px 0}
.progress i{display:block;height:100%;background:var(--blue);width:0}
.score{font-size:15px;font-weight:700}
/* seq */
.seqitem{border:1px solid var(--chip);background:var(--card);border-radius:9px;padding:10px 14px;margin:6px 0;
 cursor:grab;font-size:13.5px;display:flex;gap:10px;align-items:center}
.seqitem .h{color:var(--muted);font-family:ui-monospace,Consolas,monospace}
.seqitem.ok{border-color:var(--green)}.seqitem.no{border-color:var(--red)}
svg text{font:12px ui-monospace,Consolas,monospace}
label.lb{font-size:12px;color:var(--muted);display:block;margin:10px 0 2px}
"""

JS = r"""
var FC=__FC__, QUIZ=__QUIZ__, SEQ=__SEQ__;
var L=6420.75, H=7699.75;  // fixed leg for numeric quiz
function levels(L,H,mode){var R=H-L; return mode==='short' ? {
  start:H, fail:H-0.382*R, hwb:H-0.5*R, d382:H-0.618*R, end:L, tgt:L-0.236*R
}:{ start:L, fail:L+0.382*R, hwb:L+0.5*R, d382:L+0.618*R, end:H, tgt:H+0.236*R };}

function tab(id){var i;var ts=document.querySelectorAll('.tab');for(i=0;i<ts.length;i++)ts[i].classList.toggle('on',ts[i].dataset.p===id);
 var ps=document.querySelectorAll('.pane');for(i=0;i<ps.length;i++)ps[i].classList.toggle('on',ps[i].id===id);
 if(id==='calc')drawMM();}

var fcI=0;
function fcRender(){var c=FC[fcI];document.getElementById('fcFront').innerHTML=c[0];
 document.getElementById('fcBack').innerHTML=c[1];document.getElementById('fcCard').classList.remove('flip');
 document.getElementById('fcNum').textContent=(fcI+1)+' / '+FC.length;}
function fcFlip(){document.getElementById('fcCard').classList.toggle('flip');}
function fcNext(d){fcI=(fcI+d+FC.length)%FC.length;fcRender();}
function fcShuffle(){for(var i=FC.length-1;i>0;i--){var j=Math.floor(Math.random()*(i+1));var t=FC[i];FC[i]=FC[j];FC[j]=t;}fcI=0;fcRender();}

var qi=0,qScore=0,qDone=false;
function quizRender(){var q=QUIZ[qi];qDone=false;
 document.getElementById('qProg').style.width=((qi)/QUIZ.length*100)+'%';
 document.getElementById('qCount').textContent='Q '+(qi+1)+' / '+QUIZ.length;
 document.getElementById('qScore').textContent='Score '+qScore;
 var h='<div class="big" style="font-size:16px;margin-bottom:6px">'+q.q+'</div>';
 if(q.t==='mc'){h+='<div id="qChoices">';for(var k=0;k<q.choices.length;k++)h+='<button class="choice" onclick="ansMC('+k+')">'+q.choices[k]+'</button>';h+='</div>';}
 else{var v=levels(L,H,'long')[q.fn];h+='<div class="row"><input type="number" step="0.01" id="qNum" placeholder="price"><button class="btn" onclick="ansNum('+v+')">Check</button></div>';}
 h+='<div id="qEx"></div><div class="row" id="qNextRow" style="display:none"><button class="btn" onclick="quizNext()">Next &rarr;</button></div>';
 document.getElementById('qBody').innerHTML=h;}
function ansMC(k){if(qDone)return;qDone=true;var q=QUIZ[qi];var bs=document.querySelectorAll('#qChoices .choice');
 bs[q.a].classList.add('correct');if(k!==q.a){bs[k].classList.add('wrong');}else qScore++;
 showEx(q.ex);}
function ansNum(v){if(qDone)return;var q=QUIZ[qi];var g=parseFloat(document.getElementById('qNum').value);
 var ok=!isNaN(g)&&Math.abs(g-v)<=q.tol;qDone=true;if(ok)qScore++;
 showEx((ok?'<b style="color:#3fb950">Correct.</b> ':'<b style="color:#f85149">Not quite &mdash; '+v.toFixed(2)+'.</b> ')+q.ex);}
function showEx(t){document.getElementById('qEx').innerHTML='<div class="ex">'+t+'</div>';
 document.getElementById('qScore').textContent='Score '+qScore;document.getElementById('qNextRow').style.display='flex';}
function quizNext(){if(qi<QUIZ.length-1){qi++;quizRender();}else{
 document.getElementById('qBody').innerHTML='<div class="big">Done &mdash; '+qScore+' / '+QUIZ.length+'</div>'+
 '<p class="muted">'+(qScore===QUIZ.length?'Perfect. You know the mechanics cold.':qScore>=QUIZ.length*0.7?'Solid. Review the misses.':'Keep drilling &mdash; re-read the flashcards.')+'</p>'+
 '<div class="row"><button class="btn" onclick="quizStart()">Restart</button></div>';
 document.getElementById('qProg').style.width='100%';}}
function quizStart(){qi=0;qScore=0;quizRender();}

function drawMM(){var mode=document.querySelector('input[name=mmMode]:checked').value;
 var l=parseFloat(document.getElementById('mmL').value),h=parseFloat(document.getElementById('mmH').value);
 if(isNaN(l)||isNaN(h)||h<=l){document.getElementById('mmSvg').innerHTML='<text x=10 y=20 fill="#f85149">need H &gt; L</text>';return;}
 var Lv=levels(l,h,mode);
 var rows=[['123% TARGET',Lv.tgt,'#3fb950'],['0% (end)',Lv.end,'#8b949e'],['38.2%',Lv.d382,'#8b949e'],
  ['50% HWB (entry)',Lv.hwb,'#e3b341'],['61.8% FAILURE',Lv.fail,'#f85149'],['100% (start)',Lv.start,'#8b949e']];
 var vals=rows.map(function(r){return r[1];});var mx=Math.max.apply(null,vals),mn=Math.min.apply(null,vals);
 var W=760,Hh=340,pad=30;function y(p){return pad+(mx-p)/(mx-mn)*(Hh-2*pad);}
 var s='<rect x=0 y=0 width='+W+' height='+Hh+' fill="#0d1117"/>';
 rows.forEach(function(r){var yy=y(r[1]).toFixed(1);s+='<line x1=60 y1='+yy+' x2='+(W-210)+' y2='+yy+' stroke="'+r[2]+'" stroke-width="'+((r[0].indexOf('HWB')>=0||r[0].indexOf('FAIL')>=0||r[0].indexOf('TARGET')>=0)?2:1)+'"/>';
  s+='<text x='+(W-205)+' y='+(+yy+4)+' fill="'+r[2]+'" font-weight="bold">'+r[0]+'  '+r[1].toFixed(2)+'</text>';});
 document.getElementById('mmSvg').innerHTML=s;
 var R=h-l;document.getElementById('mmInfo').innerHTML='Range R = '+R.toFixed(2)+' pts &nbsp;&middot;&nbsp; '+
  (mode==='long'?'LONG (low&rarr;high)':'SHORT (high&rarr;low)')+' &nbsp;&middot;&nbsp; risk (entry&rarr;fail) = '+Math.abs(Lv.hwb-Lv.fail).toFixed(2)+
  ' &nbsp;&middot;&nbsp; reward (entry&rarr;target) = '+Math.abs(Lv.tgt-Lv.hwb).toFixed(2);}

function seqInit(){var wrap=document.getElementById('seqWrap');var html='';
 SEQ.forEach(function(s,si){var order=s[1].map(function(x,i){return i;});
  for(var i=order.length-1;i>0;i--){var j=(i*7+si*3+3)%(i+1);var t=order[i];order[i]=order[j];order[j]=t;}
  html+='<div class="card"><h3>'+s[0]+'</h3><div id="seq'+si+'">';
  order.forEach(function(oi){html+='<div class="seqitem" draggable="true" data-i="'+oi+'"><span class="h">&equiv;</span>'+s[1][oi]+'</div>';});
  html+='</div><div class="row"><button class="btn" onclick="seqCheck('+si+')">Check order</button><span id="seqMsg'+si+'" class="muted"></span></div></div>';});
 wrap.innerHTML=html;bindDrag();}
var dragEl=null;
function bindDrag(){var items=document.querySelectorAll('.seqitem');items.forEach(function(el){
 el.ondragstart=function(){dragEl=el;};
 el.ondragover=function(e){e.preventDefault();var box=el.parentNode;if(dragEl&&dragEl!==el&&dragEl.parentNode===box){
   var kids=[].slice.call(box.children);if(kids.indexOf(dragEl)<kids.indexOf(el))box.insertBefore(dragEl,el.nextSibling);else box.insertBefore(dragEl,el);}};});}
function seqCheck(si){var box=document.getElementById('seq'+si);var kids=[].slice.call(box.children);var ok=true;
 kids.forEach(function(el,pos){var right=(+el.dataset.i)===pos;el.classList.toggle('ok',right);el.classList.toggle('no',!right);if(!right)ok=false;});
 document.getElementById('seqMsg'+si).innerHTML=ok?'<b style="color:#3fb950">Correct order &check;</b>':'<b style="color:#f85149">Not yet &mdash; keep arranging</b>';}

fcRender();quizStart();seqInit();
"""

BODY = f"""
<div class="pane on" id="flash">
 <div class="card"><h2>Flashcards &mdash; definitions</h2>
  <p class="muted">Click the card to flip. {len(FLASHCARDS)} core terms.</p>
  <div class="fc" id="fcCard" onclick="fcFlip()"><div class="fcInner">
    <div class="fcFace fcFront" id="fcFront"></div>
    <div class="fcFace fcBack" id="fcBack"></div></div></div>
  <div class="row"><button class="btn sec" onclick="fcNext(-1)">&larr; Prev</button>
   <span class="muted" id="fcNum"></span>
   <button class="btn sec" onclick="fcNext(1)">Next &rarr;</button>
   <button class="btn" onclick="fcFlip()">Flip</button>
   <button class="btn sec" onclick="fcShuffle()">Shuffle</button></div>
 </div></div>

<div class="pane" id="quiz">
 <div class="card"><div class="row" style="justify-content:space-between">
   <span class="muted" id="qCount"></span><span class="score" id="qScore"></span></div>
  <div class="progress"><i id="qProg"></i></div>
  <div id="qBody"></div></div></div>

<div class="pane" id="calc">
 <div class="card"><h2>Live measured-move calculator</h2>
  <p class="muted">Set the swing low/high and see every Halsey level compute and draw. Try both directions.</p>
  <div class="row">
   <label class="lb">Swing low L <input type="number" step="0.25" id="mmL" value="6420.75" oninput="drawMM()"></label>
   <label class="lb">Swing high H <input type="number" step="0.25" id="mmH" value="7699.75" oninput="drawMM()"></label>
   <label class="lb">Direction
    <span class="row"><label><input type="radio" name="mmMode" value="long" checked onchange="drawMM()"> long</label>
    <label><input type="radio" name="mmMode" value="short" onchange="drawMM()"> short</label></span></label>
  </div>
  <svg id="mmSvg" viewBox="0 0 760 340" style="width:100%;border:1px solid var(--chip);border-radius:10px;margin-top:10px"></svg>
  <p class="muted" id="mmInfo" style="margin-top:8px"></p>
 </div></div>

<div class="pane" id="seq">
 <p class="muted">Drag the items into the correct order, then check.</p>
 <div id="seqWrap"></div></div>

<div class="pane" id="chartd">
 <div class="card"><h2>Chart drill &mdash; read the levels</h2>
  <p class="muted">ES daily with the MM Fib on the dominant seed leg
   (6,420.75 &rarr; 7,699.75). Identify each level, then check yourself:</p>
  {CHART_IMG}
  <div class="row"><button class="btn" onclick="document.getElementById('cdA').style.display='block'">Reveal levels</button></div>
  <div id="cdA" style="display:none" class="ex">
   <b>100% start</b> 6,420.75 &middot; <b style="color:#f85149">61.8% failure</b> 6,909.33 &middot;
   <b style="color:#e3b341">50% HWB entry</b> 7,060.25 &middot; <b>0% end</b> 7,699.75 &middot;
   <b style="color:#3fb950">123% target</b> 8,001.59. Last price 7,530 never retraced to HWB
   (shallow = strong): the MM is intact and the target is unmet.</div>
 </div></div>
"""

HTML = f"""<!doctype html><html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1"><title>{TITLE}</title>
<style>{CSS}</style></head><body>
<header><h1>EminiAddict &mdash; Study &amp; Quiz</h1>
 <div class="tabs" style="margin-left:14px">
  <div class="tab on" data-p="flash" onclick="tab('flash')">Flashcards</div>
  <div class="tab" data-p="quiz" onclick="tab('quiz')">Quiz</div>
  <div class="tab" data-p="calc" onclick="tab('calc')">MM calculator</div>
  <div class="tab" data-p="seq" onclick="tab('seq')">Sequences</div>
  <div class="tab" data-p="chartd" onclick="tab('chartd')">Chart drill</div>
 </div>
 <span style="margin-left:auto"></span>
 <a href="/artifact/eminiaddict_measured_move_method">Method reference &rarr;</a></header>
<div class="wrap">{BODY}</div>
<script>{JS.replace('__FC__', json.dumps(FLASHCARDS)).replace('__QUIZ__', json.dumps(QUIZ)).replace('__SEQ__', json.dumps(SEQUENCES))}</script>
</body></html>"""

OUT.parent.mkdir(parents=True, exist_ok=True)
OUT.write_text(HTML, encoding="utf-8")
print(f"wrote {OUT}  ({round(len(HTML)/1024,1)} KB)")

cat = json.loads(CATALOG.read_text(encoding="utf-8"))
items = cat["artifacts"]
info = ("Interactive study tool for the Halsey Measured-Move method: flip-card "
        "definitions (18 terms), a scored quiz (multiple-choice + numeric level "
        "computations), a live MM-level calculator (set swing L/H, see 50%/61.8%/"
        "123% draw for long or short), drag-to-order sequence drills (entries, trend "
        "order, gap-fill workflow), and a chart-reading drill on real ES daily.")
items[:] = [a for a in items if a.get("title") != TITLE]
items.insert(0, {"title": TITLE, "url": "", "updated": DATE, "group": "EminiAddict", "info": info})
CATALOG.write_text(json.dumps(cat, indent=1, ensure_ascii=False), encoding="utf-8")
print(f"registered '{TITLE}' in catalog")
