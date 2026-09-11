"""tempo_levels_build.py — reference levels + value areas for the tempo review tool (S116-tempo).

Per trove day, from RTH 2000t bars only (NO overnight data exists in the trove):
  hoy/loy/coy  prior session high/low/close        pmid  prior session mid (H+L)/2
  ood          today's open                        hod/lod  today's high/low
  oow/oom/ooy  open of current ISO-week / month / year (first session's open)
  ib           first-60-min high/low band
  vay          prior SESSION value area  [VAL, POC, VAH]  (70%, 0.25 grid,
               bar volume spread uniformly across the bar's range)
  vaw/vam/vaq/vayr  value area of the prior COMPLETED week / month / quarter / year

Output: tempo/outputs/levels_by_day.json  (loaded by tempo_review.py)
    python tempo/scripts/tempo_levels_build.py
"""
from __future__ import annotations
import json
from collections import defaultdict
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
BARS = ROOT / "tempo" / "outputs" / "bars_2000t_all.parquet"
OUT = ROOT / "tempo" / "outputs" / "levels_by_day.json"
GRID = 0.25


def day_hist(g: pd.DataFrame) -> dict:
    h = defaultdict(float)
    lo = g["low"].to_numpy(); hi = g["high"].to_numpy(); vol = g["vol"].to_numpy()
    for i in range(len(g)):
        n = int(round((hi[i] - lo[i]) / GRID)) + 1
        v = vol[i] / n
        p = lo[i]
        for _ in range(n):
            h[round(p / GRID) * GRID] += v
            p += GRID
    return h


def value_area(hist: dict, frac: float = 0.70):
    if not hist:
        return None
    prices = sorted(hist)
    vols = np.array([hist[p] for p in prices])
    total = vols.sum()
    poc_i = int(vols.argmax())
    lo_i = hi_i = poc_i
    acc = vols[poc_i]
    while acc < frac * total and (lo_i > 0 or hi_i < len(prices) - 1):
        up = vols[hi_i + 1] if hi_i < len(prices) - 1 else -1
        dn = vols[lo_i - 1] if lo_i > 0 else -1
        if up >= dn:
            hi_i += 1; acc += up
        else:
            lo_i -= 1; acc += dn
    return [float(prices[lo_i]), float(prices[poc_i]), float(prices[hi_i])]


def main():
    df = pd.read_parquet(BARS)
    df = df.sort_values(["date", "bar"]).reset_index(drop=True)
    days = df.groupby("date")
    day_ohlc = days.agg(o=("open", "first"), h=("high", "max"),
                        l=("low", "min"), c=("close", "last"))
    dates = list(day_ohlc.index)
    ts = pd.to_datetime(pd.Series(dates, index=dates))
    week = ts.dt.strftime("%G-W%V"); month = ts.dt.strftime("%Y-%m")
    quarter = ts.dt.year.astype(str) + "-Q" + ts.dt.quarter.astype(str)
    year = ts.dt.year.astype(str)

    print("building daily volume profiles...")
    hists = {}
    for d, g in days:
        hists[d] = day_hist(g)

    def agg_va(keys: pd.Series) -> dict:
        by = defaultdict(lambda: defaultdict(float))
        for d in dates:
            for p, v in hists[d].items():
                by[keys[d]][p] += v
        return {k: value_area(h) for k, h in by.items()}

    print("aggregating period profiles...")
    va_by = {"w": agg_va(week), "m": agg_va(month), "q": agg_va(quarter), "y": agg_va(year)}
    key_of = {"w": week, "m": month, "q": quarter, "y": year}
    period_keys = {p: sorted(set(k.values)) for p, k in key_of.items()}

    ib = {}
    for d, g in days:
        f = g[g["session_min"] < 60]
        if len(f):
            ib[d] = [float(f["low"].min()), float(f["high"].max())]

    out = {}
    for i, d in enumerate(dates):
        lv = {"ood": float(day_ohlc.loc[d, "o"]), "hod": float(day_ohlc.loc[d, "h"]),
              "lod": float(day_ohlc.loc[d, "l"])}
        if i > 0:
            p = dates[i - 1]
            lv["hoy"] = float(day_ohlc.loc[p, "h"]); lv["loy"] = float(day_ohlc.loc[p, "l"])
            lv["coy"] = float(day_ohlc.loc[p, "c"])
            lv["pmid"] = round((lv["hoy"] + lv["loy"]) / 2, 2)
            lv["vay"] = value_area(hists[p])
        for per, keys in key_of.items():
            k = keys[d]
            firsts = [dd for dd in dates if keys[dd] == k]
            lv["oo" + {"w": "w", "m": "m", "q": "q", "y": "y"}[per]] = float(day_ohlc.loc[firsts[0], "o"])
            pk = [x for x in period_keys[per] if x < k]
            if pk:
                va = va_by[per].get(pk[-1])
                if va:
                    lv["va" + ("yr" if per == "y" else per)] = va   # 'vay' is the PRIOR-SESSION VA
        if d in ib:
            lv["ib"] = ib[d]
        out[d] = lv

    OUT.write_text(json.dumps(out), encoding="utf-8")
    print(f"levels for {len(out)} days -> {OUT.relative_to(ROOT)} ({OUT.stat().st_size/1e6:.1f} MB)")


if __name__ == "__main__":
    main()
