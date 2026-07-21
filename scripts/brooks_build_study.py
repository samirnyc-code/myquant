"""Build the Brooks study deliverables from the cited corpora (no simulation):
  - docs/living/brooks_study_app.html   (interactive flashcard/quiz app)
  - docs/living/brooks_cheatsheet.html  (printable one-page reference)
Self-contained (data embedded inline). Source of truth:
  scratchpad/brooks_golden.json  (golden_rules, when_not_to_trade, memorize_10)
  docs/living/brooks_final.json  (teachings: dict theme->list)
"""
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SCR = ROOT / "scratchpad"

golden = json.load(open(SCR / "brooks_golden.json", encoding="utf-8"))
final = json.load(open(ROOT / "docs" / "living" / "brooks_final.json", encoding="utf-8"))
BOOK = {"trends": "Trends", "ranges": "Trading Ranges", "reversals": "Reversals",
        "rpcbb": "Reading Price Charts", "Reading Price Charts Bar by Bar": "Reading Price Charts"}
def bk(x): return BOOK.get(x, x or "")

gr = [{"id": f"g{i}", "rank": r.get("rank", i + 1), "rule": r["rule"], "theme": r.get("theme", ""),
       "why": r.get("why", ""), "quote": r.get("quote", ""), "pages": r.get("pages", ""), "book": bk(r.get("book", ""))}
      for i, r in enumerate(golden["golden_rules"])]
wn = [{"id": f"n{i}", "situation": r["situation"], "instead": r.get("what_instead", ""), "theme": r.get("theme", ""),
       "quote": r.get("quote", ""), "pages": r.get("pages", ""), "book": bk(r.get("book", ""))}
      for i, r in enumerate(golden["when_not_to_trade"])]
mem = [{"id": f"m{i}", "line": r["line"], "quote": r.get("quote", ""), "pages": r.get("pages", "")}
       for i, r in enumerate(golden["memorize_10"])]
lib = []
for theme, items in final["teachings"].items():
    for i, t in enumerate(items):
        lib.append({"id": f"l_{theme}_{i}", "theme": theme, "teaching": t["teaching"],
                    "quote": t.get("quote", ""), "pages": t.get("pages", ""), "book": bk(t.get("book", ""))})
DATA = {"golden": gr, "notrade": wn, "memorize": mem, "library": lib,
        "counts": {"golden": len(gr), "notrade": len(wn), "memorize": len(mem), "library": len(lib)}}
data_js = json.dumps(DATA, ensure_ascii=False)

APP = r"""<style>
:root{
 --bg:#0c1016; --panel:#141b24; --panel2:#1b2430; --ink:#e8eef6; --dim:#93a2b4; --faint:#6b7a8c;
 --line:#25303d; --gold:#e6b23a; --gold-dim:#8a6d1f; --red:#ec5b5b; --red-dim:#7d2b2b;
 --green:#45c26a; --blue:#5aa0ff; --mono:ui-monospace,"SFMono-Regular",Menlo,Consolas,monospace;
 --sans:system-ui,-apple-system,"Segoe UI",Roboto,sans-serif;
}
@media (prefers-color-scheme:light){:root{
 --bg:#eef1f5; --panel:#ffffff; --panel2:#f4f6f9; --ink:#141b24; --dim:#54636f; --faint:#8593a1;
 --line:#dbe2ea; --gold:#b1810c; --gold-dim:#e6cf94; --red:#c8352f; --red-dim:#f0c4c2; --green:#1f9a4d; --blue:#2f6fd6;
}}
:root[data-theme="dark"]{
 --bg:#0c1016; --panel:#141b24; --panel2:#1b2430; --ink:#e8eef6; --dim:#93a2b4; --faint:#6b7a8c;
 --line:#25303d; --gold:#e6b23a; --gold-dim:#8a6d1f; --red:#ec5b5b; --red-dim:#7d2b2b; --green:#45c26a; --blue:#5aa0ff;
}
:root[data-theme="light"]{
 --bg:#eef1f5; --panel:#ffffff; --panel2:#f4f6f9; --ink:#141b24; --dim:#54636f; --faint:#8593a1;
 --line:#dbe2ea; --gold:#b1810c; --gold-dim:#e6cf94; --red:#c8352f; --red-dim:#f0c4c2; --green:#1f9a4d; --blue:#2f6fd6;
}
*{box-sizing:border-box}
#bx{font-family:var(--sans);color:var(--ink);background:var(--bg);min-height:100vh;line-height:1.5;
 -webkit-font-smoothing:antialiased}
#bx .wrap{max-width:1100px;margin:0 auto;padding:0 20px}
#bx header{border-bottom:1px solid var(--line);background:linear-gradient(180deg,var(--panel),var(--bg));
 position:sticky;top:0;z-index:20;backdrop-filter:blur(6px)}
#bx .top{display:flex;align-items:center;gap:16px;padding:14px 20px;max-width:1100px;margin:0 auto;flex-wrap:wrap}
#bx .brand{display:flex;flex-direction:column;gap:2px;margin-right:auto}
#bx .brand b{font-size:19px;letter-spacing:.14em;text-transform:uppercase;font-weight:800}
#bx .brand b span{color:var(--gold)}
#bx .brand small{font-family:var(--mono);color:var(--dim);font-size:11.5px;letter-spacing:.04em}
#bx .prog{font-family:var(--mono);font-size:12px;color:var(--dim);text-align:right;line-height:1.35}
#bx .prog b{color:var(--gold);font-size:15px}
#bx .tbtn,#bx .icon{font-family:var(--mono);font-size:12.5px;letter-spacing:.06em;text-transform:uppercase;
 background:transparent;color:var(--dim);border:1px solid var(--line);border-radius:7px;padding:8px 12px;cursor:pointer;
 transition:.15s}
#bx .icon{padding:8px 10px}
#bx .tabs{display:flex;gap:8px;padding:0 20px 12px;max-width:1100px;margin:0 auto;flex-wrap:wrap}
#bx .tbtn:hover{color:var(--ink);border-color:var(--dim)}
#bx .tbtn.on{color:var(--bg);background:var(--gold);border-color:var(--gold);font-weight:700}
#bx .tbtn.on.red{background:var(--red);border-color:var(--red);color:#fff}
#bx main{padding:26px 0 80px}
#bx h2.vh{font-size:13px;letter-spacing:.16em;text-transform:uppercase;color:var(--dim);margin:0 0 4px;font-weight:700}
#bx .lead{color:var(--faint);font-size:14px;margin:0 0 20px;max-width:70ch}
#bx .chips{display:flex;gap:7px;flex-wrap:wrap;margin:0 0 20px}
#bx .chip{font-family:var(--mono);font-size:11.5px;letter-spacing:.03em;padding:5px 10px;border-radius:20px;
 border:1px solid var(--line);background:var(--panel);color:var(--dim);cursor:pointer}
#bx .chip.on{background:var(--panel2);color:var(--ink);border-color:var(--gold)}
#bx .grid{display:grid;grid-template-columns:repeat(auto-fill,minmax(320px,1fr));gap:14px}
/* flip card */
#bx .card{perspective:1400px;min-height:210px;cursor:pointer}
#bx .inner{position:relative;width:100%;height:100%;min-height:210px;transition:transform .5s;transform-style:preserve-3d}
#bx .card.flip .inner{transform:rotateY(180deg)}
#bx .face{position:absolute;inset:0;backface-visibility:hidden;border:1px solid var(--line);border-radius:12px;
 background:var(--panel);padding:18px;display:flex;flex-direction:column;gap:10px;overflow:auto}
#bx .face.back{transform:rotateY(180deg);background:var(--panel2)}
#bx .rulet{font-size:18px;font-weight:650;line-height:1.4;text-wrap:balance;margin-top:6px}
#bx .card.red .front{border-left:3px solid var(--red)}
#bx .card.gold .front{border-left:3px solid var(--gold)}
#bx .toprow{display:flex;align-items:center;gap:8px}
#bx .badge{font-family:var(--mono);font-size:10.5px;letter-spacing:.06em;text-transform:uppercase;
 padding:3px 8px;border-radius:5px;background:var(--panel2);color:var(--dim);border:1px solid var(--line)}
#bx .badge.g{color:var(--gold);border-color:var(--gold-dim)}
#bx .badge.r{color:var(--red);border-color:var(--red-dim)}
#bx .rank{font-family:var(--mono);font-size:11px;color:var(--faint);margin-left:auto}
#bx .star{margin-left:auto;font-size:17px;cursor:pointer;color:var(--faint);background:none;border:none;line-height:1}
#bx .star.on{color:var(--gold)}
#bx .why{color:var(--dim);font-size:13.5px;font-style:italic}
#bx .q{font-size:13px;color:var(--ink);border-left:2px solid var(--gold);padding-left:11px;line-height:1.55}
#bx .card.red .q{border-color:var(--red)}
#bx .cite{font-family:var(--mono);font-size:11px;color:var(--faint);letter-spacing:.03em;margin-top:auto}
#bx .fliphint{font-family:var(--mono);font-size:10.5px;color:var(--faint);letter-spacing:.05em;margin-top:auto}
#bx .instead{font-size:14px}#bx .instead b{color:var(--green)}
/* zoom-to-center */
#bx .zoom-ov{position:fixed;inset:0;z-index:100;display:flex;align-items:center;justify-content:center;
 background:rgba(4,7,11,.74);backdrop-filter:blur(3px);opacity:0;transition:opacity .35s}
#bx .zoom-ov.show{opacity:1}
#bx .zoom-wrap{width:min(560px,90vw);height:min(64vh,600px);perspective:1600px;
 transition:transform .44s cubic-bezier(.22,1,.36,1);will-change:transform}
#bx .zoom-inner{position:relative;width:100%;height:100%;transform-style:preserve-3d;transition:transform .5s;cursor:pointer}
#bx .zoom-wrap.flip .zoom-inner{transform:rotateY(180deg)}
#bx .zoom-face{position:absolute;inset:0;backface-visibility:hidden;border-radius:18px;border:1px solid var(--line);
 background:var(--panel);padding:34px 30px;display:flex;flex-direction:column;gap:18px;
 box-shadow:0 34px 90px rgba(0,0,0,.55);overflow:auto}
#bx .zoom-face.back{transform:rotateY(180deg);background:var(--panel2)}
#bx .zoom-wrap.gold .zoom-face.front{border-top:4px solid var(--gold)}
#bx .zoom-wrap.red .zoom-face.front{border-top:4px solid var(--red)}
#bx .zoom-wrap.lib .zoom-face.front{border-top:4px solid var(--blue)}
#bx .zoom-face .rulet.lib{font-size:20px;font-weight:600;line-height:1.45}
#bx .zoom-wrap.red .zoom-face .q{border-color:var(--red)}
#bx .zoom-face .rulet{font-size:26px;margin-top:2px}
#bx .zoom-face .why{font-size:16px}
#bx .zoom-face .instead{font-size:17px}
#bx .zoom-face .q{font-size:16.5px;line-height:1.62}
#bx .zoom-face .cite{font-size:12px}
#bx .zoom-face .fliphint{font-size:11px}
#bx .zoom-x{position:fixed;top:16px;right:20px;z-index:101;font-size:18px;background:var(--panel);color:var(--ink);
 border:1px solid var(--line);border-radius:10px;width:44px;height:44px;cursor:pointer}
#bx .zoom-x:hover{border-color:var(--dim)}
#bx .zoom-ctl{position:fixed;left:0;right:0;bottom:26px;z-index:101;display:flex;gap:12px;justify-content:center;padding:0 16px}
#bx .zoom-btn{font-family:var(--sans);font-size:14px;font-weight:700;letter-spacing:.02em;padding:12px 22px;border-radius:11px;
 border:1px solid var(--line);background:var(--panel);color:var(--ink);cursor:pointer;box-shadow:0 10px 28px rgba(0,0,0,.4)}
#bx .zoom-btn:hover{border-color:var(--dim);transform:translateY(-1px)}
#bx .zoom-btn.back{background:var(--gold);color:var(--bg);border-color:var(--gold)}
@media (prefers-reduced-motion:reduce){#bx .zoom-wrap,#bx .zoom-inner,#bx .zoom-ov{transition:opacity .2s}}
/* library */
#bx .search{width:100%;max-width:420px;font-family:var(--mono);font-size:13px;padding:10px 13px;border-radius:9px;
 border:1px solid var(--line);background:var(--panel);color:var(--ink);margin-bottom:20px}
#bx .lib-theme{margin:26px 0 12px;font-size:14px;letter-spacing:.06em;text-transform:uppercase;color:var(--gold);
 font-weight:700;display:flex;align-items:center;gap:10px}
#bx .lib-theme .n{font-family:var(--mono);font-size:11px;color:var(--faint);letter-spacing:0}
#bx .lib-theme::after{content:"";flex:1;height:1px;background:var(--line)}
#bx .litem{border:1px solid var(--line);border-radius:10px;background:var(--panel);padding:14px 16px;margin-bottom:10px;cursor:pointer;transition:border-color .15s,transform .15s}
#bx .litem:hover{border-color:var(--gold);transform:translateY(-1px)}
#bx .litem p{margin:0 0 8px;font-size:15px;line-height:1.5}
#bx .litem .q{font-size:12.5px;color:var(--dim)}
/* quiz */
#bx .quiz{max-width:640px;margin:0 auto;text-align:center}
#bx .qcard{border:1px solid var(--line);border-radius:16px;background:var(--panel);padding:34px 26px;min-height:280px;
 display:flex;flex-direction:column;gap:16px;justify-content:center}
#bx .qprompt{font-size:14px;color:var(--dim);letter-spacing:.04em;text-transform:uppercase;font-family:var(--mono)}
#bx .qwhy{font-size:20px;line-height:1.45;text-wrap:balance;font-weight:600}
#bx .qans{font-size:16px;color:var(--gold);line-height:1.5;border-top:1px dashed var(--line);padding-top:16px}
#bx .qbtns{display:flex;gap:12px;justify-content:center;margin-top:8px;flex-wrap:wrap}
#bx .big{font-family:var(--sans);font-size:14px;font-weight:700;padding:12px 22px;border-radius:9px;cursor:pointer;border:1px solid var(--line)}
#bx .big.reveal{background:var(--gold);color:var(--bg);border-color:var(--gold)}
#bx .big.miss{background:transparent;color:var(--red);border-color:var(--red-dim)}
#bx .big.got{background:transparent;color:var(--green);border-color:var(--green)}
#bx .qmeta{font-family:var(--mono);font-size:12px;color:var(--dim);margin-top:14px}
#bx .disc{font-family:var(--mono);font-size:11px;color:var(--faint);text-align:center;padding:30px 20px 0;border-top:1px solid var(--line);margin-top:40px;line-height:1.7}
@media (max-width:560px){#bx .grid{grid-template-columns:1fr}}
</style>
<div id="bx">
<header>
 <div class="top">
  <div class="brand"><b>THE BROOKS <span>CODEX</span></b>
   <small>Al Brooks price action &mdash; cited playbook, no simulation</small></div>
  <div class="prog" id="prog"></div>
  <button class="icon" id="themeBtn" title="toggle theme">◑</button>
 </div>
 <div class="tabs" id="tabs"></div>
</header>
<main class="wrap" id="main"></main>
<div class="disc" id="disc"></div>
</div>
<script>
const DATA=__DATA__;
const TABS=[["golden","Golden Rules"],["notrade","When NOT to Trade"],["library","Full Library"],["quiz","Quiz"]];
const LS="brooks_codex_mastered_v1";
let mastered=new Set(JSON.parse(localStorage.getItem(LS)||"[]"));
let view="golden", gfilter="ALL", q="", quiz=null;
const $=s=>document.querySelector(s), el=(t,c,h)=>{const e=document.createElement(t);if(c)e.className=c;if(h!=null)e.innerHTML=h;return e;};
const esc=s=>(s||"").replace(/[&<>]/g,m=>({"&":"&amp;","<":"&lt;",">":"&gt;"}[m]));
function saveM(){localStorage.setItem(LS,JSON.stringify([...mastered]));drawProg();}
function drawProg(){const total=DATA.golden.length+DATA.notrade.length;
 $("#prog").innerHTML=`<b>${mastered.size}</b> / ${total} mastered<br><span style="color:var(--faint)">${DATA.counts.library} teachings · ${DATA.counts.golden} rules · ${DATA.counts.notrade} red-flags</span>`;}
function tabs(){const t=$("#tabs");t.innerHTML="";TABS.forEach(([k,lab])=>{
 const b=el("button","tbtn"+(view===k?" on":"")+(k==="notrade"?" red":""),lab);
 b.onclick=()=>{view=k;q="";render();};t.appendChild(b);});}
function themeInit(){const b=$("#themeBtn");b.onclick=()=>{const cur=document.documentElement.getAttribute("data-theme");
 const nx=cur==="dark"?"light":cur==="light"?"dark":(matchMedia("(prefers-color-scheme:dark)").matches?"light":"dark");
 document.documentElement.setAttribute("data-theme",nx);};}
function updateStars(id){document.querySelectorAll('.star[data-id="'+id+'"]').forEach(s=>{
 const on=mastered.has(id);s.classList.toggle("on",on);s.innerHTML=on?"★":"☆";});}
function fillFaces(front,back,item,kind,big){
 const gold=kind==="gold",red=kind==="red",lib=kind==="lib";
 const top=el("div","toprow");
 top.appendChild(el("span","badge "+(red?"r":"g"),esc(item.theme||(gold?"RULE":red?"AVOID":"TEACHING"))));
 if(gold&&item.rank)top.appendChild(el("span","rank","#"+item.rank));
 if(!lib){const star=el("button","star"+(mastered.has(item.id)?" on":""),mastered.has(item.id)?"★":"☆");
  star.dataset.id=item.id;
  star.onclick=e=>{e.stopPropagation();mastered.has(item.id)?mastered.delete(item.id):mastered.add(item.id);
   updateStars(item.id);saveM();};
  top.appendChild(star);}
 front.appendChild(top);
 const main=gold?item.rule:red?item.situation:item.teaching;
 front.appendChild(el("div","rulet"+(lib?" lib":""),esc(main)));
 if(gold&&item.why)front.appendChild(el("div","why",esc(item.why)));
 else if(red&&item.instead)front.appendChild(el("div","instead","<b>Instead:</b> "+esc(item.instead)));
 front.appendChild(el("div","fliphint",big?"tap card or ⟲ Flip · Space or ↩ to send back":"click to enlarge ⤢"));
 back.appendChild(el("div","q","&ldquo;"+esc(item.quote)+"&rdquo;"));
 back.appendChild(el("div","cite",[item.book,item.pages?("p."+item.pages):""].filter(Boolean).join(" · ")));
}
function flipCard(item,kind){
 const card=el("div","card "+(kind==="red"?"red":"gold"));
 const inner=el("div","inner");
 const front=el("div","face front");
 const back=el("div","face back");
 fillFaces(front,back,item,kind,false);
 inner.appendChild(front);inner.appendChild(back);card.appendChild(inner);
 card.onclick=()=>openZoom(item,kind,card);
 return card;
}
let zoomOpen=null;
function openZoom(item,kind,originEl){
 if(zoomOpen)return;
 const ov=el("div","zoom-ov");
 const wrap=el("div","zoom-wrap "+(kind==="red"?"red":kind==="lib"?"lib":"gold"));
 const inner=el("div","zoom-inner");
 const front=el("div","zoom-face front");const back=el("div","zoom-face back");
 fillFaces(front,back,item,kind,true);
 inner.appendChild(front);inner.appendChild(back);wrap.appendChild(inner);
 const x=el("button","zoom-x","✕");x.title="send back (Esc)";
 const ctl=el("div","zoom-ctl");
 const flipBtn=el("button","zoom-btn","⟲ Flip");
 const backBtn=el("button","zoom-btn back","Send back ↩");
 ctl.appendChild(flipBtn);ctl.appendChild(backBtn);
 ov.appendChild(wrap);ov.appendChild(x);ov.appendChild(ctl);document.getElementById("bx").appendChild(ov);
 // FLIP technique: start at the tile's position/size, animate to center
 const flyFrom=()=>{const r=originEl.getBoundingClientRect();const br=wrap.getBoundingClientRect();
  const dx=r.left+r.width/2-(br.left+br.width/2),dy=r.top+r.height/2-(br.top+br.height/2);
  return `translate(${dx}px,${dy}px) scale(${r.width/br.width},${r.height/br.height})`;};
 wrap.style.transform=flyFrom();
 requestAnimationFrame(()=>{ov.classList.add("show");wrap.style.transform="none";});
 inner.onclick=e=>{e.stopPropagation();wrap.classList.toggle("flip");};
 let closing=false;
 function close(){if(closing)return;closing=true;
  wrap.classList.remove("flip");
  requestAnimationFrame(()=>{wrap.style.transform=flyFrom();ov.classList.remove("show");});
  setTimeout(()=>{ov.remove();zoomOpen=null;document.removeEventListener("keydown",onkey);},460);}
 function onkey(e){
  if(e.key==="Escape"||e.key===" "||e.key==="Spacebar"){e.preventDefault();close();}
  else if(e.key==="Enter"||e.key==="f"||e.key==="F"){e.preventDefault();wrap.classList.toggle("flip");}}
 ov.onclick=e=>{if(e.target===ov)close();};
 x.onclick=e=>{e.stopPropagation();close();};
 flipBtn.onclick=e=>{e.stopPropagation();wrap.classList.toggle("flip");};
 backBtn.onclick=e=>{e.stopPropagation();close();};
 document.addEventListener("keydown",onkey);
 zoomOpen={close};
}
function viewGolden(){const m=$("#main");m.innerHTML="";
 m.appendChild(el("h2","vh","Golden Rules · memorize these"));
 m.appendChild(el("p","lead","39 rules distilled from 1,390 teachings across the four books, ranked by importance. Flip any card for Brooks' verbatim words and page. Star what you've mastered — it's saved on this device."));
 const themes=["ALL",...new Set(DATA.golden.map(r=>r.theme))];
 const ch=el("div","chips");themes.forEach(t=>{const c=el("div","chip"+(gfilter===t?" on":""),t);
  c.onclick=()=>{gfilter=t;viewGolden();};ch.appendChild(c);});m.appendChild(ch);
 const g=el("div","grid");DATA.golden.filter(r=>gfilter==="ALL"||r.theme===gfilter)
  .sort((a,b)=>a.rank-b.rank).forEach(r=>g.appendChild(flipCard(r,"gold")));m.appendChild(g);}
function viewNotrade(){const m=$("#main");m.innerHTML="";
 m.appendChild(el("h2","vh","When NOT to trade · the more important list"));
 m.appendChild(el("p","lead","Brooks: knowing when to stand aside protects more money than any entry makes. 27 red-flag situations — flip for the exact quote."));
 const g=el("div","grid");DATA.notrade.forEach(r=>g.appendChild(flipCard(r,"red")));m.appendChild(g);}
function viewLibrary(){const m=$("#main");m.innerHTML="";
 const nTh=new Set(DATA.library.map(t=>t.theme)).size;
 m.appendChild(el("h2","vh",`Full library · ${DATA.counts.library.toLocaleString()} teachings · ${nTh} themes`));
 const s=el("input","search");s.placeholder="search teachings, quotes…";s.value=q;
 s.oninput=e=>{q=e.target.value.toLowerCase();renderLib();};m.appendChild(s);
 const host=el("div","",""); host.id="libhost"; m.appendChild(host); renderLib();}
function renderLib(){const host=$("#libhost");if(!host)return;host.innerHTML="";
 const themes=[...new Set(DATA.library.map(t=>t.theme))];
 themes.forEach(th=>{const items=DATA.library.filter(t=>t.theme===th &&
   (!q||(t.teaching+" "+t.quote).toLowerCase().includes(q)));
  if(!items.length)return;
  host.appendChild(el("div","lib-theme",esc(th)+` <span class="n">${items.length}</span>`));
  items.forEach(t=>{const c=el("div","litem");c.appendChild(el("p",null,esc(t.teaching)));
   if(t.quote)c.appendChild(el("div","q","&ldquo;"+esc(t.quote)+"&rdquo;"));
   c.appendChild(el("div","cite",[t.book,t.pages?("p."+t.pages):""].filter(Boolean).join(" · ")));
   c.onclick=()=>openZoom(t,"lib",c);host.appendChild(c);});});}
function startQuiz(){const pool=[...DATA.golden.map(r=>({id:r.id,prompt:r.why||"Recall the rule",ans:r.rule,q:r.quote,pages:r.pages,book:r.book,kind:"RULE"})),
  ...DATA.notrade.map(r=>({id:r.id,prompt:"When do you stand aside?",ans:r.situation,q:r.quote,pages:r.pages,book:r.book,kind:"AVOID"}))];
 const unmastered=pool.filter(p=>!mastered.has(p.id));
 const queue=(unmastered.length?unmastered:pool).map(x=>x).sort(()=>Math.random()-0.5);
 quiz={queue,i:0,revealed:false,score:0,seen:0};viewQuiz();}
function viewQuiz(){const m=$("#main");m.innerHTML="";
 m.appendChild(el("h2","vh","Quiz · active recall"));
 if(!quiz){const b=el("button","big reveal","Start quiz");b.onclick=startQuiz;
  const w=el("div","quiz");w.appendChild(el("p","lead","Read the cue, say the rule out loud, then reveal. It draws your un-mastered cards first."));
  w.appendChild(b);m.appendChild(w);return;}
 if(quiz.i>=quiz.queue.length){const w=el("div","quiz");
  w.appendChild(el("div","qwhy",`Round complete — ${quiz.score}/${quiz.seen} recalled.`));
  const b=el("button","big reveal","Go again");b.onclick=startQuiz;w.appendChild(el("div","qbtns")).appendChild(b);
  m.appendChild(w);return;}
 const it=quiz.queue[quiz.i];const w=el("div","quiz");const c=el("div","qcard");
 c.appendChild(el("div","qprompt",it.kind==="AVOID"?"When NOT to trade":"Cue"));
 c.appendChild(el("div","qwhy",esc(it.prompt)));
 if(quiz.revealed){c.appendChild(el("div","qans",esc(it.ans)));
  c.appendChild(el("div","q","&ldquo;"+esc(it.q)+"&rdquo;"));
  c.appendChild(el("div","cite",[it.book,it.pages?("p."+it.pages):""].filter(Boolean).join(" · ")));}
 w.appendChild(c);
 const bt=el("div","qbtns");
 if(!quiz.revealed){const r=el("button","big reveal","Reveal");r.onclick=()=>{quiz.revealed=true;viewQuiz();};bt.appendChild(r);}
 else{const g=el("button","big got","✓ Got it");g.onclick=()=>{mastered.add(it.id);saveM();quiz.score++;quiz.seen++;quiz.i++;quiz.revealed=false;viewQuiz();};
  const mi=el("button","big miss","✗ Missed");mi.onclick=()=>{mastered.delete(it.id);saveM();quiz.seen++;quiz.i++;quiz.revealed=false;viewQuiz();};
  bt.appendChild(g);bt.appendChild(mi);}
 w.appendChild(bt);
 w.appendChild(el("div","qmeta",`card ${quiz.i+1} / ${quiz.queue.length} · recalled ${quiz.score}`));
 m.appendChild(w);}
function render(){tabs();
 if(view==="golden")viewGolden();else if(view==="notrade")viewNotrade();
 else if(view==="library")viewLibrary();else viewQuiz();
 window.scrollTo(0,0);}
$("#disc").innerHTML="Every rule, red-flag and teaching is a verbatim excerpt from Al Brooks' four books (Trends · Trading Ranges · Reversals · Reading Price Charts Bar by Bar), with page citations. This is a study aid, not trading advice.";
drawProg();themeInit();render();
</script>"""

CHEAT = r"""<style>
:root{--bg:#fff;--ink:#12181f;--dim:#5a6875;--line:#d8dee6;--gold:#a8760a;--red:#c0322c;--green:#1f8f48;
 --mono:ui-monospace,Menlo,Consolas,monospace;--sans:system-ui,-apple-system,"Segoe UI",Roboto,sans-serif;}
@media (prefers-color-scheme:dark){:root{--bg:#0e1319;--ink:#e7edf4;--dim:#94a2b2;--line:#28323d;--gold:#e6b23a;--red:#ec5b5b;--green:#45c26a;}}
:root[data-theme="light"]{--bg:#fff;--ink:#12181f;--dim:#5a6875;--line:#d8dee6;--gold:#a8760a;--red:#c0322c;--green:#1f8f48;}
:root[data-theme="dark"]{--bg:#0e1319;--ink:#e7edf4;--dim:#94a2b2;--line:#28323d;--gold:#e6b23a;--red:#ec5b5b;--green:#45c26a;}
*{box-sizing:border-box}
body{background:var(--bg)}
#cs{background:var(--bg);color:var(--ink);font-family:var(--sans);line-height:1.42;padding:26px;max-width:1000px;margin:0 auto}
#cs .hd{display:flex;align-items:baseline;gap:14px;border-bottom:2px solid var(--ink);padding-bottom:10px;margin-bottom:16px;flex-wrap:wrap}
#cs h1{font-size:22px;letter-spacing:.12em;text-transform:uppercase;margin:0;font-weight:800}
#cs h1 span{color:var(--gold)}
#cs .hd small{font-family:var(--mono);color:var(--dim);font-size:11px;margin-left:auto}
#cs .cols{column-count:2;column-gap:26px}
@media (max-width:720px){#cs .cols{column-count:1}}
#cs section{break-inside:avoid;margin-bottom:16px;border:1px solid var(--line);border-radius:8px;overflow:hidden}
#cs h2{font-size:12px;letter-spacing:.1em;text-transform:uppercase;margin:0;padding:8px 12px;font-weight:800;color:#fff}
#cs section.red h2{background:var(--red)}#cs section.gold h2{background:var(--gold)}#cs section.mem h2{background:var(--ink);color:var(--bg)}
#cs ol,#cs ul{margin:0;padding:8px 12px 10px 30px}
#cs li{font-size:12.5px;margin:0 0 7px;line-height:1.4}
#cs li b{color:var(--red)}
#cs .mem li{font-size:13.5px;font-weight:600;margin-bottom:9px}
#cs .pg{font-family:var(--mono);font-size:10px;color:var(--dim)}
#cs .foot{font-family:var(--mono);font-size:10px;color:var(--dim);margin-top:12px;border-top:1px solid var(--line);padding-top:8px}
#cs li{cursor:pointer;border-radius:6px;padding:2px 4px;margin-left:-4px;transition:background .12s}
#cs li:hover{background:rgba(230,178,58,.12)}
.csov{position:fixed;inset:0;z-index:100;display:flex;align-items:center;justify-content:center;background:rgba(4,7,11,.84);opacity:0;transition:opacity .25s}
.csov.show{opacity:1}
.cscard{width:min(640px,92vw);perspective:1400px;cursor:pointer}
.cscard .in{position:relative;min-height:min(60vh,380px);transform-style:preserve-3d;transition:transform .5s}
.cscard.flip .in{transform:rotateY(180deg)}
.cscard .f{position:absolute;inset:0;backface-visibility:hidden;border:1px solid var(--line);border-radius:14px;background:var(--bg);color:var(--ink);padding:28px;display:flex;flex-direction:column;gap:16px;overflow:auto;font-family:var(--sans)}
.cscard .f.b{transform:rotateY(180deg)}
.cscard .kk{font-family:var(--mono);font-size:10.5px;letter-spacing:.08em;text-transform:uppercase;color:var(--gold)}
.cscard .kk.r{color:var(--red)}
.cscard .t{font-size:21px;font-weight:700;line-height:1.45}
.cscard .qq{font-size:15.5px;line-height:1.6;border-left:3px solid var(--gold);padding-left:13px;font-style:italic}
.cscard .ii{font-size:15px;border-left:3px solid var(--green);padding-left:13px}
.cscard .ct{font-family:var(--mono);font-size:11px;color:var(--dim);margin-top:auto}
.cscard .hint{font-family:var(--mono);font-size:10.5px;color:var(--dim);margin-top:auto}
.csx{position:fixed;top:16px;right:20px;z-index:101;font-size:18px;background:var(--bg);color:var(--ink);border:1px solid var(--line);border-radius:10px;width:44px;height:44px;cursor:pointer}
@media print{#cs{padding:0;font-size:11px}@page{margin:12mm}#cs .hd small,#cs .foot{display:block}.csov,.csx{display:none}}
</style>
<div id="cs">
 <div class="hd"><h1>The Brooks <span>Codex</span> — Desk Card</h1>
  <small>Al Brooks · Trends · Ranges · Reversals · RPCBB</small></div>
 <section class="mem"><h2>★ The 10 to tattoo on your brain</h2><ol id="mem"></ol></section>
 <div class="cols">
  <section class="red"><h2>✕ When NOT to Trade</h2><ul id="nt"></ul></section>
  <section class="gold"><h2>◆ Golden Rules</h2><ol id="gr"></ol></section>
 </div>
 <div class="foot" id="ft"></div>
</div>
<script>
const D=__DATA__;const esc=s=>(s||"").replace(/[&<>]/g,m=>({"&":"&amp;","<":"&lt;",">":"&gt;"}[m]));
const pg=x=>x?` <span class="pg">p.${esc(x)}</span>`:"";
const BOOKPDF={"Trends":"trends.pdf","Trading Ranges":"ranges.pdf","Reversals":"reversals.pdf","Reading Price Charts":"rpcbb.pdf","RPCBB":"rpcbb.pdf"};
const pdfLink=(book,pages)=>{const f=BOOKPDF[book];if(!f||!pages)return"";
 const m=String(pages).match(/\d+/);if(!m)return"";
 return ' <a href="books/'+f+'#page='+m[0]+'" target="_blank" title="Open this page in the book PDF" style="text-decoration:none">📖</a>';};
const GS=D.golden.slice().sort((a,b)=>a.rank-b.rank);
document.getElementById("mem").innerHTML=D.memorize.map((m,i)=>`<li data-i="${i}">${esc(m.line)}${pg(m.pages)}</li>`).join("");
document.getElementById("nt").innerHTML=D.notrade.map((n,i)=>`<li data-i="${i}"><b>${esc(n.situation)}</b>${n.instead?" — "+esc(n.instead):""}${pg(n.pages)}</li>`).join("");
document.getElementById("gr").innerHTML=GS.map((g,i)=>`<li data-i="${i}">${esc(g.rule)}${pg(g.pages)}</li>`).join("");
document.getElementById("ft").innerHTML=`${D.counts.golden} golden rules · ${D.counts.notrade} red-flags · distilled from 1,390 cited teachings. Study aid, not trading advice. Click any line for Brooks' own words.`;
/* pop a line to the center; click flips to Brooks' verbatim words, ✕/Esc/backdrop sends it back */
function pop(item,kind){
 const front=kind==="mem"?item.line:kind==="nt"?item.situation:item.rule;
 const label=kind==="mem"?"★ Memorize":kind==="nt"?"✕ When NOT to trade":"◆ Golden rule";
 const extra=(kind==="nt"&&item.instead)?`<div class="ii"><b>Instead:</b> ${esc(item.instead)}</div>`:
  (kind==="gr"&&item.why)?`<div class="ii">${esc(item.why)}</div>`:"";
 const quote=item.quote?`<div class="qq">&ldquo;${esc(item.quote)}&rdquo;</div>`:`<div class="qq">(no verbatim quote captured)</div>`;
 const cite=[item.book,item.pages?("p."+item.pages):""].filter(Boolean).join(" · ");
 const ov=document.createElement("div");ov.className="csov";
 const card=document.createElement("div");card.className="cscard";
 card.innerHTML=`<div class="in"><div class="f"><div class="kk${kind==="nt"?" r":""}">${label}</div><div class="t">${esc(front)}</div>${extra}<div class="hint">click for Brooks' words ↦</div></div>`+
  `<div class="f b"><div class="kk${kind==="nt"?" r":""}">${label} · Brooks' words</div>${quote}<div class="ct">${esc(cite)}${pdfLink(item.book,item.pages)}</div></div></div>`;
 const x=document.createElement("button");x.className="csx";x.textContent="✕";
 ov.appendChild(card);ov.appendChild(x);document.body.appendChild(ov);
 requestAnimationFrame(()=>ov.classList.add("show"));
 card.onclick=e=>{e.stopPropagation();if(e.target.closest&&e.target.closest("a"))return;card.classList.toggle("flip");};
 const k=e=>{if(e.key==="Escape")close();};
 const close=()=>{ov.classList.remove("show");setTimeout(()=>ov.remove(),250);document.removeEventListener("keydown",k);};
 ov.onclick=close;x.onclick=close;document.addEventListener("keydown",k);
}
document.querySelectorAll("#mem li").forEach(li=>li.onclick=()=>pop(D.memorize[+li.dataset.i],"mem"));
document.querySelectorAll("#nt li").forEach(li=>li.onclick=()=>pop(D.notrade[+li.dataset.i],"nt"));
document.querySelectorAll("#gr li").forEach(li=>li.onclick=()=>pop(GS[+li.dataset.i],"gr"));
</script>"""

app_html = APP.replace("__DATA__", data_js)
cheat_html = CHEAT.replace("__DATA__", data_js)
(ROOT / "docs" / "living" / "brooks_study_app.html").write_text(app_html, encoding="utf-8")
(ROOT / "docs" / "living" / "brooks_cheatsheet.html").write_text(cheat_html, encoding="utf-8")
print("wrote brooks_study_app.html (%d bytes) + brooks_cheatsheet.html (%d bytes)" % (len(app_html), len(cheat_html)))
print("counts:", DATA["counts"])
