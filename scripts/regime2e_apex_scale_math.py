"""Show the trade-by-trade math behind the MES scaling, expose the compounding, and
re-run with realistic size caps. Cached trades from regime2e_apex_mes.py.

  python scripts/regime2e_apex_scale_math.py
"""
import pickle
from datetime import date
from pathlib import Path
import numpy as np

MES_PT = 5.0; COMM = 1.02; SLIP_TICKS = 1; MES_TICK = 1.25; T = 5000.0
FEE = COMM + SLIP_TICKS * MES_TICK          # $2.27 per contract per round turn
REPO = Path(__file__).resolve().parent.parent
CACHE = REPO / "reports" / "regime2e" / "apex_mes_trades.pkl"


def walk(trades, base, R, maxc):
    realized = 0.0; peak = 0.0; rows = []; blown = None
    for t in trades:
        if blown:
            break
        floor = 100.0 if peak >= T + 100 else peak - T
        cushion = realized - floor
        size = base if R is None else int(max(base, min(maxc, cushion // R)))
        gross_pts = t["gross_pts"]
        gross = gross_pts * MES_PT * size
        fee = FEE * size
        net = gross - fee
        u = t["sgn"] * (t["seg"] - t["entry"]) * MES_PT * size
        eq = realized + u
        runpk = np.maximum(peak, np.maximum.accumulate(eq))
        fl = np.where(runpk >= T + 100, 100.0, runpk - T)
        if float((eq - fl).min()) <= 0:
            blown = t["date"]
        peak = float(runpk[-1]); realized += net
        rows.append(dict(date=t["date"], cushion_before=cushion, size=size,
                         gross_pts=gross_pts, gross=gross, fee=fee, net=net, equity=realized))
    return rows, blown


def yr_of(ds):
    return max((date(*map(int, ds[-1].split("-"))) - date(*map(int, ds[0].split("-")))).days, 1) / 365.25


def main():
    trades = pickle.load(open(CACHE, "rb"))
    ds = sorted({t["date"] for t in trades}); yrs = yr_of(ds)

    print("=== WORKED MATH: base5 +1c/$1,000 cushion (cap 100), LAST 12 trades ===")
    print("fee model: $1.02 comm + 1 MES tick ($1.25) slip = $2.27 / contract / round-turn\n")
    rows, blown = walk(trades, 5, 1000, 100)
    print(f"{'date':<11}{'cush_before':>12}{'size':>6}{'gpts':>7}{'gross$':>10}{'fee$':>8}{'net$':>10}{'equity$':>11}")
    for r in rows[-12:]:
        print(f"{r['date']:<11}{r['cushion_before']:>12,.0f}{r['size']:>6}{r['gross_pts']:>7.2f}"
              f"{r['gross']:>10,.0f}{r['fee']:>8,.0f}{r['net']:>10,.0f}{r['equity']:>11,.0f}")

    print("\n=== WHY IT 'EXPLODES': size scales with cushion = compounding. per-year: ===")
    for cap in (100, 30, 20, 10):
        rows, blown = walk(trades, 5, 1000, cap)
        yearly = {}
        for r in rows:
            yearly[r["date"][:4]] = yearly.get(r["date"][:4], 0.0) + r["net"]
        maxsz = max(r["size"] for r in rows)
        st = f"BLEW {blown[:7]}" if blown else "ok"
        print(f"\n cap {cap:>3} MES ({st}, peak {maxsz}c):  " +
              "  ".join(f"{y}:${v:+,.0f}" for y, v in sorted(yearly.items())))
        print(f"   final ${rows[-1]['equity']:+,.0f}  (~${rows[-1]['equity']/yrs:+,.0f}/yr avg)")

    print("\n=== realistic sizes: what a bad DAY costs at each size (0.30xADR stop ~ 17 pts) ===")
    for sz in (5, 10, 20, 30, 50, 100):
        print(f"  {sz:>3} MES: 1 stop-out ~ -{17*MES_PT*sz:,.0f}$ ; "
              f"one bad day (3 stops) ~ -{3*17*MES_PT*sz:,.0f}$ ; a −40pt trend-day ~ -{40*MES_PT*sz:,.0f}$")


if __name__ == "__main__":
    main()
