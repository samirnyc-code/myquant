"""Build the Brooks Codex forum day-browser (forum.html).

Input:  forum_index.json (from brooks_forum_scrape.py), charts in
        docs/living/brooks_codex/forum_charts/<id>.jpg
Output: docs/living/brooks_codex/forum.html  (app shell + embedded data)

Per day it:
  - strips the tooltip expansions "H2(Two legged...)" -> "H2", building one
    shared abbreviation dictionary (texts shrink ~10x; the view re-attaches
    definitions as hover tooltips client-side)
  - parses per-bar entries (lines starting with a bar number, monotone guard)
  - tags the text with the official encyclopedia index (brooks_tag_days)
  - calibrates the racing stripe: detects candle wicks inside the tool-geometry
    slots and Theil-Sen fits x(n) = a + b*n (see brooks_build_bbb_view.py)

  python scripts/brooks_build_forum.py <forum_index.json> [--limit N]
"""
import json, re, sys, io, itertools, statistics
from pathlib import Path
from PIL import Image

ROOT = Path(__file__).resolve().parent.parent
HUB = ROOT / 'docs' / 'living' / 'brooks_codex'
sys.path.insert(0, str(ROOT / 'scripts'))
from brooks_tag_days import tag_text, IDX

ABBR_DICT = {}

def strip_expansions(text):
    """Replace ABBR(expansion) with ABBR, collecting the dictionary."""
    def sub(m):
        abbr, exp = m.group(1), m.group(2).strip()
        if abbr not in ABBR_DICT or len(exp) > len(ABBR_DICT[abbr]):
            ABBR_DICT[abbr] = exp
        return abbr
    prev = None
    while prev != text:  # nested parens: peel inside-out
        prev = text
        text = re.sub(r"([A-Za-z][A-Za-z0-9']{0,30})\(([^()]*)\)", sub, text)
    return re.sub(r'\s+', ' ', text).strip()

def parse_bars(text):
    """Split into per-bar entries; enforce monotone bar numbers."""
    parts = re.split(r'(?:(?<=^)|(?<=[.!?)\s]))\b(\d{1,2})\s+(?=[A-Z(])', ' ' + text)
    bars, prev = [], 0
    i = 1
    while i + 1 <= len(parts) - 1:
        n, body = int(parts[i]), parts[i + 1].strip()
        if n <= prev or n > 90:
            if bars:  # glue misparse back onto previous entry
                bars[-1]['t'] += f' {n} {body}'
            i += 2
            continue
        bars.append({'n': n, 't': body})
        prev = n
        i += 2
    return bars

def fit_stripe(img_path, geom):
    """Theil-Sen fit of bar centers; returns dict or None."""
    try:
        img = Image.open(img_path).convert('L')
    except Exception:
        return None
    W, H = img.size
    px = img.load()
    bars, left, width = geom.get('bars'), geom.get('left'), geom.get('width')
    if left is None or not bars or not width or bars < 5:
        return None
    s = 780.0 / H
    inc = width / (bars - 1) / s
    Y0, Y1 = 30, H - 30
    dark = lambda x: sum(1 for y in range(Y0, Y1) if px[x, y] < 90) if 0 <= x < W else 0
    pts = []
    for n in range(1, bars + 1):
        a = (left + (n - 1) * width / (bars - 1)) / s - inc
        lo, hi = int(a + 1), int(a + inc - 1)
        if hi <= lo:
            continue
        best, bx = max((dark(x), x) for x in range(lo, hi + 1))
        if best >= 8:
            pts.append((n, bx + 0.5))
    if len(pts) >= 10:
        sl = [(x2 - x1) / (n2 - n1) for (n1, x1), (n2, x2) in itertools.combinations(pts, 2)]
        b = statistics.median(sl)
        a = statistics.median(x - b * n for n, x in pts)
    else:
        b = inc
        a = left / s - inc / 2 - b
    return {'a': round(a / W, 5), 'b': round(b / W, 6), 'bars': bars}

def build(days, limit=None):
    out = []
    for d in days if not limit else days[:limit]:
        if not d.get('has_chart'):
            continue
        rec = {'id': d['id'], 'date': d['date'], 'file': d.get('file')}
        if d.get('text'):
            txt = strip_expansions(d['text'])
            rec['bars'] = parse_bars(txt)
            rec['tags'] = {k: v['n'] for k, v in tag_text(d['text']).items()}
        if d.get('geom'):
            f = fit_stripe(HUB / d.get('file', ''), d['geom'])
            if f:
                rec['fit'] = f
        if d.get('tool_url'):
            rec['tool'] = d['tool_url']
        out.append(rec)
    return out

TMPL = r'''<!doctype html><html><head><meta charset=utf-8><title>Brooks Codex — Real Days</title><style>
:root{--bg:#0c1016;--panel:#141b24;--panel2:#1b2430;--ink:#e8eef6;--dim:#93a2b4;--line:#25303d;--gold:#e6b23a;--mono:ui-monospace,Menlo,Consolas,monospace}
*{box-sizing:border-box}body{margin:0;background:var(--bg);color:var(--ink);font-family:system-ui}
header{border-bottom:1px solid var(--line);padding:12px 20px;display:flex;align-items:center;gap:14px;flex-wrap:wrap;position:sticky;top:0;background:var(--bg);z-index:5}
header b{font-size:17px;letter-spacing:.12em;text-transform:uppercase}header b span{color:var(--gold)}
header a{color:var(--dim);font-family:var(--mono);font-size:12px;text-decoration:none}
#q,#tagsel{font-family:var(--mono);font-size:13px;background:var(--panel);color:var(--ink);border:1px solid var(--line);border-radius:8px;padding:8px 12px}
#q{width:230px}
.layout{display:grid;grid-template-columns:295px minmax(0,1fr);gap:0;height:calc(100vh - 57px)}
#list{overflow-y:auto;border-right:1px solid var(--line);padding:10px}
.day{padding:9px 12px;border-radius:8px;cursor:pointer;border:1px solid transparent}
.day:hover{background:var(--panel)}.day.sel{background:var(--panel2);border-color:var(--gold)}
.day .d{font-family:var(--mono);font-size:13px}.day .tg{font-size:11px;color:var(--dim);font-family:var(--mono)}
#main{overflow-y:auto;padding:16px 22px}
.chartwrap{display:flex;justify-content:center}
.chartbox{position:relative;border:1px solid var(--line);border-radius:10px;overflow:hidden;background:#fff;cursor:crosshair;width:100%}
.chartbox .ct{position:absolute;top:0;left:0;transform-origin:0 0}
.chartbox .ct img{display:block;width:100%}
.zctl{position:absolute;right:8px;top:8px;z-index:3;display:flex;gap:6px}
.zctl button{font-family:var(--mono);background:rgba(20,27,36,.85);color:var(--ink);border:1px solid var(--line);border-radius:7px;width:32px;height:32px;cursor:pointer;font-size:14px}
.hl{position:absolute;top:0;bottom:0;background:rgba(255,238,0,.13);border-left:1.5px solid #ffe600;border-right:1.5px solid #ffe600;pointer-events:none}
.ctl{display:flex;gap:8px;align-items:center;margin:10px 0;flex-wrap:wrap}
.ctl button{font-family:var(--mono);background:var(--panel);color:var(--ink);border:1px solid var(--line);border-radius:8px;padding:8px 13px;cursor:pointer;font-size:12.5px}
.ctl button:hover{border-color:var(--gold)}
.tagrow{margin:6px 0 12px}.tag{display:inline-block;font-family:var(--mono);font-size:11.5px;background:var(--panel2);border:1px solid var(--line);border-radius:20px;padding:3px 10px;margin:2px 4px 2px 0;color:var(--gold);cursor:pointer}
.txtpanel{border:1px solid var(--line);border-left:4px solid #ffe600;border-radius:10px;background:var(--panel);padding:14px 18px;min-height:90px;margin-bottom:12px}
.txtpanel .bn{font-family:var(--mono);color:var(--gold);font-weight:700;font-size:14px;margin-bottom:6px}
.txtpanel .bt{font-size:16px;line-height:1.6}
.cards .card{border:1px solid var(--line);border-left:3px solid var(--line);border-radius:8px;background:var(--panel);padding:10px 14px;margin-bottom:8px;cursor:pointer}
.cards .card.sel{border-left-color:#ffe600;background:var(--panel2)}
.cards .bn{font-family:var(--mono);color:var(--gold);font-size:12px;font-weight:700}
.cards .bt{font-size:13.5px;color:var(--dim);line-height:1.5}.card.sel .bt{color:var(--ink)}
abbr{text-decoration:underline dotted rgba(230,178,58,.5);cursor:help}
.empty{color:var(--dim);font-family:var(--mono);padding:30px}
.daygrid.split{display:grid;grid-template-columns:minmax(0,1fr) clamp(320px,30%,430px);gap:18px;align-items:start}
.daygrid.split .chartcol{position:sticky;top:0}
body.nolist #list{display:none}
body.nolist .layout{grid-template-columns:minmax(0,1fr)}
.daygrid.split .cards{max-height:calc(100vh - 90px);overflow-y:auto;padding-right:4px}
.zov{position:fixed;inset:0;z-index:60;background:rgba(4,7,11,.93);display:none;overflow:hidden;touch-action:none}
.zov.on{display:block}.zov img{position:absolute;top:0;left:0;transform-origin:0 0;cursor:grab;user-select:none;max-width:none;max-height:none}
.zbar{position:fixed;top:14px;right:16px;z-index:61;display:none;gap:8px}.zov.on~.zbar,{display:flex}
.zbar.on{display:flex}
.zbtn{font-family:var(--mono);background:var(--panel);color:var(--ink);border:1px solid var(--line);border-radius:9px;width:42px;height:42px;cursor:pointer;font-size:15px}
</style></head><body>
<header><button id=burger title="Show/hide day list" style="font-size:16px;background:var(--panel);color:var(--ink);border:1px solid var(--line);border-radius:8px;padding:7px 12px;cursor:pointer">&#9776;</button><b>Brooks <span>Real Days</span></b>
 <input id=q placeholder="search date / tag / text...">
 <select id=tagsel><option value="">— all tags —</option></select>
 <span id=count style="font-family:var(--mono);font-size:12px;color:var(--dim)"></span>
 <a href="index.html" style="margin-left:auto">← Codex hub</a></header>
<div class=layout>
 <nav id=list></nav>
 <div id=main><div class=empty>Pick a day on the left.</div></div>
</div>
<div class=zov id=zov><img id=zimg></div>
<div class=zbar id=zbar><button class=zbtn id=zout>&minus;</button><button class=zbtn id=zin>+</button><button class=zbtn id=zfit>&#10530;</button><button class=zbtn id=zx>&times;</button></div>
<script>
const DAYS=__DAYS__;const DICT=__DICT__;const ENC=__ENC__;
const list=document.getElementById("list"),main=document.getElementById("main"),q=document.getElementById("q"),tagsel=document.getElementById("tagsel");
const allTags={};DAYS.forEach(d=>Object.keys(d.tags||{}).forEach(t=>allTags[t]=(allTags[t]||0)+1));
Object.entries(allTags).sort((a,b)=>b[1]-a[1]).forEach(([t,n])=>{const o=document.createElement("option");o.value=t;o.textContent=t+" ("+n+") — "+(ENC[t]||"");tagsel.appendChild(o);});
let cur=null;
function esc(s){return s.replace(/&/g,"&amp;").replace(/</g,"&lt;");}
let expanded=false;let split=!!localStorage.bcSplit;
const zov=document.getElementById("zov"),zimg=document.getElementById("zimg"),zbar=document.getElementById("zbar");
let Z={s:1,x:0,y:0,d:false,px:0,py:0};
function zap(){zimg.style.transform="translate("+Z.x+"px,"+Z.y+"px) scale("+Z.s+")";}
function zfit(){const iw=zimg.naturalWidth,ih=zimg.naturalHeight;if(!iw)return;Z.s=Math.min(innerWidth/iw,innerHeight/ih)*0.98;Z.x=(innerWidth-iw*Z.s)/2;Z.y=(innerHeight-ih*Z.s)/2;zap();}
function zat(cx,cy,f){const s2=Math.max(0.1,Math.min(9,Z.s*f));Z.x=cx-(cx-Z.x)*(s2/Z.s);Z.y=cy-(cy-Z.y)*(s2/Z.s);Z.s=s2;zap();}
function openZoom(src){zimg.src=src;zov.classList.add("on");zbar.classList.add("on");zimg.onload=zfit;if(zimg.complete)zfit();}
function closeZoom(){zov.classList.remove("on");zbar.classList.remove("on");}
zov.addEventListener("wheel",e=>{e.preventDefault();zat(e.clientX,e.clientY,e.deltaY<0?1.15:0.87);},{passive:false});
zimg.addEventListener("mousedown",e=>{Z.d=true;Z.px=e.clientX;Z.py=e.clientY;zimg.style.cursor="grabbing";e.preventDefault();});
window.addEventListener("mousemove",e=>{if(!Z.d)return;Z.x+=e.clientX-Z.px;Z.y+=e.clientY-Z.py;Z.px=e.clientX;Z.py=e.clientY;zap();});
window.addEventListener("mouseup",()=>{Z.d=false;zimg.style.cursor="grab";});
document.getElementById("zin").onclick=()=>zat(innerWidth/2,innerHeight/2,1.3);
document.getElementById("zout").onclick=()=>zat(innerWidth/2,innerHeight/2,0.77);
document.getElementById("zfit").onclick=zfit;
document.getElementById("zx").onclick=closeZoom;
document.addEventListener("keydown",e=>{if(e.key==="Escape")closeZoom();});
function markup(s){
 if(expanded)return esc(s).replace(/\b([A-Za-z][A-Za-z0-9']{0,30})\b/g,(m,w)=>DICT[w]?w+' <i style="color:var(--dim)">('+esc(DICT[w])+')</i>':m);
 return esc(s).replace(/\b([A-Za-z][A-Za-z0-9']{0,30})\b/g,(m,w)=>DICT[w]?'<abbr title="'+esc(DICT[w]).replace(/"/g,"&quot;")+'">'+w+"</abbr>":m);}
function render(){
 const term=q.value.toLowerCase(),tag=tagsel.value;
 const hits=DAYS.filter(d=>{
  if(tag&&!(d.tags&&d.tags[tag]))return false;
  if(!term)return true;
  if(d.date.includes(term))return true;
  if(d.tags&&Object.keys(d.tags).some(t=>t.toLowerCase().includes(term)))return true;
  if(d.bars&&d.bars.some(b=>b.t.toLowerCase().includes(term)))return true;
  return false;});
 document.getElementById("count").textContent=hits.length+" / "+DAYS.length+" days";
 list.innerHTML="";
 hits.forEach(d=>{const el=document.createElement("div");el.className="day"+(cur===d?" sel":"");
  el.innerHTML='<div class=d>'+d.date+(d.bars?"":" · chart only")+'</div><div class=tg>'+Object.keys(d.tags||{}).slice(0,4).join(" · ")+'</div>';
  el.onclick=()=>{cur=d;render();show(d);};list.appendChild(el);});
}
function show(d){
 let h='<div class="daygrid'+(split?' split':'')+'"><div class=chartcol>';
 h+='<div class=chartwrap><div class=chartbox id=cb><div class=ct id=ct><img id=chart src="forum_charts/'+d.id+'.jpg"><div class=hl id=hl style="display:none"></div></div>';
 h+='<div class=zctl><button id=zin2>+</button><button id=zout2>&minus;</button><button id=zreset>&#10530;</button></div></div></div>';
 h+='<div class=ctl><button id=prev>◀ Prev</button><button id=next>Next ▶</button><button id=zoom>⛶ Full</button><button id=layout>◫ '+(split?"Split":"Stack")+'</button><button id=stripe>▣ Stripe: ON</button><button id=expand>Aa Expand: OFF</button>';
 if(d.tool)h+='<a href="'+d.tool+'" target=_blank><button>▶ Live tool</button></a>';
 h+='</div>';
 h+='<div class=tagrow>'+Object.entries(d.tags||{}).map(([t,n])=>'<span class=tag title="'+esc(ENC[t]||"")+'" onclick="tagsel.value=\''+t+'\';render()">'+t+" ×"+n+"</span>").join("")+'</div>';
 h+='<div class=txtpanel><div class=bn id=bn>—</div><div class=bt id=bt>Hover the chart or click a card.</div></div></div>';
 if(d.bars&&d.bars.length){
  h+='<div class=cards id=cards>';
  d.bars.forEach(b=>{h+='<div class=card data-n="'+b.n+'"><span class=bn>Bar '+b.n+'</span> <span class=bt>'+markup(b.t)+"</span></div>";});
  h+="</div>";
 } else h+='<div class=empty>No bar-by-bar text for this day (chart-only).</div>';
 h+='</div>';
 main.innerHTML=h;main.scrollTop=0;
 document.getElementById("zoom").onclick=()=>openZoom("forum_charts/"+d.id+".jpg");
 document.getElementById("layout").onclick=()=>{split=!split;localStorage.bcSplit=split?"1":"";show(d);};
 const cb=document.getElementById("cb"),ct=document.getElementById("ct"),hl=document.getElementById("hl"),bn=document.getElementById("bn"),bt=document.getElementById("bt"),chart=document.getElementById("chart");
 const hasBars=!!(d.bars&&d.bars.length);
 const map={};(d.bars||[]).forEach(b=>map[b.n]=b.t);const ns=(d.bars||[]).map(b=>b.n);let sel=null,on=hasBars&&!!d.fit;
 const F=hasBars?d.fit:null;
 // in-place pan/zoom: content div (image at box width) transformed inside the box
 let V={s:1,x:0,y:0,min:1,d:false,px:0,py:0,moved:0};
 function vap(){ct.style.transform="translate("+V.x+"px,"+V.y+"px) scale("+V.s+")";}
 function clampV(){const cw=cb.clientWidth,chh=ct.offsetHeight;
  V.x=Math.min(0,Math.max(cb.clientWidth-cw*V.s,V.x));V.y=Math.min(0,Math.max(cb.clientHeight-chh*V.s,V.y));}
 function vfit(){const cw=cb.clientWidth,nh=chart.naturalHeight/chart.naturalWidth*cw;
  const maxH=Math.round(innerHeight*(split?0.74:0.6));
  cb.style.height=Math.min(nh,maxH)+"px";ct.style.width=cw+"px";
  V.min=Math.min(1,cb.clientHeight/nh);V.s=V.min;V.x=(cb.clientWidth-cw*V.s)/2;V.y=0;vap();}
 function vat(cx,cy,f){const s2=Math.max(V.min,Math.min(8,V.s*f));
  V.x=cx-(cx-V.x)*(s2/V.s);V.y=cy-(cy-V.y)*(s2/V.s);V.s=s2;clampV();vap();}
 chart.onload=vfit;if(chart.complete&&chart.naturalWidth)vfit();
 cb.addEventListener("wheel",e=>{e.preventDefault();const r=cb.getBoundingClientRect();
  vat(e.clientX-r.left,e.clientY-r.top,e.deltaY<0?1.18:0.85);},{passive:false});
 cb.addEventListener("mousedown",e=>{V.d=true;V.px=e.clientX;V.py=e.clientY;V.moved=0;e.preventDefault();});
 window.addEventListener("mousemove",e=>{if(!V.d)return;V.x+=e.clientX-V.px;V.y+=e.clientY-V.py;
  V.moved+=Math.abs(e.clientX-V.px)+Math.abs(e.clientY-V.py);V.px=e.clientX;V.py=e.clientY;clampV();vap();});
 window.addEventListener("mouseup",()=>{V.d=false;});
 document.getElementById("zin2").onclick=()=>vat(cb.clientWidth/2,cb.clientHeight/2,1.3);
 document.getElementById("zout2").onclick=()=>vat(cb.clientWidth/2,cb.clientHeight/2,0.77);
 document.getElementById("zreset").onclick=vfit;
 cb.addEventListener("dblclick",vfit);
 if(!hasBars)return;
 function xf(n){return F.a+F.b*n;}
 function setStripe(v){on=v&&!!F;hl.style.display=on?"":"none";document.getElementById("stripe").textContent="▣ Stripe: "+(on?"ON":"OFF");}
 document.getElementById("stripe").onclick=()=>setStripe(!on);
 document.getElementById("expand").textContent="Aa Expand: "+(expanded?"ON":"OFF");
 document.getElementById("expand").onclick=()=>{expanded=!expanded;show(d);};
 function pick(n){
  if(F&&on){const w=ct.clientWidth,bw=Math.max(F.b*w,5);hl.style.left=(xf(n)*w-bw/2)+"px";hl.style.width=bw+"px";hl.style.display="";}
  const m=map[n]?n:ns.reduce((a,b)=>Math.abs(b-n)<Math.abs(a-n)?b:a,ns[0]);
  bn.textContent=map[n]?("Bar "+n):("Bar "+n+" — no note · nearest: Bar "+m);
  bt.innerHTML=markup(map[m]);bt.style.opacity=map[n]?1:.6;
  document.querySelectorAll(".card").forEach(c=>{const s=+c.dataset.n===m;c.classList.toggle("sel",s);
   if(s&&split)c.scrollIntoView({block:"nearest",behavior:"smooth"});});sel=n;}
 if(F)cb.addEventListener("mousemove",e=>{if(V.d&&V.moved>6)return;const r=cb.getBoundingClientRect();
  const f=((e.clientX-r.left)-V.x)/(V.s*ct.clientWidth);let best=1,bd=9;
  for(let n=1;n<=F.bars;n++){const dd=Math.abs(xf(n)-f);if(dd<bd){bd=dd;best=n;}}pick(best);});
 document.querySelectorAll(".card").forEach(c=>c.onclick=()=>pick(+c.dataset.n));
 document.getElementById("next").onclick=()=>{const c=sel??0;pick(ns.find(n=>n>c)??ns[ns.length-1]);};
 document.getElementById("prev").onclick=()=>{const c=sel??999;const p=[...ns].reverse().find(n=>n<c);pick(p??ns[0]);};
 setStripe(true);pick(ns[0]);
}
document.addEventListener("keydown",e=>{if(e.target.tagName==="INPUT")return;
 if(e.key==="ArrowRight")document.getElementById("next")?.click();
 if(e.key==="ArrowLeft")document.getElementById("prev")?.click();});
document.getElementById("burger").onclick=()=>document.body.classList.toggle("nolist");
q.oninput=render;tagsel.onchange=render;render();
</script></body></html>'''

if __name__ == '__main__':
    src = Path(sys.argv[1])
    limit = int(sys.argv[sys.argv.index('--limit') + 1]) if '--limit' in sys.argv else None
    days = json.load(open(src, encoding='utf-8'))
    days = [d for d in days if d.get('date')]
    days.sort(key=lambda d: (d['date'][6:10], d['date'][0:2], d['date'][3:5]), reverse=True)
    data = build(days, limit)
    enc = {e['abbr']: e['section'] for e in IDX}
    html = (TMPL.replace('__DAYS__', json.dumps(data, ensure_ascii=False))
                .replace('__DICT__', json.dumps(ABBR_DICT, ensure_ascii=False))
                .replace('__ENC__', json.dumps(enc, ensure_ascii=False)))
    out = HUB / 'forum.html'
    out.write_text(html, encoding='utf-8')
    json.dump({'days': data, 'dict': ABBR_DICT, 'enc': enc},
              open(HUB / 'forum_days.json', 'w', encoding='utf-8'), ensure_ascii=False)
    nb = sum(1 for d in data if d.get('bars'))
    print(f'forum.html: {len(data)} days ({nb} with bar-by-bar), '
          f'{len(ABBR_DICT)} dict abbrs, {out.stat().st_size/1e6:.1f} MB')
