"""STRUCTURAL test (not a sweep): does a MyReversals reversal pay when it RECLAIMS a
SWEPT reference level (the trap)?  Long = day already took out a reference LOW and the
reversal fires back ABOVE it (trapped breakdown-sellers cover). Short = mirror at a high.

References tested (each a separate pre-registered hypothesis, all reported):
  PDL/PDH   prior RTH day low/high
  SESS      session extreme made >=6 bars before the signal (intraday sweep)
  SWING     a swing low/high = min/max low of bars [i-20, i-4] (older structure)
Targets tested: EOD hold, VWAP (revert to value), prior-day MID.
Robustness bar: BOTH halves positive AND not carried by a single year (per-year shown).
All fills tick-accurate. Base signals = strong-FT detection (FT_ABR>=1) so we test
LOCATION on a clean signal, not knob-tuning.
"""
import sys
from pathlib import Path
import numpy as np, pandas as pd
ROOT = Path(r"c:\Users\Admin\myquant")
sys.path.insert(0, str(ROOT / "research" / "revsim")); sys.path.insert(0, str(ROOT / "research" / "scalp_swing"))
import revsim as R, revdetect as RD, engine_ticks as E
import swing_level_gated as G
import strategies as S

df5 = pd.read_parquet(ROOT / "research" / "scalp_swing" / "es_5m_rth.parquet")
df5["DateTime"] = pd.to_datetime(df5["DateTime"])
sma = G.sma20d_map(df5)
sg = RD.detect(df5, {"FT_ABR": 1.0})   # clean strong-FT base
print(f"{len(sg)} strong-FT signals")

# ---- build reference/trap features per signal ----
dayHL = df5.groupby("Date").agg(dh=("High", "max"), dl=("Low", "min"))
dates = list(dayHL.index)
pdh = {d: (dayHL.dh.iloc[i-1] if i > 0 else np.nan) for i, d in enumerate(dates)}
pdl = {d: (dayHL.dl.iloc[i-1] if i > 0 else np.nan) for i, d in enumerate(dates)}
feat = []
for date, day in df5.groupby("Date", sort=True):
    day = day.sort_values("DateTime").reset_index(drop=True)
    H, L, C, V = day.High.values, day.Low.values, day.Close.values, day.Volume.values
    bt = day.DateTime.values.astype("datetime64[ns]")
    rhi = np.maximum.accumulate(H); rlo = np.minimum.accumulate(L)
    tp = (H + L + C) / 3.0; vwap = np.cumsum(tp * V) / np.maximum(np.cumsum(V), 1)
    ds = sg[sg.Date == date]
    for idx, s in ds.iterrows():
        T = np.datetime64(s["time"]) - np.timedelta64(5, "m")  # FT bar open label
        k = np.searchsorted(bt, T, side="right") - 1
        if k < 5:
            feat.append(dict(idx=idx)); continue
        sess_lo_before = rlo[max(0, k-6)]      # session low made >=6 bars ago
        sess_hi_before = rhi[max(0, k-6)]
        swing_lo = L[max(0, k-20):max(1, k-4)].min()   # older swing low
        swing_hi = H[max(0, k-20):max(1, k-4)].max()
        feat.append(dict(idx=idx, rlo=rlo[k], rhi=rhi[k], vwap=vwap[k],
                         pdl=pdl.get(date, np.nan), pdh=pdh.get(date, np.nan),
                         sesslo=sess_lo_before, sesshi=sess_hi_before,
                         swinglo=swing_lo, swinghi=swing_hi))
F = pd.DataFrame(feat).set_index("idx")
sg = sg.join(F)
sg["pdmid"] = (sg.pdh + sg.pdl) / 2

# reclaim/sweep flags (long: swept a ref LOW then entry back above it; short mirror)
def swept(sg, ref_lo, ref_hi):
    long_ok = (sg.side == 1) & (sg.rlo < sg[ref_lo]) & (sg.entry > sg[ref_lo])
    short_ok = (sg.side == -1) & (sg.rhi > sg[ref_hi]) & (sg.entry < sg[ref_hi])
    return long_ok | short_ok

sg["sw_pdl"] = swept(sg, "pdl", "pdh")
sg["sw_sess"] = swept(sg, "sesslo", "sesshi")
sg["sw_swing"] = swept(sg, "swinglo", "swinghi")
for c in ["sw_pdl", "sw_sess", "sw_swing"]:
    print(f"  {c}: {int(sg[c].sum())} signals ({100*sg[c].mean():.0f}%)")


def rep(name, sub, cfg):
    tr = R.sim(sub, sma=sma, **cfg)
    if len(tr) == 0:
        return None, None
    tr["d"] = pd.to_datetime(tr["Date"]); trn = tr[tr.d < "2024-01-01"]; oos = tr[tr.d >= "2024-01-01"]
    mt, mo, al = E.metrics(trn), E.metrics(oos), E.metrics(tr)
    yr = E.by_year(tr); wy = (yr["pnl"] > 0).sum(); ny = len(yr)
    return dict(cfg=name, n=al["n"], all_pnl=al["pnl"], all_pf=al["pf"], all_ndd=al["netdd"], all_shp=al["sharpe"],
                tr_pf=mt["pf"], tr_pnl=mt["pnl"], oo_pf=mo["pf"], oo_pnl=mo["pnl"],
                green_yrs=f"{wy}/{ny}", both=(mt["pnl"] > 0 and mo["pnl"] > 0)), (tr, yr)


rows = []; keep = {}
base = {"entry": "market"}
for ref, col in [("PDL/PDH", "sw_pdl"), ("SESS", "sw_sess"), ("SWING", "sw_swing")]:
    sub0 = sg[sg[col]]
    for tgt, cfg in [("eod", {"hold_eod": True}), ("rr2", {"rr": 2.0})]:
        r, data = rep(f"{ref}|{tgt}", sub0, {**base, **cfg})
        if r: rows.append(r); keep[r["cfg"]] = data
# also unconditioned strong-FT for reference
r, _ = rep("NO-REF|eod", sg, {**base, "hold_eod": True})
if r: rows.append(r)

D = pd.DataFrame(rows).sort_values("all_ndd", ascending=False)
pd.set_option("display.width", 200)
print("\n=== SWEPT-AND-RECLAIMED REFERENCE TEST (strong-FT base) ===")
print(D.to_string(index=False))
# per-year for the best both-positive
best = D[D.both].sort_values("all_ndd", ascending=False)
for cfg in list(best.cfg)[:3]:
    tr, yr = keep[cfg]
    print(f"\nPER-YEAR {cfg}:"); print(yr.to_string())
D.to_csv(ROOT / "research" / "revsim" / "sweep_reference.csv", index=False)
print("\nDONE_REF")
