"""build_getting_started_page.py — render the Getting Started knowledge base into a single
self-contained Mission Control artifact (docs/artifacts/eminiaddict_getting_started.html),
structured in David Halsey's own curriculum order. Re-runnable: pulls text + slides from the
scrape and transcripts/nuggets when present (so re-running after transcription fills them in).

Serves at MC :8590 (group EminiAddict). Slides embedded as base64 -> the page is portable.

Usage: python build_getting_started_page.py
"""
import base64
import html
import io
import json
import os
import re

import numpy as np
import pandas as pd
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.patches import Rectangle

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
ES_PARQUET = os.path.join(ROOT, "research", "scalp_swing", "es_5m_rth.parquet")
_ESDF = None


def _load_es():
    global _ESDF
    if _ESDF is None:
        _ESDF = pd.read_parquet(ES_PARQUET)[["DateTime", "Open", "High", "Low", "Close", "Date"]]
        _ESDF["Date"] = _ESDF["Date"].astype(str)
    return _ESDF


def _es_num(s):
    m = re.search(r'\b(6[5-9]\d\d|7[0-6]\d\d)(\.\d+)?\b', str(s).replace(",", ""))
    return float(m.group(0)) if m else None


def es_levels_from_report(r):
    """Extract ES-range numeric levels (value,label,role) from key_levels + ES scenarios."""
    out = []
    for x in r.get("es", {}).get("key_levels", []):
        v = _es_num(x.get("price", ""))
        if v is None:
            continue
        lab = (x.get("label", "") + " " + str(x.get("price", ""))).lower()
        role = ("bull" if "bull" in lab else "bear" if "bear" in lab
                else "target" if ("target" in lab or "retrace" in lab) else "other")
        out.append((v, x.get("price", ""), role))
    for s in r.get("scenarios", []):
        if s.get("instrument") != "ES":
            continue
        v = _es_num(s.get("target", ""))
        if v:
            out.append((v, "target", "target"))
        v = _es_num(s.get("invalidation", ""))
        if v:
            out.append((v, "invalidation", "bear"))
    seen, ded = set(), []
    for v, l, ro in out:
        if round(v) in seen:
            continue
        seen.add(round(v)); ded.append((v, l, ro))
    return ded


def es_chart_b64(date_iso, levels):
    """Candlestick of the ~6 RTH sessions up to date_iso with the ES levels drawn. -> data URI."""
    df = _load_es()
    days = sorted(df["Date"].unique())
    le = [d for d in days if d <= date_iso]
    if not le:
        return ""
    end = le[-1]
    window = days[max(0, days.index(end) - 5): days.index(end) + 1]
    g = df[df["Date"].isin(window)].reset_index(drop=True)
    if g.empty:
        return ""
    n = len(g)
    fig, ax = plt.subplots(figsize=(11, 5), facecolor="#0d1117")
    ax.set_facecolor("#0d1117")
    for i in range(n):
        o, h, l, c = g.Open[i], g.High[i], g.Low[i], g.Close[i]
        col = "#26a65b" if c >= o else "#e2453c"
        ax.plot([i, i], [l, h], color=col, lw=0.7, zorder=2)
        ax.add_patch(Rectangle((i - .3, min(o, c)), .6, abs(c - o) or .1, facecolor=col,
                               edgecolor=col, zorder=3))
    colmap = {"bull": "#3fb950", "bear": "#f85149", "target": "#22d3ee", "other": "#e3b341"}
    for v, lab, role in levels:
        ax.axhline(v, color=colmap.get(role, "#e3b341"), lw=1.1, ls="--", alpha=.9, zorder=4)
        ax.text(n - 0.5, v, f" {v:g} {lab}", color=colmap.get(role, "#e3b341"), fontsize=7,
                va="center", ha="left")
    # day separators + labels
    for i in range(1, n):
        if g.Date[i] != g.Date[i - 1]:
            ax.axvline(i - 0.5, color="#232a33", lw=0.7, zorder=1)
    ticks = [i for i in range(n) if i == 0 or g.Date[i] != g.Date[i - 1]]
    ax.set_xticks(ticks)
    ax.set_xticklabels([g.Date[i][5:] for i in ticks], color="#8b949e", fontsize=7)
    ax.tick_params(colors="#8b949e", labelsize=7)
    for sp in ax.spines.values():
        sp.set_color("#30363d")
    ax.set_xlim(-1, n + 12)
    ax.set_title(f"ES 5-min (RTH) — levels in play thru {end}", color="#e6edf3", fontsize=9,
                 loc="left")
    buf = io.BytesIO()
    fig.tight_layout()
    fig.savefig(buf, format="png", dpi=110, facecolor=fig.get_facecolor())
    plt.close(fig)
    return "data:image/png;base64," + base64.b64encode(buf.getvalue()).decode()
GS = os.path.join(ROOT, "eminiaddict", "data", "site", "getting_started")
TR = os.path.join(GS, "transcripts")
NUG = os.path.join(GS, "nuggets")          # <idx>_*.md nugget files (assistant-produced)
OUT = os.path.join(ROOT, "docs", "artifacts", "eminiaddict_tool.html")
DAILY = os.path.join(ROOT, "eminiaddict", "data", "daily")   # daily reports live here
CATALOG = os.path.join(ROOT, "data", "_catalog", "claude_artifacts.json")

CSS = """
:root{--bg:#0d1117;--card:#161b22;--chip:#30363d;--fg:#e6edf3;--mut:#8b949e;--blue:#58a6ff;--gold:#e3b341}
*{box-sizing:border-box}body{margin:0;background:var(--bg);color:var(--fg);font:14.5px/1.65 -apple-system,Segoe UI,Roboto,sans-serif}
header{position:sticky;top:0;background:var(--bg);border-bottom:1px solid var(--chip);padding:14px 24px;z-index:10}
header h1{font-size:18px;margin:0}a{color:var(--blue);text-decoration:none}a:hover{text-decoration:underline}
.wrap{max-width:960px;margin:0 auto;padding:18px 24px 90px}
.lead{color:var(--mut);margin:6px 0 18px}
.toc{background:var(--card);border:1px solid var(--chip);border-radius:12px;padding:12px 18px;margin:0 0 22px;columns:2;column-gap:26px}
.toc a{display:block;font-size:13.5px;margin:3px 0}
.mod{background:var(--card);border:1px solid var(--chip);border-radius:12px;padding:14px 20px;margin:12px 0;border-left:3px solid var(--blue)}
.mod .k{color:var(--mut);font-size:12px;text-transform:uppercase;letter-spacing:.04em}
.modhead{cursor:pointer;font-size:16px;font-weight:600;margin:2px 0;user-select:none;display:flex;align-items:center;gap:9px}
.modhead .arw{color:var(--mut);transition:transform .15s;font-size:12px}
.mod.open .modhead .arw{transform:rotate(90deg)}
.modbody{display:none;margin-top:10px}.mod.open .modbody{display:block}
.mod p{margin:8px 0;font-size:13.7px}
.slides{display:flex;flex-wrap:wrap;gap:8px;margin:10px 0}
.slides img{max-width:100%;width:300px;border:1px solid var(--chip);border-radius:8px;cursor:zoom-in}
.vid{margin:8px 0}.vid a{font-weight:600}
details{margin:8px 0}summary{cursor:pointer;color:var(--gold);font-weight:600}
pre{white-space:pre-wrap;background:#0b0f14;border:1px solid var(--chip);border-radius:8px;padding:10px 12px;font-size:12.5px;color:#cbd5e1;max-height:340px;overflow:auto}
.nug{background:linear-gradient(180deg,#141e18,#12261a);border:1px solid #2ea043;border-radius:11px;padding:14px 18px;margin:6px 0 16px;box-shadow:0 1px 0 #0b1f13 inset}
.nug .hd{color:#3fb950;font-weight:700;font-size:14px;margin:0 0 8px;letter-spacing:.02em}
.nug h4{margin:12px 0 4px;color:var(--gold);font-size:13px;text-transform:uppercase;letter-spacing:.04em}
.nug p{margin:6px 0;font-size:13.6px}.nug ul{margin:4px 0;padding-left:20px}.nug li{margin:3px 0;font-size:13.6px}
.nug .tldr{background:#0b1f13;border-left:3px solid #3fb950;padding:7px 12px;border-radius:6px;font-size:13.6px}
.pending{color:var(--mut);font-style:italic}
.glossary dt{font-weight:600;color:var(--gold);margin-top:10px}.glossary dd{margin:2px 0 0;color:#cbd5e1}
#lb{position:fixed;inset:0;background:rgba(0,0,0,.94);display:none;flex-direction:column;z-index:100}
.lbbar{display:flex;align-items:center;gap:10px;padding:8px 14px;background:#0b0f14;border-bottom:1px solid var(--chip);flex-wrap:wrap}
.lbbar button{background:var(--chip);color:var(--fg);border:0;border-radius:7px;padding:6px 11px;font-size:14px;cursor:pointer}
.lbbar button:hover{background:#3d444d}.lbbar .cnt{color:var(--mut);font-size:13px;min-width:56px;text-align:center}
.lbbar .ttl{color:var(--gold);font-weight:600;font-size:13px;margin-right:auto;max-width:40vw;overflow:hidden;text-overflow:ellipsis;white-space:nowrap}
.lbbar .on{background:#1f6feb}
#lbstage{flex:1;overflow:hidden;position:relative;display:flex;align-items:center;justify-content:center;cursor:grab}
#lbstage.tag{cursor:crosshair}#lbstage.pan{cursor:grabbing}
#lbtx{position:relative;transform-origin:0 0;will-change:transform}
#lbtx img{display:block;max-width:96vw;max-height:calc(100vh - 180px);user-select:none;-webkit-user-drag:none}
#lbpins{position:absolute;inset:0;pointer-events:none}
.pin{position:absolute;width:16px;height:16px;margin:-8px 0 0 -8px;border-radius:50%;background:#f85149;border:2px solid #fff;box-shadow:0 0 0 1px #000;pointer-events:auto;cursor:pointer;font-size:9px;color:#fff;text-align:center;line-height:14px;font-weight:700}
.lbside{background:#0b0f14;border-top:1px solid var(--chip);padding:10px 14px;display:flex;gap:14px;align-items:flex-start}
.lbside textarea{flex:1;min-height:52px;background:#161b22;color:var(--fg);border:1px solid var(--chip);border-radius:8px;padding:8px 10px;font:13px/1.5 inherit;resize:vertical}
.lbside .pins{width:280px;max-height:120px;overflow:auto;font-size:12px}
.lbside .pins div{padding:3px 0;color:#cbd5e1;border-bottom:1px solid #1c2128}
.lbside .pins b{color:#f85149;margin-right:6px}
.lbside .pins .del{color:#f85149;cursor:pointer;float:right;font-weight:700;padding:0 5px}
.lbside .pins .del:hover{color:#ff7b72}
.lbside .clr{color:#8b949e;cursor:pointer;font-size:11px;display:inline-block;margin-top:6px}
.lbside .clr:hover{color:#f85149}
#home{position:fixed;right:18px;bottom:18px;background:var(--blue);color:#001;border:0;border-radius:24px;padding:10px 16px;font-weight:700;cursor:pointer;z-index:50;box-shadow:0 2px 8px rgba(0,0,0,.4)}
.tools{display:flex;gap:8px;margin:0 0 16px;flex-wrap:wrap}.tools button{background:var(--chip);color:var(--fg);border:0;border-radius:7px;padding:7px 12px;cursor:pointer;font-size:13px}
.tabs{display:flex;gap:4px;padding:0 24px;background:var(--bg);border-bottom:1px solid var(--chip);position:sticky;top:49px;z-index:9}
.tabs .tab{background:none;border:0;border-bottom:2px solid transparent;color:var(--mut);padding:11px 16px;font-size:14px;font-weight:600;cursor:pointer}
.tabs .tab:hover{color:var(--fg)}.tabs .tab.on{color:var(--blue);border-bottom-color:var(--blue)}
.tabpane[hidden]{display:none}
.about b{color:var(--fg)}.about code{background:#0b0f14;border:1px solid var(--chip);padding:1px 6px;border-radius:5px}
table.dt{width:100%;border-collapse:collapse;margin:6px 0 12px;font-size:13px}
table.dt th{text-align:left;color:var(--mut);font-weight:600;border-bottom:1px solid var(--chip);padding:4px 8px}
table.dt td{border-bottom:1px solid #1c2128;padding:4px 8px;vertical-align:top}
.oc-hit{color:#3fb950;font-weight:700}.oc-miss{color:#f85149;font-weight:700}
.oc-partial{color:#e3b341;font-weight:700}.oc-pending{color:#8b949e}
.score{display:flex;gap:16px;flex-wrap:wrap;background:var(--card);border:1px solid var(--chip);border-radius:11px;padding:12px 18px;margin:0 0 16px}
.score .s{font-size:13px}.score .s b{font-size:19px;color:var(--fg);display:block}
.dd{display:grid;grid-template-columns:1fr 1fr;gap:4px 18px;margin:6px 0}
.dd .lv{font-size:13px;color:#cbd5e1}.dd .lv b{color:var(--gold)}
.mut{color:var(--mut)}
.anchors{font-size:13px;color:#cbd5e1;margin:4px 0 6px}.anchors b{color:var(--fg)}
.fibtab{border-collapse:collapse;margin:4px 0 6px;font-size:13.5px}
.fibtab th{text-align:left;color:var(--mut);font-weight:600;padding:2px 14px 4px 0;font-size:11px;text-transform:uppercase}
.fibtab td{padding:3px 14px 3px 0;border-bottom:1px solid #1c2128}
.fibtab .fpct{font-weight:700}.fibtab .fp{font-variant-numeric:tabular-nums;font-weight:700}
.fl-red .fpct,.fl-red .fp{color:#f85149}.fl-yellow .fpct,.fl-yellow .fp{color:#e3b341}
.fl-green .fpct,.fl-green .fp{color:#3fb950}.fl-na .fp{color:#cbd5e1}
.pb{background:#0b0f14;border:1px solid var(--chip);border-left:3px solid var(--blue);border-radius:8px;padding:9px 12px;margin:7px 0}
.pb .pbrow{display:flex;flex-wrap:wrap;gap:10px;align-items:center;font-size:13px}
.pbif{color:#cbd5e1}.pbif b{color:var(--gold)}
.pbthen{font-weight:700}.dir-long{color:#3fb950}.dir-short{color:#f85149}.dir-TBD{color:#8b949e}
.pbtgt{color:#22d3ee}.pbinv{color:#f0883e}.pboc{margin-left:auto}
.pbth{color:var(--mut);font-size:12.5px;margin-top:4px}
.frwrap{display:grid;grid-template-columns:repeat(auto-fill,minmax(460px,1fr));gap:12px;margin:8px 0}
.fr{margin:0}.fr img{width:100%;border:1px solid var(--chip);border-radius:8px;cursor:zoom-in;display:block}
.fr figcaption{font-size:12.5px;color:var(--gold);margin:4px 0 0;font-weight:600}
"""

LB_JS = r"""
(function(){
 const KEY='ea_gs_annot';
 const store=JSON.parse(localStorage.getItem(KEY)||'{}');
 const save=()=>localStorage.setItem(KEY,JSON.stringify(store));
 const $=id=>document.getElementById(id);
 const lb=$('lb'),stage=$('lbstage'),tx=$('lbtx'),img=$('lbimg'),pinsEl=$('lbpins'),
   cnt=$('lbcnt'),ttl=$('lbttl'),ta=$('lbcomment'),pinList=$('lbpinlist'),tagBtn=$('lbtag');
 let set=[],idx=0,scale=1,px=0,py=0,tagMode=false,sid='';
 const apply=()=>tx.style.transform=`translate(${px}px,${py}px) scale(${scale})`;
 function renderPins(){
   const pins=(store[sid]&&store[sid].pins)||[];
   pinsEl.innerHTML='';
   pins.forEach((p,k)=>{const d=document.createElement('div');d.className='pin';
     d.style.left=p.x+'%';d.style.top=p.y+'%';d.textContent=k+1;d.title=p.note||'';
     d.onclick=ev=>{ev.stopPropagation();const nn=prompt('Tag note (blank=delete):',p.note||'');
       if(nn===null)return; if(nn==='')pins.splice(k,1); else p.note=nn;
       store[sid].pins=pins;save();renderPins();mark();};
     pinsEl.appendChild(d);});
   pinList.innerHTML=(pins.map((p,k)=>`<div><b>${k+1}</b>${p.note||'(no note)'}`
     +`<span class="del" data-k="${k}" title="delete tag">✕</span></div>`).join('')
     ||'<div style="color:#6e7681">no tags — turn on 🏷 then click the slide</div>')
     +(pins.length?'<span class="clr" id="clrtags">clear all tags on this slide</span>':'');
 }
 function delPin(k){const pins=(store[sid]&&store[sid].pins)||[];pins.splice(k,1);
   store[sid].pins=pins;save();renderPins();mark();}
 pinList.onclick=e=>{if(e.target.classList.contains('del'))delPin(+e.target.dataset.k);
   else if(e.target.id==='clrtags'){if(confirm('Delete all tags on this slide?')){
     store[sid].pins=[];save();renderPins();mark();}}};
 function load(i){idx=(i+set.length)%set.length;const el=set[idx];sid=el.dataset.sid;
   img.src=el.src;ttl.textContent=el.dataset.ttl||'';cnt.textContent=(idx+1)+' / '+set.length;
   scale=1;px=0;py=0;apply();ta.value=(store[sid]&&store[sid].comment)||'';renderPins();}
 const open=(list,i)=>{set=list;lb.style.display='flex';load(i);};
 const close=()=>lb.style.display='none';
 document.querySelectorAll('.slides img, .frwrap img').forEach(i=>i.onclick=()=>{
   const box=i.closest('.slides, .frwrap');
   const list=[...box.querySelectorAll('img')];open(list,list.indexOf(i));});
 $('lbprev').onclick=()=>load(idx-1);$('lbnext').onclick=()=>load(idx+1);
 $('lbin').onclick=()=>{scale=Math.min(8,scale*1.3);apply();};
 $('lbout').onclick=()=>{scale=Math.max(1,scale/1.3);apply();};
 $('lbreset').onclick=()=>{scale=1;px=0;py=0;apply();};
 tagBtn.onclick=()=>{tagMode=!tagMode;tagBtn.classList.toggle('on',tagMode);stage.classList.toggle('tag',tagMode);};
 $('lbclose').onclick=close;
 $('lbhome').onclick=()=>{const sec=set[idx]&&set[idx].closest('.mod');close();
   if(sec){sec.classList.add('open');sec.scrollIntoView({behavior:'smooth',block:'start'});}};
 ta.oninput=()=>{(store[sid]=store[sid]||{}).comment=ta.value;save();mark();};
 stage.onwheel=e=>{e.preventDefault();const r=tx.getBoundingClientRect();
   const ox=(e.clientX-r.left)/scale,oy=(e.clientY-r.top)/scale;
   const ns=Math.min(8,Math.max(1,scale*(e.deltaY<0?1.15:1/1.15)));
   px-=ox*(ns-scale);py-=oy*(ns-scale);scale=ns;apply();};
 let drag=false,sx,sy;
 stage.onmousedown=e=>{if(tagMode||e.target.classList.contains('pin'))return;
   drag=true;sx=e.clientX-px;sy=e.clientY-py;stage.classList.add('pan');};
 window.addEventListener('mousemove',e=>{if(drag){px=e.clientX-sx;py=e.clientY-sy;apply();}});
 window.addEventListener('mouseup',()=>{drag=false;stage.classList.remove('pan');});
 img.onclick=e=>{if(!tagMode)return;e.stopPropagation();const r=img.getBoundingClientRect();
   const x=(e.clientX-r.left)/r.width*100,y=(e.clientY-r.top)/r.height*100;
   const note=prompt('Tag note:','')||'';
   (store[sid]=store[sid]||{});store[sid].pins=store[sid].pins||[];
   store[sid].pins.push({x,y,note});save();renderPins();mark();};
 document.addEventListener('keydown',e=>{if(lb.style.display==='none')return;
   if(e.key==='Escape')close();else if(e.key==='ArrowLeft')load(idx-1);
   else if(e.key==='ArrowRight')load(idx+1);
   else if(e.key==='+'||e.key==='='){scale=Math.min(8,scale*1.2);apply();}
   else if(e.key==='-'){scale=Math.max(1,scale/1.2);apply();}});
 function mark(){document.querySelectorAll('.slides img').forEach(im=>{const s=store[im.dataset.sid];
   im.style.outline=(s&&((s.comment&&s.comment.trim())||(s.pins&&s.pins.length)))?'2px solid #3fb950':'';});}
 mark();
 $('exp').onclick=()=>{const b=new Blob([JSON.stringify(store,null,1)],{type:'application/json'});
   const a=document.createElement('a');a.href=URL.createObjectURL(b);
   a.download='ea_getting_started_notes.json';a.click();};
 $('imp').onchange=e=>{const f=e.target.files[0];if(!f)return;const r=new FileReader();
   r.onload=()=>{try{Object.assign(store,JSON.parse(r.result));save();mark();alert('Imported.');}
   catch(x){alert('Bad file');}};r.readAsText(f);};
 // ---- accordion (collapsible sections) ----
 const openMod=m=>{if(m)m.classList.add('open');};
 document.querySelectorAll('.modhead').forEach(h=>h.onclick=()=>h.closest('.mod').classList.toggle('open'));
 document.querySelectorAll('.toc a').forEach(a=>a.addEventListener('click',()=>
   openMod(document.getElementById(a.getAttribute('href').slice(1)))));
 if(location.hash)openMod(document.querySelector(location.hash));
 $('expandall').onclick=()=>document.querySelectorAll('.mod').forEach(m=>m.classList.add('open'));
 $('collapseall').onclick=()=>document.querySelectorAll('.mod').forEach(m=>m.classList.remove('open'));
 // ---- top-level tabs ----
 document.querySelectorAll('.tabs .tab').forEach(t=>t.onclick=()=>{
   document.querySelectorAll('.tabs .tab').forEach(x=>x.classList.toggle('on',x===t));
   document.querySelectorAll('.tabpane').forEach(p=>{p.hidden=(p.id!=='tab-'+t.dataset.t);});
   window.scrollTo({top:0});});
})();
"""


def b64img(path, maxw=1400, jpeg=False, quality=82):
    """Downscale + embed as a data URI (keeps the self-contained page small)."""
    try:
        from PIL import Image
        im = Image.open(path)
        if im.width > maxw:
            im = im.resize((maxw, round(im.height * maxw / im.width)), Image.LANCZOS)
        buf = io.BytesIO()
        if jpeg:
            im.convert("RGB").save(buf, "JPEG", quality=quality, optimize=True)
            mime = "jpeg"
        else:
            im.save(buf, "PNG", optimize=True)
            mime = "png"
        return f"data:image/{mime};base64," + base64.b64encode(buf.getvalue()).decode()
    except Exception:
        try:
            ext = os.path.splitext(path)[1].lstrip(".").lower().replace("jpg", "jpeg")
            return f"data:image/{ext};base64," + base64.b64encode(open(path, "rb").read()).decode()
        except Exception:
            return ""

def esc(s):
    return html.escape(s or "")

def render_glossary(text):
    # glossary text is "Term – definition. Term2 – ..." ; split on " – " heuristically
    out = ['<dl class="glossary">']
    # split into sentences that look like "X – def"
    parts = re.split(r'(?<=[.)])\s+(?=[A-Z][A-Za-z0-9 /()\-]{2,40}\s+[–\-]\s)', text)
    for p in parts:
        m = re.match(r'\s*([A-Z][A-Za-z0-9 /()\-]{1,40}?)\s+[–\-]\s+(.+)', p)
        if m:
            out.append(f"<dt>{esc(m.group(1).strip())}</dt><dd>{esc(m.group(2).strip())}</dd>")
    out.append("</dl>")
    return "\n".join(out) if len(out) > 2 else f"<p>{esc(text)}</p>"

def main():
    man = json.load(open(os.path.join(GS, "manifest.json"), encoding="utf-8"))
    slugmap = {re.sub(r'[^a-z0-9]+', '-', r['label'].lower()).strip('-')[:40]: r for r in man}
    toc, mods = [], []
    for r in man:
        idx = r["idx"]; label = esc(r["label"]); anchor = f"m{idx}"
        toc.append(f'<a href="#{anchor}">{idx:02d}. {label}</a>')
        item_dir = os.path.join(GS, r["dir"]) if r.get("dir") else None
        item = {}
        if item_dir and os.path.exists(os.path.join(item_dir, "item.json")):
            item = json.load(open(os.path.join(item_dir, "item.json"), encoding="utf-8"))
        text = item.get("text", "")
        parts = []
        # NUGGETS card FIRST (read the summary before the video/slides)
        nf = os.path.join(NUG, f"{idx:02d}.md")
        if os.path.exists(nf):
            parts.append(f'<div class="nug"><div class="hd">📌 Key points</div>'
                         f'{md_to_html(open(nf, encoding="utf-8").read())}</div>')
        # glossary special-render
        if "glossary" in r["label"].lower() and len(text) > 200:
            parts.append(render_glossary(text))
        elif text and len(text.split()) > 12:
            parts.append(f"<p>{esc(text)}</p>")
        # slides
        if item_dir:
            imgs = sorted(f for f in os.listdir(item_dir) if f.startswith("slide_")
                          and os.path.getsize(os.path.join(item_dir, f)) > 1000)
            if imgs:
                parts.append('<div class="slides">')
                for im in imgs:
                    d = b64img(os.path.join(item_dir, im))
                    if d:
                        sid = f"{idx:02d}_{im}"
                        parts.append(f'<img src="{d}" loading="lazy" data-sid="{sid}" '
                                     f'data-ttl="{label} — {im}">')
                parts.append("</div>")
        # video link
        for v in r.get("videos", []):
            if v.endswith(".mp4"):
                parts.append(f'<div class="vid">🎬 <a href="{esc(v)}" target="_blank">'
                             f'Lesson video (public)</a></div>')
        # transcript (collapsible) if present
        tname = f"{idx:02d}_" + re.sub(r'[^a-z0-9]+', '-', r['label'].lower()).strip('-')[:40]
        tf = os.path.join(TR, tname + ".txt")
        if os.path.exists(tf):
            tx = open(tf, encoding="utf-8").read()
            parts.append(f'<details><summary>Transcript ({len(tx.splitlines())} lines)</summary>'
                         f'<pre>{esc(tx)}</pre></details>')
        elif r.get("videos"):
            parts.append('<p class="pending">Transcript + nuggets pending transcription…</p>')
        head = (f'<div class="k">Lesson {idx:02d}</div>'
                f'<div class="modhead"><span class="arw">▶</span>{label}</div>')
        mods.append(f'<div class="mod" id="{anchor}">{head}'
                    f'<div class="modbody">{"".join(parts)}</div></div>')

    lb_html = (
        '<div id="lb"><div class="lbbar">'
        '<span class="ttl" id="lbttl"></span>'
        '<button id="lbprev" title="prev (←)">◀</button>'
        '<span class="cnt" id="lbcnt"></span>'
        '<button id="lbnext" title="next (→)">▶</button>'
        '<button id="lbout" title="zoom out (−)">−</button>'
        '<button id="lbin" title="zoom in (+)">＋</button>'
        '<button id="lbreset">reset</button>'
        '<button id="lbtag" title="click image to drop a tag">🏷 tag</button>'
        '<button id="lbhome" title="back to this section">← back</button>'
        '<button id="lbclose">✕</button></div>'
        '<div id="lbstage"><div id="lbtx"><img id="lbimg"><div id="lbpins"></div></div></div>'
        '<div class="lbside"><textarea id="lbcomment" placeholder="Your comment on this slide…">'
        '</textarea><div class="pins" id="lbpinlist"></div></div></div>')
    tools = ('<div class="tools"><button id="expandall">▽ Expand all</button>'
             '<button id="collapseall">△ Collapse all</button>'
             '<button id="exp">⬇ Export notes</button>'
             '<button onclick="document.getElementById(\'imp\').click()">⬆ Import notes</button>'
             '<input id="imp" type="file" accept="application/json" style="display:none"></div>')
    daily_pane = daily_html()
    about_pane = (
        '<div class="wrap about"><p class="lead">One page for the whole EminiAddict method — '
        'Getting Started curriculum + Daily analysis, all self-contained.</p>'
        '<h4>Use across your computers</h4><ul>'
        '<li>This is a <b>single self-contained file</b> (slides embedded). Drop '
        '<code>eminiaddict_tool.html</code> in your Google Drive transfer folder and open it '
        'on any machine — no server, no login.</li>'
        '<li>Your <b>comments &amp; tags</b> are saved in each browser (localStorage). To move them '
        'between computers use <b>⬇ Export notes</b> on one and <b>⬆ Import notes</b> on the other '
        '(keep the JSON in Drive too).</li>'
        '<li>Source content is copyrighted (paid subscription) — keep this personal, don\'t publish it.</li>'
        '</ul><h4>Sections</h4><ul>'
        '<li><b>Getting Started</b> — his curriculum in order: summaries, slides, transcripts, glossary.</li>'
        '<li><b>Daily Analysis</b> — auto-pulled daily video reports + scenario tracker.</li>'
        '</ul></div>')
    nav = ('<nav class="tabs">'
           '<button class="tab on" data-t="gs">Getting Started</button>'
           '<button class="tab" data-t="daily">Daily Analysis</button>'
           '<button class="tab" data-t="about">About / Sync</button></nav>')
    gs_pane = (f'<section id="tab-gs" class="tabpane"><div class="wrap">'
               f'<p class="lead">David Halsey\'s Getting Started curriculum, in his order. '
               f'Expand a section; click a slide to zoom/pan, cycle ◀▶, comment, and 🏷 tag a spot.</p>'
               f'{tools}<div class="toc">{"".join(toc)}</div>{"".join(mods)}</div></section>')
    page = (f'<!doctype html><html lang="en"><head><meta charset="utf-8">'
            f'<meta name="viewport" content="width=device-width,initial-scale=1">'
            f'<title>EminiAddict Tool</title><style>{CSS}</style></head><body>'
            f'<header><h1>EminiAddict</h1></header>{nav}'
            f'{gs_pane}'
            f'<section id="tab-daily" class="tabpane" hidden>{daily_pane}</section>'
            f'<section id="tab-about" class="tabpane" hidden>{about_pane}</section>'
            f'<button id="home" onclick="window.scrollTo({{top:0,behavior:\'smooth\'}})">⤒ TOP</button>'
            f'{lb_html}<script>{LB_JS}</script></body></html>')
    os.makedirs(os.path.dirname(OUT), exist_ok=True)
    open(OUT, "w", encoding="utf-8").write(page)
    print(f"wrote {os.path.relpath(OUT, ROOT)}  ({len(page)//1024} KB, {len(man)} lessons)")
    register_mc()

def es_block(es):
    """Stacked ES fib layout when a ladder is present; else the older prose fields."""
    if not es.get("ladder"):
        kl = "".join(f'<div class="lv"><b>{esc(x.get("label",""))}:</b> {esc(str(x.get("price","")))}'
                     f'</div>' for x in es.get("key_levels", []))
        return (f'<h4>ES</h4><p><b>Current MM:</b> {esc(es.get("current_mm","—"))}<br>'
                f'<b>Trend/road-map:</b> {esc(es.get("trend","—"))}<br>'
                f'<b>Watch:</b> {esc(es.get("watch","—"))}</p>'
                + (f'<div class="dd">{kl}</div>' if kl else ""))
    dblock = ""
    dd = es.get("daily")
    if dd:
        da = " &nbsp;·&nbsp; ".join(f'<b>{esc(p)}</b> {esc(v)} <span class="mut">{esc(n)}</span>'
                                    for p, v, n in dd.get("anchors", []))
        tg = dd.get("target", ["", "", ""])
        reds = "".join(f'<tr class="fl-red"><td class="fp">{esc(p)}</td><td class="mut">'
                       f'{esc(n)}</td></tr>' for p, n in dd.get("levels", []))
        dblock = (f'<h4>ES — {esc(dd.get("structure",""))} <span class="mut">'
                  f'({esc(dd.get("tf",""))})</span></h4>'
                  f'<div class="anchors">Anchors: {da}</div>'
                  f'<table class="fibtab"><tr class="fl-green"><td class="fpct">{esc(tg[0])}</td>'
                  f'<td class="fp">{esc(tg[1])}</td><td>{esc(tg[2])}</td></tr>'
                  f'<tr><td colspan=3 class="mut" style="padding-top:6px">downside levels</td></tr>'
                  f'{reds}</table>')
    anch = " &nbsp;·&nbsp; ".join(
        f'<b>{esc(p)}</b> {esc(v)} <span class="mut">{esc(n)}</span>' for p, v, n in es["anchors"])
    rows = ""
    for pct, price, role, color, note in es["ladder"]:
        c = color or "na"
        rows += (f'<tr class="fl-{c}"><td class="fpct">{esc(pct)}</td>'
                 f'<td class="fp">{esc(price)}</td><td>{esc(role)}</td>'
                 f'<td class="mut">{esc(note)}</td></tr>')
    return (dblock
            + f'<h4>ES — {esc(es.get("structure",""))} <span class="mut">({esc(es.get("tf",""))})'
            f'</span></h4>'
            f'<div class="anchors">Anchors: {anch}</div>'
            f'<table class="fibtab"><tr><th>%</th><th>price</th><th>role</th><th></th>{rows}</table>'
            f'<div class="mut" style="margin:4px 0">Price now: {esc(es.get("price_now","—"))} '
            f'&nbsp;·&nbsp; HTF: {esc(es.get("htf",""))}</div>'
            f'<p><b>Series:</b> {esc(es.get("series",""))}</p>'
            f'<p><b>Watch:</b> {esc(es.get("watch",""))}</p>')


_FRLBL = {"6E": "Euro", "6J": "USD/JPY", "CL": "Crude", "GC": "Gold", "SI": "Silver",
          "BANK": "Bank", "VIX": "VIX", "DXY": "Dollar (DXY)", "BTC": "Bitcoin",
          "ETH": "Ethereum", "NQ": "NQ", "YM": "YM", "RTY": "RTY", "ES": "ES"}


def _frlabel(t):
    if t == "ES":
        return "ES — Daily / 12h"
    if t.startswith("ES-tf"):
        return "ES — 4h"
    return _FRLBL.get(t, t)


def frames_gallery(mmddyy):
    """His actual chart frames pulled from the video (fibs/anchors/HTF), ES first."""
    fdir = os.path.join(DAILY, mmddyy, "frames")
    fj = os.path.join(fdir, "frames.json")
    if not os.path.exists(fj):
        return ""
    frames = json.load(open(fj, encoding="utf-8"))
    frames.sort(key=lambda f: (0 if f["topic"].startswith("ES") else 1, f["sec"]))
    figs = []
    for f in frames:
        p = os.path.join(fdir, f["file"])
        annot = os.path.join(fdir, os.path.splitext(f["file"])[0] + "_annot.png")
        if os.path.exists(annot) and os.path.getsize(annot) > 3000:
            p = annot                                   # prefer the callout-annotated version
        if not (os.path.exists(p) and os.path.getsize(p) > 3000):
            continue
        d = b64img(p, maxw=1680, jpeg=True, quality=80)
        lab = _frlabel(f["topic"]) + (" — fibs labeled" if p == annot else "")
        figs.append(f'<figure class="fr"><img src="{d}" loading="lazy" '
                    f'data-sid="fr_{mmddyy}_{f["topic"]}" data-ttl="{esc(lab)} — {mmddyy} '
                    f'@ {f["sec"]//60:02d}:{f["sec"]%60:02d}"><figcaption>{esc(lab)}</figcaption>'
                    f'</figure>')
    if not figs:
        return ""
    return (f'<h4>His charts — click to zoom (anchors, fibs, opposing &amp; HTF levels)</h4>'
            f'<div class="frwrap">{"".join(figs)}</div>')


def daily_html():
    """Render the Daily Analysis pane from data/daily/*/report.json (newest first)."""
    reports = []
    if os.path.isdir(DAILY):
        for d in sorted(os.listdir(DAILY), reverse=True):
            rp = os.path.join(DAILY, d, "report.json")
            if os.path.exists(rp):
                try:
                    reports.append(json.load(open(rp, encoding="utf-8")))
                except Exception:
                    pass
    if not reports:
        return ('<div class="wrap"><p class="lead">Daily analysis reports appear here. The latest '
                'David Halsey video is auto-downloaded, transcribed, and summarized into <b>market '
                'state, bias, current measured move, ES watch, per-instrument notes,</b> and tracked '
                '<b>scenarios (hit / miss)</b>.<br><i>Pipeline is built (ea_daily.py); the first '
                'report is coming next.</i></p></div>')
    # ---- scorecard across all scenarios ----
    allsc = [s for r in reports for s in r.get("scenarios", [])]
    resolved = [s for s in allsc if s.get("outcome") in ("hit", "miss", "partial")]
    hits = sum(1 for s in resolved if s.get("outcome") == "hit")
    pend = sum(1 for s in allsc if s.get("outcome", "pending") == "pending")
    rate = f"{100*hits/len(resolved):.0f}%" if resolved else "—"
    score = (f'<div class="score"><div class="s"><b>{len(reports)}</b>days</div>'
             f'<div class="s"><b>{len(allsc)}</b>scenarios</div>'
             f'<div class="s"><b class="oc-hit">{hits}</b>hit</div>'
             f'<div class="s"><b class="oc-miss">{len(resolved)-hits}</b>miss</div>'
             f'<div class="s"><b class="oc-pending">{pend}</b>pending</div>'
             f'<div class="s"><b>{rate}</b>hit-rate (resolved)</div></div>')

    def oc(s):
        o = s.get("outcome", "pending")
        auto = " ⚙" if s.get("auto") else ""
        return f'<span class="oc-{o}">{esc(o)}{auto}</span>'

    cards = []
    for r in reports:
        es = r.get("es", {})
        lv = "".join(f'<div class="lv"><b>{esc(x.get("label",""))}:</b> {esc(str(x.get("price","")))}</div>'
                     for x in es.get("key_levels", []))
        inst = "".join(
            f'<tr><td><b>{esc(k)}</b></td><td>{esc(v.get("bias",""))}</td>'
            f'<td>{esc(v.get("mm_state",""))}</td><td>{esc(v.get("levels",""))}</td>'
            f'<td>{esc(v.get("notes",""))}</td></tr>'
            for k, v in r.get("instruments", {}).items() if any(v.values()))
        chart_html = frames_gallery(r.get("mmddyy", ""))
        pb = "".join(
            f'<div class="pb"><div class="pbrow">'
            f'<span class="pbif"><b>IF</b> {esc(str(s.get("trigger","")))}</span>'
            f'<span class="pbthen dir-{esc(s.get("direction",""))}">&rarr; '
            f'{esc((s.get("direction","") or "").upper())} {esc(s.get("instrument",""))}</span>'
            f'<span class="pbtgt">&#127919; {esc(str(s.get("target","")))}</span>'
            f'<span class="pbinv">&#128721; {esc(str(s.get("invalidation","")))}</span>'
            f'<span class="pboc">{oc(s)}</span></div>'
            f'<div class="pbth">{esc(s.get("thesis",""))}</div></div>'
            for s in r.get("scenarios", []))
        quotes = "".join(f'<div class="lv">[{esc(q.get("t",""))}] "{esc(q.get("text",""))}"</div>'
                         for q in r.get("key_quotes", []))
        head_lbl = f'{esc(r.get("weekday",""))} {esc(r.get("date",""))} — {esc(r.get("headline","report"))}'
        cards.append(
            f'<div class="mod open"><div class="k">Daily analysis</div>'
            f'<div class="modhead"><span class="arw">▶</span>{head_lbl}</div><div class="modbody">'
            f'<div class="nug"><div class="hd">📌 Snapshot</div>'
            f'<p class="tldr"><b>Bias:</b> {esc(r.get("bias","—"))}</p>'
            f'<p><b>Market state:</b> {esc(r.get("market_state","—"))}</p></div>'
            + es_block(es)
            + chart_html
            + (f'<h4>Trade playbook (if &rarr; then)</h4>{pb}' if pb else "")
            + (f'<h4>Instruments</h4><table class="dt"><tr><th>Instr</th><th>Bias</th>'
               f'<th>MM state</th><th>Levels</th><th>Notes</th>{inst}</table>' if inst else "")
            + (f'<h4>Key quotes</h4>{quotes}' if quotes else "")
            + (f'<div class="vid">🎬 <a href="{esc(r.get("video_url",""))}" target="_blank">'
               f'watch the video</a></div>' if r.get("video_url") else "")
            + '</div></div>')
    return (f'<div class="wrap"><p class="lead">Newest first. ⚙ = auto-scored against price. '
            f'Scenario outcomes build a hit/miss record over time.</p>{score}'
            + "".join(cards) + '</div>')


def md_to_html(md):
    out, inul = [], False
    for ln in md.split("\n"):
        s = esc(ln.strip())
        if s.startswith("## "):
            if inul:
                out.append("</ul>"); inul = False
            out.append(f"<h4>{s[3:]}</h4>")
        elif s.startswith("- "):
            if not inul:
                out.append("<ul>"); inul = True
            out.append(f"<li>{s[2:]}</li>")
        elif s == "":
            if inul:
                out.append("</ul>"); inul = False
        else:
            if inul:
                out.append("</ul>"); inul = False
            cls = ' class="tldr"' if s.lower().startswith(("**in short", "in short",
                                                          "**tl;dr", "tl;dr")) else ""
            out.append(f"<p{cls}>{s}</p>")
    if inul:
        out.append("</ul>")
    h = "\n".join(out)
    h = re.sub(r"\*\*(.+?)\*\*", r"<b>\1</b>", h)
    return h

def register_mc():
    """Add/refresh the MC catalog entry so the page groups under EminiAddict at :8590."""
    try:
        cat = json.load(open(CATALOG, encoding="utf-8"))
    except Exception:
        cat = []
    items = cat if isinstance(cat, list) else cat.get("items", cat.get("artifacts", []))
    entry = {"title": "EminiAddict Tool", "group": "EminiAddict", "url": "",
             "info": "One-page EminiAddict tool: Getting Started curriculum + Daily analysis "
                     "reports + scenario tracker. Self-contained (syncable across machines)."}
    items = [i for i in items if i.get("title") != entry["title"]]
    items.append(entry)
    if isinstance(cat, list):
        cat = items
    else:
        key = "artifacts" if "artifacts" in cat else "items"
        cat[key] = items
    os.makedirs(os.path.dirname(CATALOG), exist_ok=True)
    json.dump(cat, open(CATALOG, "w", encoding="utf-8"), indent=1)
    print("registered MC catalog entry (group EminiAddict)")

if __name__ == "__main__":
    main()
