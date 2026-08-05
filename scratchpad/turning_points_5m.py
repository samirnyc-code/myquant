"""Turning-point flow study on 5-MINUTE RTH bars (7/13-7/17), exploratory/in-sample.
5M footprint reconstructed by summing per-price bid/ask cells (ES_footprint.csv) into
5-min time bins -> true 5M POC/VA/delta/CVD/imbalance (not just resampled OHLC)."""
import numpy as np
import pandas as pd
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.patches import Rectangle

ROOT = r"c:\Users\Admin\myquant"
TICK = 0.25
W = 4                       # 5M swing window (+/-20 min)
RTH0, RTH1 = "08:30", "15:00"

fp = pd.read_csv(ROOT + r"\data\footprint\ES_footprint.csv", parse_dates=["BarTime"])
fp = fp.drop_duplicates(subset=["BarIdx", "BarTime", "Price"], keep="last")
bars = pd.read_csv(ROOT + r"\data\footprint\ES_bars.csv", parse_dates=["BarTime"])
mq = pd.read_csv(ROOT + r"\data\menthorq\ES1!_mq_levels_history.csv")
LKEYS = ["cr", "ps", "hvl", "hvl0", "cr0", "ps0", "gw0", "gex_1", "gex_2", "gex_3", "gex_4", "gex_5"]
def mq_levels(day):
    r = mq[mq.session_date == day]
    if not len(r): return []
    r = r.iloc[0]
    return sorted({float(r[k]) for k in LKEYS if pd.notna(r.get(k))})

fp["t5"] = fp.BarTime.dt.floor("5min")
bars["t5"] = bars.BarTime.dt.floor("5min")

def stacked_imb(ladder):
    """max run of consecutive diagonal buy/sell imbalances (3x) on a 5M ladder."""
    l = ladder.sort_index()          # price asc
    P = l.index.to_numpy(); bid = l.BidVol.to_numpy(); ask = l.AskVol.to_numpy()
    buy_run = sell_run = mb = ms = 0
    for k in range(len(P) - 1):
        # ask at price vs bid at price+1tick (diagonal)
        if ask[k + 1] >= 3 * max(bid[k], 1): buy_run += 1; mb = max(mb, buy_run)
        else: buy_run = 0
        if bid[k] >= 3 * max(ask[k + 1], 1): sell_run += 1; ms = max(ms, sell_run)
        else: sell_run = 0
    return max(mb, ms)

def value_area(hist, pct=0.70):
    h = hist.sort_index(); pr = h.index.to_numpy(); v = h.to_numpy(float)
    ip = int(v.argmax()); need = v.sum() * pct; lo = hi = ip; acc = v[ip]
    while acc < need and (lo > 0 or hi < len(v) - 1):
        up = v[hi + 1] if hi < len(v) - 1 else -1
        dn = v[lo - 1] if lo > 0 else -1
        if up >= dn: hi += 1; acc += v[hi]
        else: lo -= 1; acc += v[lo]
    return pr[ip], pr[hi], pr[lo]

# ---- build 5M bars per day ----
allrows = []
for day, fpd in fp.groupby(fp.BarTime.dt.strftime("%Y-%m-%d")):
    bd = bars[bars.BarTime.dt.strftime("%Y-%m-%d") == day]
    recs = []
    for t5, g in fpd.groupby("t5"):
        if not (RTH0 <= t5.strftime("%H:%M") < RTH1): continue
        lad = g.groupby("Price")[["BidVol", "AskVol"]].sum()
        b5 = bd[bd.t5 == t5]
        if not len(b5): continue
        delta = int((lad.AskVol - lad.BidVol).sum())
        vol = int((lad.AskVol + lad.BidVol).sum())
        poc, vah, val = value_area((lad.BidVol + lad.AskVol))
        recs.append(dict(day=day, t5=t5, Open=b5.Open.iloc[0], Close=b5.Close.iloc[-1],
                         High=b5.High.max(), Low=b5.Low.min(), delta=delta, vol=vol,
                         poc=poc, vah=vah, val=val, simb=stacked_imb(lad),
                         unf=int((b5.UnfHigh > 0).any() or (b5.UnfLow > 0).any())))
    d = pd.DataFrame(recs).sort_values("t5").reset_index(drop=True)
    d["cvd"] = d.delta.cumsum()
    allrows.append(d)
D = pd.concat(allrows, ignore_index=True)
print(f"5M RTH bars: {len(D)} across {D.day.nunique()} days ({D.groupby('day').size().to_dict()})")

# ---- swings + signatures ----
rows = []; control = []
for day, g in D.groupby("day"):
    g = g.reset_index(drop=True); n = len(g)
    hi, lo, delta = g.High.values, g.Low.values, g.delta.values
    lv = mq_levels(day); sw = set()
    for i in range(W, n - W):
        is_h = hi[i] == hi[i-W:i+W+1].max() and hi[i] > hi[i-W:i].max()
        is_l = lo[i] == lo[i-W:i+W+1].min() and lo[i] < lo[i-W:i].min()
        if not (is_h or is_l): continue
        sw.add(i); a0 = max(i-W, 0)
        appr = delta[a0:i+1].sum()
        prog = max(abs((hi[i]-g.Low[a0]) if is_h else (g.High[a0]-lo[i])), TICK)
        cwin = g.cvd.values[a0:i+1]
        cvd_div = (g.cvd[i] < cwin.max()-1e-9) if is_h else (g.cvd[i] > cwin.min()+1e-9)
        px = hi[i] if is_h else lo[i]
        dist = min((abs(px-L) for L in lv), default=np.nan)/TICK
        rows.append(dict(day=day, i=i, kind="HIGH" if is_h else "LOW", price=px,
                         turn_delta=delta[i], approach_delta=appr, absorption=abs(appr)/prog,
                         cvd_div=int(cvd_div), simb=g.simb[i], unf=g.unf[i], dist_mq_ticks=dist))
    for i in range(W, n-W):
        if i in sw: continue
        a0 = max(i-W, 0); appr = delta[a0:i+1].sum()
        prog = max(abs(g.High[i]-g.Low[a0]), TICK)
        control.append(dict(absorption=abs(appr)/prog, simb=g.simb[i], unf=g.unf[i]))
R = pd.DataFrame(rows); C = pd.DataFrame(control)
print(f"swings {len(R)} (H {sum(R.kind=='HIGH')}/L {sum(R.kind=='LOW')}) | controls {len(C)}\n")
print("=== 5M signature means: swings vs control ===")
print(pd.DataFrame({
    "swing_HIGH": R[R.kind=="HIGH"][["absorption","simb","unf"]].mean(),
    "swing_LOW":  R[R.kind=="LOW"][["absorption","simb","unf"]].mean(),
    "control":    C[["absorption","simb","unf"]].mean()}).round(2).to_string())
print(f"\nCVD divergence at swings: {R.cvd_div.mean()*100:.0f}% (H {R[R.kind=='HIGH'].cvd_div.mean()*100:.0f}% / L {R[R.kind=='LOW'].cvd_div.mean()*100:.0f}%)")
print(f"swings within 8t (~2pt) of MQ level: {(R.dist_mq_ticks<=8).mean()*100:.0f}% (median {R.dist_mq_ticks.median():.0f}t)")
print(f"stacked-imbalance>=3 at swings vs control: {(R.simb>=3).mean()*100:.0f}% vs {(C.simb>=3).mean()*100:.0f}%")

# ---- per-day panel chart ----
days = sorted(D.day.unique())
fig, axes = plt.subplots(len(days), 1, figsize=(20, 3.4*len(days)), squeeze=False)
UP, DN = "#2e9e4f", "#d64545"
for ax, day in zip(axes[:, 0], days):
    g = D[D.day == day].reset_index(drop=True); g["x"] = np.arange(len(g))
    for _, r in g.iterrows():
        c = UP if r.Close >= r.Open else DN
        ax.plot([r.x, r.x], [r.Low, r.High], color=c, lw=1.0, zorder=2)
        l, h = sorted([r.Open, r.Close])
        ax.add_patch(Rectangle((r.x-0.34, l), 0.68, max(h-l, .05), facecolor=c, edgecolor=c, lw=.5, zorder=3))
    for L in mq_levels(day):
        if g.Low.min()-2 <= L <= g.High.max()+2:
            ax.axhline(L, color="#9a7", lw=0.7, ls="--", alpha=.6, zorder=1)
    sd = R[R.day == day]
    for _, s in sd.iterrows():
        col = "#b02020" if s.kind == "HIGH" else "#0e7a3b"
        y = g.High[s.i]+1.4 if s.kind == "HIGH" else g.Low[s.i]-1.4
        ax.scatter([s.i], [y], marker="v" if s.kind == "HIGH" else "^", s=80, color=col,
                   edgecolor="black", lw=.5, zorder=6)
        tag = ("A" if s.cvd_div else "")+("I" if s.simb >= 3 else "")+("U" if s.unf else "")
        if tag: ax.text(s.i, y+(1.8 if s.kind == "HIGH" else -1.8), tag, ha="center",
                        fontsize=8, fontweight="bold", color=col)
    ax.set_title(f"ES {day} — 5M RTH turning points  (▲low ▼high · A=CVD div · I=stacked imb≥3 · U=unfinished)",
                 fontsize=11)
    ax.grid(alpha=.15)
    tk = g.x[:: max(len(g)//10, 1)]
    ax.set_xticks(tk); ax.set_xticklabels(g.t5.dt.strftime("%H:%M")[:: max(len(g)//10, 1)], fontsize=8)
fig.tight_layout()
out = ROOT + r"\scratchpad\turning_points_5m.png"
fig.savefig(out, dpi=105, bbox_inches="tight")
print("\nsaved", out)
