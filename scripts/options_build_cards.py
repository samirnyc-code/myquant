"""Build the interactive trade-card wall (S73) -> data/options_sim/cards.html.

One tile per trade: front = strategy, grade chip, headline P&L, mini payoff
sparkline. Click = zoom to center; click again = 3D flip to the detail side
(legs, credit, collateral, POP, breakevens, est. greeks, full commentary) with
the full expiry-payoff diagram (green profit / red loss, spot + breakeven
markers). Self-contained file; embedded by the Streamlit app (Trades tab) and
openable standalone in any browser.

Greeks are Black-Scholes ESTIMATES (IV from the trade's entry VIX, r=0) —
labeled as such; we do not store per-leg entry greeks yet.
"""
import datetime as dt
import glob
import json
import math
from pathlib import Path
from zoneinfo import ZoneInfo

import numpy as np
import pandas as pd

import options_trade_log as tlog

ROOT = Path(__file__).resolve().parents[1]
SIM = ROOT / "data" / "options_sim"
ET = ZoneInfo("America/New_York")


def spx_close_on(date_iso):
    """SPX (^GSPC) close for a past calendar date, from the daily cache. None if absent."""
    try:
        d = pd.read_csv(SIM / "spx_daily_yahoo.csv")
        row = d[d.Date == date_iso]
        return float(row.Close.iloc[0]) if len(row) else None
    except Exception:
        return None


def _phi(x):
    return math.exp(-x * x / 2) / math.sqrt(2 * math.pi)


def _N(x):
    return (1 + math.erf(x / math.sqrt(2))) / 2


def bs_greeks(S, K, T, sig, right):
    """Per-contract delta/gamma/theta(day)/vega for one long option."""
    T = max(T, 1e-6)
    d1 = (math.log(S / K) + sig * sig / 2 * T) / (sig * math.sqrt(T))
    d2 = d1 - sig * math.sqrt(T)
    delta = _N(d1) if right == "C" else _N(d1) - 1
    gamma = _phi(d1) / (S * sig * math.sqrt(T))
    theta = (-S * _phi(d1) * sig / (2 * math.sqrt(T))) / 365
    vega = S * _phi(d1) * math.sqrt(T) / 100
    return delta, gamma, theta, vega


NAMES = {
    "bps_stmr": "Bull Put Spread — STMR",
    "sell_0dte_gamma": "Put Credit Spread @ Put Support",
    "condor_0dte": "Iron Condor — 0DTE Walls",
    "straddle_0dte": "Long ATM Straddle",
    "fly_gw_0dte": "Call Butterfly @ Gamma Wall",
    "bcs_cr_0dte": "Bear Call Spread @ Call Resistance",
    "bull_cs_wk": "Bull Call Spread — Weekly",
    "put_cal_wk": "Put Calendar",
}


def latest_spot():
    fs = sorted(glob.glob(str(SIM / "underlying_*.csv")))
    if fs:
        u = pd.read_csv(fs[-1])
        if len(u):
            return float(u.und.iloc[-1])
    return None


def _series_for(hist):
    """Downsample a trade's metrics history to <=120 points for the inline card chart.
    Returns {t:[HH:MM...], pnl:[...], pop:[...%]} or None if too few points."""
    if hist is None or len(hist) < 2:
        return None
    h = hist
    if len(h) > 120:                       # even stride keeps first+last
        h = h.iloc[:: max(1, len(h) // 120)]
    t = pd.to_datetime(h.ts_et)
    return {"t": [x.strftime("%H:%M") for x in t],
            "pnl": [None if pd.isna(x) else round(float(x)) for x in h.unreal_pnl],
            "pop": [None if pd.isna(x) else round(float(x) * 100) for x in h["pop"]]}


def trade_payload(r, last_marks, spot, metrics_hist=None):
    legs = json.loads(r.legs) if isinstance(r.legs, str) else []
    is_open = pd.isna(r.exit_dt)
    un = last_marks.unreal_pnl.get(r.trade_id) if last_marks is not None and is_open else None
    pnl = un if is_open else (float(r.pnl) if pd.notna(r.pnl) else None)
    # multi-expiry only counts LIVE legs: once a calendar's near leg expires, the
    # position collapses to its surviving single-expiry legs and DOES have a payoff.
    today = dt.datetime.now(ET).strftime("%Y%m%d")
    live_legs = [l for l in legs if l["expiry"] >= today]
    expired_close = {l["expiry"]: spx_close_on(dt.datetime.strptime(l["expiry"], "%Y%m%d").date().isoformat())
                     for l in legs if l["expiry"] < today}
    multi_exp = len({l["expiry"] for l in live_legs}) > 1
    S0 = spot or (legs[0]["strike"] if legs else 7500)
    payoff, bes = None, []
    if live_legs and not multi_exp:
        ks = [l["strike"] for l in live_legs]
        grid = np.unique(np.concatenate([np.linspace(min(ks) - 120, max(ks) + 120, 220), ks, [S0]]))

        credit = float(r.credit) if pd.notna(r.credit) else 0.0

        def pv(S):
            # P&L at the surviving legs' expiry = net entry credit − settlement cost.
            # Already-expired legs settle at their OWN expiry-date SPX close (a fixed
            # constant), surviving legs at the terminal S being swept.
            v = credit
            for l in legs:
                if l["expiry"] < today:
                    base = expired_close.get(l["expiry"])
                    if base is None:
                        base = S               # fallback if that close isn't cached
                else:
                    base = S
                intr = max(0.0, (base - l["strike"]) if l["right"] == "C" else (l["strike"] - base))
                v += l.get("qty", 1) * (-intr if l["side"] == "sell" else intr)
            return v * 100
        vals = np.array([pv(S) for S in grid])
        for i in range(1, len(grid)):
            a, b = vals[i - 1], vals[i]
            if a * b < 0:
                bes.append(round(float(grid[i - 1] + (grid[i] - grid[i - 1]) * (-a) / (b - a)), 1))
        payoff = {"s": [round(float(x), 1) for x in grid], "v": [round(float(x)) for x in vals]}
    # est. greeks (position-level, BS, IV from entry VIX)
    greeks = None
    if legs and spot:
        sig = (float(r.vix) / 100 if pd.notna(r.vix) else 0.16)
        tot = [0.0, 0.0, 0.0, 0.0]
        for l in legs:
            expiry = dt.datetime.strptime(l["expiry"], "%Y%m%d").replace(hour=16, tzinfo=ET)
            T = max((expiry - dt.datetime.now(ET)).total_seconds(), 600) / (365 * 24 * 3600)
            g = bs_greeks(spot, l["strike"], T, sig, l["right"])
            sgn = -1 if l["side"] == "sell" else 1
            for i in range(4):
                tot[i] += sgn * l["qty"] * g[i] * 100
        greeks = {"delta": round(tot[0], 1), "gamma": round(tot[1], 3),
                  "theta": round(tot[2], 0), "vega": round(tot[3], 0)}
    pop_v = r["pop"]
    exps = sorted({l["expiry"] for l in legs})
    exp_str = " / ".join(f"{e[4:6]}/{e[6:]}/{e[:4]}" for e in exps) if exps else ""
    return {
        "id": r.trade_id, "strat": r.strategy_id,
        "name": NAMES.get(r.strategy_id, r.strategy_id.replace("_", " ").title()),
        "exp": exp_str, "structure": r.structure or "",
        "grade": r.grade if isinstance(r.grade, str) else "?",
        "state": "OPEN" if is_open else "CLOSED",
        "exitd": (str(r.exit_dt)[:10] if (not is_open and pd.notna(r.exit_dt)) else None),
        "pnl": None if pnl is None else round(pnl),
        "legs": [f"{l['side'][0].upper()}{l.get('qty', 1)} {l['strike']:.0f}{l['right']} {l['expiry'][4:6]}/{l['expiry'][6:]}" for l in legs],
        "credit": round(float(r.credit), 2) if pd.notna(r.credit) else None,
        "collateral": round(float(r.collateral)) if pd.notna(r.collateral) else None,
        "maxg": None if pd.isna(r.max_gain) else round(float(r.max_gain)),
        "maxl": None if pd.isna(r.max_loss) else round(float(r.max_loss)),
        "pop": None if pd.isna(pop_v) else round(float(pop_v) * 100),
        "vix": None if pd.isna(r.vix) else float(r.vix),
        "entry": str(r.entry_dt), "dow": r.dow if isinstance(r.dow, str) else "",
        "commentary": r.commentary if isinstance(r.commentary, str) else "",
        "payoff": payoff, "breakevens": bes, "spot": None if spot is None else round(spot, 1),
        "greeks": greeks, "multi": multi_exp,
        "series": _series_for(metrics_hist),
    }


HTML = r"""<!doctype html><html><head><meta charset="utf-8"><title>Trade Cards</title><style>
:root{--bg:#0d0f14;--card:#171b23;--card2:#1b202b;--ink:#e6e9ef;--mut:#8a91a0;--line:#2a3040;
--blue:#3987e5;--good:#1baf7a;--warn:#eda100;--crit:#e34948;--orange:#eb6834;--vio:#9085e9}
@media (prefers-color-scheme: light){:root{--bg:#eef0f3;--card:#fff;--card2:#fafbfc;--ink:#151821;--mut:#68707f;--line:#dde1e8}}
*{box-sizing:border-box}body{margin:0;background:var(--bg);color:var(--ink);
font:14px/1.45 system-ui,'Segoe UI',sans-serif;padding:16px}
.grid{display:grid;grid-template-columns:repeat(auto-fill,minmax(300px,1fr));gap:14px}
.tile{background:linear-gradient(160deg,var(--card2),var(--card) 55%);border:1px solid var(--line);
border-radius:16px;padding:16px 16px 12px;cursor:pointer;position:relative;overflow:hidden;
transition:transform .16s, box-shadow .16s, border-color .16s}
.tile::before{content:'';position:absolute;top:0;left:0;right:0;height:3px;background:var(--gc,#777)}
.tile:hover{transform:translateY(-4px) scale(1.015);box-shadow:0 14px 34px rgba(0,0,0,.45);border-color:var(--gc,#777)}
.trow{display:flex;justify-content:space-between;align-items:flex-start;gap:8px}
.strat{font-weight:800;font-size:16px;letter-spacing:.01em}
.exp{color:var(--mut);font-size:12px;margin-top:1px}
.chip{min-width:2.2em;text-align:center;padding:3px 10px;border-radius:10px;color:#fff;font-weight:800;
box-shadow:0 2px 10px rgba(0,0,0,.35)}
.staterow{display:flex;align-items:center;gap:7px;margin-top:8px;font-size:10.5px;letter-spacing:.14em;color:var(--mut)}
.dot{width:8px;height:8px;border-radius:50%}
.dot.open{background:var(--good);animation:pulse 1.6s infinite}
.dot.closed{background:var(--mut)}
@keyframes pulse{0%{box-shadow:0 0 0 0 rgba(27,175,122,.55)}70%{box-shadow:0 0 0 8px rgba(27,175,122,0)}100%{box-shadow:0 0 0 0 rgba(27,175,122,0)}}
.pnl{font-size:26px;font-weight:850;margin:6px 0 0;text-shadow:0 0 24px rgba(0,0,0,.3)}
.pos{color:var(--good)}.neg{color:var(--crit)}
.sub{color:var(--mut);font-size:12px;margin-top:2px}
.spark{margin-top:10px;display:block}
#ovl{position:fixed;inset:0;background:rgba(5,6,10,.72);backdrop-filter:blur(4px);
display:none;align-items:center;justify-content:center;z-index:9}
#ovl.on{display:flex}
.big{width:min(1000px,96vw);height:min(760px,94vh);perspective:1500px;cursor:pointer;
animation:zoomin .22s ease-out}
@keyframes zoomin{from{transform:scale(.6);opacity:.2}to{transform:scale(1);opacity:1}}
.inner{position:relative;width:100%;height:100%;transition:transform .6s cubic-bezier(.4,.1,.2,1);transform-style:preserve-3d}
.big.flip .inner{transform:rotateY(180deg)}
.face{position:absolute;inset:0;backface-visibility:hidden;background:linear-gradient(165deg,var(--card2),var(--card) 60%);
border:1px solid var(--line);border-radius:20px;padding:24px;overflow:hidden;box-shadow:0 24px 70px rgba(0,0,0,.5);
display:flex;flex-direction:column}
.face::before{content:'';position:absolute;top:0;left:0;right:0;height:4px;background:var(--gc,#777);border-radius:20px 20px 0 0}
.back{transform:rotateY(180deg)}
.kv{display:grid;grid-template-columns:repeat(3,1fr);gap:10px;margin:12px 0}
.kv>div{background:var(--card);border:1px solid var(--line);border-left:3px solid var(--kc,var(--line));
border-radius:11px;padding:8px 11px}
.kv b{display:block;font-size:9.5px;color:var(--mut);letter-spacing:.09em;margin-bottom:2px}
.kv span{font-weight:700;font-size:14px}
.gauge{height:10px;border-radius:6px;background:linear-gradient(90deg,var(--crit),var(--warn) 50%,var(--good));
position:relative;margin:6px 0 2px}
.gauge i{position:absolute;top:-4px;width:4px;height:18px;background:var(--ink);border-radius:2px;box-shadow:0 0 6px rgba(0,0,0,.6)}
.glabel{display:flex;justify-content:space-between;font-size:10px;color:var(--mut)}
.hint{position:absolute;bottom:12px;right:18px;font-size:11px;color:var(--mut)}
.comm{background:var(--card);border-left:3px solid var(--blue);border-radius:9px;padding:11px 13px;
margin-top:10px;font-size:13px;line-height:1.5;max-height:82px;overflow:hidden}
.legchips{display:flex;flex-wrap:wrap;gap:6px;margin:8px 0}
.legchip{background:var(--card);border:1px solid var(--line);border-radius:8px;padding:3px 9px;
font-size:12px;font-weight:600}
.legchip.sell{border-color:var(--crit);color:var(--crit)}
.legchip.buy{border-color:var(--good);color:var(--good)}
h2{margin:0 0 1px;font-size:21px}.mut{color:var(--mut)}
.sechead{display:flex;align-items:center;gap:10px;margin:18px 2px 10px;font-size:13px;
letter-spacing:.14em;color:var(--mut);font-weight:700}
.sechead::after{content:'';flex:1;height:1px;background:var(--line)}
.sechead .cnt{background:var(--card);border:1px solid var(--line);border-radius:8px;padding:1px 8px}
</style></head><body>
<details class="ex ex-sec" id="oh" open><summary>● OPEN POSITIONS <span class="cnt" id="oc"></span></summary>
<div class="grid" id="grid_open"></div></details>
<details class="ex ex-sec" id="ch" open><summary>CLOSED TODAY <span class="cnt" id="cc"></span>
<span class="muted" style="font-weight:400;margin-left:6px">· history in the Calendar tab</span></summary>
<div class="grid" id="grid_closed"></div></details>
<div id="ovl"><div class="big" id="big"><div class="inner" id="inner"></div></div></div>
<script>
const T = __DATA__;
const GC = {A:'var(--good)',B:'var(--blue)',C:'var(--warn)',D:'var(--orange)',F:'var(--crit)'};
const $ = s=>document.querySelector(s);
const fmt = v => v==null ? '—' : (v<0?'−':'+')+'$'+Math.abs(v).toLocaleString();
const fmtu = v => v==null ? '—' : '$'+Math.abs(v).toLocaleString();

function payoffSVG(t, w, h, mini){
  if(!t.payoff) return `<div class="sub" style="height:${h}px;display:flex;align-items:center">`+
    (t.multi?'multi-expiry — single-expiry payoff undefined':'no payoff data')+`</div>`;
  const s=t.payoff.s, v=t.payoff.v, ml=mini?4:44, mb=mini?4:22, mt=mini?4:10, mr=8;
  const x0=s[0], x1=s[s.length-1], vmin=Math.min(...v,0), vmax=Math.max(...v,0), pad=(vmax-vmin)*.14||1;
  const X=x=> ml+(x-x0)/(x1-x0)*(w-ml-mr), Y=y=> mt+(1-(y-(vmin-pad))/((vmax+pad)-(vmin-pad)))*(h-mt-mb);
  const zero=Y(0).toFixed(1);
  let up='',dn='';
  for(let i=0;i<s.length;i++){const c=`${X(s[i]).toFixed(1)},${Y(v[i]).toFixed(1)} `;
    up+= (v[i]>=0? c : `${X(s[i]).toFixed(1)},${zero} `);
    dn+= (v[i]<0?  c : `${X(s[i]).toFixed(1)},${zero} `);}
  let extras='';
  if(!mini){
    // strike ticks
    for(const L of t.legs){const k=parseFloat(L.split(' ')[1]);
      if(k>=x0&&k<=x1) extras+=`<line x1="${X(k)}" y1="${h-mb}" x2="${X(k)}" y2="${h-mb+5}" stroke="var(--mut)"/>`+
        `<text x="${X(k)}" y="${h-4}" fill="var(--mut)" font-size="10" text-anchor="middle">${k}</text>`;}
    // y labels
    extras+=`<text x="4" y="${Y(vmax)+4}" fill="var(--good)" font-size="11" font-weight="700">${fmt(vmax)}</text>`+
            `<text x="4" y="${Y(vmin)+4}" fill="var(--crit)" font-size="11" font-weight="700">${fmt(vmin)}</text>`+
            `<text x="4" y="${+zero+4}" fill="var(--mut)" font-size="10">$0</text>`;
    // max annotations on curve
    const iMax=v.indexOf(Math.max(...v)), iMin=v.indexOf(Math.min(...v));
    extras+=`<circle cx="${X(s[iMax])}" cy="${Y(v[iMax])}" r="4" fill="var(--good)"/>`+
            `<circle cx="${X(s[iMin])}" cy="${Y(v[iMin])}" r="4" fill="var(--crit)"/>`;
    if(t.spot!=null && t.spot>=x0 && t.spot<=x1)
      extras+=`<line x1="${X(t.spot)}" y1="${mt}" x2="${X(t.spot)}" y2="${h-mb}" stroke="var(--blue)" stroke-width="2" stroke-dasharray="6 4"/>`+
              `<text x="${X(t.spot)+5}" y="${mt+12}" fill="var(--blue)" font-size="11" font-weight="700">spot ${t.spot}</text>`;
    for(const b of t.breakevens)
      extras+=`<circle cx="${X(b)}" cy="${zero}" r="5" fill="var(--warn)" stroke="var(--bg)" stroke-width="2"/>`+
              `<text x="${X(b)}" y="${+zero-9}" fill="var(--warn)" font-size="10.5" font-weight="700" text-anchor="middle">BE ${b}</text>`;
  }
  return `<svg class="spark" width="${w}" height="${h}" viewBox="0 0 ${w} ${h}">
    <defs>
     <linearGradient id="gup${w}" x1="0" y1="0" x2="0" y2="1">
       <stop offset="0" stop-color="var(--good)" stop-opacity=".45"/><stop offset="1" stop-color="var(--good)" stop-opacity=".04"/></linearGradient>
     <linearGradient id="gdn${w}" x1="0" y1="1" x2="0" y2="0">
       <stop offset="0" stop-color="var(--crit)" stop-opacity=".45"/><stop offset="1" stop-color="var(--crit)" stop-opacity=".04"/></linearGradient>
    </defs>
    <line x1="${ml}" y1="${zero}" x2="${w-mr}" y2="${zero}" stroke="var(--line)" stroke-width="1.5"/>
    <polygon points="${X(s[0])},${zero} ${up}${X(s[s.length-1])},${zero}" fill="url(#gup${w})"/>
    <polygon points="${X(s[0])},${zero} ${dn}${X(s[s.length-1])},${zero}" fill="url(#gdn${w})"/>
    <polyline points="${s.map((x,i)=>X(x).toFixed(1)+','+Y(v[i]).toFixed(1)).join(' ')}"
      fill="none" stroke="var(--ink)" stroke-width="2.4" stroke-linejoin="round"/>${extras}</svg>`;
}

const MW=900, MH=214;                 // metrics-chart viewBox (fixed → hover math is exact)
function mgeom(S){
  const n=S.pnl.length, ml=44, mr=56, gap=16;
  const hP=Math.round((MH-gap)*0.6), oy=hP+gap, hQ=MH-oy;
  const pv=S.pnl.map(x=>x==null?0:x);
  const pmin=Math.min(...pv,0), pmax=Math.max(...pv,0), pad=(pmax-pmin)*.12||1;
  const X=i=> ml+(n<=1?0:i/(n-1))*(MW-ml-mr);
  const YP=y=> (1-(y-(pmin-pad))/((pmax+pad)-(pmin-pad)))*hP;
  const YQ=y=> oy+(1-y/100)*hQ;
  return {n,ml,mr,hP,oy,hQ,pv,X,YP,YQ};
}
function metricsSVG(t){
  // two stacked sparklines (never dual-axis): P&L($) area + POP(%) line, over the
  // trade's life from trade_metrics.csv. Rebuilds every card-wall refresh = live.
  // Hover crosshair + tooltip wired in wireMetricsHover().
  const S=t.series;
  if(!S || !S.pnl || S.pnl.length<2)
    return `<div class="sub" style="height:${MH}px;display:flex;align-items:center">no live metrics history yet — the marker logs one point per cycle</div>`;
  const G=mgeom(S), n=G.n, w=MW, h=MH, zP=G.YP(0).toFixed(1), last=G.pv[n-1];
  let up='',dn='';
  for(let i=0;i<n;i++){const c=`${G.X(i).toFixed(1)},${G.YP(G.pv[i]).toFixed(1)} `;
    up+=(G.pv[i]>=0?c:`${G.X(i).toFixed(1)},${zP} `); dn+=(G.pv[i]<0?c:`${G.X(i).toFixed(1)},${zP} `);}
  const pl=S.pnl.map((x,i)=>G.X(i).toFixed(1)+','+G.YP(x==null?0:x).toFixed(1)).join(' ');
  const lastPop=S.pop[n-1];
  const pop=S.pop.map((x,i)=>x==null?null:G.X(i).toFixed(1)+','+G.YQ(x).toFixed(1)).filter(Boolean).join(' ');
  return `<svg id="msvg" class="spark" width="${w}" height="${h}" viewBox="0 0 ${w} ${h}" style="cursor:crosshair;max-width:100%">
    <defs>
     <linearGradient id="mup" x1="0" y1="0" x2="0" y2="1"><stop offset="0" stop-color="var(--good)" stop-opacity=".4"/><stop offset="1" stop-color="var(--good)" stop-opacity=".03"/></linearGradient>
     <linearGradient id="mdn" x1="0" y1="1" x2="0" y2="0"><stop offset="0" stop-color="var(--crit)" stop-opacity=".4"/><stop offset="1" stop-color="var(--crit)" stop-opacity=".03"/></linearGradient>
    </defs>
    <text x="0" y="10" fill="var(--mut)" font-size="10" font-weight="700">P&amp;L $</text>
    <line x1="${G.ml}" y1="${zP}" x2="${w-G.mr}" y2="${zP}" stroke="var(--line)" stroke-width="1.4"/>
    <polygon points="${G.X(0)},${zP} ${up}${G.X(n-1)},${zP}" fill="url(#mup)"/>
    <polygon points="${G.X(0)},${zP} ${dn}${G.X(n-1)},${zP}" fill="url(#mdn)"/>
    <polyline points="${pl}" fill="none" stroke="var(--blue)" stroke-width="2.4" stroke-linejoin="round"/>
    <text x="2" y="${+zP+3}" fill="var(--mut)" font-size="9">$0</text>
    <text x="${w-G.mr+5}" y="${G.YP(last)+4}" fill="${last>=0?'var(--good)':'var(--crit)'}" font-size="12" font-weight="700">${fmt(last)}</text>
    <text x="0" y="${G.oy+9}" fill="var(--mut)" font-size="10" font-weight="700">POP %</text>
    <line x1="${G.ml}" y1="${G.YQ(0).toFixed(1)}" x2="${w-G.mr}" y2="${G.YQ(0).toFixed(1)}" stroke="var(--line)" stroke-width="1"/>
    <line x1="${G.ml}" y1="${G.YQ(50).toFixed(1)}" x2="${w-G.mr}" y2="${G.YQ(50).toFixed(1)}" stroke="var(--line)" stroke-width=".6" stroke-dasharray="3 4"/>
    <polyline points="${pop}" fill="none" stroke="var(--good)" stroke-width="2.4" stroke-linejoin="round"/>
    <text x="${w-G.mr+5}" y="${G.YQ(lastPop==null?0:lastPop)+4}" fill="var(--good)" font-size="12" font-weight="700">${lastPop==null?'—':lastPop+'%'}</text>
    <text x="${G.ml}" y="${h-1}" fill="var(--mut)" font-size="9">${S.t[0]}</text>
    <text x="${w-G.mr}" y="${h-1}" fill="var(--mut)" font-size="9" text-anchor="end">${S.t[n-1]}</text>
    <line id="mcx" x1="0" y1="0" x2="0" y2="${h}" stroke="var(--ink)" stroke-width="1" stroke-dasharray="3 3" opacity="0"/>
    <circle id="mcd1" r="4.5" fill="var(--blue)" stroke="var(--bg)" stroke-width="1.5" opacity="0"/>
    <circle id="mcd2" r="4.5" fill="var(--good)" stroke="var(--bg)" stroke-width="1.5" opacity="0"/>
    <g id="mtt" opacity="0">
      <rect id="mttb" width="112" height="52" rx="7" fill="var(--card)" stroke="var(--line)"/>
      <text id="mtt0" x="10" y="17" fill="var(--ink)" font-size="11.5" font-weight="700"></text>
      <text id="mtt1" x="10" y="33" fill="var(--blue)" font-size="11.5" font-weight="700"></text>
      <text id="mtt2" x="10" y="47" fill="var(--good)" font-size="11.5" font-weight="700"></text>
    </g>
  </svg>`;
}
function wireMetricsHover(t){
  const svg=document.getElementById('msvg');
  if(!svg || !t.series || t.series.pnl.length<2) return;
  const S=t.series, G=mgeom(S);
  const cx=document.getElementById('mcx'), d1=document.getElementById('mcd1'), d2=document.getElementById('mcd2'),
        tt=document.getElementById('mtt'), l0=document.getElementById('mtt0'),
        l1=document.getElementById('mtt1'), l2=document.getElementById('mtt2');
  const setOp=o=>[cx,d1,d2,tt].forEach(e=>e.setAttribute('opacity',o));
  svg.addEventListener('mousemove', e=>{
    const r=svg.getBoundingClientRect();           // back face renders un-mirrored → 1:1 map
    const lx=(e.clientX-r.left)*(MW/r.width);
    let i=Math.round((lx-G.ml)/(MW-G.ml-G.mr)*(G.n-1));
    i=Math.max(0, Math.min(G.n-1, i));
    const x=G.X(i), py=G.YP(G.pv[i]), qy=(S.pop[i]==null?G.oy:G.YQ(S.pop[i]));
    cx.setAttribute('x1',x); cx.setAttribute('x2',x);
    d1.setAttribute('cx',x); d1.setAttribute('cy',py);
    d2.setAttribute('cx',x); d2.setAttribute('cy',qy);
    l0.textContent=S.t[i];
    l1.textContent='P&L '+fmt(S.pnl[i]);
    l2.textContent='POP '+(S.pop[i]==null?'—':S.pop[i]+'%');
    let tx=x+13; if(tx+112>MW-2) tx=x-13-112; if(tx<2) tx=2;
    tt.setAttribute('transform',`translate(${tx},6)`);
    setOp(1);
  });
  svg.addEventListener('mouseleave', ()=>setOp(0));
}

function tile(t,i){
  const pc = t.pnl==null?'':(t.pnl>=0?'pos':'neg');
  const gc = GC[t.grade[0]]||'#777';
  return `<div class="tile" style="--gc:${gc}" onclick="openCard(${i})">
    <div class="trow"><div><div class="strat">${t.name}</div><div class="exp">Exp ${t.exp||'—'}</div></div>
      <span class="chip" style="background:${gc}">${t.grade}</span></div>
    <div class="staterow"><span class="dot ${t.state=='OPEN'?'open':'closed'}"></span>${t.state}
      ${t.state=='OPEN'?'· RUNNING':''} &nbsp;·&nbsp; POP ${t.pop==null?'—':t.pop+'%'}</div>
    <div class="pnl ${pc}">${fmt(t.pnl)}</div>
    <div class="sub">${t.structure}</div>
    ${payoffSVG(t, 272, 74, true)}</div>`;
}

function expAtSpot(t){
  // the payoff curve's value at TODAY'S spot — makes running-PnL vs expiry-payoff explicit
  if(!t.payoff || t.spot==null || t.state!='OPEN') return '';
  const s=t.payoff.s, v=t.payoff.v;
  if(t.spot<s[0]||t.spot>s[s.length-1]) return '';
  let i=1; while(i<s.length-1 && s[i]<t.spot) i++;
  const w=(t.spot-s[i-1])/(s[i]-s[i-1]), val=v[i-1]+w*(v[i]-v[i-1]);
  const cls=val>=0?'pos':'neg';
  return `<div class="mut" style="margin:-4px 0 6px;font-size:13px">if it expired at spot ${t.spot}: `+
         `<b class="${cls}">${fmt(Math.round(val))}</b> — the difference vs running is remaining time value</div>`;
}

function gauge(t){
  if(t.maxl==null||t.maxg==null||t.pnl==null||t.maxg==t.maxl) return '';
  const p=Math.max(0,Math.min(1,(t.pnl-t.maxl)/(t.maxg-t.maxl)));
  return `<div class="gauge"><i style="left:calc(${(p*100).toFixed(1)}% - 2px)"></i></div>
    <div class="glabel"><span>max loss ${fmtu(t.maxl)}</span><span>P&L position</span><span>max gain ${fmtu(t.maxg)}</span></div>`;
}

// Manual close. The page NEVER places an order itself — it posts a request and
// the trigger daemon (the one process holding the IB connection) executes it on
// its next poll (~3s). Single writer of orders, by design.
function closeBtn(t){
  if(t.state!='OPEN') return '';
  return `<div style="margin:14px 0 4px">
    <button id="cb_${t.id}" onclick="reqClose(event,'${t.id}')"
      style="background:#c0392b;color:#fff;border:0;border-radius:10px;padding:11px 20px;
             font:600 15px system-ui;cursor:pointer">✕ CLOSE THIS TRADE</button>
    <span id="cs_${t.id}" class="mut" style="margin-left:12px;font-size:13px"></span></div>`;
}
async function reqClose(e,id){
  e.stopPropagation();
  const btn=document.getElementById('cb_'+id), st=document.getElementById('cs_'+id);
  if(!confirm('Close '+id+' at market now?')) return;
  btn.disabled=true; btn.style.opacity=.5; st.textContent='sending…';
  try{
    const r=await fetch('/close',{method:'POST',headers:{'Content-Type':'application/json'},
                                  body:JSON.stringify({trade_id:id})});
    const j=await r.json();
    st.textContent = r.ok ? 'queued — daemon closes it within ~3s' : ('failed: '+(j.error||r.status));
    if(!r.ok){ btn.disabled=false; btn.style.opacity=1; }
  }catch(err){ st.textContent='failed: '+err; btn.disabled=false; btn.style.opacity=1; }
}
function openCard(i){
  const t=T[i], big=$('#big'), gc=GC[t.grade[0]]||'#777', g=t.greeks;
  big.classList.remove('flip');
  const legchips=t.legs.map(l=>`<span class="legchip ${l[0]=='S'?'sell':'buy'}">${l}</span>`).join('');
  $('#inner').innerHTML = `
   <div class="face" style="--gc:${gc}">
     <div class="trow"><div><h2>${t.name}</h2><div class="mut">Exp ${t.exp} · ${t.structure} · ${t.state}</div></div>
       <span class="chip" style="background:${gc};font-size:18px">${t.grade}</span></div>
     <div class="pnl ${t.pnl>=0?'pos':'neg'}" style="font-size:40px">${fmt(t.pnl)}
       <span class="mut" style="font-size:13px;font-weight:400">${t.state=='OPEN'?'running (mark-to-market now — includes time value)':'final'}</span></div>
     ${expAtSpot(t)}
     ${gauge(t)}
     ${payoffSVG(t, 900, 340, false)}
     ${closeBtn(t)}
     <div class="hint">click to flip for details ⟲</div></div>
   <div class="face back" style="--gc:${gc}">
     <div class="trow"><div><h2>${t.name} — details</h2>
       <div class="mut">${t.id} · entered ${t.entry} (${t.dow}) · VIX ${t.vix??'—'}</div></div>
       <span class="chip" style="background:${gc};font-size:16px">${t.grade}</span></div>
     <div class="legchips">${legchips}</div>
     <div class="kv">
       <div style="--kc:var(--blue)"><b>NET ${t.credit>=0?'CREDIT':'DEBIT'}</b><span style="color:var(--blue)">${Math.abs(t.credit??0).toFixed(2)}</span></div>
       <div style="--kc:var(--vio)"><b>COLLATERAL</b><span style="color:var(--vio)">${fmtu(t.collateral)}</span></div>
       <div style="--kc:var(--blue)"><b>POP @ ENTRY</b><span style="color:var(--blue)">${t.pop==null?'—':t.pop+'%'}</span></div>
       <div style="--kc:var(--good)"><b>MAX GAIN</b><span style="color:var(--good)">${t.maxg==null?'unbounded':fmtu(t.maxg)}</span></div>
       <div style="--kc:var(--crit)"><b>MAX LOSS</b><span style="color:var(--crit)">${fmtu(t.maxl)}</span></div>
       <div style="--kc:var(--warn)"><b>BREAKEVENS</b><span style="color:var(--warn)">${t.breakevens.length?t.breakevens.join(' / '):'—'}</span></div>
       <div style="--kc:${g&&g.delta>=0?'var(--good)':'var(--crit)'}"><b>DELTA (est)</b><span>${g?g.delta:'—'}</span></div>
       <div style="--kc:${g&&g.theta>=0?'var(--good)':'var(--crit)'}"><b>THETA/DAY (est)</b><span style="color:${g&&g.theta>=0?'var(--good)':'var(--crit)'}">${g?fmt(g.theta):'—'}</span></div>
       <div style="--kc:${g&&g.vega>=0?'var(--good)':'var(--crit)'}"><b>VEGA (est)</b><span>${g?fmt(g.vega):'—'}</span></div></div>
     <div class="sechead" style="margin-top:10px">Live metrics over the trade's life · hover to read any point<span class="cnt">${t.series?t.series.pnl.length+' pts':'—'}</span></div>
     ${metricsSVG(t)}
     <div class="comm"><b>Why this trade:</b> ${t.commentary||'<i>none recorded</i>'}</div>
     <div class="hint">P&L/POP series from the marker (every ~2 min) · greeks = BS est. from entry VIX · Esc closes</div></div>`;
  wireMetricsHover(t);
  $('#ovl').classList.add('on');
}
$('#big').addEventListener('click', e=>{e.stopPropagation();$('#big').classList.toggle('flip');});
$('#ovl').addEventListener('click', ()=>$('#ovl').classList.remove('on'));
document.addEventListener('keydown', e=>{if(e.key=='Escape')$('#ovl').classList.remove('on');});
const TODAY = '__TODAY__';  // CT date — closed section shows only today's, resets daily
const openIdx = T.map((t,i)=>[t,i]).filter(([t])=>t.state=='OPEN');
const closedIdx = T.map((t,i)=>[t,i]).filter(([t])=>t.state!='OPEN' && t.exitd==TODAY);
$('#grid_open').innerHTML = openIdx.map(([t,i])=>tile(t,i)).join('');
$('#grid_closed').innerHTML = closedIdx.length ? closedIdx.map(([t,i])=>tile(t,i)).join('')
  : '<div class="sub" style="padding:6px 2px">no trades closed today — see the Calendar tab for history</div>';
$('#oc').textContent = openIdx.length; $('#cc').textContent = closedIdx.length;
if(!openIdx.length){$('#oh').style.display='none';}
</script></body></html>"""


def main():
    trades = tlog.load()
    marks_f = SIM / "marks.csv"
    last_marks = None
    if marks_f.exists():
        mk = pd.read_csv(marks_f)
        if len(mk):
            last_marks = mk.groupby("trade_id").last()
    # per-trade metrics time series for the inline live-metrics card chart
    met_f = SIM / "trade_metrics.csv"
    hist_by_id = {}
    if met_f.exists():
        mt = pd.read_csv(met_f)
        if len(mt):
            hist_by_id = {tid: g for tid, g in mt.groupby("trade_id")}
    spot = latest_spot()
    data = [trade_payload(r, last_marks, spot, hist_by_id.get(r.trade_id))
            for _, r in trades.iloc[::-1].iterrows()]
    today = dt.datetime.now(ZoneInfo("America/Chicago")).strftime("%Y-%m-%d")
    out = SIM / "cards.html"
    out.write_text(HTML.replace("__DATA__", json.dumps(data)).replace("__TODAY__", today),
                   encoding="utf-8")
    print(f"wrote {out} ({len(data)} cards, spot={spot})")
    return out


if __name__ == "__main__":
    main()
