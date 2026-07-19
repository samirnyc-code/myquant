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
K1D = 0.9809             # fitted 2023-24, held out 2025-26 (median level err 2.5pt)


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
    ES = ES[[c == front.get(d) for d, c in zip(ES.date, ES.contract)]].sort_values("DateTime")
    ES = ES.reset_index(drop=True)
    # ATR(14) on 5-min bars, GAP-ADJUSTED: the first bar of an RTH session uses High-Low
    # rather than swallowing the overnight gap (which inflates bar-0 TR ~4x).
    ES["bar"] = ES.groupby("date").cumcount()
    pc = ES.Close.shift(1)
    tr = pd.concat([ES.High-ES.Low, (ES.High-pc).abs(), (ES.Low-pc).abs()], axis=1).max(axis=1)
    ES["atr"] = pd.Series(np.where(ES.bar == 0, ES.High-ES.Low, tr)).rolling(14).mean()
    return ES


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

    VIX = pd.read_csv(ROOT / "data" / "vix_daily_full.csv")
    VIX["Date"] = VIX.Date.astype(str); VIX = VIX.set_index("Date")
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
        _a = bars[s]["atr"].iloc[0] if "atr" in bars[s] else None
        if _a is not None and np.isfinite(_a) and _a > 0:
            rec["atr"] = round(float(_a), 2)
        # ---- OUR levels (prior session chain) ----
        if d in ours:
            o = ours[d]
            for k in ("cr", "ps", "hvl"):
                if o.get(k) is not None:
                    rec["o_" + k] = o[k]
            if o.get("prof"):
                rec["prof"] = o["prof"]
        # ---- OUR 1D expected move: spot * (VIX/100) * sqrt(1/365) * K1D ----
        # Reverse-engineered from MQ's published d1 (k fitted 2023-24, held out
        # 2025-26: median level error 2.5pt). VIX is free — no MQ dependency.
        if d in VIX.index and d in S.index:
            mv = float(S.Close.loc[d]) * (float(VIX.vix.loc[d]) / 100) * np.sqrt(1 / 365) * K1D
            rec["o_d1lo"] = round(float(S.Close.loc[d]) - mv, 1)
            rec["o_d1hi"] = round(float(S.Close.loc[d]) + mv, 1)
        # ---- MenthorQ levels + their 1D + GEX 1-4 ----
        if d in MQ.index:
            m = MQ.loc[d]
            for k in ("cr", "ps", "hvl"):
                if pd.notna(m.get(k)):
                    rec["m_" + k] = float(m[k])
            for k, tag in (("d1_min", "m_d1lo"), ("d1_max", "m_d1hi")):
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

    daily = [{"d": r.Date, "c": round(float(r.Close), 1)}
             for r in spx.itertuples() if days[0]["s"] <= r.Date <= days[-1]["s"]]
    payload = {"days": days, "daily": daily, "n_sessions": len(days),
               "per_view": PER_SLIDE, "range": [days[0]["s"], days[-1]["s"]]}

    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / "levels.html").write_text(HTML.replace("__DATA__",
                                     json.dumps(payload, separators=(",", ":"))), encoding="utf-8")
    kb = (OUT / "levels.html").stat().st_size / 1024
    print(f"wrote {OUT/'levels.html'}  ({kb:.0f} KB)")
    print(f"  {len(days)} sessions  ({days[0]['s']} .. {days[-1]['s']})")
    for k, lbl in (("o_cr", "our CR"), ("m_cr", "MQ CR"), ("o_d1lo", "our 1D"),
                   ("vah", "prior VAH/VAL/POC"), ("gx", "GEX1-4"), ("prof", "GEX profile")):
        print(f"    {lbl:20} on {sum(1 for x in days if k in x)}/{len(days)} sessions")


HTML = r"""<!doctype html><html lang="en"><head>
<meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>Gamma Levels Slides — SPX</title>
<style>
:root{--surface:#fcfcfb;--plane:#f9f9f7;--ink:#0b0b0b;--ink2:#52514e;--muted:#898781;
 --border:rgba(11,11,11,.12);--grid:#00000010;--px:#1a1a19;
 --cr:#e34948;--ps:#2a78d6;--hvl:#eda100;--vp:#1baf7a;--gx:#4a3aa7;
 --ph:#e34948;--pl:#008300;--pc:#2a78d6;--d1:#e87ba4}
@media(prefers-color-scheme:dark){:root{--surface:#1a1a19;--plane:#0d0d0d;--ink:#fff;--ink2:#c3c2b7;
 --muted:#898781;--border:rgba(255,255,255,.14);--grid:#ffffff14;--px:#f2f2ef;
 --cr:#e66767;--ps:#3987e5;--hvl:#c98500;--vp:#199e70;--gx:#9085e9;
 --ph:#e66767;--pl:#008300;--pc:#3987e5;--d1:#d55181}}
:root[data-theme=dark]{--surface:#1a1a19;--plane:#0d0d0d;--ink:#fff;--ink2:#c3c2b7;--muted:#898781;
 --border:rgba(255,255,255,.14);--grid:#ffffff14;--px:#f2f2ef;
 --cr:#e66767;--ps:#3987e5;--hvl:#c98500;--vp:#199e70;--gx:#9085e9;
 --ph:#e66767;--pl:#008300;--pc:#3987e5;--d1:#d55181}
:root[data-theme=light]{--surface:#fcfcfb;--plane:#f9f9f7;--ink:#0b0b0b;--ink2:#52514e;--muted:#898781;
 --border:rgba(11,11,11,.12);--grid:#00000010;--px:#1a1a19;
 --cr:#e34948;--ps:#2a78d6;--hvl:#eda100;--vp:#1baf7a;--gx:#4a3aa7;
 --ph:#e34948;--pl:#008300;--pc:#2a78d6;--d1:#e87ba4}
*{box-sizing:border-box}
body{margin:0;background:var(--plane);color:var(--ink);font:14px system-ui,-apple-system,"Segoe UI",sans-serif}
header{padding:8px 16px;border-bottom:1px solid var(--border);background:var(--surface);
 display:flex;gap:10px;align-items:center;flex-wrap:wrap;position:sticky;top:0;z-index:5}
h1{font-size:14px;margin:0;font-weight:650;white-space:nowrap}
button{font:inherit;color:var(--ink);background:var(--surface);border:1px solid var(--border);
 border-radius:7px;padding:4px 9px;cursor:pointer;line-height:1.2}
button:hover{border-color:var(--muted)}button:disabled{opacity:.4;cursor:default}
button.on{background:var(--ps);color:#fff;border-color:var(--ps)}
.grp{display:inline-flex;gap:3px;align-items:center;border:1px solid var(--border);
 border-radius:8px;padding:2px 5px}
.grp>span{font-size:11px;color:var(--muted);margin-right:2px}
.wrap{max-width:1760px;margin:0 auto;padding:10px 16px 40px}
.chip{display:inline-flex;gap:5px;align-items:center;font-size:11.5px;color:var(--ink2)}
.sw{width:18px;height:3px;border-radius:2px;display:inline-block}
input[type=text]{font:inherit;padding:4px 8px;border:1px solid var(--border);border-radius:7px;
 background:var(--surface);color:var(--ink);width:104px}
label{font-size:11.5px;color:var(--ink2);display:inline-flex;gap:3px;align-items:center;cursor:pointer}
canvas{width:100%;display:block;border:1px solid var(--border);border-radius:10px;background:var(--surface)}
#c{cursor:grab}#c.drag{cursor:grabbing}
#nav{margin-top:8px}
.muted{color:var(--muted);font-size:11.5px}
.count{font-variant-numeric:tabular-nums;font-weight:650;min-width:96px;text-align:center}
</style></head><body>
<header>
  <h1>⬡ Gamma Levels</h1>
  <button id="prev">←</button><span class="count" id="cnt">—</span><button id="next">→</button>
  <input type="text" id="jump" placeholder="YYYY-MM-DD"><button id="go">Jump</button>
  <span class="grp"><span>sessions</span>
    <button data-n="1">1</button><button data-n="2">2</button><button data-n="5">5</button>
    <button data-n="10">10</button><button data-n="20">20</button><button data-n="40">40</button></span>
  <span class="grp"><span>Y</span><button id="yout">−</button><button id="yin">+</button></span>
  <span class="grp"><span>height</span><button id="hout">−</button><button id="hin">+</button></span>
  <button id="reset">reset</button>
  <span style="margin-left:auto"></span>
  <label><input type="checkbox" id="showOurs" checked>ours</label>
  <label><input type="checkbox" id="showMQ">MQ</label>
  <label><input type="checkbox" id="showCR" checked>CR</label>
  <label><input type="checkbox" id="showPS" checked>PS</label>
  <label><input type="checkbox" id="showHVL" checked>HVL</label>
  <label><input type="checkbox" id="showD1" checked>1D</label>
  <label><input type="checkbox" id="showVP" checked>VA</label>
  <label><input type="checkbox" id="showPrior" checked>prior HLC</label>
  <label><input type="checkbox" id="showGX">GEX1-4</label>
  <label><input type="checkbox" id="showProf" checked>profile</label>
  <label><input type="checkbox" id="showATR" checked>ATR zone</label>
  <button id="theme">◐</button>
</header>
<div class="wrap">
  <div style="display:flex;gap:13px;flex-wrap:wrap;margin-bottom:6px">
    <span class="chip"><i class="sw" style="background:var(--px)"></i>price</span>
    <span class="chip"><i class="sw" style="background:var(--cr)"></i>CR</span>
    <span class="chip"><i class="sw" style="background:var(--cr);height:9px;opacity:.3"></i>CR &plusmn;1 ATR</span>
    <span class="chip"><i class="sw" style="background:var(--ps)"></i>PS</span>
    <span class="chip"><i class="sw" style="background:var(--hvl)"></i>HVL</span>
    <span class="chip"><i class="sw" style="background:var(--vp)"></i>value area</span>
    <span class="chip"><i class="sw" style="background:var(--d1)"></i>1D</span>
    <span class="chip"><i class="sw" style="background:var(--gx)"></i>GEX1-4</span>
    <span class="chip"><i class="sw" style="background:var(--ph)"></i>pH</span>
    <span class="chip"><i class="sw" style="background:var(--pl)"></i>pL</span>
    <span class="chip"><i class="sw" style="background:var(--pc)"></i>pC</span>
    <span class="muted">solid = ours · dashed = MQ &amp; prior HLC · wheel = zoom Y · shift+wheel = sessions · drag = pan · dbl-click = reset</span>
  </div>
  <canvas id="c" height="640"></canvas>
  <canvas id="nav" height="66"></canvas>
  <p class="muted" id="meta"></p>
</div>
<script id="payload" type="application/json">__DATA__</script>
<script>
const D=JSON.parse(document.getElementById('payload').textContent);
const DAYS=D.days;
let start=0,count=D.per_view||10,yz=1,yc=0,chartH=640;
const el=id=>document.getElementById(id);
const cssv=n=>getComputedStyle(document.documentElement).getPropertyValue(n).trim();
const on=id=>el(id).checked;
let VIEW={lo:0,hi:1,L:58,R:16,T:12,B:28};

function fit(cv){const r=cv.getBoundingClientRect(),dpr=devicePixelRatio||1;
  const h=parseInt(cv.getAttribute('height'));cv.width=r.width*dpr;cv.height=h*dpr;
  const x=cv.getContext('2d');x.setTransform(dpr,0,0,dpr,0,0);return x;}

function slice(){return DAYS.slice(start,Math.min(start+count,DAYS.length));}

function autoRange(sl){
  const wantO=on('showOurs'),wantM=on('showMQ');
  const w={cr:on('showCR'),ps:on('showPS'),hvl:on('showHVL')};
  let lo=1e9,hi=-1e9;const grow=v=>{if(v==null||!isFinite(v))return;if(v<lo)lo=v;if(v>hi)hi=v};
  sl.forEach(d=>{d.p.forEach(grow);
    ['cr','ps','hvl'].forEach(k=>{if(!w[k])return;if(wantO)grow(d['o_'+k]);if(wantM)grow(d['m_'+k]);});
    if(on('showD1')){grow(d.o_d1lo);grow(d.o_d1hi);if(wantM){grow(d.m_d1lo);grow(d.m_d1hi)}}
    if(on('showVP')){grow(d.vah);grow(d.val)}
    if(on('showPrior')){grow(d.ph);grow(d.pl);grow(d.pc)}
    if(on('showGX')&&d.gx)d.gx.forEach(grow);
    if(on('showATR')&&d.atr&&w.cr){const L=wantO?d.o_cr:d.m_cr;
      if(L!=null){grow(L+d.atr);grow(L-d.atr);}}});
  if(lo>hi){lo=0;hi=1}
  const pad=(hi-lo)*0.07||10;return[lo-pad,hi+pad];
}

function draw(){
  el('c').setAttribute('height',chartH);
  const cv=el('c'),ctx=fit(cv),W=cv.clientWidth,H=chartH;
  ctx.clearRect(0,0,W,H);
  const sl=slice();if(!sl.length)return;
  const [alo,ahi]=autoRange(sl);
  const mid=(alo+ahi)/2+yc, half=(ahi-alo)/2/yz;
  const lo=mid-half, hi=mid+half;
  VIEW={lo,hi,L:58,R:16,T:12,B:28};
  const {L,R,T,B}=VIEW,pw=W-L-R,ph=H-T-B;
  const total=sl.reduce((a,d)=>a+d.p.length,0);
  const X=i=>L+i/total*pw,Y=v=>T+(hi-v)/(hi-lo)*ph;
  VIEW.Y=Y;VIEW.ph=ph;VIEW.T=T;
  // grid
  ctx.strokeStyle=cssv('--grid');ctx.lineWidth=1;ctx.fillStyle=cssv('--muted');
  ctx.font='11px system-ui';ctx.textAlign='right';
  let step=Math.pow(10,Math.floor(Math.log10(Math.max(hi-lo,1))))/2;
  while((hi-lo)/step>14)step*=2; while((hi-lo)/step<4)step/=2;
  for(let v=Math.ceil(lo/step)*step;v<hi;v+=step){const y=Y(v);
    ctx.beginPath();ctx.moveTo(L,y);ctx.lineTo(W-R,y);ctx.stroke();ctx.fillText(v.toFixed(0),L-6,y+3.5);}
  const wantO=on('showOurs'),wantM=on('showMQ');
  const w={cr:on('showCR'),ps:on('showPS'),hvl:on('showHVL')};
  let i0=0;ctx.textAlign='center';
  const showLbl=count<=20;
  sl.forEach((d,si)=>{
    const n=d.p.length,xa=X(i0),xb=X(i0+n-1),sw=xb-xa;
    if(on('showVP')&&d.vah!=null&&d.val!=null){
      ctx.fillStyle=cssv('--vp')+'1f';ctx.fillRect(xa,Y(d.vah),Math.max(sw,1),Y(d.val)-Y(d.vah));}
    // ATR(14) pinning zone around CR
    if(on('showATR')&&on('showCR')&&d.atr){
      const Lc=(wantO&&d.o_cr!=null)?d.o_cr:((wantM&&d.m_cr!=null)?d.m_cr:null);
      if(Lc!=null){
        // solid-ish fill carries the zone; edges are faint hairlines
        ctx.fillStyle=cssv('--cr')+'3d';
        ctx.fillRect(xa,Y(Lc+d.atr),Math.max(sw,1),Y(Lc-d.atr)-Y(Lc+d.atr));
        ctx.save();ctx.setLineDash([2,4]);ctx.strokeStyle=cssv('--cr');ctx.globalAlpha=.35;ctx.lineWidth=0.8;
        [Lc+d.atr,Lc-d.atr].forEach(function(v){ctx.beginPath();ctx.moveTo(xa,Y(v));ctx.lineTo(xb,Y(v));ctx.stroke();});
        ctx.restore();}}
    if(on('showProf')&&d.prof){const maxw=sw*0.42;
      const binPx=Math.max(1.5,ph/((hi-lo)/25)*0.7);
      d.prof.forEach(([k,v])=>{if(k<lo||k>hi)return;
        ctx.fillStyle=(v>=0?cssv('--cr'):cssv('--ps'))+'2e';
        ctx.fillRect(xa,Y(k)-binPx/2,Math.abs(v)*maxw,binPx);});}
    if(si){ctx.strokeStyle=cssv('--border');ctx.beginPath();ctx.moveTo(xa,T);ctx.lineTo(xa,H-B);ctx.stroke();}
    const seg=(v,col,dash,lw)=>{if(v==null||!isFinite(v)||v<lo||v>hi)return;
      ctx.save();ctx.setLineDash(dash);ctx.strokeStyle=col;ctx.lineWidth=lw;
      ctx.beginPath();ctx.moveTo(xa,Y(v));ctx.lineTo(xb,Y(v));ctx.stroke();ctx.restore();};
    if(on('showPrior')){seg(d.ph,cssv('--ph'),[3,3],1.6);seg(d.pl,cssv('--pl'),[3,3],1.6);
                        seg(d.pc,cssv('--pc'),[3,3],1.6);}
    if(on('showVP')){seg(d.vah,cssv('--vp'),[],1.4);seg(d.val,cssv('--vp'),[],1.4);}
    if(on('showD1')){seg(d.o_d1lo,cssv('--d1'),[],1.4);seg(d.o_d1hi,cssv('--d1'),[],1.4);
      if(wantM){seg(d.m_d1lo,cssv('--d1'),[6,4],1.4);seg(d.m_d1hi,cssv('--d1'),[6,4],1.4);}}
    if(on('showGX')&&d.gx)d.gx.forEach(v=>seg(v,cssv('--gx'),[],1));
    ['cr','ps','hvl'].forEach(k=>{if(!w[k])return;const col=cssv('--'+k),lw=(k==='hvl')?2.6:2;
      if(wantO)seg(d['o_'+k],col,[],lw); if(wantM)seg(d['m_'+k],col,[6,4],lw);});
    ctx.strokeStyle=cssv('--px');ctx.lineWidth=count>20?1:1.4;ctx.beginPath();
    let started=false;
    d.p.forEach((v,j)=>{const x=X(i0+j),y=Y(v);started?ctx.lineTo(x,y):(ctx.moveTo(x,y),started=true)});
    ctx.stroke();
    if(showLbl){ctx.fillStyle=cssv('--muted');ctx.font='11px system-ui';
      ctx.fillText(count<=5?d.s:d.s.slice(5),(xa+xb)/2,H-9);}
    i0+=n;});
  const last=sl[sl.length-1];
  el('cnt').textContent=`${start+1}–${start+sl.length} / ${DAYS.length}`;
  el('meta').textContent=`${sl[0].s} → ${last.s} · ${count} session(s)/view · Y zoom ${yz.toFixed(2)}× · `
    +`levels are prior-session EOD (known before the bar opens)`;
  el('prev').disabled=start<=0;el('next').disabled=start+count>=DAYS.length;
  document.querySelectorAll('[data-n]').forEach(b=>b.classList.toggle('on',+b.dataset.n===count));
  drawNav();
}
function drawNav(){
  const cv=el('nav'),ctx=fit(cv),W=cv.clientWidth,H=parseInt(cv.getAttribute('height'));
  ctx.clearRect(0,0,W,H);const d=D.daily;if(!d.length)return;
  let lo=Math.min(...d.map(o=>o.c)),hi=Math.max(...d.map(o=>o.c));
  const pad=(hi-lo)*.06;lo-=pad;hi+=pad;
  const X=i=>i/(d.length-1)*W,Y=v=>6+(hi-v)/(hi-lo)*(H-16);
  const sl=slice(),a=sl[0].s,b=sl[sl.length-1].s;
  const ia=d.findIndex(o=>o.d>=a);let ib=d.findIndex(o=>o.d>=b);if(ib<0)ib=d.length-1;
  if(ia>=0){ctx.fillStyle=cssv('--ps')+'33';ctx.fillRect(X(ia),0,Math.max(3,X(ib)-X(ia)),H);}
  ctx.strokeStyle=cssv('--px');ctx.lineWidth=1.2;ctx.beginPath();
  d.forEach((o,i)=>{const x=X(i),y=Y(o.c);i?ctx.lineTo(x,y):ctx.moveTo(x,y)});ctx.stroke();
  ctx.fillStyle=cssv('--muted');ctx.font='10px system-ui';ctx.textAlign='left';
  ctx.fillText('SPX daily — click to jump',6,H-4);
}
function gotoDate(date){const i=DAYS.findIndex(x=>x.s>=date);
  start=Math.max(0,Math.min(i<0?DAYS.length-count:i,DAYS.length-1));draw();}
el('nav').onclick=e=>{const r=e.target.getBoundingClientRect(),f=(e.clientX-r.left)/r.width;
  const i=Math.max(0,Math.min(Math.round(f*(D.daily.length-1)),D.daily.length-1));
  gotoDate(D.daily[i].d);};
el('prev').onclick=()=>{start=Math.max(0,start-count);draw()};
el('next').onclick=()=>{start=Math.min(DAYS.length-1,start+count);draw()};
el('go').onclick=()=>{const v=el('jump').value.trim();if(v)gotoDate(v)};
el('jump').addEventListener('keydown',e=>{if(e.key==='Enter')el('go').click()});
document.querySelectorAll('[data-n]').forEach(b=>b.onclick=()=>{count=+b.dataset.n;draw()});
el('yin').onclick=()=>{yz=Math.min(yz*1.3,60);draw()};
el('yout').onclick=()=>{yz=Math.max(yz/1.3,1);if(yz===1)yc=0;draw()};
el('hin').onclick=()=>{chartH=Math.min(chartH+120,1800);draw()};
el('hout').onclick=()=>{chartH=Math.max(chartH-120,280);draw()};
el('reset').onclick=()=>{yz=1;yc=0;chartH=640;draw()};
// wheel: zoom Y about cursor ; shift+wheel: sessions per view
el('c').addEventListener('wheel',e=>{e.preventDefault();
  if(e.shiftKey){const opts=[1,2,5,10,20,40,80];let i=opts.indexOf(count);
    if(i<0)i=3; i=Math.max(0,Math.min(opts.length-1,i+(e.deltaY>0?1:-1)));count=opts[i];draw();return;}
  const r=e.target.getBoundingClientRect(),y=e.clientY-r.top;
  const {lo,hi,T,ph}=VIEW,pAt=hi-(y-T)/ph*(hi-lo);
  const f=e.deltaY>0?1/1.15:1.15;const nz=Math.max(1,Math.min(yz*f,60));
  if(nz!==yz){
    // keep the price under the cursor pinned while zooming
    const [alo,ahi]=autoRange(slice());
    const mid0=(alo+ahi)/2, half=(ahi-alo)/2/nz, frac=(y-T)/ph;
    yz=nz; yc=pAt+(2*frac-1)*half-mid0;}
  draw();},{passive:false});
// drag to pan Y
let dragY=null;
el('c').addEventListener('mousedown',e=>{dragY={y:e.clientY,yc};el('c').classList.add('drag')});
addEventListener('mouseup',()=>{dragY=null;el('c').classList.remove('drag')});
addEventListener('mousemove',e=>{if(!dragY)return;
  const {lo,hi,ph}=VIEW;yc=dragY.yc+(e.clientY-dragY.y)/ph*(hi-lo);draw();});
el('c').addEventListener('dblclick',()=>{yz=1;yc=0;draw()});
addEventListener('keydown',e=>{if(e.target.tagName==='INPUT')return;
  if(e.key==='ArrowLeft')el('prev').click();if(e.key==='ArrowRight')el('next').click();});
['showOurs','showMQ','showCR','showPS','showHVL','showD1','showVP','showPrior','showGX','showProf','showATR']
  .forEach(id=>el(id).onchange=draw);
el('theme').onclick=()=>{const r=document.documentElement;
  const cur=r.getAttribute('data-theme')||(matchMedia('(prefers-color-scheme:dark)').matches?'dark':'light');
  r.setAttribute('data-theme',cur==='dark'?'light':'dark');draw();};
addEventListener('resize',draw);draw();
</script></body></html>"""


if __name__ == "__main__":
    main()
