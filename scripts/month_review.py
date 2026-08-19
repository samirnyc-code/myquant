"""month_review.py — is the premium-selling desk consistent, and could we have done
better this PnL month (Aug 6-18, the clean book)? Cross-references the daily GexLog
report (day_type forecast) + the ACTUAL ES move against the day's P&L split by side.

Observational only. Small sample (~9 trading days) — every 'edge' here is a hypothesis,
not a validated rule. Saves a dated per-day CSV.

    python scripts/month_review.py
"""
from __future__ import annotations
import glob, json, os
from pathlib import Path
import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
SIM = ROOT / "data" / "options_sim"
TROVE = ROOT / "data" / "ticks_continuous"
CALL = lambda s: str(s).endswith("_c") or str(s) in ("gx_bcs",)


def es_move(date):
    p = TROVE / f"{date[:4]}-{date[4:6]}-{date[6:]}.parquet"
    if not p.exists():
        return None
    t = pd.read_parquet(p)
    return round(float(t.Price.iloc[-1] - t.Price.iloc[0]), 1)


def day_type(date):
    f = SIM / f"gameplan_{date}.json"
    if not f.exists():
        return None
    return (json.load(open(f)).get("gexlog") or {}).get("day_type")


def main():
    d = pd.read_parquet(ROOT / "data" / "options_log" / "trades.parquet")
    d["e"] = pd.to_datetime(d["entry_dt"], errors="coerce")
    c = d[(d["e"] >= "2026-08-06") & (d["e"] < "2026-08-19") & d.pnl.notna()].copy()
    c["day"] = c["e"].dt.strftime("%Y%m%d")
    c["side"] = c.strategy_id.map(lambda s: "CALL" if CALL(s) else "PUT")

    # ---- daily table ----
    rows = []
    for day, g in c.groupby("day"):
        cp = g[g.side == "CALL"].pnl.sum(); pp = g[g.side == "PUT"].pnl.sum()
        rows.append(dict(day=day, move=es_move(day), forecast=day_type(day),
                         pnl=round(g.pnl.sum()), call=round(cp), put=round(pp), n=len(g)))
    t = pd.DataFrame(rows)

    print("=" * 78)
    print("PER DAY — forecast vs actual move vs P&L (by side)")
    print("=" * 78)
    print(f"{'day':>9} {'fcast':>6} {'ESmove':>7} {'dayP&L':>8} {'CALL$':>7} {'PUT$':>7}  read")
    for _, r in t.iterrows():
        mv = r["move"]
        trend = "big move" if (mv is not None and abs(mv) >= 25) else "quiet"
        read = f"{'DOWN' if (mv or 0)<0 else 'UP'} {trend}"
        print(f"{r['day']:>9} {str(r['forecast']):>6} {mv:>7} {r['pnl']:>+8} {r['call']:>+7} {r['put']:>+7}  {read}")

    # ---- consistency ----
    p = t.pnl.values
    print("\n" + "=" * 78); print("CONSISTENCY"); print("=" * 78)
    print(f"  days: {len(p)} | green {int((p>0).sum())} / red {int((p<0).sum())}  ({100*(p>0).mean():.0f}% green)")
    print(f"  total ${p.sum():,.0f} | mean/day ${p.mean():,.0f} | std ${p.std():,.0f} | best ${p.max():,.0f} | worst ${p.min():,.0f}")
    print(f"  daily Sharpe-ish (mean/std): {p.mean()/p.std():.2f}")
    # outlier dependence: how much of the total is the single best trade / best day
    print(f"  single best trade ${c.pnl.max():,.0f} = {100*c.pnl.max()/c.pnl.sum():.0f}% of month; best day = {100*p.max()/p.sum():.0f}%")

    # ---- side vs direction (is it edge or just directional exposure?) ----
    tv = t.dropna(subset=["move"])
    print("\n" + "=" * 78); print("SIDE vs DIRECTION  (does the market's direction decide the winner?)"); print("=" * 78)
    print(f"  corr(CALL side P&L, ES move): {np.corrcoef(tv.call, tv.move)[0,1]:+.2f}   (negative = calls win when market falls)")
    print(f"  corr(PUT  side P&L, ES move): {np.corrcoef(tv.put,  tv.move)[0,1]:+.2f}   (positive = puts win when market rises)")
    print(f"  corr(day P&L, |ES move|):     {np.corrcoef(tv.pnl, tv.move.abs())[0,1]:+.2f}   (negative = we lose on big-move days)")

    # ---- forecast usefulness ----
    print("\n" + "=" * 78); print("REPORT (day_type) vs REALITY"); print("=" * 78)
    for _, r in tv.iterrows():
        big = abs(r["move"]) >= 25
        verdict = ("MISS: forecast quiet, market trended" if r["forecast"] in ("CHOP", "RANGE") and big
                   else "hit-ish" if (r["forecast"] in ("HIVOL", "TREND")) == big else "ok")
        print(f"  {r['day']}: {str(r['forecast']):6} vs move {r['move']:+.0f} -> {verdict}")

    # ---- hindsight: skip the side that direction was going to punish ----
    print("\n" + "=" * 78); print("HINDSIGHT (overfit! bounded by perfect foresight of direction)"); print("=" * 78)
    # perfect: keep only the side that helped given the actual move
    perfect = sum((r.call if r.move < 0 else 0) + (r.put if r.move > 0 else 0)
                  + (max(r.call, 0) + max(r.put, 0) if r.move == 0 else 0) for _, r in tv.iterrows())
    print(f"  actual month total:                 ${p.sum():,.0f}")
    print(f"  if we'd traded ONLY the with-move side each day (perfect foresight): ${perfect:,.0f}")
    print(f"  => the directional side cost us ~${p.sum()-perfect:,.0f} vs a perfect directional filter")

    out = SIM / "month_review_20260819.csv"
    t.to_csv(out, index=False)
    print(f"\nsaved -> {out.relative_to(ROOT)}")


if __name__ == "__main__":
    main()
