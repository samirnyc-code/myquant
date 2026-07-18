"""Build the MAIN Brooks study app from brooks_app_data.json (self-contained).
Tabs: Setups (cards + matched figures) · Rules (78 tiered, Core-15 filter) ·
Don't Trade · Library (1390) · Quiz (Name-that-chart / Recall / Core-15).
Fly-to-center zoom on every card & figure. Captions always shown (no mismatch).
Output: docs/living/brooks_app.html  + brooks_app_standalone.html
"""
import base64
import json
from pathlib import Path
ROOT = Path(r"c:\Users\Admin\myquant")
SCR = Path(r"C:\Users\Admin\AppData\Local\Temp\claude\c--Users-Admin-myquant\f04593f3-53f8-4ab9-9690-dd0509e339a3\scratchpad")
D = json.load(open(SCR / "brooks_app_data.json", encoding="utf-8"))

# enrich setup figures with the Figure Explorer's full explanation + full-res file
fidx = {x['id']: x for x in json.load(open(ROOT / 'docs' / 'living' / 'brooks_codex' / 'figure_index.json', encoding='utf-8'))}
for s in D['setups']:
    for f in (s.get('figures') or []):
        e = fidx.get(f['id'])
        if e:
            f['text'] = e.get('explanation', '')
            f['file'] = e.get('file', '')

# the MTR setup had no matched figures; attach the Reversals book's MTR sequence
# (caption-verified: setup, trading it, LH/HL structure, TL-break caveat, test of extreme)
MTR_FIGS = ['RVPI_5', 'RV1_1', 'RV3_1', 'RV3_2', 'RV3_3', 'RV9_12']
for s in D['setups']:
    if s['name'].startswith('Major Trend Reversal') and not (s.get('figures') or []):
        figs = []
        for fid in MTR_FIGS:
            e = fidx.get(fid)
            if not e:
                continue
            figs.append({'id': fid, 'caption': e['caption'], 'fig_num': e['fig_num'],
                         'book': e['book'], 'page': str(e.get('printed_page') or e.get('pdf_page') or ''),
                         'text': e.get('explanation', ''), 'file': e.get('file', '')})
            if fid not in D['images']:
                raw = (ROOT / 'docs' / 'living' / 'brooks_codex' / e['file']).read_bytes()
                D['images'][fid] = base64.b64encode(raw).decode()
        s['figures'] = figs

data_js = json.dumps(D, ensure_ascii=False)

APP = r"""<style>
:root{--bg:#0c1016;--panel:#141b24;--panel2:#1b2430;--ink:#e8eef6;--dim:#93a2b4;--faint:#6b7a8c;--line:#25303d;
 --gold:#e6b23a;--gold2:#8a6d1f;--red:#ec5b5b;--red2:#7d2b2b;--green:#45c26a;--blue:#5aa0ff;
 --mono:ui-monospace,Menlo,Consolas,monospace;--sans:system-ui,-apple-system,"Segoe UI",Roboto,sans-serif;}
@media(prefers-color-scheme:light){:root{--bg:#eef1f5;--panel:#fff;--panel2:#f4f6f9;--ink:#141b24;--dim:#54636f;--faint:#8593a1;--line:#dbe2ea;--gold:#b1810c;--gold2:#e6cf94;--red:#c8352f;--red2:#f0c4c2;--green:#1f9a4d;--blue:#2f6fd6;}}
:root[data-theme="light"]{--bg:#eef1f5;--panel:#fff;--panel2:#f4f6f9;--ink:#141b24;--dim:#54636f;--faint:#8593a1;--line:#dbe2ea;--gold:#b1810c;--gold2:#e6cf94;--red:#c8352f;--red2:#f0c4c2;--green:#1f9a4d;--blue:#2f6fd6;}
:root[data-theme="dark"]{--bg:#0c1016;--panel:#141b24;--panel2:#1b2430;--ink:#e8eef6;--dim:#93a2b4;--faint:#6b7a8c;--line:#25303d;--gold:#e6b23a;--gold2:#8a6d1f;--red:#ec5b5b;--red2:#7d2b2b;--green:#45c26a;--blue:#5aa0ff;}
*{box-sizing:border-box}
#bx{font-family:var(--sans);color:var(--ink);background:var(--bg);min-height:100vh;line-height:1.5;-webkit-font-smoothing:antialiased}
#bx .wrap{max-width:1120px;margin:0 auto;padding:0 20px}
#bx header{border-bottom:1px solid var(--line);background:linear-gradient(180deg,var(--panel),var(--bg));position:sticky;top:0;z-index:30;backdrop-filter:blur(6px)}
#bx .top{display:flex;align-items:center;gap:16px;padding:13px 20px;max-width:1120px;margin:0 auto;flex-wrap:wrap}
#bx .brand{margin-right:auto}
#bx .brand b{font-size:19px;letter-spacing:.14em;text-transform:uppercase;font-weight:800}
#bx .brand b span{color:var(--gold)}
#bx .brand small{display:block;font-family:var(--mono);color:var(--dim);font-size:11px;letter-spacing:.03em;margin-top:2px}
#bx .prog{font-family:var(--mono);font-size:12px;color:var(--dim);text-align:right}#bx .prog b{color:var(--gold);font-size:15px}
#bx .icon{font-family:var(--mono);background:transparent;color:var(--dim);border:1px solid var(--line);border-radius:8px;padding:8px 10px;cursor:pointer}
#bx .tabs{display:flex;gap:8px;padding:0 20px 11px;max-width:1120px;margin:0 auto;flex-wrap:wrap}
#bx .tbtn{font-family:var(--mono);font-size:12.5px;letter-spacing:.05em;text-transform:uppercase;background:transparent;color:var(--dim);border:1px solid var(--line);border-radius:7px;padding:8px 13px;cursor:pointer;transition:.15s}
#bx .tbtn:hover{color:var(--ink);border-color:var(--dim)}
#bx .tbtn.on{color:var(--bg);background:var(--gold);border-color:var(--gold);font-weight:700}
#bx .tbtn.on.red{background:var(--red);border-color:var(--red);color:#fff}
#bx main{padding:26px 0 90px}
#bx h2.vh{font-size:13px;letter-spacing:.16em;text-transform:uppercase;color:var(--dim);margin:0 0 4px;font-weight:700}
#bx .lead{color:var(--faint);font-size:14px;margin:0 0 18px;max-width:74ch}
#bx .chips{display:flex;gap:7px;flex-wrap:wrap;margin:0 0 20px}
#bx .chip{font-family:var(--mono);font-size:11.5px;padding:5px 11px;border-radius:20px;border:1px solid var(--line);background:var(--panel);color:var(--dim);cursor:pointer}
#bx .chip.on{background:var(--panel2);color:var(--ink);border-color:var(--gold)}
#bx .chip.core.on{border-color:var(--gold);color:var(--gold)}
/* rule/teaching flip cards */
#bx .grid{display:grid;grid-template-columns:repeat(auto-fill,minmax(320px,1fr));gap:14px}
#bx .card{perspective:1400px;min-height:212px;cursor:pointer}
#bx .inner{position:relative;width:100%;min-height:212px;transition:transform .5s;transform-style:preserve-3d}
#bx .card.flip .inner{transform:rotateY(180deg)}
#bx .face{position:absolute;inset:0;backface-visibility:hidden;border:1px solid var(--line);border-radius:12px;background:var(--panel);padding:18px;display:flex;flex-direction:column;gap:10px;overflow:auto}
#bx .face.back{transform:rotateY(180deg);background:var(--panel2)}
#bx .rulet{font-size:17.5px;font-weight:650;line-height:1.4;text-wrap:balance;margin-top:4px}
#bx .rulet.lib{font-size:15.5px;font-weight:600}
#bx .toprow{display:flex;align-items:center;gap:8px}
#bx .badge{font-family:var(--mono);font-size:10.5px;letter-spacing:.05em;text-transform:uppercase;padding:3px 8px;border-radius:5px;background:var(--panel2);color:var(--dim);border:1px solid var(--line)}
#bx .badge.g{color:var(--gold);border-color:var(--gold2)}#bx .badge.r{color:var(--red);border-color:var(--red2)}
#bx .badge.core{background:var(--gold);color:var(--bg);border-color:var(--gold);font-weight:700}
#bx .tier{font-family:var(--mono);font-size:10px;color:var(--faint);margin-left:auto;text-transform:uppercase;letter-spacing:.06em}
#bx .star{margin-left:auto;font-size:17px;cursor:pointer;color:var(--faint);background:none;border:none}
#bx .star.on{color:var(--gold)}
#bx .why{color:var(--dim);font-size:13.5px;font-style:italic}
#bx .q{font-size:13px;border-left:2px solid var(--gold);padding-left:11px;line-height:1.55}
#bx .card.red .q{border-color:var(--red)}#bx .card.lib .q{border-color:var(--blue)}
#bx .cite{font-family:var(--mono);font-size:11px;color:var(--faint);margin-top:auto}
#bx .fliphint{font-family:var(--mono);font-size:10.5px;color:var(--faint);margin-top:auto}
#bx .instead{font-size:14px}#bx .instead b{color:var(--green)}
/* setup cards */
#bx .setup{border:1px solid var(--line);border-radius:16px;background:var(--panel);overflow:hidden;margin-bottom:20px}
#bx .shead{padding:18px 22px;border-bottom:1px solid var(--line);background:linear-gradient(180deg,var(--panel2),var(--panel))}
#bx .grade{font-family:var(--mono);font-weight:800;font-size:12px;color:var(--bg);background:var(--gold);padding:3px 9px;border-radius:6px}
#bx .grade.a{background:var(--blue)}
#bx .setup h3{font-size:21px;margin:8px 0 5px}
#bx .one{color:var(--dim);font-size:14.5px;max-width:70ch}
#bx .sbody{padding:20px 22px;display:grid;grid-template-columns:1fr;gap:20px}
#bx .cxt{display:grid;grid-template-columns:84px 1fr;gap:6px 14px;font-size:13.5px}
#bx .cxt .k{font-family:var(--mono);font-size:10.5px;letter-spacing:.05em;text-transform:uppercase;color:var(--faint);padding-top:2px}
#bx .cxt .v b{color:var(--green)}
#bx .sh{font-size:12px;letter-spacing:.1em;text-transform:uppercase;color:var(--gold);margin:0 0 10px;font-weight:800}
#bx .sh.red{color:var(--red)}
#bx ul.rl{list-style:none;margin:0;padding:0;display:flex;flex-direction:column;gap:11px}
#bx ul.rl li{border-left:3px solid var(--gold);padding-left:12px;cursor:pointer;border-radius:0 6px 6px 0;transition:background .12s}
#bx ul.rl li:hover{background:rgba(230,178,58,.08)}
#bx ul.rl li.tell{border-color:var(--red)}
#bx ul.rl li.tell:hover{background:rgba(236,91,91,.08)}
#bx ul.rl .rt{font-size:14px;font-weight:600}
#bx ul.rl .qt{font-size:12px;color:var(--dim);font-style:italic;margin-top:3px}
#bx ul.rl .pg{font-family:var(--mono);font-style:normal;color:var(--faint);font-size:10.5px}
#bx .figs{display:grid;grid-template-columns:repeat(auto-fill,minmax(190px,1fr));gap:12px}
#bx figure{margin:0;cursor:zoom-in;border:1px solid var(--line);border-radius:10px;overflow:hidden;background:var(--panel2);transition:border-color .15s,transform .15s}
#bx figure:hover{border-color:var(--gold);transform:translateY(-2px)}
#bx figure img{width:100%;display:block}
#bx figcaption{font-family:var(--mono);font-size:10.5px;color:var(--faint);padding:8px 10px;line-height:1.4}
#bx figcaption b{color:var(--blue)}
#bx .nofig{font-family:var(--mono);font-size:11px;color:var(--faint)}
/* library */
#bx .search{width:100%;max-width:430px;font-family:var(--mono);font-size:13px;padding:10px 13px;border-radius:9px;border:1px solid var(--line);background:var(--panel);color:var(--ink);margin-bottom:20px}
#bx .lib-theme{margin:24px 0 12px;font-size:14px;letter-spacing:.05em;text-transform:uppercase;color:var(--gold);font-weight:700;display:flex;align-items:center;gap:10px}
#bx .lib-theme .n{font-family:var(--mono);font-size:11px;color:var(--faint)}
#bx .lib-theme::after{content:"";flex:1;height:1px;background:var(--line)}
#bx .litem{border:1px solid var(--line);border-radius:10px;background:var(--panel);padding:14px 16px;margin-bottom:10px;cursor:pointer;transition:border-color .15s,transform .15s}
#bx .litem:hover{border-color:var(--gold);transform:translateY(-1px)}
#bx .litem p{margin:0 0 8px;font-size:15px;line-height:1.5}
#bx .litem .q{font-size:12.5px;color:var(--dim)}
/* quiz */
#bx .quiz{max-width:720px;margin:0 auto}
#bx .qmodes{display:flex;gap:10px;justify-content:center;flex-wrap:wrap;margin-bottom:22px}
#bx .qmode{font-family:var(--sans);font-size:13.5px;font-weight:700;padding:11px 18px;border-radius:10px;border:1px solid var(--line);background:var(--panel);color:var(--ink);cursor:pointer}
#bx .qmode:hover{border-color:var(--gold)}
#bx .qcard{border:1px solid var(--line);border-radius:16px;background:var(--panel);padding:26px;text-align:center;display:flex;flex-direction:column;gap:16px}
#bx .qcard img{max-width:100%;border-radius:10px;border:1px solid var(--line)}
#bx .qprompt{font-family:var(--mono);font-size:12px;letter-spacing:.06em;text-transform:uppercase;color:var(--dim)}
#bx .qwhy{font-size:19px;line-height:1.45;text-wrap:balance;font-weight:600}
#bx .opts{display:grid;grid-template-columns:1fr 1fr;gap:10px}
@media(max-width:560px){#bx .opts{grid-template-columns:1fr}}
#bx .opt{font-family:var(--sans);font-size:14px;padding:12px 14px;border-radius:9px;border:1px solid var(--line);background:var(--panel2);color:var(--ink);cursor:pointer;text-align:left}
#bx .opt:hover{border-color:var(--dim)}
#bx .opt.right{background:rgba(69,194,106,.16);border-color:var(--green);color:var(--green);font-weight:700}
#bx .opt.wrong{background:rgba(236,91,91,.14);border-color:var(--red);color:var(--red)}
#bx .qans{font-size:15px;color:var(--gold);border-top:1px dashed var(--line);padding-top:14px}
#bx .big{font-family:var(--sans);font-size:14px;font-weight:700;padding:12px 22px;border-radius:9px;cursor:pointer;border:1px solid var(--line)}
#bx .big.reveal{background:var(--gold);color:var(--bg);border-color:var(--gold)}
#bx .big.got{color:var(--green);border-color:var(--green);background:transparent}
#bx .big.miss{color:var(--red);border-color:var(--red2);background:transparent}
#bx .qbtns{display:flex;gap:12px;justify-content:center;flex-wrap:wrap}
#bx .qmeta{font-family:var(--mono);font-size:12px;color:var(--dim);text-align:center;margin-top:8px}
/* zoom */
#bx .zov{position:fixed;inset:0;z-index:100;display:flex;align-items:center;justify-content:center;background:rgba(4,7,11,.82);backdrop-filter:blur(3px);opacity:0;transition:opacity .32s}
#bx .zov.show{opacity:1}
#bx .zwrap{display:flex;gap:16px;align-items:flex-start;justify-content:center;max-width:96vw;max-height:90vh;transition:transform .42s cubic-bezier(.22,1,.36,1);will-change:transform}
#bx .zimgbox{flex:1 1 auto;min-width:0;display:flex;flex-direction:column;align-items:center}
#bx .zwrap img{max-width:100%;max-height:82vh;object-fit:contain;border-radius:12px;border:1px solid var(--line);box-shadow:0 30px 80px rgba(0,0,0,.6);display:block}
#bx .zpan{flex:0 0 420px;max-width:36vw;max-height:82vh;overflow-y:auto;overscroll-behavior:contain;background:var(--panel);border:1px solid var(--line);border-radius:12px;padding:18px 20px;text-align:left}
#bx .zpan h4{margin:0 0 10px;font-size:16px;color:var(--gold);line-height:1.4}
#bx .zpan .ztext{font-size:14.5px;line-height:1.68;white-space:pre-line;color:var(--ink)}
#bx .zpan .zcite{font-family:var(--mono);font-size:11px;color:var(--faint);margin-top:12px}
@media(max-width:980px){#bx .zwrap{flex-direction:column;align-items:center}#bx .zpan{flex:0 0 auto;max-width:92vw;max-height:30vh}}
#bx .zcap{font-family:var(--mono);font-size:12px;color:#cfd8e3;margin-top:12px;text-align:center;max-width:760px}
#bx .zcap b{color:var(--blue)}
#bx .zx{position:fixed;top:16px;right:20px;z-index:101;font-size:18px;background:var(--panel);color:var(--ink);border:1px solid var(--line);border-radius:10px;width:44px;height:44px;cursor:pointer}
#bx .zlens{right:72px}
#bx .zlens.on{background:var(--gold);color:#0c1016}
#bx .lens{position:fixed;z-index:120;width:364px;height:364px;border-radius:50%;border:2px solid var(--gold);box-shadow:0 6px 28px rgba(0,0,0,.55);background-repeat:no-repeat;background-color:#fff;pointer-events:none;display:none}
#bx .zbig{width:min(660px,92vw);perspective:1400px;cursor:pointer}
#bx .zbig .inner{min-height:min(72vh,440px)}
#bx .zbig .face{padding:26px}
#bx .zbig .rulet{font-size:22px}
#bx .zbig .rulet.lib{font-size:19px}
#bx .zbig .q{font-size:15.5px}
#bx .zbig .why,#bx .zbig .instead{font-size:15px}
#bx .hublink{font-family:var(--mono);font-size:12px;color:var(--dim);text-decoration:none;border:1px solid var(--line);border-radius:8px;padding:9px 11px}
#bx .hublink:hover{color:var(--ink);border-color:var(--dim)}
#bx .disc{font-family:var(--mono);font-size:11px;color:var(--faint);text-align:center;padding:28px 20px 0;border-top:1px solid var(--line);margin-top:36px;line-height:1.7}
@media(prefers-reduced-motion:reduce){#bx .inner,#bx .zwrap,#bx .zov{transition:opacity .2s}}
</style>
<div id="bx">
<header>
 <div class="top">
  <div class="brand"><b>THE BROOKS <span>CODEX</span></b><small>Al Brooks price action · four books · cited · no simulation</small></div>
  <div class="prog" id="prog"></div>
  <a class="hublink" id="hubLink" href="index.html" target="_top">← Codex hub</a>
  <button class="icon" id="themeBtn" title="theme">◑</button>
 </div>
 <div class="tabs" id="tabs"></div>
</header>
<main class="wrap" id="main"></main>
<div class="disc" id="disc"></div>
</div>
<script>
const DATA=__DATA__;
const IMG=DATA.images;
const TABS=[["setups","Setups"],["rules","Golden Rules"],["notrade","When NOT to Trade"],["library","Library"],["quiz","Quiz"]];
const LS="brooks_codex_v2";
let mastered=new Set(JSON.parse(localStorage.getItem(LS)||"[]"));
let view="setups",rfilter="core",gfilter="ALL",libTheme="ALL",q="",quiz=null;
const $=s=>document.querySelector(s),el=(t,c,h)=>{const e=document.createElement(t);if(c)e.className=c;if(h!=null)e.innerHTML=h;return e;};
const esc=s=>(s||"").replace(/[&<>]/g,m=>({"&":"&amp;","<":"&lt;",">":"&gt;"}[m]));
const src=id=>IMG[id]?("data:image/jpeg;base64,"+IMG[id]):"";
const BOOKPDF={"Trends":"trends.pdf","Trading Ranges":"ranges.pdf","Reversals":"reversals.pdf","Reading Price Charts":"rpcbb.pdf","RPCBB":"rpcbb.pdf"};
function pdfLink(book,pages){const f=BOOKPDF[book];if(!f||!pages)return"";
 const m=String(pages).match(/\d+/);if(!m)return"";
 return ' <a class="pdfjump" href="books/'+f+'#page='+m[0]+'" target="_blank" title="Open this page in the book PDF">📖</a>';}
function saveM(){localStorage.setItem(LS,JSON.stringify([...mastered]));drawProg();}
function drawProg(){const tot=DATA.rules.length+DATA.notrade.length;
 $("#prog").innerHTML=`<b>${mastered.size}</b>/${tot} mastered · ${DATA.counts.figures_embedded} figures`;}
function tabs(){const t=$("#tabs");t.innerHTML="";TABS.forEach(([k,l])=>{const b=el("button","tbtn"+(view===k?" on":"")+(k==="notrade"?" red":""),l);b.onclick=()=>{view=k;q="";quiz=null;render();};t.appendChild(b);});}
function themeInit(){$("#themeBtn").onclick=()=>{const c=document.documentElement.getAttribute("data-theme");
 const n=c==="dark"?"light":c==="light"?"dark":(matchMedia("(prefers-color-scheme:dark)").matches?"light":"dark");
 document.documentElement.setAttribute("data-theme",n);};}
function updateStars(id){document.querySelectorAll('.star[data-id="'+id+'"]').forEach(s=>{const on=mastered.has(id);s.classList.toggle("on",on);s.innerHTML=on?"★":"☆";});}
/* ---- image zoom (fly to center) ---- */
let zoomOn=false;
function zoomImg(imgEl,caption,extra){
 if(zoomOn)return;zoomOn=true;
 const ov=el("div","zov");const wrap=el("div","zwrap");
 const box=el("div","zimgbox");
 const big=new Image();
 if(extra&&extra.file){big.onerror=()=>{big.onerror=null;big.src=imgEl.src;};big.src=extra.file;}
 else big.src=imgEl.src;
 box.appendChild(big);wrap.appendChild(box);
 if(extra&&extra.text){
  const p=el("div","zpan");
  if(caption)p.appendChild(el("h4",null,caption));
  p.appendChild(el("div","ztext",esc(extra.text)));
  if(extra.cite)p.appendChild(el("div","zcite",esc(extra.cite)+pdfLink(extra.book,extra.pages)));
  wrap.appendChild(p);
 }else if(caption)box.appendChild(el("div","zcap",caption));
 const x=el("button","zx","✕");
 ov.appendChild(wrap);ov.appendChild(x);document.getElementById("bx").appendChild(ov);
 const lens=el("div","lens");ov.appendChild(lens);let lzz=2.5,lon=false;
 const lb=el("button","zx zlens","🔎");lb.title="Lens — hover to magnify, wheel to adjust";
 lb.onclick=e=>{e.stopPropagation();lon=!lon;lb.classList.toggle("on",lon);if(!lon)lens.style.display="none";};
 ov.appendChild(lb);
 const mv=e=>{if(!lon||!big.naturalWidth){lens.style.display="none";return;}
  const r=big.getBoundingClientRect();
  const s=Math.min(r.width/big.naturalWidth,r.height/big.naturalHeight);
  const dw=big.naturalWidth*s,dh=big.naturalHeight*s;
  const ox=r.left+(r.width-dw)/2,oy=r.top+(r.height-dh)/2;
  const lx=e.clientX-ox,ly=e.clientY-oy;
  if(lx<0||ly<0||lx>dw||ly>dh){lens.style.display="none";return;}
  const R=182;lens.style.display="block";
  lens.style.left=(e.clientX-R)+"px";lens.style.top=(e.clientY-R)+"px";
  lens.style.backgroundImage='url("'+big.src+'")';
  lens.style.backgroundSize=(dw*lzz)+"px "+(dh*lzz)+"px";
  lens.style.backgroundPosition=(R-lx*lzz)+"px "+(R-ly*lzz)+"px";};
 big.addEventListener("mousemove",mv);
 big.addEventListener("mouseleave",()=>{lens.style.display="none";});
 /* deep zoom + pan (lens off): wheel zooms toward the cursor, drag pans, dblclick resets */
 let sc=1,tx=0,ty=0,drag=null;
 big.style.transformOrigin="0 0";
 const apt=()=>{big.style.transform=(sc===1&&!tx&&!ty)?"":`translate(${tx}px,${ty}px) scale(${sc})`;
  big.style.cursor=sc>1?(drag?"grabbing":"grab"):"auto";};
 ov.addEventListener("wheel",e=>{e.preventDefault();
  if(lon){lzz=Math.min(6,Math.max(1.5,lzz*(e.deltaY<0?1.15:1/1.15)));mv(e);return;}
  const r=big.getBoundingClientRect();
  if(e.clientX<r.left||e.clientX>r.right||e.clientY<r.top||e.clientY>r.bottom)return;
  const ns=Math.min(8,Math.max(1,sc*(e.deltaY<0?1.2:1/1.2)));
  const px=(e.clientX-r.left)/sc,py=(e.clientY-r.top)/sc;
  tx=e.clientX-(r.left-tx)-px*ns;ty=e.clientY-(r.top-ty)-py*ns;sc=ns;
  if(sc===1){tx=0;ty=0;}
  apt();},{passive:false});
 big.addEventListener("mousedown",e=>{if(lon||sc===1)return;e.preventDefault();drag={x:e.clientX,y:e.clientY,tx,ty};apt();});
 window.addEventListener("mousemove",e=>{if(!drag)return;tx=drag.tx+e.clientX-drag.x;ty=drag.ty+e.clientY-drag.y;apt();});
 window.addEventListener("mouseup",()=>{if(drag){drag=null;apt();}});
 big.addEventListener("dblclick",e=>{e.preventDefault();sc=1;tx=0;ty=0;apt();});
 const from=()=>{const r=imgEl.getBoundingClientRect(),b=wrap.getBoundingClientRect();
  return `translate(${r.left+r.width/2-(b.left+b.width/2)}px,${r.top+r.height/2-(b.top+b.height/2)}px) scale(${Math.max(0.05,r.width/b.width)})`;};
 wrap.style.transform=from();
 requestAnimationFrame(()=>{ov.classList.add("show");wrap.style.transform="none";});
 let closing=false;
 const close=()=>{if(closing)return;closing=true;requestAnimationFrame(()=>{wrap.style.transform=from();ov.classList.remove("show");});
  setTimeout(()=>{ov.remove();zoomOn=false;document.removeEventListener("keydown",k);},460);};
 const k=e=>{if(e.key==="Escape"||e.key===" "){e.preventDefault();close();}};
 ov.onclick=e=>{if(e.target===ov||e.target===x)close();};
 x.onclick=close;document.addEventListener("keydown",k);
}
function figThumb(f){
 const fig=el("figure");
 if(src(f.id)){const im=new Image();im.src=src(f.id);im.alt=esc(f.caption);fig.appendChild(im);}
 const cap=`Fig ${esc(f.fig_num)} — ${esc(f.caption)}`;
 fig.appendChild(el("figcaption",null,`<b>${cap}</b><br>${esc(f.book)}${f.page?" · p."+esc(f.page):""}`));
 fig.onclick=()=>zoomImg(fig.querySelector("img"),`Figure ${esc(f.fig_num)} — ${esc(f.caption)}`,
  {text:f.text||"",file:f.file||"",book:f.book,pages:f.page,cite:`Brooks, ${f.book||""}${f.page?", p."+f.page:""}`});
 return fig;
}
/* ---- flip card zoom (rules/teachings) ---- */
let cardZoom=null;
function fillFaces(front,back,item,kind){
 const gold=kind==="gold",red=kind==="red",lib=kind==="lib";
 const top=el("div","toprow");
 const core=gold&&item.tier==="core";
 top.appendChild(el("span","badge "+(core?"core":red?"r":"g"),esc(core?"CORE":(item.theme||(gold?"RULE":red?"AVOID":"TEACHING")))));
 if(gold&&item.theme&&!core)top.appendChild(el("span","tier",esc(item.tier||"")));
 if(!lib&&item.id){const st=el("button","star"+(mastered.has(item.id)?" on":""),mastered.has(item.id)?"★":"☆");st.dataset.id=item.id;
  st.onclick=e=>{e.stopPropagation();mastered.has(item.id)?mastered.delete(item.id):mastered.add(item.id);updateStars(item.id);saveM();};top.appendChild(st);}
 front.appendChild(top);
 front.appendChild(el("div","rulet"+(lib?" lib":""),esc(gold?item.rule:red?item.situation:item.teaching)));
 if(gold&&item.why)front.appendChild(el("div","why",esc(item.why)));
 else if(red&&item.what_instead)front.appendChild(el("div","instead","<b>Instead:</b> "+esc(item.what_instead)));
 front.appendChild(el("div","fliphint","click for Brooks' words ↦"));
 back.appendChild(el("div","q","&ldquo;"+esc(item.quote)+"&rdquo;"));
 back.appendChild(el("div","cite",esc([item.book,item.pages?("p."+item.pages):""].filter(Boolean).join(" · "))+pdfLink(item.book,item.pages)));
}
function flipCard(item,kind,inPlace){
 const card=el("div","card "+kind);const inner=el("div","inner");
 const f=el("div","face front"),b=el("div","face back");
 fillFaces(f,b,item,kind);inner.appendChild(f);inner.appendChild(b);card.appendChild(inner);
 card.onclick=e=>{if(e.target.closest&&e.target.closest("a"))return;
  if(inPlace)card.classList.toggle("flip");else zoomFlip(item,kind);};
 return card;
}
/* pop a tile to the center of the screen; click flips it, ✕/Esc/backdrop sends it back */
function zoomFlip(item,kind){
 const ov=el("div","zov");const w=el("div","zwrap");
 const card=flipCard(item,kind,true);card.className+=" zbig";
 w.appendChild(card);const x=el("button","zx","✕");
 ov.appendChild(w);ov.appendChild(x);document.getElementById("bx").appendChild(ov);
 requestAnimationFrame(()=>ov.classList.add("show"));
 const close=()=>{ov.classList.remove("show");setTimeout(()=>ov.remove(),300);document.removeEventListener("keydown",k);};
 const k=e=>{if(e.key==="Escape")close();};
 ov.onclick=e=>{if(e.target===ov||e.target===w||e.target===x)close();};
 x.onclick=close;document.addEventListener("keydown",k);
}
/* ---- views ---- */
function ruleList(items,cls){return items.map(it=>{
 const rule=esc(it.rule||it.tell||"");const q=esc(it.quote||"");
 const cite=[it.book,it.pages?("p."+it.pages):""].filter(Boolean).join(" · ");
 return `<li class="${cls}"><div class="rt">${rule}</div><div class="qt">&ldquo;${q}&rdquo; <span class="pg">${esc(cite)}</span>${pdfLink(it.book,it.pages)}</div></li>`;
}).join("");}
function viewSetups(){const m=$("#main");m.innerHTML="";
 m.appendChild(el("h2","vh","The setups · context, entry, stop, management, traps + Brooks' own charts"));
 m.appendChild(el("p","lead","Every setup with its must-know rules, its don't-trade tells, and Brooks' actual book figures — click any chart to enlarge. Grades are Brooks' own emphasis."));
 const gorder=["A+","A","A-","B+","B","C"];
 const grades=[...new Set(DATA.setups.map(s=>s.grade||"?"))].sort((a,b)=>{
  const ia=gorder.indexOf(a),ib=gorder.indexOf(b);
  return (ia<0?99:ia)-(ib<0?99:ib)||a.localeCompare(b);});
 const gch=el("div","chips");
 [["ALL","All grades"],...grades.map(g=>[g,g])].forEach(([k,l])=>{
  const c=el("div","chip"+(gfilter===k?" on":""),esc(l));
  c.onclick=()=>{gfilter=k;viewSetups();};gch.appendChild(c);});
 m.appendChild(gch);
 DATA.setups.filter(s=>gfilter==="ALL"||(s.grade||"?")===gfilter).forEach(s=>{
  const card=el("div","setup");
  const h=el("div","shead");
  h.innerHTML=`<span class="grade ${s.grade==='A'?'a':''}">${esc(s.grade||'')}</span>`+
   `<h3>${esc(s.name)}</h3><div class="one">${esc(s.one_liner)}</div>`;
  card.appendChild(h);
  const bd=el("div","sbody");
  const cxt=el("div","cxt");
  [["Context",s.context],["Entry",s.entry],["Stop",s.stop],["Manage",s.management]].forEach(([k,v])=>{
   if(v){cxt.appendChild(el("div","k",k));cxt.appendChild(el("div","v",esc(v)));}});
  bd.appendChild(cxt);
  if(s.must_know_rules&&s.must_know_rules.length){const d=el("div");d.innerHTML=`<div class="sh">Must-know rules</div><ul class="rl">${ruleList(s.must_know_rules,'rule')}</ul>`;
   d.querySelectorAll("li").forEach((li,i)=>{const it=s.must_know_rules[i];
    li.onclick=e=>{if(e.target.closest("a"))return;zoomFlip({rule:it.rule||it.tell,why:it.why,quote:it.quote,book:it.book,pages:it.pages,theme:"MUST-KNOW"},"gold");};});
   bd.appendChild(d);}
  if(s.dont_trade_tells&&s.dont_trade_tells.length){const d=el("div");d.innerHTML=`<div class="sh red">Don't trade it when…</div><ul class="rl">${ruleList(s.dont_trade_tells,'tell')}</ul>`;
   d.querySelectorAll("li").forEach((li,i)=>{const it=s.dont_trade_tells[i];
    li.onclick=e=>{if(e.target.closest("a"))return;zoomFlip({situation:it.tell||it.rule,what_instead:it.what_instead,quote:it.quote,book:it.book,pages:it.pages},"red");};});
   bd.appendChild(d);}
  const fd=el("div");fd.innerHTML=`<div class="sh">Brooks' own charts</div>`;
  if(s.figures&&s.figures.length){const fg=el("div","figs");s.figures.forEach(f=>fg.appendChild(figThumb(f)));fd.appendChild(fg);}
  else fd.appendChild(el("div","nofig","(no clearly-matching book figure — none shown rather than risk a mismatch)"));
  bd.appendChild(fd);
  card.appendChild(bd);m.appendChild(card);
 });}
function viewRules(){const m=$("#main");m.innerHTML="";
 m.appendChild(el("h2","vh","Golden rules · "+DATA.rules.length+" tiered, cited"));
 m.appendChild(el("p","lead","Start with the Core 15, then Important, then Supporting. Filter by tier or theme. Flip any card for Brooks' verbatim words + page; star what you've mastered."));
 const themes=[...new Set(DATA.rules.map(r=>r.theme))].sort();
 const filters=[["core","Core 15"],["important","Important"],["supporting","Supporting"],["ALL","All"],...themes.map(t=>[t,t])];
 const ch=el("div","chips");filters.forEach(([k,l])=>{const c=el("div","chip"+(rfilter===k?" on":"")+(k==="core"?" core":""),l);c.onclick=()=>{rfilter=k;viewRules();};ch.appendChild(c);});m.appendChild(ch);
 const g=el("div","grid");
 DATA.rules.filter(r=>rfilter==="ALL"?true:(r.tier===rfilter||r.theme===rfilter))
  .forEach(r=>g.appendChild(flipCard(r,"gold")));m.appendChild(g);}
function viewNotrade(){const m=$("#main");m.innerHTML="";
 m.appendChild(el("h2","vh","When NOT to trade · protects more than any entry makes"));
 m.appendChild(el("p","lead",DATA.notrade.length+" red-flag situations. Flip for the exact Brooks quote."));
 const g=el("div","grid");DATA.notrade.forEach(r=>g.appendChild(flipCard(r,"red")));m.appendChild(g);}
function viewLibrary(){const m=$("#main");m.innerHTML="";
 const nTh=Object.keys(DATA.teachings).length;
 m.appendChild(el("h2","vh",`Library · ${DATA.counts.teachings.toLocaleString()} teachings · ${nTh} themes`));
 const s=el("input","search");s.placeholder="search teachings, quotes…";s.value=q;s.oninput=e=>{q=e.target.value.toLowerCase();renderLib();};m.appendChild(s);
 const themes=Object.keys(DATA.teachings).sort();
 const ch=el("div","chips");[["ALL","All themes"],...themes.map(t=>[t,t])].forEach(([k,l])=>{
  const c=el("div","chip"+(libTheme===k?" on":""),esc(l));c.onclick=()=>{libTheme=k;viewLibrary();};ch.appendChild(c);});
 m.appendChild(ch);
 const host=el("div");host.id="libhost";m.appendChild(host);renderLib();}
function renderLib(){const host=$("#libhost");if(!host)return;host.innerHTML="";
 Object.keys(DATA.teachings).filter(th=>libTheme==="ALL"||th===libTheme).forEach(th=>{const items=DATA.teachings[th].filter(t=>!q||(t.teaching+" "+(t.quote||"")).toLowerCase().includes(q));
  if(!items.length)return;host.appendChild(el("div","lib-theme",esc(th)+` <span class="n">${items.length}</span>`));
  items.forEach(t=>{const c=el("div","litem");c.appendChild(el("p",null,esc(t.teaching)));
   if(t.quote)c.appendChild(el("div","q","&ldquo;"+esc(t.quote)+"&rdquo;"));
   c.appendChild(el("div","cite",esc([t.book,t.pages?("p."+t.pages):""].filter(Boolean).join(" · "))+pdfLink(t.book,t.pages)));
   c.onclick=e=>{if(e.target.closest("a"))return;zoomFlip({teaching:t.teaching,quote:t.quote,book:t.book,pages:t.pages,theme:th},"lib");};
   host.appendChild(c);});});}
/* ---- quiz ---- */
function viewQuiz(){const m=$("#main");m.innerHTML="";
 m.appendChild(el("h2","vh","Quiz · test yourself"));
 const modes=el("div","qmodes");
 [["chart","🖼 Name that chart"],["recall","🧠 Recall rules"],["core","⭐ Core-15 test"]].forEach(([k,l])=>{
  const b=el("button","qmode",l);b.onclick=()=>startQuiz(k);modes.appendChild(b);});
 m.appendChild(modes);
 const host=el("div","quiz");host.id="qhost";m.appendChild(host);
 if(quiz)renderQuiz();else host.appendChild(el("p","lead","Pick a mode. <b>Name that chart</b> shows a real Brooks figure — guess the setup. <b>Recall</b> cues you on a rule. <b>Core-15</b> drills the essentials."));
}
function startQuiz(mode){
 let items=[];
 if(mode==="chart"){items=DATA.quiz_pool.map(x=>({type:"chart",id:x.id,answer:x.answer,cite:x.cite,caption:x.caption}));}
 else{const pool=(mode==="core")?DATA.rules.filter(r=>r.tier==="core"):DATA.rules;
  items=pool.map(r=>({type:"recall",theme:r.theme||"",cueKind:r.why?"why":"quote",
   prompt:r.why||("“"+(r.quote||"").slice(0,180)+((r.quote||"").length>180?"…":"")+"”"),
   ans:r.rule,q:r.quote,cite:[r.book,r.pages?("p."+r.pages):""].filter(Boolean).join(" · "),id:r.id||("r"+Math.round(r.rank))}));}
 items=items.slice().sort(()=>Math.random()-0.5);
 quiz={mode,items,i:0,score:0,seen:0,revealed:false,picked:null};renderQuiz();
}
function renderQuiz(){const host=$("#qhost");if(!host)return;host.innerHTML="";
 if(quiz.i>=quiz.items.length){host.appendChild(el("div","qcard",`<div class="qwhy">Round done — ${quiz.score}/${quiz.seen} correct.</div>`));
  const b=el("button","big reveal","Go again");b.onclick=()=>startQuiz(quiz.mode);const bb=el("div","qbtns");bb.appendChild(b);host.appendChild(bb);return;}
 const it=quiz.items[quiz.i];const c=el("div","qcard");
 if(it.type==="chart"){
  c.appendChild(el("div","qprompt","A real Brooks book chart — which setup / concept does it illustrate?"));
  if(src(it.id)){const im=new Image();im.src=src(it.id);c.appendChild(im);}
  const opts=el("div","opts");
  let choices=[it.answer];const others=DATA.quiz_answers.filter(a=>a!==it.answer).sort(()=>Math.random()-0.5).slice(0,3);
  choices=choices.concat(others).sort(()=>Math.random()-0.5);
  choices.forEach(ch=>{const b=el("button","opt",esc(ch));
   if(quiz.picked){if(ch===it.answer)b.classList.add("right");else if(ch===quiz.picked)b.classList.add("wrong");}
   b.onclick=()=>{if(quiz.picked)return;quiz.picked=ch;quiz.seen++;if(ch===it.answer)quiz.score++;renderQuiz();};
   opts.appendChild(b);});
  c.appendChild(opts);
  if(quiz.picked){c.appendChild(el("div","qans",`${esc(it.answer)} — ${esc(it.caption)} · ${esc(it.cite)}`));}
  host.appendChild(c);
  const bb=el("div","qbtns");if(quiz.picked){const n=el("button","big reveal","Next →");n.onclick=()=>{quiz.i++;quiz.picked=null;renderQuiz();};bb.appendChild(n);}host.appendChild(bb);
 }else{
  c.appendChild(el("div","qprompt",(it.theme?esc(it.theme)+" · ":"")+(it.cueKind==="why"?"This is WHY a rule exists — say the rule, then reveal":"These are Brooks' words — say the rule they belong to, then reveal")));
  c.appendChild(el("div","qwhy",esc(it.prompt)));
  if(quiz.revealed){c.appendChild(el("div","qans",esc(it.ans)));c.appendChild(el("div","q","&ldquo;"+esc(it.q)+"&rdquo;"));c.appendChild(el("div","cite",esc(it.cite)));}
  host.appendChild(c);const bb=el("div","qbtns");
  if(!quiz.revealed){const r=el("button","big reveal","Reveal");r.onclick=()=>{quiz.revealed=true;renderQuiz();};bb.appendChild(r);}
  else{const g=el("button","big got","✓ Got it");g.onclick=()=>{if(it.id)mastered.add(it.id);saveM();quiz.score++;quiz.seen++;quiz.i++;quiz.revealed=false;renderQuiz();};
   const mi=el("button","big miss","✗ Missed");mi.onclick=()=>{quiz.seen++;quiz.i++;quiz.revealed=false;renderQuiz();};bb.appendChild(g);bb.appendChild(mi);}
  host.appendChild(bb);
 }
 host.appendChild(el("div","qmeta",`${quiz.i+1} / ${quiz.items.length} · score ${quiz.score}`));
}
function render(){tabs();
 if(view==="setups")viewSetups();else if(view==="rules")viewRules();else if(view==="notrade")viewNotrade();
 else if(view==="library")viewLibrary();else viewQuiz();window.scrollTo(0,0);}
$("#disc").innerHTML="Every rule, tell, teaching and figure is a verbatim excerpt or chart from Al Brooks' four books (Trends · Trading Ranges · Reversals · Reading Price Charts Bar by Bar), page-cited. Study aid, not trading advice.";
if(window.self!==window.top){const hl=document.getElementById("hubLink");if(hl)hl.style.display="none";}
drawProg();themeInit();render();
</script>"""

html = APP.replace("__DATA__", data_js)
(ROOT / "docs" / "living" / "brooks_app.html").write_text(html, encoding="utf-8")
full = ('<!doctype html><html lang="en"><head><meta charset="utf-8">'
        '<meta name="viewport" content="width=device-width, initial-scale=1">'
        '<title>The Brooks Codex</title><style>html,body{margin:0;padding:0}</style></head><body>\n'
        + html + '\n</body></html>')
(ROOT / "docs" / "living" / "brooks_app_standalone.html").write_text(full, encoding="utf-8")
print("wrote brooks_app.html (%d bytes) + standalone" % len(html))
print("counts:", D["counts"])
