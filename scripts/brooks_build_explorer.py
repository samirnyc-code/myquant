"""Build the Figure Explorer HTML (file-based: loads figures/*.jpg and books/*.pdf
from sibling folders). Complete library, per-book, full explanation text, deep
zoom (scroll+pan), favorites (localStorage), and a page-jump link to the PDF.
Writes docs/living/brooks_explorer/index.html  (open by double-click / host on Streamlit).
"""
import json, re
from pathlib import Path
OUT = Path(r"c:\Users\Admin\myquant\docs\living\brooks_codex")
index = json.load(open(OUT / "figure_index.json", encoding="utf-8"))

def clean_expl(t):
    if not t:
        return t
    t = re.sub(r'(\w)-\s+(\w)', r'\1\2', t)                 # de-hyphenate line breaks: "com- mon" -> "common"
    t = re.sub(r'Figure\s+\d+\.\d+', '', t)                 # stray figure refs from page breaks
    t = re.sub(r'\b\d{2,4}\s+(?=[A-Z]{2,}\b)', '', t)       # page number before a running head
    t = re.sub(r'\b[A-Z][A-Z]+(?:\s+[A-Z][A-Z&]+){1,}\b', '', t)  # ALLCAPS running heads (2+ words)
    t = re.sub(r'\s+([.,;])', r'\1', t)
    t = re.sub(r'\s{2,}', ' ', t).strip()
    return t

for f in index:
    f["explanation"] = clean_expl(f.get("explanation", ""))
data_js = json.dumps(index, ensure_ascii=False)

HTML = r"""<!doctype html><html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Brooks Figure Explorer</title>
<style>
:root{--bg:#0c1016;--panel:#141b24;--panel2:#1b2430;--ink:#e8eef6;--dim:#93a2b4;--faint:#6b7a8c;--line:#25303d;
 --gold:#e6b23a;--blue:#5aa0ff;--green:#45c26a;--mono:ui-monospace,Menlo,Consolas,monospace;--sans:system-ui,-apple-system,"Segoe UI",Roboto,sans-serif;}
@media(prefers-color-scheme:light){:root{--bg:#eef1f5;--panel:#fff;--panel2:#f4f6f9;--ink:#141b24;--dim:#54636f;--faint:#8593a1;--line:#dbe2ea;--gold:#b1810c;--blue:#2f6fd6;}}
:root[data-theme="light"]{--bg:#eef1f5;--panel:#fff;--panel2:#f4f6f9;--ink:#141b24;--dim:#54636f;--faint:#8593a1;--line:#dbe2ea;--gold:#b1810c;--blue:#2f6fd6;}
:root[data-theme="dark"]{--bg:#0c1016;--panel:#141b24;--panel2:#1b2430;--ink:#e8eef6;--dim:#93a2b4;--faint:#6b7a8c;--line:#25303d;--gold:#e6b23a;--blue:#5aa0ff;}
*{box-sizing:border-box}html,body{margin:0;padding:0}
body{font-family:var(--sans);background:var(--bg);color:var(--ink);line-height:1.55}
header{position:sticky;top:0;z-index:20;background:linear-gradient(180deg,var(--panel),var(--bg));border-bottom:1px solid var(--line);backdrop-filter:blur(6px)}
.top{display:flex;gap:14px;align-items:center;padding:12px 20px;max-width:1200px;margin:0 auto;flex-wrap:wrap}
.brand b{font-size:18px;letter-spacing:.13em;text-transform:uppercase;font-weight:800}.brand b span{color:var(--gold)}
.brand small{display:block;font-family:var(--mono);font-size:11px;color:var(--dim)}
.spacer{margin-left:auto}
select,input,button.ctl{font-family:var(--mono);font-size:12.5px;background:var(--panel);color:var(--ink);border:1px solid var(--line);border-radius:8px;padding:8px 11px}
.tabs{display:flex;gap:8px;padding:0 20px 11px;max-width:1200px;margin:0 auto;flex-wrap:wrap}
.tb{font-family:var(--mono);font-size:12px;letter-spacing:.05em;text-transform:uppercase;background:transparent;color:var(--dim);border:1px solid var(--line);border-radius:7px;padding:7px 12px;cursor:pointer}
.tb.on{background:var(--gold);color:var(--bg);border-color:var(--gold);font-weight:700}
main{max-width:1240px;margin:0 auto;padding:22px 20px 90px}
.count{font-family:var(--mono);font-size:12px;color:var(--faint);margin-bottom:16px}
.shell{display:grid;grid-template-columns:270px 1fr;gap:28px;align-items:start}
.toc{position:sticky;top:118px;max-height:calc(100vh - 140px);overflow:auto;border:1px solid var(--line);border-radius:12px;background:var(--panel);padding:10px}
.toc .th{font-family:var(--mono);font-size:11px;letter-spacing:.08em;text-transform:uppercase;color:var(--faint);padding:6px 8px 8px}
.toc a{display:block;font-size:12.5px;color:var(--dim);text-decoration:none;padding:6px 8px;border-radius:7px;border-left:2px solid transparent;line-height:1.35}
.toc a:hover{background:var(--panel2);color:var(--ink);border-left-color:var(--gold)}
.toc a b{font-family:var(--mono);color:var(--gold);font-size:11.5px;margin-right:6px}
.fig{scroll-margin-top:112px}
.toctoggle{display:none}
@media(max-width:860px){.shell{grid-template-columns:1fr}
 .toc{position:static;max-height:320px;margin-bottom:8px}
 .toctoggle{display:inline-block}}
.fig{border:1px solid var(--line);border-radius:14px;background:var(--panel);overflow:hidden;margin-bottom:26px}
.fig .imgwrap{position:relative;background:#fff;cursor:zoom-in}
.fig img{width:100%;display:block}
.fig .bar{display:flex;align-items:center;gap:12px;padding:13px 18px;border-top:1px solid var(--line);flex-wrap:wrap}
.fig .cap{font-weight:700;font-size:16px}
.fig .cap .num{font-family:var(--mono);color:var(--gold);margin-right:8px}
.fig .meta{font-family:var(--mono);font-size:11.5px;color:var(--faint)}
.fig .acts{margin-left:auto;display:flex;gap:8px;align-items:center}
.star{font-size:20px;cursor:pointer;color:var(--faint);background:none;border:none;line-height:1}.star.on{color:var(--gold)}
.pdflink{font-family:var(--mono);font-size:12px;color:var(--blue);text-decoration:none;border:1px solid var(--line);border-radius:7px;padding:6px 10px}
.pdflink:hover{border-color:var(--blue)}
.expl{padding:2px 18px 18px;color:var(--ink);font-size:14.5px;max-width:80ch}
.expl.empty{color:var(--faint);font-style:italic;font-family:var(--mono);font-size:12.5px}
.zov{position:fixed;inset:0;z-index:60;background:rgba(4,7,11,.92);display:none;overflow:hidden;touch-action:none}
.zov.on{display:block}
.zov img{position:absolute;top:0;left:0;transform-origin:0 0;user-select:none;-webkit-user-drag:none;cursor:grab}
.zbar{position:fixed;top:14px;left:0;right:0;z-index:61;display:flex;gap:10px;justify-content:center;align-items:center;flex-wrap:wrap;pointer-events:none}
.zbar>*{pointer-events:auto}
.zcap{font-family:var(--mono);font-size:12px;color:#cfd8e3;background:rgba(0,0,0,.5);padding:7px 12px;border-radius:8px;max-width:70vw}
.zbtn{font-family:var(--mono);font-size:15px;background:var(--panel);color:var(--ink);border:1px solid var(--line);border-radius:9px;width:42px;height:42px;cursor:pointer}
.hint{font-family:var(--mono);font-size:11px;color:var(--faint);text-align:center;padding:26px 20px 0;border-top:1px solid var(--line);margin-top:30px;line-height:1.7}
</style></head><body>
<header>
 <div class="top">
  <div class="brand"><b>BROOKS <span>FIGURE EXPLORER</span></b><small>every chart + full text · all 4 books · deep zoom · favorites</small></div>
  <input id="search" class="ctl" placeholder="search captions / text…" style="min-width:200px">
  <button class="ctl" id="theme">◑</button>
 </div>
 <div class="tabs" id="tabs"></div>
</header>
<main><div class="count" id="count"></div>
 <div class="shell"><nav class="toc" id="toc"></nav><div id="list"></div></div>
 <div class="hint" id="hint"></div>
</main>
<div class="zov" id="zov">
 <div class="zbar"><button class="zbtn" id="zout">−</button><button class="zbtn" id="zin">+</button>
  <button class="zbtn" id="zfit" title="fit">⤢</button><div class="zcap" id="zcap"></div>
  <a class="pdflink" id="zpdf" target="_blank">📖 open page</a><button class="zbtn" id="zx">✕</button></div>
 <img id="zimg" alt="">
</div>
<script>
const FIGS=__DATA__;
const BOOKS=["Trends","Trading Ranges","Reading Price Charts","Reversals"];
const LS="brooks_explorer_favs";
let favs=new Set(JSON.parse(localStorage.getItem(LS)||"[]"));
let book="Trends",q="";
const $=s=>document.querySelector(s),el=(t,c,h)=>{const e=document.createElement(t);if(c)e.className=c;if(h!=null)e.innerHTML=h;return e;};
const esc=s=>(s==null?"":""+s).replace(/[&<>]/g,m=>({"&":"&amp;","<":"&lt;",">":"&gt;"}[m]));
function saveF(){localStorage.setItem(LS,JSON.stringify([...favs]));}
function tabs(){const t=$("#tabs");t.innerHTML="";
 [["Trends","Trends"],["Trading Ranges","Ranges"],["Reading Price Charts","Reading Price Charts"],["Reversals","Reversals"],["__fav","★ Favorites"]].forEach(([k,l])=>{
  const b=el("button","tb"+(book===k?" on":""),l+(k==="__fav"?` (${favs.size})`:""));b.onclick=()=>{book=k;render();};t.appendChild(b);});}
function items(){let a=(book==="__fav")?FIGS.filter(f=>favs.has(f.id)):FIGS.filter(f=>f.book===book);
 if(q)a=a.filter(f=>(f.caption+" "+f.explanation).toLowerCase().includes(q));return a;}
function render(){tabs();const list=$("#list");list.innerHTML="";const a=items();
 $("#count").textContent=`${a.length} figure${a.length!==1?"s":""}`+(q?` matching "${q}"`:book==="__fav"?" saved":` in ${book}`);
 const toc=$("#toc");toc.innerHTML=`<div class="th">Contents · ${a.length}</div>`;
 a.forEach(f=>{
  const card=el("div","fig");card.id="fig-"+f.id;
  const tl=el("a",null,`<b>${esc(f.fig_num)}</b>${esc(f.caption)}`);tl.href="#";
  tl.onclick=ev=>{ev.preventDefault();card.scrollIntoView({behavior:"smooth",block:"start"});};
  toc.appendChild(tl);
  const iw=el("div","imgwrap");const im=new Image();im.src=f.file;im.alt=esc(f.caption);im.loading="lazy";iw.appendChild(im);
  iw.onclick=()=>openZoom(f);card.appendChild(iw);
  const bar=el("div","bar");
  bar.appendChild(el("div","cap",`<span class="num">Fig ${esc(f.fig_num)}</span>${esc(f.caption)}`));
  bar.appendChild(el("div","meta",`${esc(f.book)}${f.printed_page?" · p."+esc(f.printed_page):""}`));
  const acts=el("div","acts");
  const pdf=el("a","pdflink");pdf.href=`books/${f.book_file}#page=${f.pdf_page}`;pdf.target="_blank";pdf.textContent=`📖 book p.${f.pdf_page}`;
  const st=el("button","star"+(favs.has(f.id)?" on":""),favs.has(f.id)?"★":"☆");
  st.onclick=e=>{e.stopPropagation();favs.has(f.id)?favs.delete(f.id):favs.add(f.id);st.classList.toggle("on");st.textContent=st.classList.contains("on")?"★":"☆";saveF();tabs();};
  acts.appendChild(pdf);acts.appendChild(st);bar.appendChild(acts);card.appendChild(bar);
  if(f.explanation)card.appendChild(el("div","expl",esc(f.explanation)));
  else card.appendChild(el("div","expl empty","Scanned page — read the full walkthrough via 📖 book p."+f.pdf_page+" (text OCR pending)."));
  list.appendChild(card);
 });
 window.scrollTo(0,0);
}
/* deep zoom + pan */
let Z={s:1,x:0,y:0,drag:false,px:0,py:0,fig:null};
const zov=$("#zov"),zimg=$("#zimg");
function openZoom(f){Z.fig=f;zimg.src=f.file;$("#zcap").innerHTML=`<b>Fig ${esc(f.fig_num)}</b> — ${esc(f.caption)} · ${esc(f.book)}`;
 $("#zpdf").href=`books/${f.book_file}#page=${f.pdf_page}`;$("#zpdf").textContent=`📖 book p.${f.pdf_page}`;
 zov.classList.add("on");zimg.onload=fit;if(zimg.complete)fit();}
function fit(){const iw=zimg.naturalWidth,ih=zimg.naturalHeight,W=innerWidth,H=innerHeight-10;
 Z.s=Math.min(W/iw,H/ih);Z.x=(W-iw*Z.s)/2;Z.y=(H-ih*Z.s)/2+6;apply();}
function apply(){zimg.style.transform=`translate(${Z.x}px,${Z.y}px) scale(${Z.s})`;}
function zoomAt(cx,cy,factor){const ns=Math.max(0.1,Math.min(8,Z.s*factor));
 Z.x=cx-(cx-Z.x)*(ns/Z.s);Z.y=cy-(cy-Z.y)*(ns/Z.s);Z.s=ns;apply();}
zov.addEventListener("wheel",e=>{e.preventDefault();zoomAt(e.clientX,e.clientY,e.deltaY<0?1.15:0.87);},{passive:false});
zimg.addEventListener("mousedown",e=>{Z.drag=true;Z.px=e.clientX;Z.py=e.clientY;zimg.style.cursor="grabbing";});
window.addEventListener("mousemove",e=>{if(!Z.drag)return;Z.x+=e.clientX-Z.px;Z.y+=e.clientY-Z.py;Z.px=e.clientX;Z.py=e.clientY;apply();});
window.addEventListener("mouseup",()=>{Z.drag=false;zimg.style.cursor="grab";});
$("#zin").onclick=()=>zoomAt(innerWidth/2,innerHeight/2,1.3);
$("#zout").onclick=()=>zoomAt(innerWidth/2,innerHeight/2,0.77);
$("#zfit").onclick=fit;
$("#zx").onclick=()=>zov.classList.remove("on");
document.addEventListener("keydown",e=>{if(!zov.classList.contains("on"))return;
 if(e.key==="Escape")zov.classList.remove("on");else if(e.key==="+"||e.key==="=")zoomAt(innerWidth/2,innerHeight/2,1.3);
 else if(e.key==="-")zoomAt(innerWidth/2,innerHeight/2,0.77);else if(e.key==="0")fit();});
/* touch pinch */
let pt=[];
zov.addEventListener("touchstart",e=>{pt=[...e.touches];},{passive:false});
zov.addEventListener("touchmove",e=>{e.preventDefault();
 if(e.touches.length===1&&pt.length===1){Z.x+=e.touches[0].clientX-pt[0].clientX;Z.y+=e.touches[0].clientY-pt[0].clientY;apply();pt=[...e.touches];}
 else if(e.touches.length===2&&pt.length===2){const d0=Math.hypot(pt[0].clientX-pt[1].clientX,pt[0].clientY-pt[1].clientY);
  const d1=Math.hypot(e.touches[0].clientX-e.touches[1].clientX,e.touches[0].clientY-e.touches[1].clientY);
  const cx=(e.touches[0].clientX+e.touches[1].clientX)/2,cy=(e.touches[0].clientY+e.touches[1].clientY)/2;
  zoomAt(cx,cy,d1/d0);pt=[...e.touches];}},{passive:false});
$("#search").oninput=e=>{q=e.target.value.toLowerCase();render();};
$("#theme").onclick=()=>{const c=document.documentElement.getAttribute("data-theme");
 const n=c==="dark"?"light":c==="light"?"dark":(matchMedia("(prefers-color-scheme:dark)").matches?"light":"dark");document.documentElement.setAttribute("data-theme",n);};
$("#hint").innerHTML="Click any chart for deep zoom (scroll / +− / drag to pan / pinch). ★ to save to Favorites. 📖 opens the actual book PDF at that page. All charts &amp; text are from Al Brooks' four books — study aid, not trading advice.";
const withtext=FIGS.filter(f=>f.explanation).length;
render();
</script></body></html>"""
html = HTML.replace("__DATA__", data_js)
(OUT / "explorer.html").write_text(html, encoding="utf-8")
print(f"wrote Figure Explorer explorer.html ({len(html)} bytes) with {len(index)} figures")
