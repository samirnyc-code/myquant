"""mq_regime_backfill_20260725.py — 19-year daily MQ-style gamma levels + regime
using the CRACKED spec from the S84 reverse-engineering (docs/research_notes/
mq_level_reveng_20260724.md). Replaces the v1 series (gamma_regime_daily_2007_2026.csv,
naive cumulative zero-cross — refuted at 12-14% regime agreement).

Spec (per tradeDate, same-day ORATS EOD chain, gamma zeroed outside [0,0.5]):
  net(K) = sum_{dte>=2} gamma*(callOI-putOI);  value = net*100*spot ($/1-pt move)
  CR  = argmax net(K)                (92.1% exact on 2024+ holdout)
  PS  = argmin net(K), |K/spot-1|<=20%  (87.0%)
  HVL = negative-side strike of net sign-flip nearest spot, 5-pt grid,
        +-25pt window smoothing      (medAE 10pt holdout)
  regime = positive_gamma if spot > HVL else negative_gamma  (96.5% holdout)
0DTE set and GEX1-10 intentionally NOT backfilled (S84 verdict: not trustworthy from EOD).

Sanity gate: on the 2021-09..2026-07 overlap the output must reproduce the synthesis
regime agreement (95.3% +-1pp) or the script FAILS loudly.

Output: data/regime/mq_regime_daily_2007_2026_v2.csv
"""
import datetime as dt
import sys
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parent.parent
COLS = ["tradeDate", "strike", "callOpenInterest", "putOpenInterest", "gamma", "spotPrice"]


def smooth_window_sum(strikes, vals, half):
    cs = np.concatenate([[0.0], np.cumsum(vals)])
    lo = np.searchsorted(strikes, strikes - half, side="left")
    hi = np.searchsorted(strikes, strikes + half, side="right")
    return cs[hi] - cs[lo]


def hvl_flip(strikes, net, spot, half=25.0):
    gridk = np.round(strikes / 5.0) * 5.0
    dfg = pd.DataFrame({"k": gridk, "v": net}).groupby("k")["v"].sum()
    k = dfg.index.to_numpy(float)
    s = smooth_window_sum(k, dfg.to_numpy(float), half)
    sgn = np.sign(s)
    flips = np.where(sgn[:-1] * sgn[1:] < 0)[0]
    if len(flips) == 0:
        return float(k[np.argmin(np.abs(s))]), True
    dist = np.minimum(np.abs(k[flips] - spot), np.abs(k[flips + 1] - spot))
    i = flips[np.argmin(dist)]
    return float(k[i] if s[i] < 0 else k[i + 1]), False


rows = []
for p in sorted((ROOT / "data" / "orats" / "SPX").glob("SPX_*.parquet")):
    df = pd.read_parquet(p, columns=COLS + ["dte"])
    g = df["gamma"].to_numpy(copy=True)
    g[(g < 0) | (g > 0.5) | ~np.isfinite(g)] = 0.0
    df["gamma"] = g
    df = df[df["dte"] >= 2]
    df["net"] = df["gamma"] * (df["callOpenInterest"] - df["putOpenInterest"])
    spots = df.groupby("tradeDate")["spotPrice"].first()
    by = (df.groupby(["tradeDate", "strike"], as_index=False)["net"].sum()
            .sort_values(["tradeDate", "strike"]))
    for d, gd in by.groupby("tradeDate"):
        spot = float(spots[d])
        ks = gd["strike"].to_numpy(float)
        nv = gd["net"].to_numpy(float)
        i_cr = int(np.argmax(nv))
        band = np.abs(ks / spot - 1.0) <= 0.20
        if not band.any():
            continue
        i_ps = int(np.argmin(np.where(band, nv, np.inf)))
        hvl, fb = hvl_flip(ks, nv, spot)
        rows.append(dict(
            date=pd.to_datetime(d).date(), spot=spot,
            cr=ks[i_cr], cr_gex=nv[i_cr] * 100 * spot,
            ps=ks[i_ps], ps_gex=nv[i_ps] * 100 * spot,
            hvl=hvl, hvl_fallback=int(fb),
            net_total_gex=float(nv.sum() * 100 * spot),
            regime="positive_gamma" if spot > hvl else "negative_gamma"))
    print(f"{p.name}: cumulative days={len(rows)}", flush=True)

daily = pd.DataFrame(rows).set_index("date").sort_index()
f_out = ROOT / "data" / "regime" / "mq_regime_daily_2007_2026_v2.csv"
daily.to_csv(f_out)
print(f"days={len(daily)} range={daily.index.min()}..{daily.index.max()}")

# ---- sanity gate vs MQ truth on the overlap
truth = pd.read_csv(ROOT / "data" / "regime" / "mq_reveng" / "mq_truth.csv")
truth["eod_date"] = pd.to_datetime(truth["eod_date"]).dt.date
truth = truth.set_index("eod_date")
j = daily.join(truth[["hvl", "spot_eod"]], how="inner", rsuffix="_mq").dropna(
    subset=["hvl_mq"])
sp = np.where(np.isfinite(j["spot_eod"]), j["spot_eod"], j["spot"])
agree = float((np.sign(sp - j["hvl"]) == np.sign(sp - j["hvl_mq"])).mean())
med = float((j["hvl"] - j["hvl_mq"]).abs().median())
print(f"sanity: overlap n={len(j)} regime agreement={agree*100:.1f}% hvl medAE={med:.0f}pt")
if abs(agree - 0.953) > 0.01:
    print("FAIL: does not reproduce the S84 synthesis regime agreement (95.3% +-1pp)")
    sys.exit(1)
print("PASS: reproduces S84 synthesis within tolerance")
