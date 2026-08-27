"""eod_scenario.py — where does today's book settle across a ladder of SPX closes?
Answers 'do we end green if it keeps dropping?' by pricing every OPEN 0DTE position
at settlement intrinsic (correct per-right formula) over a spot ladder, adding today's
already-realized P&L. Ignores the trigger daemon's intraday exits — this is the
hold-to-settlement projection. Saves a dated CSV.

    python scripts/eod_scenario.py [--date 2026-08-20] [--lo 7580 --hi 7680 --step 10]
"""
from __future__ import annotations
import argparse, datetime as dt, json
from pathlib import Path
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
SIM = ROOT / "data" / "options_sim"


def intrinsic(leg, S):
    k = float(leg["strike"])
    return max(S - k, 0.0) if leg["right"] == "C" else max(k - S, 0.0)


def settle_pnl(row, S):
    legs = row["legs"] if isinstance(row["legs"], list) else json.loads(row["legs"])
    cost = sum((intrinsic(l, S) if l["side"] == "sell" else -intrinsic(l, S)) for l in legs)
    fee = 2.6 / 100.0  # per-position round-trip approx (per-share)
    return (float(row["credit"]) - max(cost, 0.0) - fee) * 100


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--date", default=dt.date.today().isoformat())
    ap.add_argument("--lo", type=float, default=None)
    ap.add_argument("--hi", type=float, default=None)
    ap.add_argument("--step", type=float, default=10)
    a = ap.parse_args()

    d = pd.read_parquet(ROOT / "data" / "options_log" / "trades.parquet")
    d["e"] = pd.to_datetime(d["entry_dt"], errors="coerce")
    day = pd.Timestamp(a.date)
    t = d[(d["e"] >= day) & (d["e"] < day + pd.Timedelta("1d"))].copy()
    op = t[t.exit_dt.isna()]; cl = t[t.exit_dt.notna()]
    realized = float(cl.pnl.sum())
    spot = float(json.loads((SIM / "live.json").read_text()).get("spx") or 0)

    lo = a.lo or (spot - 70); hi = a.hi or (spot + 30)
    ladder = [lo + i * a.step for i in range(int((hi - lo) / a.step) + 1)]
    print(f"{a.date}: spot~{spot:.0f} | realized {realized:+.0f} | {len(op)} open positions")
    print(f"{'SPX close':>10} {'open settle':>12} {'+ realized':>11} {'DAY total':>10}  {'move':>6}")
    rows = []
    for S in ladder:
        ops = sum(settle_pnl(r, S) for _, r in op.iterrows())
        tot = ops + realized
        mv = S - spot
        flag = "  <= current" if abs(S - spot) < a.step / 2 else ""
        print(f"{S:>10.0f} {ops:>+12.0f} {realized:>+11.0f} {tot:>+10.0f}  {mv:>+6.0f}{flag}")
        rows.append(dict(spx_close=round(S), open_settle=round(ops), realized=round(realized), day_total=round(tot)))
    out = SIM / f"eod_scenario_{a.date.replace('-','')}.csv"
    pd.DataFrame(rows).to_csv(out, index=False)
    print(f"\nsaved -> {out.relative_to(ROOT)}")


if __name__ == "__main__":
    main()
