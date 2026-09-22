"""Final BO setup -> full metrics + per-trade JSON for ChartSim.
Setup: RevType=BO, entry time >=11:00 CT, skip gap days (|gap|<0.3%), MARKET entry at
signal-bar close, stop = export stop, fixed 2R target, else EOD. Ticks, $50/pt, $17.5 RT.
Writes bo_setup_index.json (keyed by date) into the ChartSim data dir; PnL is TICK-accurate.
Per trade: [ft, dir(+1/-1), btc, export_stop, pnl$, reason(0=stop,1=2Rtgt,2=eod), exit_bar]
"""
import glob, json
from pathlib import Path
import pandas as pd, numpy as np
from datetime import date as _D

ROOT = Path(r"c:\Users\Admin\myquant"); TICKS = ROOT / "data/ticks_continuous"
OUT = Path(r"c:\Users\Admin\myquant-regime\data\annotations\book_review\bo_setup_index.json")
PT, RT, INF, T = 50.0, 17.5, 10 ** 9, 2.0

b5 = pd.read_parquet(ROOT / "research/scalp_swing/es_5m_rth.parquet")
b5["DateTime"] = pd.to_datetime(b5["DateTime"]); b5["Date"] = b5["DateTime"].dt.date.astype(str)
BARS = {d: {int(k): (o, h, l, c) for k, o, h, l, c in zip(g.sort_values("bar")["bar"], g.Open, g.High, g.Low, g.Close)}
        for d, g in b5.groupby("Date")}
dl = b5.groupby("Date").agg(o=("Open", "first"), c=("Close", "last"), h=("High", "max"), l=("Low", "min")).reset_index()
dl["pclose"] = dl.c.shift(1)
DF = dl.set_index("Date").to_dict("index")

f = [x for x in glob.glob(str(ROOT / "data/signals/*.txt"))
     if "LMTPrice" in open(x, encoding="utf-8").read(400) and "JUN26" in x and "1830" in x][0]
sigs = []
for ln in open(f, encoding="utf-8"):
    p = ln.split()
    if len(p) != 9 or not p[0].isdigit(): continue
    _, rt, dr, dt, tm, bn, btc, stop, lmt = p
    if rt != "BO" or int(tm[:2]) < 11: continue          # BO + skip morning
    dd, mm, yy = dt.split("/"); num = lambda s: round(float(s.replace(",", "")), 2)
    sigs.append(dict(long=dr.lower().startswith("l"), date=f"{yy}-{mm}-{dd}", ft=int(bn) - 1, btc=num(btc), stop=num(stop)))
byday = {}
for s in sigs: byday.setdefault(s["date"], []).append(s)

index = {}; trades = []
for date in sorted(byday):
    tp = TICKS / f"{date}.parquet"; bd = BARS.get(date); df = DF.get(date)
    if not tp.exists() or not bd or df is None: continue
    gap = abs(df["o"] - df["pclose"]) / df["pclose"] * 100 if df["pclose"] else 0
    if gap >= 0.3: continue                              # skip gap days
    t = pd.read_parquet(tp); Pr = t["Price"].to_numpy(float)
    B = (t["DateTime"].dt.hour.to_numpy() * 60 + t["DateTime"].dt.minute.to_numpy() - 510) // 5
    for s in sorted(byday[date], key=lambda x: x["ft"]):
        ft = s["ft"]
        if ft not in bd: continue
        sc = bd[ft][3]; sh = sc - s["btc"]; stop = s["stop"] + sh; long = s["long"]
        live = int(np.searchsorted(B, ft + 1))
        if live >= len(Pr): continue
        ex = Pr[live:]; exB = B[live:]; entry = ex[0]; risk = abs(entry - stop)
        if risk < 0.25: continue
        if long:
            stopm = ex <= stop; tm = ex >= entry + T * risk
        else:
            stopm = ex >= stop; tm = ex <= entry - T * risk
        si = int(np.argmax(stopm)) if stopm.any() else INF; ti = int(np.argmax(tm)) if tm.any() else INF
        if si == INF and ti == INF:
            k = len(ex) - 1; px = ex[-1]; reason = 2
        elif si <= ti:
            k = si; px = stop; reason = 0
        else:
            k = ti; px = entry + T * risk if long else entry - T * risk; reason = 1
        pnl = round(((px - entry) if long else (entry - px)) * PT - RT, 2)
        exit_bar = int(exB[k])
        index.setdefault(date, []).append([ft, 1 if long else -1, s["btc"], s["stop"], pnl, reason, exit_bar])
        trades.append(dict(date=date, usd=pnl, reason=reason))

OUT.write_text(json.dumps(index))
print(f"wrote {OUT}  ({sum(len(v) for v in index.values())} trades, {len(index)} days)")

# --- full metrics ---
us = np.array([t["usd"] for t in trades]); n = len(us)
net = us.sum(); w = us[us > 0]; l = us[us <= 0]; pf = w.sum() / -l.sum()
eq = np.cumsum(us); dd = float((np.maximum.accumulate(eq) - eq).max())
mcl = cl = 0
for x in us:
    cl = cl + 1 if x <= 0 else 0; mcl = max(mcl, cl)
dts = sorted(t["date"] for t in trades); yrs = (_D.fromisoformat(dts[-1]) - _D.fromisoformat(dts[0])).days / 365.25
sd = us.std(ddof=1)
rc = {0: "stop", 1: "2R", 2: "eod"}
from collections import Counter
rcnt = Counter(rc[t["reason"]] for t in trades)
print(f"\n=== FINAL BO SETUP — full metrics (1 ES, $50/pt, $17.5 RT) ===")
print(f"  trades {n}   net ${round(net):,}   $/yr ${round(net/yrs):,}   exp/trade ${round(us.mean(),1)}")
print(f"  PF {round(pf,2)}   win% {round(100*len(w)/n,1)}   avgWin ${round(w.mean(),1)}   avgLoss ${round(l.mean(),1)}   payoff {round(w.mean()/-l.mean(),2)}")
print(f"  maxDD ${round(dd):,}   net/DD {round(net/dd,2)}   Sharpe/trade {round(us.mean()/sd,3)}   Sharpe ann {round((us.mean()/sd)*np.sqrt(n/yrs),2)}")
print(f"  maxConsecLoss {mcl}   best ${round(us.max()):,}   worst ${round(us.min()):,}   exits: {dict(rcnt)}")
print("  by year:", "  ".join(f"{y[2:]}:${round(sum(t['usd'] for t in trades if t['date'][:4]==y)):>6,}" for y in ["2021","2022","2023","2024","2025","2026"]))
