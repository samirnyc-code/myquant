"""flip_wedge_join.py — do MyWedge signals mark the good climax flips? (S119-tempo)

User: wedge failed-BOs of the prior-day extreme are often the best reversal of the day
— check whether flip trades coinciding with a MyWedge signal did better.

Wedge source: NT8 export data/wedge/wedge_signals_ES_2000t_6mo.csv (2026-02..08 ONLY;
there is NO python wedge detector — MyWedge runs in NT8). Flip trades restricted to
the same window, so n is small; this is a look, not a verdict.

Method:
  - dedup wedge signals to the first of each same-side run (as wedge_climax_confluence)
  - auto-detect the constant hour offset wedge-chart-clock -> trove clock (match bar
    END within 45s AND close within 1.5 pts, offset chosen by max sample hits)
  - map each wedge signal to its bar index in the SAME state>=0-filtered day frames
    the flip sim uses, so indices are comparable to the trades' entry bar `i`
  - flip trade is WEDGE-ALIGNED if a same-direction wedge signal (BL->long, BR->short)
    sits within bars [i-2 .. i]; ANY-side variant also reported
  - tables: aligned vs not; beyond-PD subset; per-side; in $, win%, PF, avgR

    python tempo/scripts/flip_wedge_join.py
"""
from __future__ import annotations
import datetime as dt
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
SRC = ROOT / "tempo" / "outputs" / "flip_bucket_trades_2026-09-12.csv"
ENG = ROOT / "tempo" / "outputs" / "tempo_engine_bars.parquet"
WEDGE = ROOT / "data" / "wedge" / "wedge_signals_ES_2000t_6mo.csv"
OUT = ROOT / "tempo" / "outputs"
PT_USD = 50.0
MATCH_TOL_S, PRICE_TOL = 45.0, 1.5
NEAR = 2          # wedge bar within [i-NEAR .. i]


def stats(t, label):
    pnl = t["pnl"]
    gp = pnl[pnl > 0].sum(); gl = -pnl[pnl < 0].sum()
    return {"group": label, "n": len(t),
            "win%": round(100 * (pnl > 0).mean(), 1) if len(t) else np.nan,
            "PF": round(gp / gl, 2) if gl > 0 else np.inf,
            "tot_pts": round(pnl.sum(), 1),
            "$/trade": round(pnl.mean() * PT_USD, 1) if len(t) else np.nan,
            "avgR": round(t["R"].mean(), 3) if len(t) else np.nan}


def main():
    today = dt.date.today().isoformat()
    df = pd.read_parquet(ENG)
    df = df[df["state"] >= 0].sort_values(["date", "bar"]).reset_index(drop=True)
    df["end_ts"] = pd.to_datetime(df["end"])
    byday = {d: g.reset_index(drop=True) for d, g in df.groupby("date")}

    w = pd.read_csv(WEDGE, parse_dates=["SignalTime"])
    w = w.sort_values(["Date", "BarNum"]).reset_index(drop=True)
    w["run"] = ((w["Signal"] != w["Signal"].shift()) | (w["Date"] != w["Date"].shift())
                | (w["BarNum"].diff() > 3)).cumsum()
    w = w.groupby("run").first().reset_index(drop=True)
    print(f"wedge signals after dedup: {len(w)}  ({w['Date'].min()} .. {w['Date'].max()})")

    best = (None, -1)
    sample = w.sample(min(400, len(w)), random_state=42)
    for off in range(-12, 13):
        hits = 0
        for _, r in sample.iterrows():
            ts = r["SignalTime"] + pd.Timedelta(hours=off)
            g = byday.get(ts.strftime("%Y-%m-%d"))
            if g is None:
                continue
            i = (g["end_ts"] - ts).abs().idxmin()
            if abs((g["end_ts"].iloc[i] - ts).total_seconds()) <= MATCH_TOL_S \
                    and abs(g["close"].iloc[i] - r["Close"]) <= PRICE_TOL:
                hits += 1
        if hits > best[1]:
            best = (off, hits)
    off, hits = best
    print(f"offset detected: {off:+d}h ({hits}/{len(sample)} sample matches)")

    wmap = {}          # (date) -> list of (bar_idx, side)
    unmatched = 0
    for _, r in w.iterrows():
        ts = r["SignalTime"] + pd.Timedelta(hours=off)
        date = ts.strftime("%Y-%m-%d")
        g = byday.get(date)
        if g is None:
            unmatched += 1
            continue
        i = (g["end_ts"] - ts).abs().idxmin()
        if abs((g["end_ts"].iloc[i] - ts).total_seconds()) > MATCH_TOL_S \
                or abs(g["close"].iloc[i] - r["Close"]) > PRICE_TOL:
            unmatched += 1
            continue
        wmap.setdefault(date, []).append((int(i), "long" if r["Signal"] == "BL" else "short"))
    print(f"mapped wedge signals: {sum(len(v) for v in wmap.values())}  unmatched: {unmatched}")

    t = pd.read_csv(SRC)
    lo, hi = w["Date"].min(), w["Date"].max()
    t = t[(t["date"] >= lo) & (t["date"] <= hi)].copy()
    print(f"flip trades in wedge window: {len(t)}")

    def near(r, same_side):
        for j, s in wmap.get(r["date"], []):
            if r["i"] - NEAR <= j <= r["i"] and (not same_side or s == r["side"]):
                return True
        return False

    t["wedge_same"] = t.apply(lambda r: near(r, True), axis=1)
    t["wedge_any"] = t.apply(lambda r: near(r, False), axis=1)

    rows = [stats(t, "all flips in window"),
            stats(t[t["wedge_same"]], "wedge SAME-side within 2 bars"),
            stats(t[~t["wedge_same"]], "no same-side wedge"),
            stats(t[t["wedge_any"]], "wedge ANY-side within 2 bars"),
            stats(t[t["beyond_pd"] & t["wedge_same"]], "beyond-PD + same-side wedge"),
            stats(t[t["beyond_pd"] & ~t["wedge_same"]], "beyond-PD, no wedge"),
            stats(t[~t["beyond_pd"] & t["wedge_same"]], "inside-PD + same-side wedge"),
            stats(t[~t["beyond_pd"] & ~t["wedge_same"]], "inside-PD, no wedge")]
    for side in ("long", "short"):
        s = t[t["side"] == side]
        rows += [stats(s[s["wedge_same"]], f"{side} + same-side wedge"),
                 stats(s[~s["wedge_same"]], f"{side}, no wedge")]
    res = pd.DataFrame(rows)
    res.to_csv(OUT / f"flip_wedge_join_{today}.csv", index=False)
    t.to_csv(OUT / f"flip_wedge_trades_{today}.csv", index=False)
    print(res.to_string(index=False))


if __name__ == "__main__":
    main()
