"""Build the Daily Charts page (daily.html) — Brooks' ~1,500 real EOD blog charts,
day-type, tags, and real bar-by-bar commentary WHERE it exists (flagged 'detailed';
generic AI filler is suppressed, not shown as Brooks). Same look/UX as the Figure
Explorer: contents sidebar, search, day-type filter, detailed-only toggle, deep
zoom, favorites, and DELETE (hide) with a Trash/restore view. File-based.
"""
import json
from pathlib import Path
HUB = Path(__file__).resolve().parent.parent / "docs" / "living" / "brooks_codex"
index = json.load(open(HUB / "daily_index.json", encoding="utf-8"))
data_js = json.dumps(index, ensure_ascii=False)

HTML = r"""<!doctype html><html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1"><title>Brooks Daily Charts</title>
<style>
:root{--bg:#0c1016;--panel:#141b24;--panel2:#1b2430;--ink:#e8eef6;--dim:#93a2b4;--faint:#6b7a8c;--line:#25303d;
 --gold:#e6b23a;--blue:#5aa0ff;--green:#45c26a;--red:#ec5b5b;--mono:ui-monospace,Menlo,Consolas,monospace;--sans:system-ui,-apple-system,"Segoe UI",Roboto,sans-serif;}
@media(prefers-color-scheme:light){:root{--bg:#eef1f5;--panel:#fff;--panel2:#f4f6f9;--ink:#141b24;--dim:#54636f;--faint:#8593a1;--line:#dbe2ea;--gold:#b1810c;--blue:#2f6fd6;--green:#1f9a4d;--red:#c8352f;}}
:root[data-theme=light]{--bg:#eef1f5;--panel:#fff;--panel2:#f4f6f9;--ink:#141b24;--dim:#54636f;--faint:#8593a1;--line:#dbe2ea;--gold:#b1810c;--blue:#2f6fd6;--green:#1f9a4d;--red:#c8352f;}
:root[data-theme=dark]{--bg:#0c1016;--panel:#141b24;--panel2:#1b2430;--ink:#e8eef6;--dim:#93a2b4;--faint:#6b7a8c;--line:#25303d;--gold:#e6b23a;--blue:#5aa0ff;--green:#45c26a;--red:#ec5b5b;}
*{box-sizing:border-box}html,body{margin:0;padding:0}
body{font-family:var(--sans);background:var(--bg);color:var(--ink);line-height:1.55}
header{position:sticky;top:0;z-index:20;background:linear-gradient(180deg,var(--panel),var(--bg));border-bottom:1px solid var(--line);backdrop-filter:blur(6px)}
.top{display:flex;gap:10px;align-items:center;padding:12px 20px;max-width:1240px;margin:0 auto;flex-wrap:wrap}
.brand{margin-right:auto}.brand b{font-size:18px;letter-spacing:.13em;text-transform:uppercase;font-weight:800}.brand b span{color:var(--gold)}
.brand small{display:block;font-family:var(--mono);font-size:11px;color:var(--dim)}
select,input,button.ctl,a.home{font-family:var(--mono);font-size:12.5px;background:var(--panel);color:var(--ink);border:1px solid var(--line);border-radius:8px;padding:8px 11px;cursor:pointer;text-decoration:none}
button.ctl.on{background:var(--gold);color:var(--bg);border-color:var(--gold);font-weight:700}
button.ctl.trash.on{background:var(--red);border-color:var(--red);color:#fff}
a.home:hover,select:hover,input:hover{border-color:var(--gold)}
main{max-width:1240px;margin:0 auto;padding:22px 20px 90px}
.count{font-family:var(--mono);font-size:12px;color:var(--faint);margin-bottom:16px}
.shell{display:grid;grid-template-columns:270px 1fr;gap:28px;align-items:start}
.toc{position:sticky;top:76px;max-height:calc(100vh - 96px);overflow:auto;border:1px solid var(--line);border-radius:12px;background:var(--panel);padding:10px}
.toc .th{font-family:var(--mono);font-size:11px;letter-spacing:.08em;text-transform:uppercase;color:var(--faint);padding:6px 8px 8px}
.toc a{display:block;font-size:12px;color:var(--dim);text-decoration:none;padding:6px 8px;border-radius:7px;border-left:2px solid transparent;line-height:1.35}
.toc a:hover{background:var(--panel2);color:var(--ink);border-left-color:var(--gold)}
.toc a b{font-family:var(--mono);color:var(--gold);font-size:11px;margin-right:6px}
.fig{scroll-margin-top:76px;border:1px solid var(--line);border-radius:14px;background:var(--panel);overflow:hidden;margin-bottom:26px}
.imgwrap{background:#fff;cursor:zoom-in}.imgwrap img{width:100%;display:block}
.bar{display:flex;align-items:center;gap:10px;padding:13px 18px;border-top:1px solid var(--line);flex-wrap:wrap}
.dtype{font-family:var(--mono);font-size:11px;color:var(--bg);background:var(--gold);padding:3px 8px;border-radius:6px;white-space:nowrap}
.cap{font-weight:700;font-size:15.5px}
.dt{font-family:var(--mono);font-size:11.5px;color:var(--faint)}
.detbadge{font-family:var(--mono);font-size:10.5px;color:var(--green);border:1px solid var(--green);border-radius:5px;padding:2px 6px}
.acts{margin-left:auto;display:flex;gap:8px}
.star,.del{font-size:18px;cursor:pointer;color:var(--faint);background:none;border:none;line-height:1}
.star.on{color:var(--gold)}.del:hover{color:var(--red)}
.tags{display:flex;gap:6px;flex-wrap:wrap;padding:0 18px 4px}
.tag{font-family:var(--mono);font-size:10.5px;color:var(--dim);background:var(--panel2);border:1px solid var(--line);border-radius:20px;padding:2px 9px}
.lesson{margin:6px 18px 0;font-size:13.5px;color:var(--gold);border-left:3px solid var(--gold);padding-left:11px}
.expl{padding:8px 18px 18px;font-size:14.5px;max-width:82ch;white-space:pre-wrap}
.note{padding:6px 18px 16px;font-family:var(--mono);font-size:11.5px;color:var(--faint);font-style:italic}
.hint{font-family:var(--mono);font-size:11px;color:var(--faint);text-align:center;padding:26px 20px 0;border-top:1px solid var(--line);margin-top:30px;line-height:1.7}
.zov{position:fixed;inset:0;z-index:60;background:rgba(4,7,11,.92);display:none;overflow:hidden;touch-action:none}.zov.on{display:block}
.zov img{position:absolute;top:0;left:0;transform-origin:0 0;user-select:none;cursor:grab}
.zbar{position:fixed;top:14px;left:0;right:0;z-index:61;display:flex;gap:10px;justify-content:center;align-items:center;flex-wrap:wrap;pointer-events:none}.zbar>*{pointer-events:auto}
.zcap{font-family:var(--mono);font-size:12px;color:#cfd8e3;background:rgba(0,0,0,.5);padding:7px 12px;border-radius:8px;max-width:70vw}
.zbtn{font-family:var(--mono);font-size:15px;background:var(--panel);color:var(--ink);border:1px solid var(--line);border-radius:9px;width:42px;height:42px;cursor:pointer}
.expl,.note{cursor:zoom-in}
.rov{position:fixed;inset:0;z-index:70;background:rgba(4,7,11,.86);backdrop-filter:blur(3px);display:none;align-items:flex-start;justify-content:center;overflow:auto;padding:36px 16px}
.rov.on{display:flex}
.rcard{background:var(--panel);border:1px solid var(--line);border-radius:16px;max-width:860px;width:100%;overflow:hidden;box-shadow:0 30px 80px rgba(0,0,0,.5)}
.rcard>img{width:100%;display:block;cursor:zoom-in;background:#fff}
.rhead{padding:16px 20px;border-bottom:1px solid var(--line);display:flex;gap:10px;align-items:center;flex-wrap:wrap}
.rhead .cap{font-size:17px}.rtext{padding:22px;font-size:17px;line-height:1.75;white-space:pre-wrap;max-width:80ch}
.rlesson{margin:16px 22px 0;font-size:15px;color:var(--gold);border-left:3px solid var(--gold);padding-left:13px}
.rx{position:fixed;top:16px;right:20px;z-index:71;font-size:18px;background:var(--panel);color:var(--ink);border:1px solid var(--line);border-radius:10px;width:44px;height:44px;cursor:pointer}
@media(max-width:860px){.shell{grid-template-columns:1fr}.toc{position:static;max-height:300px;margin-bottom:8px}}
</style></head><body>
<header><div class="top">
 <div class="brand"><b>BROOKS <span>DAILY CHARTS</span></b><small>Brooks' real EOD blog charts · day-type + real commentary where available</small></div>
 <input id="search" class="ctl" placeholder="search…" style="min-width:150px">
 <select id="dtf" class="ctl"><option value="">all day-types</option></select>
 <button class="ctl" id="detbtn" title="only charts with real detailed commentary">✍ detailed</button>
 <button class="ctl trash" id="trashbtn">🗑 <span id="tn">0</span></button>
 <a class="home" href="index.html">⌂ Home</a>
 <button class="ctl" id="theme">◑</button>
</div></header>
<main><div class="count" id="count"></div>
 <div class="shell"><nav class="toc" id="toc"></nav><div id="list"></div></div>
 <div class="hint" id="hint"></div>
</main>
<div class="zov" id="zov"><div class="zbar"><button class="zbtn" id="zout">−</button><button class="zbtn" id="zin">+</button>
 <button class="zbtn" id="zfit" title="fit">⤢</button><div class="zcap" id="zcap"></div><button class="zbtn" id="zx">✕</button></div>
 <img id="zimg" alt=""></div>
<div class="rov" id="rov"></div>
<script>
const CARDS=__DATA__;
const FLS="brooks_daily_favs",HLS="brooks_daily_hidden";
let favs=new Set(JSON.parse(localStorage.getItem(FLS)||"[]"));
let hidden=new Set(JSON.parse(localStorage.getItem(HLS)||"[]"));
let q="",dtf="",detailedOnly=false,showTrash=false;
const $=s=>document.querySelector(s),el=(t,c,h)=>{const e=document.createElement(t);if(c)e.className=c;if(h!=null)e.innerHTML=h;return e;};
const esc=s=>(s==null?"":""+s).replace(/[&<>]/g,m=>({"&":"&amp;","<":"&lt;",">":"&gt;"}[m]));
function saveF(){localStorage.setItem(FLS,JSON.stringify([...favs]));}
function saveH(){localStorage.setItem(HLS,JSON.stringify([...hidden]));$("#tn").textContent=hidden.size;}
function items(){
 if(showTrash)return CARDS.filter(c=>hidden.has(c.id));
 let a=CARDS.filter(c=>!hidden.has(c.id));
 if(dtf)a=a.filter(c=>(c.day_type_short||"Other").toLowerCase()===dtf);
 if(detailedOnly)a=a.filter(c=>c.detailed);
 if(q)a=a.filter(c=>((c.title+" "+c.text+" "+c.day_type+" "+(c.tags||[]).join(" ")).toLowerCase().includes(q)));
 return a;}
function fillDtf(){const set={};CARDS.forEach(c=>{const k=c.day_type_short||"Other";set[k]=(set[k]||0)+1;});
 const sel=$("#dtf");Object.keys(set).sort().forEach(k=>{const o=document.createElement("option");o.value=k.toLowerCase();o.textContent=`${k} (${set[k]})`;sel.appendChild(o);});
 sel.onchange=e=>{dtf=e.target.value;render();};}
function render(){const list=$("#list");list.innerHTML="";const a=items();
 const det=CARDS.filter(c=>c.detailed).length;
 $("#count").innerHTML=(showTrash?`🗑 ${a.length} hidden`:`${a.length} chart${a.length!==1?"s":""}`)
  +(q?` matching "${esc(q)}"`:"")+(dtf?` · ${dtf}`:"")+(detailedOnly?` · detailed only`:"")
  +` &nbsp;·&nbsp; <span style="color:var(--green)">${det} have real detailed commentary</span>`;
 const toc=$("#toc");toc.innerHTML=`<div class="th">Contents · ${a.length}</div>`;
 a.forEach(c=>{
  const card=el("div","fig");card.id="d-"+c.id;
  const tl=el("a",null,`<b>${esc(c.date||"·")}</b>${esc(c.title)}`);tl.href="#";
  tl.onclick=ev=>{ev.preventDefault();card.scrollIntoView({behavior:"smooth",block:"start"});};toc.appendChild(tl);
  const iw=el("div","imgwrap");const im=new Image();im.src=c.file;im.alt=esc(c.title);im.loading="lazy";iw.appendChild(im);
  iw.onclick=()=>openZoom(c);card.appendChild(iw);
  const bar=el("div","bar");
  bar.appendChild(el("span","dtype",esc(c.day_type_short||"—")));
  bar.appendChild(el("div","cap",esc(c.day_type||c.title)));
  if(c.date)bar.appendChild(el("div","dt",esc(c.date)));
  if(c.detailed)bar.appendChild(el("span","detbadge","✍ detailed"));
  const acts=el("div","acts");
  const st=el("button","star"+(favs.has(c.id)?" on":""),favs.has(c.id)?"★":"☆");
  st.onclick=e=>{e.stopPropagation();favs.has(c.id)?favs.delete(c.id):favs.add(c.id);st.classList.toggle("on");st.textContent=st.classList.contains("on")?"★":"☆";saveF();};
  const rd=el("button","del","⤢");rd.title="read larger";rd.onclick=e=>{e.stopPropagation();openRead(c);};
  const del=el("button","del",showTrash?"↩":"🗑");del.title=showTrash?"restore":"delete (hide)";
  del.onclick=e=>{e.stopPropagation();if(showTrash){hidden.delete(c.id);}else{hidden.add(c.id);}saveH();render();};
  acts.appendChild(st);acts.appendChild(rd);acts.appendChild(del);bar.appendChild(acts);card.appendChild(bar);
  if(c.tags&&c.tags.length){const tg=el("div","tags");c.tags.forEach(t=>tg.appendChild(el("span","tag",esc(t))));card.appendChild(tg);}
  if(c.lesson)card.appendChild(el("div","lesson","💡 "+esc(c.lesson)));
  if(c.detailed&&c.text){const ex=el("div","expl",esc(c.text)+"  ⤢");ex.title="click to read larger";ex.onclick=()=>openRead(c);card.appendChild(ex);}
  else {const nt=el("div","note","Real chart + day-type. Detailed Brooks-method commentary is being reworked. (Click the chart to zoom.)");nt.onclick=()=>openZoom(c);card.appendChild(nt);}
  list.appendChild(card);
 });
 window.scrollTo(0,0);
}
function openRead(c){const rov=$("#rov");rov.innerHTML='<button class="rx" id="rx">✕</button><div class="rcard"></div>';
 const rc=rov.querySelector(".rcard");
 const im=new Image();im.src=c.file;im.onclick=()=>openZoom(c);rc.appendChild(im);
 const head=el("div","rhead");head.appendChild(el("span","dtype",esc(c.day_type_short||"—")));
 head.appendChild(el("div","cap",esc(c.day_type||c.title)));if(c.date)head.appendChild(el("div","dt",esc(c.date)));
 head.appendChild(el("span","detbadge","🤖 AI · Brooks-method"));rc.appendChild(head);
 if(c.detailed&&c.lesson)rc.appendChild(el("div","rlesson","💡 "+esc(c.lesson)));
 rc.appendChild(el("div","rtext",(c.detailed&&c.text)?esc(c.text):"⚠️ Real chart + day-type + tags are Brooks' own. Detailed Brooks-method commentary for this day is being reworked (many blog posts had the wrong image scraped, so we're verifying/regenerating). Click the chart above to deep-zoom."));
 rov.classList.add("on");
 rov.querySelector("#rx").onclick=()=>rov.classList.remove("on");
 rov.onclick=e=>{if(e.target===rov)rov.classList.remove("on");};
}
document.addEventListener("keydown",e=>{if(e.key==="Escape")$("#rov").classList.remove("on");});
let Z={s:1,x:0,y:0,drag:false,px:0,py:0};
const zov=$("#zov"),zimg=$("#zimg");
function openZoom(c){zimg.src=c.file;$("#zcap").innerHTML=`${esc(c.date||"")} · <b>${esc(c.day_type||c.title)}</b>`;zov.classList.add("on");zimg.onload=fit;if(zimg.complete)fit();}
function fit(){const iw=zimg.naturalWidth,ih=zimg.naturalHeight,W=innerWidth,H=innerHeight-10;Z.s=Math.min(W/iw,H/ih);Z.x=(W-iw*Z.s)/2;Z.y=(H-ih*Z.s)/2+6;apply();}
function apply(){zimg.style.transform=`translate(${Z.x}px,${Z.y}px) scale(${Z.s})`;}
function zoomAt(cx,cy,f){const ns=Math.max(0.1,Math.min(8,Z.s*f));Z.x=cx-(cx-Z.x)*(ns/Z.s);Z.y=cy-(cy-Z.y)*(ns/Z.s);Z.s=ns;apply();}
zov.addEventListener("wheel",e=>{e.preventDefault();zoomAt(e.clientX,e.clientY,e.deltaY<0?1.15:0.87);},{passive:false});
zimg.addEventListener("mousedown",e=>{Z.drag=true;Z.px=e.clientX;Z.py=e.clientY;zimg.style.cursor="grabbing";});
window.addEventListener("mousemove",e=>{if(!Z.drag)return;Z.x+=e.clientX-Z.px;Z.y+=e.clientY-Z.py;Z.px=e.clientX;Z.py=e.clientY;apply();});
window.addEventListener("mouseup",()=>{Z.drag=false;zimg.style.cursor="grab";});
$("#zin").onclick=()=>zoomAt(innerWidth/2,innerHeight/2,1.3);$("#zout").onclick=()=>zoomAt(innerWidth/2,innerHeight/2,0.77);
$("#zfit").onclick=fit;$("#zx").onclick=()=>zov.classList.remove("on");
document.addEventListener("keydown",e=>{if(!zov.classList.contains("on"))return;if(e.key==="Escape")zov.classList.remove("on");else if(e.key==="+"||e.key==="=")zoomAt(innerWidth/2,innerHeight/2,1.3);else if(e.key==="-")zoomAt(innerWidth/2,innerHeight/2,0.77);else if(e.key==="0")fit();});
let pt=[];zov.addEventListener("touchstart",e=>{pt=[...e.touches];},{passive:false});
zov.addEventListener("touchmove",e=>{e.preventDefault();if(e.touches.length===1&&pt.length===1){Z.x+=e.touches[0].clientX-pt[0].clientX;Z.y+=e.touches[0].clientY-pt[0].clientY;apply();pt=[...e.touches];}else if(e.touches.length===2&&pt.length===2){const d0=Math.hypot(pt[0].clientX-pt[1].clientX,pt[0].clientY-pt[1].clientY),d1=Math.hypot(e.touches[0].clientX-e.touches[1].clientX,e.touches[0].clientY-e.touches[1].clientY),cx=(e.touches[0].clientX+e.touches[1].clientX)/2,cy=(e.touches[0].clientY+e.touches[1].clientY)/2;zoomAt(cx,cy,d1/d0);pt=[...e.touches];}},{passive:false});
$("#search").oninput=e=>{q=e.target.value.toLowerCase();render();};
$("#detbtn").onclick=()=>{detailedOnly=!detailedOnly;$("#detbtn").classList.toggle("on",detailedOnly);render();};
$("#trashbtn").onclick=()=>{showTrash=!showTrash;$("#trashbtn").classList.toggle("on",showTrash);render();};
$("#theme").onclick=()=>{const c=document.documentElement.getAttribute("data-theme");document.documentElement.setAttribute("data-theme",c==="dark"?"light":c==="light"?"dark":(matchMedia("(prefers-color-scheme:dark)").matches?"light":"dark"));};
$("#hint").innerHTML="Brooks' real EOD blog charts + his day-type &amp; tags. Detailed bar-by-bar commentary shown only where genuine (✍). Click a chart for deep zoom, ★ favorite, 🗑 delete (restore from the Trash toggle). Study aid, not trading advice; not for redistribution.";
saveH();fillDtf();render();
</script></body></html>"""
html = HTML.replace("__DATA__", data_js)
(HUB / "daily.html").write_text(html, encoding="utf-8")
print(f"wrote daily.html ({len(html)} bytes) with {len(index)} daily charts; detailed={sum(1 for x in index if x.get('detailed'))}")
