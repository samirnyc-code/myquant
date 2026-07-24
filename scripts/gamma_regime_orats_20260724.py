"""gamma_regime_orats_20260724.py — 19-year daily gamma-regime series from ORATS SPX
per-strike EOD chains, scored against MenthorQ's published levels on the overlap.

Per tradeDate (strikes within ±20% of spot, all expiries, unweighted v1):
  callGEX(K) =  gamma * callOpenInterest   (constant factors dropped — levels unaffected)
  putGEX(K)  = -gamma * putOpenInterest
  CR   = strike with max call GEX at/above spot   (MenthorQ Call Resistance analogue)
  PS   = strike with max |put GEX| at/below spot  (Put Support analogue)
  FLIP = zero-cross of cumulative net GEX (low→high strike) nearest spot (HVL analogue)
  regime = spot above FLIP -> positive_gamma else negative_gamma

Outputs (dated, in data/regime/):
  gamma_regime_daily_2007_2026.csv       full series
  gamma_regime_vs_mq_overlap.csv         per-day comparison vs MQ SPX history
  gamma_regime_vs_mq_20260724.png        overlay chart (opened in VSCode)
"""
import datetime as dt
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "data" / "regime"
OUT.mkdir(exist_ok=True)

COLS = ["tradeDate", "strike", "callOpenInterest", "putOpenInterest", "gamma", "spotPrice"]


def day_levels(by_k: pd.DataFrame, spot: float):
    """by_k: per-strike cgex/pgex sums for ONE tradeDate, strikes ascending."""
    by_k = by_k[(by_k["strike"] >= spot * 0.8) & (by_k["strike"] <= spot * 1.2)]
    if by_k.empty:
        return None
    ks = by_k["strike"].to_numpy()
    net = (by_k["cgex"] - by_k["pgex"]).to_numpy()
    cum = np.cumsum(net)
    # zero-crossings of the cumulative profile; pick the one nearest spot
    sgn = np.sign(cum)
    xi = np.where(np.diff(sgn) != 0)[0]
    flip = float(ks[xi[np.argmin(np.abs(ks[xi] - spot))] + 1]) if len(xi) else np.nan
    above, below = by_k[by_k["strike"] >= spot], by_k[by_k["strike"] <= spot]
    cr = float(above.loc[above["cgex"].idxmax(), "strike"]) if len(above) else np.nan
    ps = float(below.loc[below["pgex"].idxmax(), "strike"]) if len(below) else np.nan
    return dict(spot=float(spot), flip=flip, cr=cr, ps=ps,
                net_total=float(net.sum()),
                regime="positive_gamma" if (not np.isnan(flip) and spot > flip)
                       else "negative_gamma")


rows = []
for p in sorted((ROOT / "data" / "orats" / "SPX").glob("SPX_*.parquet")):
    df = pd.read_parquet(p, columns=COLS)
    df["cgex"] = df["gamma"] * df["callOpenInterest"]
    df["pgex"] = df["gamma"] * df["putOpenInterest"]
    spots = df.groupby("tradeDate")["spotPrice"].first()
    by = (df.groupby(["tradeDate", "strike"], as_index=False)[["cgex", "pgex"]].sum()
            .sort_values(["tradeDate", "strike"]))
    for d, g in by.groupby("tradeDate"):
        r = day_levels(g, float(spots[d]))
        if r:
            r["date"] = pd.to_datetime(d).date()
            rows.append(r)
    print(f"{p.name}: cumulative days={len(rows)}", flush=True)

daily = pd.DataFrame(rows).set_index("date").sort_index()
f_daily = OUT / "gamma_regime_daily_2007_2026.csv"
daily.to_csv(f_daily)

# ---- compare vs MenthorQ on the overlap (their session uses prior EOD = our tradeDate)
mq = pd.read_csv(ROOT / "data" / "menthorq" / "SPX_mq_levels_history.csv")
mq["eod_date"] = pd.to_datetime(mq["eod_date"]).dt.date
mq = mq.drop_duplicates("eod_date", keep="last").set_index("eod_date")
cmp_ = daily.join(mq[["hvl", "cr", "ps", "spot_eod"]], how="inner",
                  lsuffix="_orats", rsuffix="_mq").dropna(subset=["hvl", "flip"])
cmp_["hvl_err"] = cmp_["flip"] - cmp_["hvl"]
cmp_["cr_err"] = cmp_["cr_orats"] - cmp_["cr_mq"]
cmp_["ps_err"] = cmp_["ps_orats"] - cmp_["ps_mq"]
cmp_["regime_mq"] = np.where(cmp_["spot"] > cmp_["hvl"], "positive_gamma", "negative_gamma")
cmp_["regime_agree"] = cmp_["regime"] == cmp_["regime_mq"]
f_cmp = OUT / "gamma_regime_vs_mq_overlap.csv"
cmp_.to_csv(f_cmp)

summ = {}
for name, e in [("HVL_vs_flip", "hvl_err"), ("CR", "cr_err"), ("PS", "ps_err")]:
    v = cmp_[e].dropna()
    summ[name] = dict(n=len(v), median_abs=float(v.abs().median()),
                      mean_abs=float(v.abs().mean()),
                      pct_within_25=float((v.abs() <= 25).mean() * 100),
                      pct_within_50=float((v.abs() <= 50).mean() * 100))
print("\noverlap days:", len(cmp_))
for k, s in summ.items():
    print(f"{k}: n={s['n']} medAE={s['median_abs']:.1f} meanAE={s['mean_abs']:.1f} "
          f"<=25pt {s['pct_within_25']:.0f}% <=50pt {s['pct_within_50']:.0f}%")
agree = float(cmp_["regime_agree"].mean() * 100)
print(f"regime label agreement (spot vs flip/HVL): {agree:.1f}%")
pd.DataFrame(summ).T.assign(regime_agreement_pct=agree).to_csv(
    OUT / "gamma_regime_vs_mq_summary_20260724.csv")

# ---- chart: overlay + error, light surface, validated 2-series palette
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

BLUE, ORANGE, MUT, INK, SURF = "#2a78d6", "#eb6834", "#898781", "#0b0b0b", "#fcfcfb"
fig, (ax, ax2) = plt.subplots(2, 1, figsize=(13, 7.5), sharex=True, dpi=130,
                              gridspec_kw={"height_ratios": [2.4, 1]})
fig.patch.set_facecolor(SURF)
x = pd.to_datetime(cmp_.index)
ax.set_facecolor(SURF)
ax.plot(x, cmp_["flip"], color=BLUE, lw=1.2, label="ORATS computed flip")
ax.plot(x, cmp_["hvl"], color=ORANGE, lw=1.2, label="MenthorQ HVL")
ax.legend(frameon=False, loc="upper left", fontsize=9)
ax.set_title("Gamma flip level — ORATS-computed vs MenthorQ HVL (SPX, overlap)",
             color=INK, fontsize=11, loc="left")
ax2.set_facecolor(SURF)
ax2.plot(x, cmp_["hvl_err"], color=MUT, lw=0.9)
ax2.axhline(0, color=INK, lw=0.6)
ax2.set_ylabel("flip − HVL (pts)", color=INK, fontsize=9)
for a in (ax, ax2):
    for s in a.spines.values():
        s.set_color(MUT)
    a.tick_params(colors=MUT, labelsize=8)
    a.grid(color="#f0efec", lw=0.6)
fig.tight_layout()
f_png = OUT / "gamma_regime_vs_mq_20260724.png"
fig.savefig(f_png, facecolor=SURF)
print("saved:", f_daily, f_cmp, f_png, sep="\n  ")
