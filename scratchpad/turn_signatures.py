"""Which order-flow signatures actually DISCRIMINATE 5M turning points from ordinary
bars? (7/13-7/17, exploratory/in-sample). Each candidate is computed on EVERY bar so
we get a real control baseline — the thing the 'unfinished auction' tag was missing.
Recomputes finished/unfinished from the per-price ladder (no NT8 recompile)."""
import numpy as np, pandas as pd
ROOT = r"c:\Users\Admin\myquant"
TICK = 0.25; W = 4; RTH0, RTH1 = "08:30", "15:00"

fp = pd.read_csv(ROOT + r"\data\footprint\ES_footprint.csv", parse_dates=["BarTime"])
fp = fp.drop_duplicates(subset=["BarIdx", "BarTime", "Price"], keep="last")
bars = pd.read_csv(ROOT + r"\data\footprint\ES_bars.csv", parse_dates=["BarTime"])
fp["t5"] = fp.BarTime.dt.floor("5min"); bars["t5"] = bars.BarTime.dt.floor("5min")

# ---- build 5M bars with ladder-derived extras ----
recs = []
for day, fpd in fp.groupby(fp.BarTime.dt.strftime("%Y-%m-%d")):
    bd = bars[bars.BarTime.dt.strftime("%Y-%m-%d") == day]
    for t5, g in fpd.groupby("t5"):
        if not (RTH0 <= t5.strftime("%H:%M") < RTH1): continue
        b5 = bd[bd.t5 == t5]
        if not len(b5): continue
        lad = g.groupby("Price")[["BidVol", "AskVol"]].sum()
        lad = lad.sort_index()
        vol = int((lad.BidVol + lad.AskVol).sum()); delta = int((lad.AskVol - lad.BidVol).sum())
        hi = b5.High.max(); lo = b5.Low.min()
        # extreme-cell minority fraction (finished = one-sided rejection)
        hc = lad.loc[lad.index.max()]; lc = lad.loc[lad.index.min()]
        hi_min = min(hc.BidVol, hc.AskVol) / max(hc.BidVol + hc.AskVol, 1)
        lo_min = min(lc.BidVol, lc.AskVol) / max(lc.BidVol + lc.AskVol, 1)
        poc = (lad.BidVol + lad.AskVol).idxmax()
        recs.append(dict(day=day, t5=t5, Open=b5.Open.iloc[0], Close=b5.Close.iloc[-1],
                         High=hi, Low=lo, delta=delta, vol=vol, poc=poc,
                         hi_minfrac=hi_min, lo_minfrac=lo_min))
D = pd.concat([pd.DataFrame(recs)], ignore_index=True).sort_values(["day", "t5"]).reset_index(drop=True)
D["cvd"] = D.groupby("day").delta.cumsum()

# ---- label each bar: swing-HIGH / swing-LOW / control ----
D["kind"] = "control"
for day, g in D.groupby("day"):
    idx = g.index.to_numpy(); hi = g.High.values; lo = g.Low.values; n = len(g)
    for k in range(W, n - W):
        if hi[k] == hi[k-W:k+W+1].max() and hi[k] > hi[k-W:k].max(): D.loc[idx[k], "kind"] = "HIGH"
        elif lo[k] == lo[k-W:k+W+1].min() and lo[k] < lo[k-W:k].min(): D.loc[idx[k], "kind"] = "LOW"

# ---- candidate signatures on EVERY bar (baseline-able) ----
sig = {}
for day, g in D.groupby("day"):
    g = g.sort_values("t5"); idx = g.index.to_numpy()
    d = g.delta.values; cvd = g.cvd.values; vol = g.vol.values
    hi = g.High.values; lo = g.Low.values; op = g.Open.values; cl = g.Close.values
    for k in range(len(g)):
        i = idx[k]
        prev = d[k-1] if k > 0 else 0
        flip = int(k > 0 and d[k] * prev < 0)
        mism = int((cl[k] > op[k] and d[k] < 0) or (cl[k] < op[k] and d[k] > 0))
        churn = int(abs(d[k]) / max(vol[k], 1) < 0.08)
        # local extreme not confirmed by cvd (computable on all bars = fair baseline)
        a, b = max(k-W, 0), min(k+W+1, len(g))
        isH = hi[k] == hi[a:b].max(); isL = lo[k] == lo[a:b].min()
        cvddiv = int((isH and cvd[k] < cvd[a:b].max()-1e-9) or (isL and cvd[k] > cvd[a:b].min()+1e-9))
        climax = int(vol[k] == vol[a:b].max())
        sig[i] = dict(delta_flip=flip, delta_close_mismatch=mism, churn_absorption=churn,
                      cvd_div_local=cvddiv, vol_climax=climax)
S = pd.DataFrame(sig).T
D = D.join(S)
# finished-rejection at the relevant extreme (kind-specific)
D["finished_rej"] = np.where(D.kind == "HIGH", (D.hi_minfrac < 0.25).astype(int),
                     np.where(D.kind == "LOW", (D.lo_minfrac < 0.25).astype(int), np.nan))

feats = ["delta_flip", "delta_close_mismatch", "churn_absorption", "cvd_div_local", "vol_climax"]
sw = D[D.kind != "control"]; ct = D[D.kind == "control"]
print(f"bars {len(D)} | swings {len(sw)} (H {sum(D.kind=='HIGH')}/L {sum(D.kind=='LOW')}) | controls {len(ct)}\n")
print(f"{'signature':22s} {'swing%':>7s} {'ctrl%':>7s} {'lift':>6s}")
res = []
for f in feats:
    s = sw[f].mean()*100; c = ct[f].mean()*100
    res.append((f, s, c, s/max(c, 1e-9)))
for f, s, c, lift in sorted(res, key=lambda x: -x[3]):
    print(f"{f:22s} {s:6.0f}% {c:6.0f}% {lift:5.2f}x")

# finished-rejection: compare at swings' own extreme vs a random control-bar extreme
fr_sw = D[D.kind != "control"].finished_rej.mean()*100
# control baseline: minority-frac at control bars' high cell (same strict rule)
fr_ct = (D[D.kind == "control"].hi_minfrac < 0.25).mean()*100
print(f"\n{'finished_rejection':22s} {fr_sw:6.0f}% {fr_ct:6.0f}% {fr_sw/max(fr_ct,1e-9):5.2f}x  (strict <25% minority at extreme)")

print("\nsplit by direction (swing-HIGH vs swing-LOW vs control):")
print(f"{'signature':22s} {'HIGH%':>6s} {'LOW%':>6s} {'ctrl%':>6s}")
for f in feats:
    print(f"{f:22s} {D[D.kind=='HIGH'][f].mean()*100:5.0f}% {D[D.kind=='LOW'][f].mean()*100:5.0f}% {ct[f].mean()*100:5.0f}%")
D.to_csv(ROOT + r"\scratchpad\turn_sig_table.csv", index=False)
print("\nsaved per-bar table -> scratchpad/turn_sig_table.csv")

# ---- honest chart: tag ONLY the discriminating signatures (D=CVD div, V=vol climax) ----
import matplotlib; matplotlib.use("Agg"); import matplotlib.pyplot as plt
from matplotlib.patches import Rectangle
mq = pd.read_csv(ROOT + r"\data\menthorq\ES1!_mq_levels_history.csv")
LK = ["cr","ps","hvl","hvl0","cr0","ps0","gw0","gex_1","gex_2","gex_3"]
def mlv(day):
    r = mq[mq.session_date == day]
    if not len(r): return []
    r = r.iloc[0]; return [float(r[k]) for k in LK if pd.notna(r.get(k))]
days = sorted(D.day.unique()); UP, DN = "#2e9e4f", "#d64545"
fig, axes = plt.subplots(len(days), 1, figsize=(20, 3.4*len(days)), squeeze=False)
for ax, day in zip(axes[:,0], days):
    g = D[D.day == day].sort_values("t5").reset_index(drop=True); g["x"] = np.arange(len(g))
    for _, r in g.iterrows():
        c = UP if r.Close >= r.Open else DN
        ax.plot([r.x, r.x],[r.Low, r.High], color=c, lw=1.0, zorder=2)
        l, h = sorted([r.Open, r.Close]); ax.add_patch(Rectangle((r.x-0.34, l), 0.68, max(h-l,.05), facecolor=c, edgecolor=c, lw=.5, zorder=3))
    for L in mlv(day):
        if g.Low.min()-2 <= L <= g.High.max()+2: ax.axhline(L, color="#9a7", lw=.6, ls="--", alpha=.5, zorder=1)
    for _, s in g[g.kind != "control"].iterrows():
        col = "#b02020" if s.kind == "HIGH" else "#0e7a3b"
        y = s.High+1.4 if s.kind == "HIGH" else s.Low-1.4
        ax.scatter([s.x],[y], marker="v" if s.kind == "HIGH" else "^", s=80, color=col, edgecolor="black", lw=.5, zorder=6)
        tag = ("D" if s.cvd_div_local else "")+("V" if s.vol_climax else "")
        if tag: ax.text(s.x, y+(1.9 if s.kind == "HIGH" else -1.9), tag, ha="center", fontsize=9, fontweight="bold", color=col)
    ax.set_title(f"ES {day} — 5M turns · tags: D=CVD divergence (19.9x) · V=volume climax (3.0x) — only discriminating signals shown", fontsize=11)
    ax.grid(alpha=.15); tk = g.x[:: max(len(g)//10, 1)]
    ax.set_xticks(tk); ax.set_xticklabels(g.t5.dt.strftime("%H:%M")[:: max(len(g)//10, 1)], fontsize=8)
fig.tight_layout()
out = ROOT + r"\scratchpad\turn_signatures.png"; fig.savefig(out, dpi=105, bbox_inches="tight")
print("saved chart ->", out)
