"""Build slides.html — the course-slide explorer for the Brooks Codex.

Walks the synced shared Drive folder (default shortcut path below), builds the
topic tree (Part N / 'NN - Topic'), pairs annotated slides with their M-
(un-annotated) twins for drill mode, and best-effort maps each topic to its
official Encyclopedia section. Slides are NOT copied — the page references
them via a configurable base path (localStorage), so it works on any machine
with the same Drive shortcut.

  python scripts/brooks_build_slides.py
"""
import json, os, re, difflib
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
HUB = ROOT / 'docs' / 'living' / 'brooks_codex'
SLIDES = Path(r'G:\.shortcut-targets-by-id\1oanmO7XO-brbZThAYjV6t6hZdzRyy9rE\Slides')
DEFAULT_BASE = 'file:///G:/.shortcut-targets-by-id/1oanmO7XO-brbZThAYjV6t6hZdzRyy9rE/Slides'

enc = json.load(open(ROOT / 'docs' / 'living' / 'brooks_encyc_index.json', encoding='utf-8'))

def norm(s):
    s = s.lower()
    s = re.sub(r'\b(disapointed|disappointment)\b', 'disappointed', s)
    s = re.sub(r'[^a-z0-9 ]+', ' ', s)
    s = re.sub(r'\s+', ' ', s).strip()
    return s

enc_by_norm = {norm(e['section']): e for e in enc}
enc_norms = list(enc_by_norm)

def match_enc(topic_name):
    n = norm(topic_name)
    if n in enc_by_norm:
        return enc_by_norm[n]['abbr']
    best = difflib.get_close_matches(n, enc_norms, n=1, cutoff=0.82)
    return enc_by_norm[best[0]]['abbr'] if best else None

parts = []
for part_dir in sorted(SLIDES.iterdir()):
    if not part_dir.is_dir():
        continue
    topics = []
    for tdir in sorted(part_dir.iterdir()):
        if not tdir.is_dir():
            continue
        m = re.match(r'^(New \d+|\d+)\s*-\s*(.+)$', tdir.name.strip())
        num, name = (m.group(1), m.group(2).strip()) if m else ('', tdir.name)
        files = sorted(f.name for f in tdir.iterdir()
                       if f.suffix.lower() in ('.png', '.jpg', '.jpeg', '.webp', '.gif'))
        ann = [f for f in files if not f.upper().startswith('M-')]
        mfiles = [f for f in files if f.upper().startswith('M-')]
        topics.append({'num': num, 'name': name, 'dir': f'{part_dir.name}/{tdir.name}',
                       'ann': ann, 'm': mfiles, 'abbr': match_enc(name)})
    if topics:
        parts.append({'part': part_dir.name, 'topics': topics})

nt = sum(len(p['topics']) for p in parts)
ns = sum(len(t['ann']) + len(t['m']) for p in parts for t in p['topics'])
nmap = sum(1 for p in parts for t in p['topics'] if t['abbr'])

TMPL = r'''<!doctype html><html><head><meta charset=utf-8><title>Brooks Codex — Course Slides</title><style>
:root{--bg:#0c1016;--panel:#141b24;--panel2:#1b2430;--ink:#e8eef6;--dim:#93a2b4;--line:#25303d;--gold:#e6b23a;--mono:ui-monospace,Menlo,Consolas,monospace}
*{box-sizing:border-box}body{margin:0;background:var(--bg);color:var(--ink);font-family:system-ui}
header{border-bottom:1px solid var(--line);padding:10px 18px;display:flex;gap:12px;align-items:center;position:sticky;top:0;background:var(--bg);z-index:5;flex-wrap:wrap}
header b{font-size:16px;letter-spacing:.12em;text-transform:uppercase}header b span{color:var(--gold)}
header a{color:var(--dim);font-family:var(--mono);font-size:12px;text-decoration:none;margin-left:auto}
#q{font-family:var(--mono);font-size:13px;background:var(--panel);color:var(--ink);border:1px solid var(--line);border-radius:8px;padding:8px 12px;width:250px}
button{font-family:var(--mono);font-size:12.5px;background:var(--panel);color:var(--ink);border:1px solid var(--line);border-radius:8px;padding:8px 13px;cursor:pointer}
button:hover{border-color:var(--gold)}button.on{background:var(--gold);color:#0c1016;font-weight:700}
.layout{display:grid;grid-template-columns:320px minmax(0,1fr);height:calc(100vh - 55px)}
#side{overflow-y:auto;border-right:1px solid var(--line);padding:10px}
.part{font-family:var(--mono);font-size:11px;letter-spacing:.12em;text-transform:uppercase;color:var(--dim);margin:14px 6px 4px}
.topic{padding:7px 10px;border-radius:7px;cursor:pointer;font-size:13.5px;border:1px solid transparent}
.topic:hover{background:var(--panel)}.topic.sel{background:var(--panel2);border-color:var(--gold)}
.topic .ab{font-family:var(--mono);font-size:10.5px;color:var(--gold)}
#main{overflow-y:auto;padding:16px 22px}
h2{margin:0 0 4px;font-size:20px}
.meta{font-family:var(--mono);font-size:12px;color:var(--dim);margin-bottom:14px}
.grid{display:grid;grid-template-columns:repeat(auto-fill,minmax(330px,1fr));gap:14px}
.slide{border:1px solid var(--line);border-radius:10px;overflow:hidden;background:#fff;cursor:zoom-in}
.slide img{width:100%;display:block}
.slide .cap{font-family:var(--mono);font-size:11px;color:var(--dim);background:var(--panel);padding:5px 9px}
.empty{color:var(--dim);font-family:var(--mono);padding:30px}
.zov{position:fixed;inset:0;z-index:60;background:rgba(4,7,11,.94);display:none;overflow:hidden;touch-action:none}
.zov.on{display:block}.zov img{position:absolute;top:0;left:0;transform-origin:0 0;cursor:grab;user-select:none;max-width:none}
.zbar{position:fixed;top:14px;right:16px;z-index:61;display:none;gap:8px}.zbar.on{display:flex}
.zbtn{font-family:var(--mono);background:var(--panel);color:var(--ink);border:1px solid var(--line);border-radius:9px;min-width:42px;height:42px;cursor:pointer;font-size:14px;padding:0 12px}
.note{border-left:3px solid var(--gold);background:var(--panel);border-radius:0 8px 8px 0;padding:10px 14px;font-size:13px;color:var(--dim);margin-bottom:14px}
</style></head><body>
<header><b>Brooks <span>Course Slides</span></b>
<input id=q placeholder="search topics / abbreviations...">
<button id=drill>🎯 Drill mode: OFF</button>
<button id=setbase title="Change the folder path if slides do not load">📁 Path</button>
<a href="index.html">← Codex hub</a></header>
<div class=layout><nav id=side></nav><div id=main><div class=empty>Pick a pattern topic on the left. 🎯 Drill mode shows the un-annotated chart first — read it, then click to reveal Al's annotated version.</div></div></div>
<div class=zov id=zov><img id=zimg></div>
<div class=zbar id=zbar><button class=zbtn id=zrev style="display:none">Reveal</button><button class=zbtn id=zout>−</button><button class=zbtn id=zin>+</button><button class=zbtn id=zfit>⤢</button><button class=zbtn id=zx>×</button></div>
<script>
const PARTS=__PARTS__;
let BASE=localStorage.slBase||__BASE__;
const side=document.getElementById("side"),main=document.getElementById("main"),q=document.getElementById("q");
let cur=null,drill=false;
// The shared Slides folder can mount on a different drive letter (or under
// "My Drive") on other machines — probe candidates and keep the first that loads.
(function(){
 const probe=PARTS[0]&&PARTS[0].topics[0];if(!probe||!probe.ann.length)return;
 const rel="/"+encodeURI(probe.dir+"/"+probe.ann[0]);
 const test=b=>new Promise(res=>{const im=new Image();im.onload=()=>res(true);im.onerror=()=>res(false);im.src=b+rel;});
 test(BASE).then(async ok=>{
  if(ok)return;
  const tail=".shortcut-targets-by-id/1oanmO7XO-brbZThAYjV6t6hZdzRyy9rE/Slides";
  const cands=[];
  for(const L of "GHIJKLDEF")cands.push("file:///"+L+":/"+tail,"file:///"+L+":/My Drive/"+tail);
  for(const b of cands){if(b===BASE)continue;if(await test(b)){BASE=b;localStorage.slBase=b;if(cur)show(cur);return;}}
 });
})();
document.getElementById("setbase").onclick=()=>{const v=prompt("Slides folder base URL:",BASE);if(v){BASE=v;localStorage.slBase=v;if(cur)show(cur);}};
document.getElementById("drill").onclick=function(){drill=!drill;this.textContent="🎯 Drill mode: "+(drill?"ON":"OFF");this.classList.toggle("on",drill);if(cur)show(cur);};
function url(t,f){return BASE+"/"+encodeURI(t.dir+"/"+f);}
function renderSide(){
 const term=q.value.toLowerCase();side.innerHTML="";
 PARTS.forEach(p=>{
  const ts=p.topics.filter(t=>!term||t.name.toLowerCase().includes(term)||(t.abbr||"").toLowerCase().includes(term));
  if(!ts.length)return;
  const h=document.createElement("div");h.className="part";h.textContent=p.part;side.appendChild(h);
  ts.forEach(t=>{const el=document.createElement("div");el.className="topic"+(cur===t?" sel":"");
   el.innerHTML=(t.num?t.num+" · ":"")+t.name+(t.abbr?' <span class=ab>'+t.abbr+"</span>":"");
   el.onclick=()=>{cur=t;renderSide();show(t);};side.appendChild(el);});});}
function show(t){
 let h="<h2>"+t.name+"</h2><div class=meta>"+t.dir+(t.abbr?" · Encyclopedia: "+t.abbr:"")+" · "+t.ann.length+" slides"+(t.m.length?" + "+t.m.length+" bare charts":"")+"</div>";
 if(drill&&t.m.length){
  h+='<div class=note>Drill: read each bare chart first — where is the pattern, where do you enter? Click to zoom, then Reveal.</div><div class=grid>';
  t.m.forEach(f=>{const pair=t.ann.find(a=>a.replace(/\.[^.]+$/,"")===f.replace(/^M-?/i,"").replace(/\.[^.]+$/,""))||t.ann[0];
   h+='<div class=slide data-src="'+url(t,f)+'" data-rev="'+(pair?url(t,pair):"")+'"><img loading=lazy src="'+url(t,f)+'"><div class=cap>'+f+" → reveal: "+(pair||"—")+"</div></div>";});
  h+="</div>";
 }else{
  h+='<div class=grid>';
  t.ann.forEach(f=>{h+='<div class=slide data-src="'+url(t,f)+'"><img loading=lazy src="'+url(t,f)+'"><div class=cap>'+f+"</div></div>";});
  h+="</div>";
  if(!t.ann.length)h+='<div class=empty>No annotated slides in this folder.</div>';
 }
 main.innerHTML=h;main.scrollTop=0;
 main.querySelectorAll(".slide").forEach(s=>s.onclick=()=>openZoom(s.dataset.src,s.dataset.rev));}
const zov=document.getElementById("zov"),zimg=document.getElementById("zimg"),zbar=document.getElementById("zbar"),zrev=document.getElementById("zrev");
let Z={s:1,x:0,y:0,d:false,px:0,py:0};
function zap(){zimg.style.transform="translate("+Z.x+"px,"+Z.y+"px) scale("+Z.s+")";}
function zfit(){const iw=zimg.naturalWidth,ih=zimg.naturalHeight;if(!iw)return;Z.s=Math.min(innerWidth/iw,innerHeight/ih)*0.97;Z.x=(innerWidth-iw*Z.s)/2;Z.y=(innerHeight-ih*Z.s)/2;zap();}
function zat(cx,cy,f){const s2=Math.max(0.05,Math.min(9,Z.s*f));Z.x=cx-(cx-Z.x)*(s2/Z.s);Z.y=cy-(cy-Z.y)*(s2/Z.s);Z.s=s2;zap();}
function openZoom(src,rev){zimg.src=src;zov.classList.add("on");zbar.classList.add("on");
 zrev.style.display=rev?"":"none";zrev.onclick=()=>{zimg.src=rev;zrev.style.display="none";zimg.onload=zfit;};
 zimg.onload=zfit;if(zimg.complete)zfit();}
function closeZoom(){zov.classList.remove("on");zbar.classList.remove("on");}
zov.addEventListener("wheel",e=>{e.preventDefault();zat(e.clientX,e.clientY,e.deltaY<0?1.15:0.87);},{passive:false});
zimg.addEventListener("mousedown",e=>{Z.d=true;Z.px=e.clientX;Z.py=e.clientY;e.preventDefault();});
window.addEventListener("mousemove",e=>{if(!Z.d)return;Z.x+=e.clientX-Z.px;Z.y+=e.clientY-Z.py;Z.px=e.clientX;Z.py=e.clientY;zap();});
window.addEventListener("mouseup",()=>Z.d=false);
document.getElementById("zin").onclick=()=>zat(innerWidth/2,innerHeight/2,1.3);
document.getElementById("zout").onclick=()=>zat(innerWidth/2,innerHeight/2,0.77);
document.getElementById("zfit").onclick=zfit;
document.getElementById("zx").onclick=closeZoom;
document.addEventListener("keydown",e=>{if(e.key==="Escape")closeZoom();});
q.oninput=renderSide;renderSide();
</script></body></html>'''

html = (TMPL.replace('__PARTS__', json.dumps(parts, ensure_ascii=False))
            .replace('__BASE__', json.dumps(DEFAULT_BASE)))
(HUB / 'slides.html').write_text(html, encoding='utf-8')
print(f'slides.html: {len(parts)} parts, {nt} topics ({nmap} mapped to encyclopedia), {ns} slides')
