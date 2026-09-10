"""day_dna_gallery.py — Day-DNA gallery (S116-tempo, MD sections 17-19).

Renders ALL trading days as time-of-day tempo heat strips in one standalone
interactive HTML (no external libs, dark surface):

  - each row = one day, 27 x 15-min cells, color = mean tod-calibrated tempo
    percentile of that bucket's 2000t bars (single-hue orange ramp; gold cell
    = bucket mean >= 95 climactic)
  - k-means (k=6, numpy, seed 42) on the z-scored 27-dim profile -> cluster chips
  - sort by date / cluster / day range / net / opening tempo; filter year+cluster
  - hover tooltip per cell; click a day -> detail panel: enlarged strip, stats,
    5 nearest historical neighbours (euclidean on the profile), clickable

Output: tempo/outputs/day_dna_gallery.html
    python tempo/scripts/day_dna_gallery.py
"""
from __future__ import annotations
import json
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
BARS = ROOT / "tempo" / "outputs" / "bars_2000t_all.parquet"
TOD = ROOT / "tempo" / "outputs" / "tod_percentiles.csv"
OUT = ROOT / "tempo" / "outputs" / "day_dna_gallery.html"
SIZE = 2000
NB = 27
K = 6


def bar_pctiles(df: pd.DataFrame) -> pd.DataFrame:
    tod = pd.read_csv(TOD)
    grids = {}
    for _, r in tod[tod["metric"] == "tempo"].iterrows():
        grids[int(r["bucket"])] = r[[f"p{p:02d}" for p in range(1, 100)]].to_numpy(float)
    df = df[df["ticks"] == SIZE].copy()
    df["bucket"] = (df["session_min"] // 15).astype(int).clip(0, NB - 1)
    pct = np.empty(len(df))
    for b, g in df.groupby("bucket"):
        grid = grids.get(int(b), grids[-1])
        pct[df.index.get_indexer(g.index)] = np.searchsorted(grid, g["tempo"].to_numpy()) + 1
    df["tpct"] = np.clip(pct, 1, 99)
    return df


def kmeans(X: np.ndarray, k: int, seed: int = 42, iters: int = 100) -> np.ndarray:
    rng = np.random.default_rng(seed)
    C = X[rng.choice(len(X), k, replace=False)]
    lab = np.zeros(len(X), int)
    for _ in range(iters):
        d = ((X[:, None, :] - C[None, :, :]) ** 2).sum(2)
        new = d.argmin(1)
        if (new == lab).all():
            break
        lab = new
        for j in range(k):
            if (lab == j).any():
                C[j] = X[lab == j].mean(0)
    return lab


def main():
    df = bar_pctiles(pd.read_parquet(BARS))
    prof = df.pivot_table(index="date", columns="bucket", values="tpct", aggfunc="mean")
    prof = prof.reindex(columns=range(NB))
    day = df.groupby("date").agg(hi=("high", "max"), lo=("low", "min"),
                                 op=("open", "first"), cl=("close", "last"),
                                 eff=("eff", "mean"), n=("bar", "size"),
                                 climax=("tpct", lambda s: float((s >= 95).mean())))
    day["rng"] = day["hi"] - day["lo"]
    day["net"] = day["cl"] - day["op"]
    day = day.loc[prof.index]

    X = prof.to_numpy()
    Xf = np.where(np.isnan(X), np.nanmean(X, 0), X)
    Z = (Xf - Xf.mean(0)) / Xf.std(0)
    lab = kmeans(Z, K)
    # stable cluster ids: order by mean opening tempo (buckets 0-1)
    order = np.argsort([-Xf[lab == j][:, :2].mean() for j in range(K)])
    remap = {int(old): int(new) for new, old in enumerate(order)}
    lab = np.array([remap[int(v)] for v in lab])

    data = {
        "dates": list(prof.index),
        "m": [[None if np.isnan(v) else int(round(v)) for v in row] for row in X],
        "rng": [round(float(v), 2) for v in day["rng"]],
        "net": [round(float(v), 2) for v in day["net"]],
        "eff": [round(float(v), 3) for v in day["eff"]],
        "nbars": [int(v) for v in day["n"]],
        "climax": [round(float(v), 3) for v in day["climax"]],
        "cluster": [int(v) for v in lab],
    }
    counts = pd.Series(lab).value_counts().sort_index()
    print("days:", len(prof), " cluster sizes:", counts.tolist())

    html = HTML.replace("__DATA__", json.dumps(data, separators=(",", ":")))
    OUT.write_text(html, encoding="utf-8")
    print(f"saved -> {OUT.relative_to(ROOT)}  ({OUT.stat().st_size/1e6:.1f} MB)")


HTML = """<!DOCTYPE html>
<html><head><meta charset="utf-8"><title>ES Day-DNA gallery — 2000t tempo</title>
<style>
:root{--bg:#16181d;--panel:#1d2026;--ink:#e8e8e6;--ink2:#a5a8ad;--mut:#6b6f76;--line:#2c3038}
*{box-sizing:border-box}body{margin:0;background:var(--bg);color:var(--ink);
font:13px/1.45 Consolas,Menlo,monospace}
#top{position:sticky;top:0;background:var(--bg);padding:10px 14px;border-bottom:1px solid var(--line);z-index:5}
#top h1{font-size:15px;margin:0 0 8px}
#top .ctl{display:flex;gap:10px;flex-wrap:wrap;align-items:center}
select,button{background:var(--panel);color:var(--ink);border:1px solid var(--line);
border-radius:4px;padding:3px 8px;font:inherit;cursor:pointer}
.chip{display:inline-flex;align-items:center;gap:5px;padding:2px 8px;border-radius:10px;
border:1px solid var(--line);cursor:pointer;color:var(--ink2)}
.chip.on{color:var(--ink);border-color:#555}
.dot{width:9px;height:9px;border-radius:2px;display:inline-block}
#wrap{display:flex;gap:0}
#left{flex:1;min-width:0;overflow-x:auto;padding:6px 0 40px 14px}
#right{width:390px;flex:none;padding:12px;border-left:1px solid var(--line);
position:sticky;top:96px;align-self:flex-start;max-height:calc(100vh - 96px);overflow-y:auto}
#cv{display:block;cursor:pointer}
#tip{position:fixed;pointer-events:none;background:#000c;border:1px solid var(--line);
padding:4px 8px;border-radius:4px;display:none;z-index:9;color:var(--ink)}
#detail table{border-collapse:collapse;margin:8px 0}
#detail td{padding:1px 10px 1px 0;color:var(--ink2)}#detail td+td{color:var(--ink)}
#nbrs div{padding:3px 6px;border:1px solid var(--line);border-radius:4px;margin:3px 0;cursor:pointer}
#nbrs div:hover{background:var(--panel)}
.legend{display:flex;gap:2px;align-items:center;color:var(--mut)}
.legend i{width:14px;height:10px;display:inline-block}
h3{font-size:13px;margin:14px 0 4px;color:var(--ink2)}
</style></head><body>
<div id="top"><h1>ES Day-DNA — 2000-tick tempo fingerprints, 2021&ndash;2026 (tod-calibrated percentiles)</h1>
<div class="ctl">
 <select id="year"><option value="">all years</option></select>
 <select id="sort">
  <option value="date_desc">newest first</option><option value="date_asc">oldest first</option>
  <option value="cluster">by cluster</option><option value="rng">by day range</option>
  <option value="net">by net move</option><option value="open">by opening tempo</option>
  <option value="climax">by climactic share</option></select>
 <span id="chips"></span>
 <span class="legend">low <i style="background:hsl(28,75%,12%)"></i><i style="background:hsl(28,75%,26%)"></i><i style="background:hsl(28,75%,40%)"></i><i style="background:hsl(28,75%,54%)"></i><i style="background:hsl(28,75%,66%)"></i> high &nbsp;|&nbsp; <i style="background:#ffd23f"></i> climactic&ge;95 &nbsp;|&nbsp; gray = no data</span>
 <span id="count" style="color:var(--mut)"></span>
</div></div>
<div id="wrap">
 <div id="left"><canvas id="cv"></canvas></div>
 <div id="right"><div id="detail" style="color:var(--mut)">click a day&hellip;</div></div>
</div>
<div id="tip"></div>
<script>
const D=__DATA__;
const NB=27,CW=15,CH=13,GUT=86,CLC=["#3987e5","#d95926","#199e70","#c98500","#d55181","#008300"];
const N=D.dates.length;
const times=[...Array(NB)].map((_,b)=>{const m=8*60+30+b*15;return String(Math.floor(m/60)).padStart(2,"0")+":"+String(m%60).padStart(2,"0")});
function heat(v){if(v==null)return "#22242a";if(v>=95)return "#ffd23f";
 return `hsl(28,75%,${(12+v*0.56).toFixed(1)}%)`}
let view=[],sel=-1;
const cv=document.getElementById("cv"),cx=cv.getContext("2d");
const yearSel=document.getElementById("year"),sortSel=document.getElementById("sort");
[...new Set(D.dates.map(d=>d.slice(0,4)))].forEach(y=>yearSel.add(new Option(y,y)));
const clOn=Array(6).fill(true);
const chips=document.getElementById("chips");
for(let j=0;j<6;j++){const c=document.createElement("span");c.className="chip on";
 c.innerHTML=`<span class=dot style="background:${CLC[j]}"></span>C${j+1}`;
 c.onclick=()=>{clOn[j]=!clOn[j];c.classList.toggle("on");refresh()};chips.appendChild(c)}
function openTempo(i){const a=D.m[i][0],b=D.m[i][1];return ((a??0)+(b??0))/2}
function refresh(){
 view=[...Array(N).keys()].filter(i=>(!yearSel.value||D.dates[i].startsWith(yearSel.value))&&clOn[D.cluster[i]]);
 const s=sortSel.value;
 const key={date_desc:i=>D.dates[i],date_asc:i=>D.dates[i],cluster:i=>D.cluster[i]*1e6-i,
  rng:i=>-D.rng[i],net:i=>-Math.abs(D.net[i]),open:i=>-openTempo(i),climax:i=>-D.climax[i]}[s];
 view.sort((a,b)=>key(a)<key(b)?-1:1);
 if(s==="date_desc")view.reverse();
 document.getElementById("count").textContent=view.length+" days";
 draw()}
function draw(){
 cv.width=GUT+NB*CW+70;cv.height=view.length*CH+22;
 cx.font="10px Consolas";cx.fillStyle="#6b6f76";
 for(let b=0;b<NB;b+=4)cx.fillText(times[b],GUT+b*CW,12);
 view.forEach((i,r)=>{const y=18+r*CH;
  if(r%25===0||i===sel){cx.fillStyle=i===sel?"#e8e8e6":"#6b6f76";cx.fillText(D.dates[i],2,y+10)}
  for(let b=0;b<NB;b++){cx.fillStyle=heat(D.m[i][b]);
   cx.fillRect(GUT+b*CW,y,CW-1,CH-2)}
  cx.fillStyle=CLC[D.cluster[i]];cx.fillRect(GUT+NB*CW+6,y,8,CH-2);
  if(i===sel){cx.strokeStyle="#e8e8e6";cx.strokeRect(GUT-1,y-1,NB*CW+16,CH)}})}
function hit(e){const rc=cv.getBoundingClientRect(),x=e.clientX-rc.left,y=e.clientY-rc.top;
 const r=Math.floor((y-18)/CH),b=Math.floor((x-GUT)/CW);
 if(r<0||r>=view.length)return null;return{i:view[r],b:(b>=0&&b<NB)?b:null}}
const tip=document.getElementById("tip");
cv.onmousemove=e=>{const h=hit(e);if(!h||h.b==null){tip.style.display="none";return}
 const v=D.m[h.i][h.b];
 tip.textContent=D.dates[h.i]+"  "+times[h.b]+"  "+(v==null?"no data":"tempo p"+v);
 tip.style.display="block";tip.style.left=(e.clientX+14)+"px";tip.style.top=(e.clientY+10)+"px"};
cv.onmouseleave=()=>tip.style.display="none";
cv.onclick=e=>{const h=hit(e);if(h){sel=h.i;detail();draw()}};
function dist(i,j){let s=0,n=0;for(let b=0;b<NB;b++){const a=D.m[i][b],c=D.m[j][b];
 if(a!=null&&c!=null){s+=(a-c)**2;n++}}return n>=20?Math.sqrt(s/n):1e9}
function detail(){const i=sel,el=document.getElementById("detail");
 const nb=[...Array(N).keys()].filter(j=>j!==i).map(j=>[dist(i,j),j])
  .sort((a,b)=>a[0]-b[0]).slice(0,5);
 el.innerHTML=`<h3>${D.dates[i]} &nbsp;<span class=dot style="background:${CLC[D.cluster[i]]}"></span> C${D.cluster[i]+1}</h3>
 <canvas id=dcv width=364 height=46></canvas>
 <table>
 <tr><td>day range</td><td>${D.rng[i]} pts</td></tr>
 <tr><td>net</td><td>${D.net[i]>0?"+":""}${D.net[i]} pts</td></tr>
 <tr><td>bars</td><td>${D.nbars[i]}</td></tr>
 <tr><td>mean efficiency</td><td>${D.eff[i]}</td></tr>
 <tr><td>climactic share</td><td>${(D.climax[i]*100).toFixed(1)}% of bars &ge;p95</td></tr>
 </table><h3>5 nearest tempo-profile days</h3><div id=nbrs></div>`;
 const d=document.getElementById("dcv").getContext("2d");
 for(let b=0;b<NB;b++){d.fillStyle=heat(D.m[i][b]);d.fillRect(b*13.4,4,12.4,30)}
 d.fillStyle="#6b6f76";d.font="9px Consolas";
 [0,8,16,24].forEach(b=>d.fillText(times[b],b*13.4,44));
 const nEl=document.getElementById("nbrs");
 nb.forEach(([dd,j])=>{const r=document.createElement("div");
  r.innerHTML=`${D.dates[j]} &nbsp;<span class=dot style="background:${CLC[D.cluster[j]]}"></span> C${D.cluster[j]+1} &nbsp; rng ${D.rng[j]} &nbsp; net ${D.net[j]>0?"+":""}${D.net[j]} &nbsp; <span style="color:var(--mut)">d=${dd.toFixed(1)}</span>`;
  r.onclick=()=>{sel=j;detail();draw();};nEl.appendChild(r)})}
yearSel.onchange=refresh;sortSel.onchange=refresh;refresh();
</script></body></html>
"""

if __name__ == "__main__":
    main()
