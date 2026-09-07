"""EMPIRICAL fill-realism audit: did the sim's actual fills respect the NBBO?

Uses data/options_log/xsp_fills.csv, which logs the per-leg bid/ask at fill time
plus the real combo_fill (IB avgFillPrice) for every XSP entry. For each 2-leg
credit spread we compute where the fill landed relative to the live NBBO:

  worst  = sell_bid - buy_ask     (fully marketable CROSS -> least credit; conservative)
  best   = sell_ask - buy_bid     (favorable touch       -> most credit;  optimistic)
  mid    = sell_mid - buy_mid
  pos    = (fill - worst) / (best - worst)    # 0=worst(cross), 0.5=mid, 1=best

pos<=0.5 => fill at/worse-than mid = conservative (consistent with crossing the
spread). pos>1 => filled THROUGH the best quote = phantom/impossible.

Read-only. Writes a DATED CSV. Changes NOTHING.
  .venv/Scripts/python.exe scripts/fill_vs_nbbo_audit.py
"""
from __future__ import annotations
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "data" / "options_log" / "xsp_fills.csv"
OUT = ROOT / "data" / "options_sim"
EPS = 1e-9


def main() -> int:
    f = pd.read_csv(SRC)
    rows = []
    for tid, g in f.groupby("trade_id"):
        g = g[g["kind"] == "entry"]
        sells = g[g["action"] == "SELL"]
        buys = g[g["action"] == "BUY"]
        if len(sells) != 1 or len(buys) != 1:
            continue                                   # only clean 2-leg verticals
        s, b = sells.iloc[0], buys.iloc[0]
        worst = s.leg_bid - b.leg_ask                  # cross to establish -> least credit
        best = s.leg_ask - b.leg_bid                   # favorable -> most credit
        mid = s.mid - b.mid
        fill = float(s.combo_fill)
        width = best - worst                           # = sum of leg spreads
        pos = (fill - worst) / width if width > EPS else 0.0
        rows.append({
            "trade_id": tid, "strategy": s.strategy,
            "sell": s.leg, "buy": b.leg,
            "worst_cross": round(worst, 3), "mid": round(mid, 3),
            "best": round(best, 3), "fill": round(fill, 3),
            "pos": round(pos, 3),
            "through_best": fill > best + 0.005,
            "worse_than_cross": fill < worst - 0.005,
            "conservative": pos <= 0.5 + 1e-6,
        })
    d = pd.DataFrame(rows)
    n = len(d)
    print(f"XSP entry fills audited: {n} (2-leg verticals)\n")
    print("Where fills landed in the live NBBO (0=marketable cross / least credit, "
          "0.5=mid, 1=favorable touch):")
    print(f"  mean pos   : {d.pos.mean():.3f}   median: {d.pos.median():.3f}")
    print(f"  conservative (pos<=0.5, at/worse than mid): {d.conservative.sum()}/{n} "
          f"({100*d.conservative.mean():.0f}%)")
    print(f"  optimistic   (pos>0.5, better than mid)   : {(~d.conservative).sum()}/{n} "
          f"({100*(~d.conservative).mean():.0f}%)")
    print(f"  filled THROUGH best quote (impossible)    : {d.through_best.sum()}/{n}")
    print(f"  filled WORSE than full cross (extra cons.): {d.worse_than_cross.sum()}/{n}")

    print("\nMost-optimistic fills (highest pos):")
    for _, r in d.sort_values("pos", ascending=False).head(6).iterrows():
        print(f"  {r.trade_id[-13:]} {r.strategy:9} sell {r.sell} buy {r.buy}  "
              f"worst={r.worst_cross} mid={r.mid} best={r.best} fill={r.fill}  pos={r.pos}")

    outp = OUT / "fill_vs_nbbo_audit.csv"
    d.to_csv(outp, index=False)
    print(f"\nsaved -> {outp.relative_to(ROOT)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
