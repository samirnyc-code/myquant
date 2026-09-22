"""closed_hindsight.py — for trades CLOSED intraday today, would we have been better
off holding them to the close? Compares the realized P&L (what the early exit banked)
against the hold-to-settlement P&L at the current/expected SPX close. 0DTE settles at
intrinsic, so 'held' value = intrinsic at the settlement price. Saves a dated CSV.

    python scripts/closed_hindsight.py [--date 2026-08-20] [--settle 7650]
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


def hold_pnl(row, S):
    legs = row["legs"] if isinstance(row["legs"], list) else json.loads(row["legs"])
    cost = sum((intrinsic(l, S) if l["side"] == "sell" else -intrinsic(l, S)) for l in legs)
    fee = 2.6 / 100.0
    return (float(row["credit"]) - max(cost, 0.0) - fee) * 100


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--date", default=dt.date.today().isoformat())
    ap.add_argument("--settle", type=float, default=None, help="SPX close to price 'held' against")
    a = ap.parse_args()
    S = a.settle or float(json.loads((SIM / "live.json").read_text()).get("spx") or 0)

    d = pd.read_parquet(ROOT / "data" / "options_log" / "trades.parquet")
    d["e"] = pd.to_datetime(d["entry_dt"], errors="coerce")
    day = pd.Timestamp(a.date)
    t = d[(d["e"] >= day) & (d["e"] < day + pd.Timedelta("1d"))]
    cl = t[t.exit_dt.notna()].copy()

    print(f"{a.date}: closed intraday, priced 'held' at SPX {S:.0f}")
    print(f"{'strategy':>10} {'exit_dt':>17} {'reason':>16} {'realized':>9} {'if_held':>9} {'better?':>9}")
    tot_r = tot_h = 0.0
    rows = []
    for _, r in cl.iterrows():
        h = hold_pnl(r, S)
        realized = float(r["pnl"])
        diff = h - realized
        verdict = f"hold +{diff:.0f}" if diff > 1 else (f"close +{-diff:.0f}" if diff < -1 else "≈ same")
        reason = str(r.get("close_reason"))[:16]
        print(f"{r['strategy_id']:>10} {str(r['exit_dt'])[:16]:>17} {reason:>16} {realized:>+9.0f} {h:>+9.0f} {verdict:>9}")
        tot_r += realized; tot_h += h
        rows.append(dict(strategy=r["strategy_id"], exit_dt=str(r["exit_dt"]), reason=reason,
                         realized=round(realized), if_held=round(h), diff=round(diff)))
    print("-" * 72)
    print(f"{'TOTAL':>10} {'':>17} {'':>16} {tot_r:>+9.0f} {tot_h:>+9.0f} "
          f"{('HOLD better +'+str(round(tot_h-tot_r))) if tot_h>tot_r else ('CLOSE better +'+str(round(tot_r-tot_h)))}")
    out = SIM / f"closed_hindsight_{a.date.replace('-','')}.csv"
    pd.DataFrame(rows).to_csv(out, index=False)
    print(f"\nnote: 'if_held' uses SPX {S:.0f} as the settlement proxy — final close may differ.")
    print(f"saved -> {out.relative_to(ROOT)}")


if __name__ == "__main__":
    main()
