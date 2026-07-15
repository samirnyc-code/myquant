"""Cross-market gauntlet (S73): the identical first-touch fade validation on every
market we have levels + repaired bars for. Extends note 0016 §4.4 to a panel.

Per market x level: n, months spread, % positive sweep cells, ref-cell (stop8/tgt10
scaled by ATR ratio to ES? NO — keep points but scale stop/tgt by each market's
median daily range vs ES so the geometry is comparable), OOS split.
Scaling: stops/targets in ES points x (mkt median 5m ATR / ES median 5m ATR),
rounded to the market's tick.

Run: .venv/Scripts/python.exe scripts/panel_gauntlet.py
"""
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
FRIC_ES = 1.25
STOPS = [3, 4, 5, 6, 8, 10]      # ES-point equivalents, scaled per market
TGTS = [6, 8, 10, 12, 15, 20]
MKTS = {"ES": "_continuous_unadj.parquet", "NQ": "_continuous_NQ_unadj.parquet",
        "CL": "_continuous_CL_unadj.parquet", "GC": "_continuous_GC_unadj.parquet",
        "YM": "_continuous_YM_unadj.parquet"}
POINT = {"ES": 50, "NQ": 20, "CL": 1000, "GC": 100, "YM": 5}  # $ per point
LEVELS = [("cr", "res"), ("ps", "sup"), ("cr0", "res"), ("ps0", "sup")]


def load_levels():
    l1 = pd.read_csv(ROOT / "data" / "menthorq" / "levels_history.csv")
    l0 = pd.read_csv(ROOT / "data" / "menthorq" / "levels0_history.csv")
    return l1, l0


def bars_for(sym):
    f = ROOT / "data" / "bars" / MKTS[sym]
    if not f.exists():
        return None
    b = pd.read_parquet(f)
    b["DateTime"] = pd.to_datetime(b["DateTime"])
    b["date"] = b.DateTime.dt.strftime("%Y-%m-%d")
    return b


def day_range_scale(bars_es, bars_m):
    r_es = bars_es.groupby("date").apply(lambda d: d.High.max() - d.Low.min()).median()
    r_m = bars_m.groupby("date").apply(lambda d: d.High.max() - d.Low.min()).median()
    return r_m / r_es


def entries_for(lv_df, sym, bars, col, kind):
    sub = lv_df[lv_df.symbol == sym]
    if col not in sub.columns:
        return []
    levels = {str(r.date): getattr(r, col) for r in sub.itertuples()
              if np.isfinite(getattr(r, col, np.nan))}
    out = []
    for d in sorted(set(bars.date)):
        if d not in levels:
            continue
        day = bars[bars.date == d].reset_index(drop=True)
        if len(day) < 10:
            continue
        lvl = levels[d]
        H, L, Cl = day.High.values, day.Low.values, day.Close.values
        tol = max(1.0 * (lvl / 7500), 0.0005 * lvl)  # scale tolerance to price level
        for i in range(1, len(day)):
            k = max(0, i - 3)
            ok = (np.max(Cl[k:i]) < lvl - tol / 2) if kind == "res" else (np.min(Cl[k:i]) > lvl + tol / 2)
            if ok and (L[i] - tol) <= lvl <= (H[i] + tol):
                out.append((d, day, lvl, i))
                break
    return out


def pnl_for(day, lvl, ti, stop, tgt, kind, fric):
    H, L, Cl = day.High.values, day.Low.values, day.Close.values
    for j in range(ti + 1, len(day)):
        if kind == "res":
            if H[j] >= lvl + stop:
                return -stop - fric
            if L[j] <= lvl - tgt:
                return tgt - fric
        else:
            if L[j] <= lvl - stop:
                return -stop - fric
            if H[j] >= lvl + tgt:
                return tgt - fric
    raw = (lvl - Cl[-1]) if kind == "res" else (Cl[-1] - lvl)
    return raw - fric


def main():
    l1, l0 = load_levels()
    bars_es = bars_for("ES")
    print(f"{'mkt':4s} {'level':6s} {'n':>4s} {'cells+':>7s} {'refE$':>7s} {'win':>5s} "
          f"{'tot$':>9s} {'IS$':>6s} {'OOS$':>6s}  verdict")
    for sym in MKTS:
        bars = bars_for(sym)
        if bars is None:
            print(f"{sym:4s} — no repaired bars")
            continue
        scale = day_range_scale(bars_es, bars) if sym != "ES" else 1.0
        fric = FRIC_ES * scale  # friction scales roughly with range/price
        for col, kind in LEVELS:
            lv_df = l1 if col in ("cr", "ps") else l0
            ents = entries_for(lv_df, sym, bars, col, kind)
            if len(ents) < 10:
                print(f"{sym:4s} {col:6s} {len(ents):4d}  (too few)")
                continue
            pos = 0
            for s in STOPS:
                for t in TGTS:
                    p = np.array([pnl_for(day, lvl, ti, s * scale, t * scale, kind, fric)
                                  for _, day, lvl, ti in ents])
                    pos += p.mean() > 0
            p_ref = np.array([pnl_for(day, lvl, ti, 8 * scale, 10 * scale, kind, fric)
                              for _, day, lvl, ti in ents])
            dates = [d for d, *_ in ents]
            cut = sorted(dates)[int(len(dates) * 0.66)]
            is_p = np.array([pnl_for(day, lvl, ti, 8 * scale, 10 * scale, kind, fric)
                             for d, day, lvl, ti in ents if d <= cut])
            oos_p = np.array([pnl_for(day, lvl, ti, 8 * scale, 10 * scale, kind, fric)
                              for d, day, lvl, ti in ents if d > cut])
            mult = POINT[sym]
            verdict = ("SURVIVES" if pos >= 31 and oos_p.mean() > 0 else
                       "fragile" if pos >= 22 else "REJECT")
            print(f"{sym:4s} {col:6s} {len(ents):4d} {pos:4d}/36 {p_ref.mean() * mult:+7.0f} "
                  f"{(p_ref > 0).mean() * 100:4.0f}% {p_ref.sum() * mult:+9,.0f} "
                  f"{is_p.mean() * mult:+6.0f} {oos_p.mean() * mult:+6.0f}  {verdict}")
    print("\nstops/targets scaled by each market's median daily range vs ES; $ = per-market point value")


if __name__ == "__main__":
    main()
