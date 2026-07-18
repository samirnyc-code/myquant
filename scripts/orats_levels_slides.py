"""Build the Gamma Levels Slide Deck — every session we have, 10 per slide.

Self-contained HTML (data embedded, no CDN) served by Mission Control at /levels.

Per session, everything below is EOD-KNOWABLE BEFORE the session trades:
  * our CR / PS / HVL      (ORATS chain of the PRIOR session, dte>1 NetGEX)
  * MenthorQ CR / PS / HVL (published, prior session)     [toggle]
  * MQ GEX 1-4             (next gamma walls after CR/PS)
  * MQ 1D Min / 1D Max     (expected-move band — MQ's published values; ours has
                            ~6pt median error so we plot theirs, which are exact)
  * prior session VAH / VAL / POC  (approx: 5-min bars, volume spread over H-L)
  * prior session High / Low / Close
  * the full NetGEX profile as a translucent per-session histogram

ES is shown in SPX-equivalent points (minus that day's basis) so every level stays
in native SPX units. No labels on the chart — colour only.

Run:  .venv/Scripts/python.exe scripts/orats_levels_slides.py
Out:  docs/levels_slides/levels.html
"""
import glob, json, os
import numpy as np, pandas as pd
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "docs" / "levels_slides"
PER_SLIDE = 10
PROF_BIN = 25.0          # $25 bins for the GEX profile histogram
PROF_SPAN = 0.05         # +/-5% of spot


def front_month_es():
    fr = []
    for f in sorted(glob.glob(str(ROOT / "data" / "bars" / "ES*.parquet"))):
        d = pd.read_parquet(f)
        d["contract"] = os.path.basename(f).split(".")[0]
        fr.append(d)
    ES = pd.concat(fr, ignore_index=True)
    ES["date"] = ES.DateTime.dt.strftime("%Y-%m-%d")
    vol = ES.groupby(["date", "contract"]).Volume.sum().reset_index()
    front = vol.sort_values("Volume").groupby("date").tail(1).set_index("date")["contract"].to_dict()
    return ES[[c == front.get(d) for d, c in zip(ES.date, ES.contract)]].sort_values("DateTime")


def volume_profile(g, binsz=1.0):
    """Approx VP from 5-min OHLCV: spread each bar's volume over its H-L range."""
    lo, hi = float(g.Low.min()), float(g.High.max())
    if not np.isfinite(lo) or hi <= lo:
        return None
    edges = np.arange(lo, hi + binsz, binsz)
    acc = np.zeros(len(edges))
    for L, H, V in zip(g.Low.values, g.High.values, g.Volume.values):
        i0, i1 = int((L - lo) / binsz), int((H - lo) / binsz)
        i1 = max(i1, i0)
        if i1 >= len(acc):
            i1 = len(acc) - 1
        acc[i0:i1 + 1] += V / (i1 - i0 + 1)
    if acc.sum() <= 0:
        return None
    poc = float(edges[int(acc.argmax())])
    order = np.argsort(acc)[::-1]
    keep, tot, target = [], 0.0, acc.sum() * 0.70
    for i in order:
        keep.append(i); tot += acc[i]
        if tot >= target:
            break
    return {"poc": poc, "vah": float(edges[max(keep)]), "val": float(edges[min(keep)])}


def our_levels():
    out = {}
    for f in sorted(glob.glob(str(ROOT / "data" / "orats" / "SPX" / "SPX_*.parquet"))):
        yr = pd.read_parquet(f)
        for c in ["strike", "gamma", "delta", "callOpenInterest", "putOpenInterest",
                  "dte", "spotPrice"]:
            yr[c] = pd.to_numeric(yr[c], errors="coerce")
        yr = yr[(yr.dte > 1) & (yr.gamma.abs() < 0.1) & (yr.delta.abs() <= 1.01)]
        for d, g in yr.groupby("tradeDate"):
            d = str(d)
            spot = g["spotPrice"].median()
            p = (g.gamma * (g.callOpenInterest - g.putOpenInterest)).groupby(g.strike).sum()
            p = p[np.isfinite(p)]
            if p.empty or not np.isfinite(spot):
                continue
            fb = p[(p.index >= spot * 0.90) & (p.index <= spot * 1.10)]
            near = p[(p.index >= spot * (1 - PROF_SPAN)) & (p.index <= spot * (1 + PROF_SPAN))]
            prof = []
            if not near.empty:
                b = (near.index / PROF_BIN).round() * PROF_BIN
                agg = near.groupby(b).sum()
                mx = agg.abs().max()
                if mx > 0:
                    prof = [[float(k), round(float(v / mx), 3)] for k, v in agg.items()
                            if abs(v / mx) > 0.02]
            out[d] = {"cr": float(p.idxmax()), "ps": float(p.idxmin()),
                      "hvl": float(fb.cumsum().idxmin()) if not fb.empty else None,
                      "prof": prof}
    return out


def main():
    ES = front_month_es()
    spx = pd.read_csv(ROOT / "data" / "spx_daily_full.csv")
    spx["Date"] = spx.Date.astype(str)
    S = spx.set_index("Date")
    esC = ES.groupby("date").Close.last()
    common = sorted(set(esC.index) & set(S.index))
    basis = (esC.loc[common] - S.Close.loc[common])

    MQ = pd.read_csv(ROOT / "data" / "menthorq" / "SPX_mq_levels_history.csv")
    MQ["session_date"] = MQ.session_date.astype(str)
    MQ = MQ.set_index("session_date")
    ours = our_levels()

    bars = {d: g for d, g in ES.groupby("date")}
    sess = sorted(set(basis.index) & set(bars))
    prev = {s: sess[i - 1] for i, s in enumerate(sess) if i > 0}

    days = []
    for s in sess:
        d = prev.get(s)
        if d is None or (d not in MQ.index and d not in ours):
            continue
        rec = {"s": s, "p": [round(float(v), 1) for v in (bars[s].Close.values - basis.loc[s])]}
        # ---- OUR levels (prior session chain) ----
        if d in ours:
            o = ours[d]
            for k in ("cr", "ps", "hvl"):
                if o.get(k) is not None:
                    rec["o_" + k] = o[k]
            if o.get("prof"):
                rec["prof"] = o["prof"]
        # ---- MenthorQ levels + 1D band + GEX 1-4 ----
        if d in MQ.index:
            m = MQ.loc[d]
            for k in ("cr", "ps", "hvl"):
                if pd.notna(m.get(k)):
                    rec["m_" + k] = float(m[k])
            for k, tag in (("d1_min", "d1lo"), ("d1_max", "d1hi")):
                if pd.notna(m.get(k)):
                    rec[tag] = float(m[k])
            gx = [float(m[f"gex_{i}"]) for i in range(1, 5) if pd.notna(m.get(f"gex_{i}"))]
            if gx:
                rec["gx"] = gx
        # ---- prior session VP + H/L/C, in SPX-equivalent ----
        if d in bars and d in basis.index:
            bp = basis.loc[d]
            vp = volume_profile(bars[d])
            if vp:
                rec["vah"] = round(vp["vah"] - bp, 1)
                rec["val"] = round(vp["val"] - bp, 1)
                rec["poc"] = round(vp["poc"] - bp, 1)
            g = bars[d]
            rec["ph"] = round(float(g.High.max()) - bp, 1)
            rec["pl"] = round(float(g.Low.min()) - bp, 1)
            rec["pc"] = round(float(g.Close.iloc[-1]) - bp, 1)
        days.append(rec)

    slides = [days[i:i + PER_SLIDE] for i in range(0, len(days), PER_SLIDE)]
    daily = [{"d": r.Date, "c": round(float(r.Close), 1)}
             for r in spx.itertuples() if days[0]["s"] <= r.Date <= days[-1]["s"]]
    payload = {"slides": slides, "daily": daily, "n_sessions": len(days),
               "range": [days[0]["s"], days[-1]["s"]]}

    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / "levels.html").write_text(HTML.replace("__DATA__",
                                     json.dumps(payload, separators=(",", ":"))), encoding="utf-8")
    kb = (OUT / "levels.html").stat().st_size / 1024
    print(f"wrote {OUT/'levels.html'}  ({kb:.0f} KB)")
    print(f"  {len(days)} sessions -> {len(slides)} slides  ({days[0]['s']} .. {days[-1]['s']})")
    for k, lbl in (("o_cr", "our CR"), ("m_cr", "MQ CR"), ("d1lo", "1D band"),
                   ("vah", "prior VAH/VAL/POC"), ("gx", "GEX1-4"), ("prof", "GEX profile")):
        print(f"    {lbl:20} on {sum(1 for x in days if k in x)}/{len(days)} sessions")


HTML = r"""<!doctype html><html lang="en"><head>
<meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>Gamma Levels Slides — SPX</title>
<style>
:root{--surface:#fcfcfb;--plane:#f9f9f7;--ink:#0b0b0b;--ink2:#52514e;--muted:#898781;
 --border:rgba(11,11,11,.12);--grid:#00000010;--px:#1a1a19;
 --cr:#e34948;--ps:#2a78d6;--hvl:#eda100;--vp:#1baf7a;--gx:#4a3aa7;--prior:#8b8a84}
@media(prefers-color-scheme:dark){:root{--surface:#1a1a19;--plane:#0d0d0d;--ink:#fff;--ink2:#c3c2b7;
 --muted:#898781;--border:rgba(255,255,255,.14);--grid:#ffffff14;--px:#f2f2ef;
 --cr:#e66767;--ps:#3987e5;--hvl:#c98500;--vp:#199e70;--gx:#9085e9;--prior:#7e7d78}}
:root[data-theme=dark]{--surface:#1a1a19;--plane:#0d0d0d;--ink:#fff;--ink2:#c3c2b7;--muted:#898781;
 --border:rgba(255,255,255,.14);--grid:#ffffff14;--px:#f2f2ef;
 --cr:#e66767;--ps:#3987e5;--hvl:#c98500;--vp:#199e70;--gx:#9085e9;--prior:#7e7d78}
:root[data-theme=light]{--surface:#fcfcfb;--plane:#f9f9f7;--ink:#0b0b0b;--ink2:#52514e;--muted:#898781;
 --border:rgba(11,11,11,.12);--grid:#00000010;--px:#1a1a19;
 --cr:#e34948;--ps:#2a78d6;--hvl:#eda100;--vp:#1baf7a;--gx:#4a3aa7;--prior:#8b8a84}
*{box-sizing:border-box}
body{margin:0;background:var(--plane);color:var(--ink);font:14px system-ui,-apple-system,"Segoe UI",sans-serif}
header{padding:10px 18px;border-bottom:1px solid var(--border);background:var(--surface);
 display:flex;gap:12px;align-items:center;flex-wrap:wrap;position:sticky;top:0;z-index:5}
h1{font-size:15px;margin:0;font-weight:650}
button{font:inherit;color:var(--ink);background:var(--surface);border:1px solid var(--border);
 border-radius:8px;padding:5px 11px;cursor:pointer}
button:hover{border-color:var(--muted)}button:disabled{opacity:.4;cursor:default}
.wrap{max-width:1640px;margin:0 auto;padding:12px 18px 50px}
.chip{display:inline-flex;gap:6px;align-items:center;font-size:12px;color:var(--ink2)}
.sw{width:20px;height:3px;border-radius:2px;display:inline-block}
input[type=text]{font:inherit;padding:5px 9px;border:1px solid var(--border);border-radius:8px;
 background:var(--surface);color:var(--ink);width:112px}
label{font-size:12px;color:var(--ink2);display:inline-flex;gap:4px;align-items:center;cursor:pointer}
canvas{width:100%;display:block;border:1px solid var(--border);border-radius:12px;background:var(--surface)}
#nav{margin-top:9px}
.muted{color:var(--muted);font-size:12px}
.count{font-variant-numeric:tabular-nums;font-weight:650}
</style></head><body>
<header>
  <h1>⬡ Gamma Levels Slides — SPX</h1>
  <button id="prev">←</button><span class="count" id="cnt">—</span><button id="next">→</button>
  <input type="text" id="jump" placeholder="YYYY-MM-DD"><button id="go">Jump</button>
  <span style="margin-left:auto"></span>
  <label><input type="checkbox" id="showOurs" checked>ours</label>
  <label><input type="checkbox" id="showMQ">MQ</label>
  <label><input type="checkbox" id="showCR" checked>CR</label>
  <label><input type="checkbox" id="showPS" checked>PS</label>
  <label><input type="checkbox" id="showHVL" checked>HVL</label>
  <label><input type="checkbox" id="showD1" checked>1D</label>
  <label><input type="checkbox" id="showVP" checked>VP</label>
  <label><input type="checkbox" id="showPrior" checked>prior H/L/C</label>
  <label><input type="checkbox" id="showGX">GEX1-4</label>
  <label><input type="checkbox" id="showProf" checked>profile</label>
  <button id="theme">◐</button>
</header>
<div class="wrap">
  <div style="display:flex;gap:15px;flex-wrap:wrap;margin-bottom:7px">
    <span class="chip"><i class="sw" style="background:var(--px)"></i>price</span>
    <span class="chip"><i class="sw" style="background:var(--cr)"></i>CR</span>
    <span class="chip"><i class="sw" style="background:var(--ps)"></i>PS</span>
    <span class="chip"><i class="sw" style="background:var(--hvl)"></i>HVL</span>
    <span class="chip"><i class="sw" style="background:var(--vp)"></i>VAH/VAL/POC</span>
    <span class="chip"><i class="sw" style="background:var(--gx)"></i>GEX 1-4</span>
    <span class="chip"><i class="sw" style="background:var(--prior)"></i>prior H/L/C</span>
    <span class="muted">solid = ours · dashed = MenthorQ · shaded band = 1D min/max · ← → to page</span>
  </div>
  <canvas id="c" height="640"></canvas>
  <canvas id="nav" height="70"></canvas>
  <p class="muted" id="meta"></p>
</div>
<script id="payload" type="application/json">__DATA__</script>
<script>
const D=JSON.parse(document.getElementById('payload').textContent);
let idx=0;const el=id=>document.getElementById(id);
const cssv=n=>getComputedStyle(document.documentElement).getPropertyValue(n).trim();
function fit(cv){const r=cv.getBoundingClientRect(),dpr=devicePixelRatio||1;
  const h=parseInt(cv.getAttribute('height'));cv.width=r.width*dpr;cv.height=h*dpr;
  const x=cv.getContext('2d');x.setTransform(dpr,0,0,dpr,0,0);return x;}
const on=id=>el(id).checked;

function draw(){
  const cv=el('c'),ctx=fit(cv),W=cv.clientWidth,H=parseInt(cv.getAttribute('height'));
  ctx.clearRect(0,0,W,H);
  const sl=D.slides[idx];if(!sl)return;
  const wantO=on('showOurs'),wantM=on('showMQ');
  const w={cr:on('showCR'),ps:on('showPS'),hvl:on('showHVL')};
  let lo=1e9,hi=-1e9;const grow=v=>{if(v==null||!isFinite(v))return;if(v<lo)lo=v;if(v>hi)hi=v};
  sl.forEach(d=>{d.p.forEach(grow);
    ['cr','ps','hvl'].forEach(k=>{if(!w[k])return;
      if(wantO)grow(d['o_'+k]); if(wantM)grow(d['m_'+k]);});
    if(on('showD1')){grow(d.d1lo);grow(d.d1hi)}
    if(on('showVP')){grow(d.vah);grow(d.val);grow(d.poc)}
    if(on('showPrior')){grow(d.ph);grow(d.pl)}
    if(on('showGX')&&d.gx)d.gx.forEach(grow);});
  const pad=(hi-lo)*0.07||10;lo-=pad;hi+=pad;
  const L=58,R=16,T=12,B=28,pw=W-L-R,ph=H-T-B;
  const total=sl.reduce((a,d)=>a+d.p.length,0);
  const X=i=>L+i/total*pw,Y=v=>T+(hi-v)/(hi-lo)*ph;
  ctx.strokeStyle=cssv('--grid');ctx.lineWidth=1;ctx.fillStyle=cssv('--muted');
  ctx.font='11px system-ui';ctx.textAlign='right';
  const step=Math.pow(10,Math.floor(Math.log10(hi-lo)))/2;
  for(let v=Math.ceil(lo/step)*step;v<hi;v+=step){const y=Y(v);
    ctx.beginPath();ctx.moveTo(L,y);ctx.lineTo(W-R,y);ctx.stroke();ctx.fillText(v.toFixed(0),L-6,y+3.5);}
  let i0=0;ctx.textAlign='center';
  sl.forEach((d,si)=>{
    const n=d.p.length,xa=X(i0),xb=X(i0+n-1),sw=xb-xa;
    // 1D expected-move band
    if(on('showD1')&&d.d1lo!=null&&d.d1hi!=null){
      ctx.fillStyle=cssv('--ink2')+'14';ctx.fillRect(xa,Y(d.d1hi),sw,Y(d.d1lo)-Y(d.d1hi));}
    // GEX profile histogram (translucent, from session's left edge)
    if(on('showProf')&&d.prof){const maxw=sw*0.42;
      d.prof.forEach(([k,v])=>{if(k<lo||k>hi)return;
        const y=Y(k),hgt=Math.max(1.5,ph/((hi-lo)/25)*0.7);
        ctx.fillStyle=(v>=0?cssv('--cr'):cssv('--ps'))+'2e';
        ctx.fillRect(xa,y-hgt/2,Math.abs(v)*maxw,hgt);});}
    if(si){ctx.strokeStyle=cssv('--border');ctx.beginPath();ctx.moveTo(xa,T);ctx.lineTo(xa,H-B);ctx.stroke();}
    const seg=(v,col,dash,lw)=>{if(v==null||!isFinite(v))return;
      ctx.save();ctx.setLineDash(dash);ctx.strokeStyle=col;ctx.lineWidth=lw;
      ctx.beginPath();ctx.moveTo(xa,Y(v));ctx.lineTo(xb,Y(v));ctx.stroke();ctx.restore();};
    if(on('showPrior')){[d.ph,d.pl,d.pc].forEach(v=>seg(v,cssv('--prior'),[2,3],1));}
    if(on('showVP')){seg(d.vah,cssv('--vp'),[],1.6);seg(d.val,cssv('--vp'),[],1.6);
                     seg(d.poc,cssv('--vp'),[],2.6);}
    if(on('showGX')&&d.gx)d.gx.forEach(v=>seg(v,cssv('--gx'),[],1));
    ['cr','ps','hvl'].forEach(k=>{if(!w[k])return;const col=cssv('--'+k);
      const lw=(k==='hvl')?2.6:2;
      if(wantO)seg(d['o_'+k],col,[],lw);
      if(wantM)seg(d['m_'+k],col,[6,4],lw);});
    ctx.strokeStyle=cssv('--px');ctx.lineWidth=1.4;ctx.beginPath();
    d.p.forEach((v,j)=>{const x=X(i0+j),y=Y(v);j?ctx.lineTo(x,y):ctx.moveTo(x,y)});ctx.stroke();
    ctx.fillStyle=cssv('--muted');ctx.font='11px system-ui';
    ctx.fillText(d.s.slice(5),(xa+xb)/2,H-9);
    i0+=n;});
  el('cnt').textContent=`${idx+1} / ${D.slides.length}`;
  el('meta').textContent=`${sl[0].s} → ${sl[sl.length-1].s} · ${D.n_sessions} sessions (${D.range[0]} → ${D.range[1]}) · levels are prior-session EOD, known before the bar opens`;
  el('prev').disabled=idx<=0;el('next').disabled=idx>=D.slides.length-1;
  drawNav();
}
function drawNav(){
  const cv=el('nav'),ctx=fit(cv),W=cv.clientWidth,H=parseInt(cv.getAttribute('height'));
  ctx.clearRect(0,0,W,H);const d=D.daily;if(!d.length)return;
  let lo=Math.min(...d.map(o=>o.c)),hi=Math.max(...d.map(o=>o.c));
  const pad=(hi-lo)*.06;lo-=pad;hi+=pad;
  const X=i=>i/(d.length-1)*W,Y=v=>6+(hi-v)/(hi-lo)*(H-16);
  const sl=D.slides[idx],a=sl[0].s,b=sl[sl.length-1].s;
  const ia=d.findIndex(o=>o.d>=a);let ib=d.findIndex(o=>o.d>=b);if(ib<0)ib=d.length-1;
  if(ia>=0){ctx.fillStyle=cssv('--ps')+'33';ctx.fillRect(X(ia),0,Math.max(3,X(ib)-X(ia)),H);}
  ctx.strokeStyle=cssv('--px');ctx.lineWidth=1.2;ctx.beginPath();
  d.forEach((o,i)=>{const x=X(i),y=Y(o.c);i?ctx.lineTo(x,y):ctx.moveTo(x,y)});ctx.stroke();
  ctx.fillStyle=cssv('--muted');ctx.font='10px system-ui';ctx.textAlign='left';
  ctx.fillText('SPX daily — click to jump',6,H-4);
}
el('nav').onclick=e=>{const r=e.target.getBoundingClientRect(),f=(e.clientX-r.left)/r.width;
  const i=Math.max(0,Math.min(Math.round(f*(D.daily.length-1)),D.daily.length-1));
  gotoDate(D.daily[i].d);};
function gotoDate(date){for(let i=0;i<D.slides.length;i++){const s=D.slides[i];
  if(s[s.length-1].s>=date){idx=i;draw();return}}idx=D.slides.length-1;draw();}
el('prev').onclick=()=>{if(idx>0){idx--;draw()}};
el('next').onclick=()=>{if(idx<D.slides.length-1){idx++;draw()}};
el('go').onclick=()=>{const v=el('jump').value.trim();if(v)gotoDate(v)};
el('jump').addEventListener('keydown',e=>{if(e.key==='Enter')el('go').click()});
addEventListener('keydown',e=>{if(e.target.tagName==='INPUT')return;
  if(e.key==='ArrowLeft')el('prev').click();if(e.key==='ArrowRight')el('next').click();});
['showOurs','showMQ','showCR','showPS','showHVL','showD1','showVP','showPrior','showGX','showProf']
  .forEach(id=>el(id).onchange=draw);
el('theme').onclick=()=>{const r=document.documentElement;
  const cur=r.getAttribute('data-theme')||(matchMedia('(prefers-color-scheme:dark)').matches?'dark':'light');
  r.setAttribute('data-theme',cur==='dark'?'light':'dark');draw();};
addEventListener('resize',draw);draw();
</script></body></html>"""


if __name__ == "__main__":
    main()
