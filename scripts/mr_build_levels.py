"""Self-computed gamma levels from OptionsDX SPX chains (S73 — the sample-size unlock).

Implements MenthorQ's documented definitions on our own 2010-2023 chains:
  CR   = strike with largest call-side gamma exposure (weight x C_GAMMA)
  PS   = strike with largest put-side gamma exposure
  HVL  = zero-cross / inflection of the cumulative net-GEX curve across strikes
  GEX1..3 = next-largest |net GEX| strikes after CR/PS
  NetGEX  = total net (calls + / puts -)
  1D Max/Min = spot ± K * spot * IV_near_atm * sqrt(1/252)   (K swept later; default 1.0)
  CR0/PS0 = same as CR/PS on the <=1 DTE slice (exists once daily expiries begin, ~2022+)

WEIGHTS: true GEX weights gamma by OPEN INTEREST (not in OptionsDX). Until ORATS OI is
purchased, weight = VOLUME (documented PROXY — flag on every output). Level LOCATIONS
depend on relative concentration, so the proxy is testable: validated against MenthorQ's
live per-strike surface (mq_levels_validate.py) and replaceable in one line.

Output: data/menthorq/levels_computed_SPX.csv
        (date, spot, cr, ps, hvl, gex1..3, net_gex, d1_min, d1_max, cr0, ps0, weight)
Run: .venv/Scripts/python.exe scripts/mr_build_levels.py [--from 2021-01]
"""
import glob
import sys
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
OPT = ROOT / "data" / "optionsdx"
FROM = sys.argv[sys.argv.index("--from") + 1] if "--from" in sys.argv else "2010-01"

USE = ["QUOTE_DATE", "UNDERLYING_LAST", "EXPIRE_DATE", "DTE", "STRIKE",
       "C_GAMMA", "C_VOLUME", "C_IV", "P_GAMMA", "P_VOLUME", "P_IV"]


def load_file(f):
    hdr = pd.read_csv(f, nrows=0, skipinitialspace=True)
    cols = {c.strip().strip("[]").upper(): c for c in hdr.columns}
    if any(k not in cols for k in USE):
        return None
    df = pd.read_csv(f, usecols=[cols[k] for k in USE], skipinitialspace=True)
    df.columns = [c.strip().strip("[]").upper() for c in df.columns]
    df["QUOTE_DATE"] = df.QUOTE_DATE.astype(str).str.strip()
    for c in USE[1:]:
        if c not in ("QUOTE_DATE", "EXPIRE_DATE"):
            df[c] = pd.to_numeric(df[c], errors="coerce")
    return df


def levels_for_day(day):
    spot = float(day.UNDERLYING_LAST.iloc[0])
    day = day[(day.DTE >= 0) & (day.DTE <= 120)].copy()
    day["cw"] = day.C_VOLUME.fillna(0).clip(lower=0)
    day["pw"] = day.P_VOLUME.fillna(0).clip(lower=0)
    day["cgex"] = day.C_GAMMA.fillna(0) * day.cw
    day["pgex"] = day.P_GAMMA.fillna(0) * day.pw

    def extract(sub, spot_ref=spot):
        if sub.empty:
            return dict(cr=np.nan, ps=np.nan, hvl=np.nan, g1=np.nan, g2=np.nan,
                        g3=np.nan, net=np.nan)
        by = sub.groupby("STRIKE").agg(c=("cgex", "sum"), p=("pgex", "sum"))
        by["net"] = by.c - by.p
        if by.c.max() <= 0 or by.p.max() <= 0:
            return dict(cr=np.nan, ps=np.nan, hvl=np.nan, g1=np.nan, g2=np.nan,
                        g3=np.nan, net=np.nan)
        above = by[by.index >= spot_ref]
        below = by[by.index <= spot_ref]
        if above.empty or below.empty or above.c.max() <= 0 or below.p.max() <= 0:
            return dict(cr=np.nan, ps=np.nan, hvl=np.nan, g1=np.nan, g2=np.nan,
                        g3=np.nan, net=np.nan)
        cr = float(above.c.idxmax())
        ps = float(below.p.idxmax())
        # HVL: zero-cross of cumulative net gex across ascending strikes
        cum = by.net.sort_index().cumsum()
        sc = np.where(np.diff(np.sign(cum.values)) != 0)[0]
        if len(sc):
            cands = cum.index.values[sc + 1].astype(float)
            hvl = float(cands[np.abs(cands - spot_ref).argmin()])  # zero-cross NEAREST spot
        else:
            hvl = np.nan
        rest = by.net.abs().drop(index=[cr, ps], errors="ignore").nlargest(3)
        g = list(rest.index) + [np.nan] * 3
        return dict(cr=cr, ps=ps, hvl=hvl, g1=g[0], g2=g[1], g3=g[2],
                    net=float(by.net.sum()))

    full = extract(day)
    zero = extract(day[day.DTE <= 1])
    # 1D band from nearest-expiry ATM IV
    nz = day[day.DTE >= 1]
    near = nz[nz.DTE == nz.DTE.min()] if len(nz) else day[day.DTE == day.DTE.min()]
    atm = near.iloc[(near.STRIKE - spot).abs().argsort()[:4]]
    iv = np.nanmedian(pd.concat([atm.C_IV, atm.P_IV]))
    move = spot * iv * np.sqrt(1 / 252) if np.isfinite(iv) else np.nan
    return dict(spot=spot, cr=full["cr"], ps=full["ps"], hvl=full["hvl"],
                gex1=full["g1"], gex2=full["g2"], gex3=full["g3"], net_gex=full["net"],
                d1_min=spot - move if np.isfinite(move) else np.nan,
                d1_max=spot + move if np.isfinite(move) else np.nan,
                cr0=zero["cr"], ps0=zero["ps"])


def main():
    rows = []
    files = sorted(glob.glob(str(OPT / "*.txt")))
    files = [f for f in files if Path(f).stem.split("_")[-1] >= FROM.replace("-", "")[:6]]
    print(f"{len(files)} monthly files from {FROM}")
    for f in files:
        df = load_file(f)
        if df is None:
            print(f"  skip {Path(f).name} (missing cols)")
            continue
        for d, day in df.groupby("QUOTE_DATE"):
            try:
                r = levels_for_day(day)
                r["date"] = d
                rows.append(r)
            except Exception as e:
                print(f"  {d}: {e}")
        print(f"  {Path(f).name}: cum {len(rows)} days", flush=True)
    out = pd.DataFrame(rows)
    out["weight"] = "volume_proxy"
    cols = ["date", "spot", "cr", "ps", "hvl", "gex1", "gex2", "gex3",
            "net_gex", "d1_min", "d1_max", "cr0", "ps0", "weight"]
    out[cols].to_csv(ROOT / "data" / "menthorq" / "levels_computed_SPX.csv", index=False)
    print(f"\nwrote {len(out)} daily level rows -> levels_computed_SPX.csv")


if __name__ == "__main__":
    main()
