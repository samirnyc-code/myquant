"""cover_now_vs_eod.py — A/B: cover the open 0DTE book NOW vs let it ride to EOD.

  mark     snapshot each OPEN position's current mark (= what covering now locks in),
           the spot, and the time. Saved to data/options_sim/cover_vs_eod_<date>.json.
  compare  read that snapshot + each trade's FINAL realized P&L (once settled) and show,
           per position and total, whether covering at mark time would have beaten
           letting it ride.

    python scripts/cover_now_vs_eod.py mark
    python scripts/cover_now_vs_eod.py compare
"""
from __future__ import annotations
import json
import sys
from pathlib import Path
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
SIM = ROOT / "data" / "options_sim"
TRADES = ROOT / "data" / "options_log" / "trades.parquet"
sys.path.insert(0, str(ROOT / "scripts"))


def _snap_path(day):
    return SIM / f"cover_vs_eod_{day}.json"


def _marks():
    f = SIM / "marks.csv"
    if not f.exists():
        return {}
    m = pd.read_csv(f)
    if not len(m) or "unreal_pnl" not in m:
        return {}
    return {tid: float(r["unreal_pnl"]) for tid, r in m.groupby("trade_id").last().iterrows()}


def _short(legs):
    try:
        L = json.loads(legs) if isinstance(legs, str) else legs
        for leg in L:
            if leg.get("side") == "sell":
                return f"{float(leg['strike']):.0f}{leg['right']}"
    except Exception:
        pass
    return "?"


def cmd_mark():
    import pipeline_health as ph
    now = ph.chicago_now()
    day = now.strftime("%Y%m%d")
    try:
        spot = json.loads((SIM / "live.json").read_text()).get("spx")
    except Exception:
        spot = None
    d = pd.read_parquet(TRADES)
    op = d[d.exit_dt.isna()].copy()
    marks = _marks()
    positions = []
    for _, r in op.iterrows():
        positions.append({
            "trade_id": r.trade_id, "strategy": r.strategy_id,
            "short": _short(r.get("legs")),
            "cover_now_pnl": marks.get(r.trade_id),   # covering now ~ locks in this mark
        })
    total = sum(p["cover_now_pnl"] or 0 for p in positions)
    snap = {"mark_time_ct": now.strftime("%Y-%m-%d %H:%M CT (machine)"),
            "spot_at_mark": spot, "cover_now_total": round(total, 2),
            "positions": positions}
    _snap_path(day).write_text(json.dumps(snap, indent=2))
    print(f"MARKED {snap['mark_time_ct']}  spot {spot}")
    for p in positions:
        print(f"  {p['strategy']:<12} {p['short']:>7}  cover-now ${(p['cover_now_pnl'] or 0):,.0f}")
    print(f"COVER-NOW TOTAL: ${total:,.0f}  (locks in now; ride = let settle at 15:00 CT)")
    print(f"saved -> {_snap_path(day).relative_to(ROOT)}")


def cmd_compare():
    import pipeline_health as ph
    day = ph.chicago_now().strftime("%Y%m%d")
    p = _snap_path(day)
    if not p.exists():
        sys.exit("no snapshot today — run `cover_now_vs_eod.py mark` first")
    snap = json.loads(p.read_text())
    d = pd.read_parquet(TRADES).set_index("trade_id")
    print(f"COVER-NOW (marked {snap['mark_time_ct']}, spot {snap['spot_at_mark']}) vs RIDE-TO-EOD\n")
    print(f"{'strategy':<12} {'short':>7} {'cover_now$':>11} {'ride/final$':>12} {'ride-cover':>11} {'settled?':>9}")
    cov_t = ride_t = 0.0
    for pos in snap["positions"]:
        tid = pos["trade_id"]
        cov = pos["cover_now_pnl"] or 0
        final = None
        if tid in d.index and pd.notna(d.loc[tid, "pnl"]):
            final = float(d.loc[tid, "pnl"])
        cov_t += cov
        settled = final is not None
        ride = final if settled else _marks().get(tid, 0)   # live mark if not yet settled
        ride_t += ride
        diff = ride - cov
        print(f"{pos['strategy']:<12} {pos['short']:>7} {cov:>11,.0f} {ride:>12,.0f} {diff:>+11,.0f} "
              f"{'yes' if settled else 'OPEN':>9}")
    print(f"\nCOVER-NOW total: ${cov_t:,.0f}   RIDE total: ${ride_t:,.0f}   "
          f"DELTA (ride - cover): ${ride_t - cov_t:+,.0f}")
    print("verdict:", "RIDING won" if ride_t > cov_t else "COVERING would have won" if ride_t < cov_t else "tie")


if __name__ == "__main__":
    cmd = sys.argv[1] if len(sys.argv) > 1 else "mark"
    {"mark": cmd_mark, "compare": cmd_compare}.get(cmd, cmd_mark)()
