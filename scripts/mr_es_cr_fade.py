"""Candidate edge test (S73): FADE Call Resistance on negative-GEX mornings.

From v2: CR touches on neg-GEX days before ~10:30 CT reject ~80%. Test it as a
real trade with defined risk and costs, vs controls:
  entry  = first CR touch in the session before CUTOFF (CT)
  short  = sell at CR; stop = CR + STOP pts; target = CR - TGT pts
  exits  = stop / target / session close (mark-to-close)
  cost   = FRICTION pts round-trip (comm+slip), ES $50/pt
Compare: neg-GEX-morning  vs  pos-GEX  vs  all-day-all-regime.
Writes data/options_sim/cr_fade.json for the morning report.
"""
import json
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
STOP, TGT, FRICTION = 5.0, 10.0, 1.25   # 2:1 reward:risk, ~$62 friction/RT
CUTOFF = "10:30"


def load():
    lv = pd.read_csv(ROOT / "data" / "menthorq" / "levels_history.csv")
    lv = lv[lv.symbol == "ES"].copy(); lv["date"] = lv.date.astype(str)
    b = pd.read_parquet(ROOT / "data" / "bars" / "_continuous_unadj.parquet")
    b["DateTime"] = pd.to_datetime(b["DateTime"]); b["date"] = b.DateTime.dt.strftime("%Y-%m-%d")
    b["hm"] = b.DateTime.dt.strftime("%H:%M")
    gi = pd.read_csv(ROOT / "data" / "menthorq" / "gex_insights_ES1.csv").sort_values("date")
    gi["date"] = gi.date.astype(str)
    return lv, b, gi


def prior_gex(d, gi):
    p = gi[gi.date < d]
    return p.iloc[-1].gex if len(p) else None


def sim(day, cr, cutoff):
    """first CR touch before cutoff -> short; returns pts P&L (pre-cost) or None."""
    d = day[day.hm <= cutoff]
    H, L = d.High.values, d.Low.values
    ti = next((i for i in range(len(d)) if L[i] - 1.0 <= cr <= H[i] + 1.0), None)
    if ti is None:
        return None
    # walk forward from touch bar (use full session bars)
    fh, fl = day.High.values, day.Low.values
    start = len(d) if len(d) < len(day) else ti + 1
    # find absolute index of touch in full day
    ti_abs = day.index[day.hm <= cutoff][ti] - day.index[0]
    for j in range(ti_abs + 1, len(day)):
        if fh[j] >= cr + STOP:
            return -STOP
        if fl[j] <= cr - TGT:
            return TGT
    return cr - day.Close.values[-1]   # mark to close (short)


def stats(pnls):
    p = np.array(pnls) - FRICTION
    if not len(p):
        return {}
    wins = p[p > 0]
    return {"n": len(p), "win_pct": round((p > 0).mean() * 100, 1),
            "E_pts": round(p.mean(), 2), "E_usd": round(p.mean() * 50),
            "total_usd": round(p.sum() * 50), "avg_win": round(wins.mean(), 1) if len(wins) else 0}


def main():
    lv, bars, gi = load()
    levels = {r.date: r for r in lv.itertuples()}
    days = [d for d in sorted(set(bars.date)) if d in levels]
    buckets = {"neg_morning": [], "pos_morning": [], "all_morning": [], "neg_allday": []}
    for d in days:
        day = bars[bars.date == d].reset_index(drop=True)
        if len(day) < 10 or not np.isfinite(levels[d].cr):
            continue
        cr = levels[d].cr
        g = prior_gex(d, gi)
        pnl_m = sim(day, cr, CUTOFF)
        pnl_all = sim(day, cr, "23:59")
        if pnl_m is not None:
            buckets["all_morning"].append(pnl_m)
            if g is not None and g < 0:
                buckets["neg_morning"].append(pnl_m)
            elif g is not None and g > 0:
                buckets["pos_morning"].append(pnl_m)
        if pnl_all is not None and g is not None and g < 0:
            buckets["neg_allday"].append(pnl_all)
    out = {k: stats(v) for k, v in buckets.items()}
    out["params"] = {"stop": STOP, "tgt": TGT, "friction": FRICTION, "cutoff": CUTOFF}
    (ROOT / "data" / "options_sim" / "cr_fade.json").write_text(json.dumps(out, indent=1))
    print(f"FADE Call Resistance — stop {STOP}pt / target {TGT}pt / friction {FRICTION}pt, ES $50/pt\n")
    for k in ("neg_morning", "pos_morning", "all_morning", "neg_allday"):
        print(f"  {k:14s}: {out[k]}")
    print("\nneg_morning = the candidate edge (short CR touch before 10:30 CT on prior-EOD-negative-GEX days)")


if __name__ == "__main__":
    main()
