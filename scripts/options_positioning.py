"""options_positioning.py — how is the open 0DTE book positioned RIGHT NOW, and
which way does it want the market to go? Answers "are we OK if the selloff continues?"

For every OPEN position: the SHORT (sold) strike is the risk. Short PUT => a selloff
hurts (spot falling toward/through it). Short CALL => a selloff helps. Prints each
position's short strike, cushion to spot, current mark, and max loss, then the
net directional tilt + total downside if spot keeps dropping. Saves a dated snapshot.

    python scripts/options_positioning.py
"""
from __future__ import annotations
import datetime as dt
import json
from pathlib import Path
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
SIM = ROOT / "data" / "options_sim"


def _spot():
    try:
        d = json.loads((SIM / "live.json").read_text())
        return float(d["spx"]), d.get("ts_et"), d.get("state")
    except Exception:
        return None, None, None


def _marks():
    f = SIM / "marks.csv"
    if not f.exists():
        return {}
    m = pd.read_csv(f)
    if not len(m):
        return {}
    last = m.groupby("trade_id").last()
    col = "unreal_pnl" if "unreal_pnl" in last else None
    return {tid: float(r[col]) for tid, r in last.iterrows()} if col else {}


def _short_leg(legs):
    """Return (strike, right) of the sold leg."""
    try:
        L = json.loads(legs) if isinstance(legs, str) else legs
        for leg in L:
            if leg.get("side") == "sell":
                return float(leg["strike"]), leg["right"]
    except Exception:
        pass
    return None, None


def main():
    spot, ts, state = _spot()
    d = pd.read_parquet(ROOT / "data" / "options_log" / "trades.parquet")
    op = d[d.exit_dt.isna()].copy()
    marks = _marks()

    print(f"SPOT {spot} (live.json {ts}, {state})\n")
    rows, put_loss, call_gainroom, unreal_tot = [], 0.0, 0.0, 0.0
    print(f"{'strategy':<12} {'short':>8} {'cushion':>8} {'mark$':>8} {'maxLoss$':>9}  selloff")
    for _, r in op.iterrows():
        k, right = _short_leg(r.get("legs"))
        if k is None:
            continue
        mk = marks.get(r.trade_id)
        unreal_tot += mk or 0
        maxloss = float(r.max_loss) if pd.notna(r.get("max_loss")) else None
        if right == "P":
            cushion = (spot - k) if spot else None       # +cushion = spot above short put
            effect = "HURTS"
            if maxloss:
                put_loss += maxloss
        else:
            cushion = (k - spot) if spot else None        # +cushion = spot below short call
            effect = "helps"
        rows.append((r.strategy_id, k, right, cushion, mk, maxloss, effect))
        print(f"{r.strategy_id:<12} {k:>7.0f}{right} {cushion:>8.0f} "
              f"{(mk if mk is not None else float('nan')):>8.0f} "
              f"{(maxloss if maxloss else float('nan')):>9.0f}  {effect}")

    puts = [x for x in rows if x[2] == "P"]
    calls = [x for x in rows if x[2] == "C"]
    nearest_put = max((x[1] for x in puts), default=None)   # highest short put = first tested
    print()
    print(f"open positions: {len(rows)}  |  short-PUT (selloff hurts): {len(puts)}  |  short-CALL (selloff helps): {len(calls)}")
    print(f"current unrealized: ${unreal_tot:,.0f}")
    if nearest_put and spot:
        print(f"nearest short PUT: {nearest_put:.0f}  ({spot - nearest_put:+.0f} pts below spot) — first pain if selloff continues")
    print(f"total max loss on the PUT side if breached: ${put_loss:,.0f}")
    tilt = ("SHORT-PUT tilt -> a continued selloff HURTS" if len(puts) > len(calls)
            else "SHORT-CALL tilt -> a continued selloff HELPS" if len(calls) > len(puts)
            else "balanced put/call")
    print(f"tilt: {tilt}")

    out = SIM / f"positioning_{dt.date(2026,8,17).isoformat().replace('-','')}.csv"
    pd.DataFrame(rows, columns=["strategy", "short_k", "right", "cushion", "mark", "max_loss", "selloff"]).to_csv(out, index=False)
    print(f"\nsaved -> {out.relative_to(ROOT)}")


if __name__ == "__main__":
    main()
