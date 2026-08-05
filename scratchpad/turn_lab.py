"""Creative proprietary turn-signature lab (5M RTH, 7/13-7/17, EXPLORATORY).
Engineers named composite features from footprint + MQ levels, each scored vs a
control baseline (lift = swing% / control%). MULTIPLE-TESTING WARNING: ~10 features
on 5 days — survivors are HYPOTHESES to pre-register + test OOS, not edges."""
import numpy as np, pandas as pd
ROOT = r"c:\Users\Admin\myquant"; TICK = 0.25
D = pd.read_csv(ROOT + r"\scratchpad\turn_sig_table.csv", parse_dates=["t5"])
mq = pd.read_csv(ROOT + r"\data\menthorq\ES1!_mq_levels_history.csv")
LK = ["cr","ps","hvl","hvl0","cr0","ps0","gw0","gex_1","gex_2","gex_3","gex_4","gex_5"]
def levels(day):
    r = mq[mq.session_date == day]
    return [float(r.iloc[0][k]) for k in LK if len(r) and pd.notna(r.iloc[0].get(k))]

D = D.sort_values(["day","t5"]).reset_index(drop=True)
D["rng"] = (D.High - D.Low).clip(lower=TICK)
D["close_pos"] = (D.Close - D.Low) / D.rng                      # 0=low .. 1=high
D["wick_up"] = (D.High - D[["Open","Close"]].max(axis=1)) / D.rng
D["wick_dn"] = (D[["Open","Close"]].min(axis=1) - D.Low) / D.rng

# per-day series features
def byday(fn):
    out = []
    for _, g in D.groupby("day"):
        out.append(fn(g.sort_values("t5")))
    return pd.concat(out).sort_index()
D["delta3"]   = byday(lambda g: g.delta.rolling(3, min_periods=1).sum())
D["px_prog3"] = byday(lambda g: (g.Close - g.Close.shift(3)) / TICK)     # net ticks over 3 bars
D["cvd_d1"]   = byday(lambda g: g.cvd.diff())
D["cvd_kink"] = byday(lambda g: g.cvd.diff().diff().abs())               # |2nd diff| = curvature
D["dist_mq"]  = [min((abs((r.High if r.kind=='HIGH' else r.Low if r.kind=='LOW' else r.Close)-L)
                      for L in levels(r.day)), default=np.nan)/TICK for r in D.itertuples()]

# --- named proprietary signatures (each -> 0/1 on every bar) ---
# ERD: 3-bar delta per point of progress, signed AGAINST the move & large
erd = D.delta3.abs() / D.px_prog3.abs().clip(lower=1)
against = ((D.px_prog3 > 0) & (D.delta3 < 0)) | ((D.px_prog3 < 0) & (D.delta3 > 0)) | (D.px_prog3.abs() <= 2)
D["ERD"] = ((erd > erd.quantile(0.70)) & against).astype(int)
# CVD kink: curvature in the top quartile (order-flow momentum turning hard)
D["CVDkink"] = (D.cvd_kink > D.cvd_kink.quantile(0.75)).astype(int)
# Trapped aggressor: strong one-way delta but close rejected to opposite third
strong = D.delta.abs() > D.delta.abs().quantile(0.60)
D["Trapped"] = (strong & (((D.delta > 0) & (D.close_pos < 0.33)) |
                          ((D.delta < 0) & (D.close_pos > 0.67)))).astype(int)
# Wick rejection: rejection tail >50% of range on the side of the extreme (side-aware)
wick = np.where(D.kind == "HIGH", D.wick_up, np.where(D.kind == "LOW", D.wick_dn,
                np.maximum(D.wick_up, D.wick_dn)))
D["WickRej"] = (wick > 0.45).astype(int)
# Exhaustion Pulse: vol climax AND delta extreme AND wick rejection
dbig = D.delta.abs() > D.delta.abs().quantile(0.70)
D["ExhPulse"] = (D.vol_climax.astype(bool) & dbig & (D.WickRej == 1)).astype(int)
# Level-gated divergence: CVD divergence within 2pt of an MQ level
D["LvlDiv"] = ((D.cvd_div_local == 1) & (D.dist_mq <= 8)).astype(int)

feats = ["cvd_div_local", "vol_climax", "ERD", "CVDkink", "Trapped", "WickRej", "ExhPulse", "LvlDiv"]
sw = D[D.kind != "control"]; ct = D[D.kind == "control"]
print(f"bars {len(D)} | swings {len(sw)} | controls {len(ct)}   (5 days — hypothesis generation only)\n")
print(f"{'signature':16s} {'swing%':>7s} {'ctrl%':>7s} {'lift':>6s}   {'HIGH%':>6s} {'LOW%':>6s}")
rows = []
for f in feats:
    s = sw[f].mean()*100; c = ct[f].mean()*100
    rows.append((f, s, c, s/max(c, 1e-9), D[D.kind=="HIGH"][f].mean()*100, D[D.kind=="LOW"][f].mean()*100))
for f, s, c, lift, h, l in sorted(rows, key=lambda x: -x[3]):
    print(f"{f:16s} {s:6.0f}% {c:6.0f}% {lift:5.2f}x   {h:5.0f}% {l:5.0f}%")

# --- proprietary composite "TURN SCORE" (weight the survivors) ---
D["TurnScore"] = (2.0*D.cvd_div_local + 1.2*D.vol_climax + 1.0*D.WickRej +
                  0.8*D.ExhPulse + 0.8*D.LvlDiv + 0.6*D.ERD)
sw = D[D.kind != "control"]; ct = D[D.kind == "control"]   # re-slice after adding TurnScore
print(f"\nTURN SCORE (weighted composite) mean:  swings {sw.TurnScore.mean():.2f}  vs  control {ct.TurnScore.mean():.2f}  "
      f"({sw.TurnScore.mean()/max(ct.TurnScore.mean(),1e-9):.2f}x)")
for thr in [2, 3, 4]:
    prec = (D[D.TurnScore >= thr].kind != "control").mean()*100
    rec = (sw.TurnScore >= thr).mean()*100
    n = (D.TurnScore >= thr).sum()
    print(f"  score>={thr}: fires on {n:3d} bars · {prec:3.0f}% are real turns (precision) · catches {rec:3.0f}% of turns (recall)")
print("\nbase rate of turns among all bars: {:.0f}%".format(len(sw)/len(D)*100))
D.to_csv(ROOT + r"\scratchpad\turn_lab_table.csv", index=False)
