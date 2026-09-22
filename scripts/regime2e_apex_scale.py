"""Dynamic MES scaling on Apex legacy 150K (intraday trailing $5,000): trade small
through the ramp, grow size as the cushion grows. Uses the cached trades from
regime2e_apex_mes.py (no tick pass).

Sizer (set at each trade's start, held for that trade):
    cushion = realized_equity - current_floor       (floor = peak-T, or start+$100 once locked)
    size_MES = clamp( base , floor(cushion / R) , maxc )
R = cushion-dollars required per MES contract (lower R = more aggressive). Sweeps R.

Reports: blow?, final net, per-year, peak size reached, deepest cushion — vs the
flat 5-MES and 8-MES baselines. Official MES fee $2.27/contract/trade.

  python scripts/regime2e_apex_scale.py
"""
import pickle
from datetime import date
from pathlib import Path
import numpy as np

MES_PT = 5.0; MES_FEE = 1.02 + 1.25; T = 5000.0; MAXC = 100
REPO = Path(__file__).resolve().parent.parent
CACHE = REPO / "reports" / "regime2e" / "apex_mes_trades.pkl"


def load():
    if not CACHE.exists():
        raise SystemExit("run regime2e_apex_mes.py first to build the trade cache")
    return pickle.load(open(CACHE, "rb"))


def run(trades, base, R, maxc=MAXC):
    """R=None -> flat `base` size. Else dynamic size = clamp(base, cushion/R, maxc)."""
    realized = 0.0; peak = 0.0; blown = None; min_c = 1e12
    yearly = {}; peak_size = 0; sizes = []
    for t in trades:
        if blown is not None:
            break
        floor = 100.0 if peak >= T + 100 else peak - T
        cushion = realized - floor
        if R is None:
            size = base
        else:
            size = int(max(base, min(maxc, cushion // R)))
        peak_size = max(peak_size, size); sizes.append(size)
        u = t["sgn"] * (t["seg"] - t["entry"]) * MES_PT * size
        eq = realized + u
        runpk = np.maximum(peak, np.maximum.accumulate(eq))
        fl = np.where(runpk >= T + 100, 100.0, runpk - T)
        mc = float((eq - fl).min()); min_c = min(min_c, mc)
        if mc <= 0:
            blown = t["date"]
        peak = float(runpk[-1])
        realized += t["gross_pts"] * MES_PT * size - MES_FEE * size
        yearly[t["date"][:4]] = yearly.get(t["date"][:4], 0.0) + t["gross_pts"] * MES_PT * size - MES_FEE * size
    return dict(blown=blown, final=realized, min_c=min_c, peak_size=peak_size, yearly=yearly,
                med_size=int(np.median(sizes)) if sizes else 0)


def main():
    trades = load()
    ds = sorted({t["date"] for t in trades})
    yrs = max((date(*map(int, ds[-1].split("-"))) - date(*map(int, ds[0].split("-")))).days, 1) / 365.25
    print(f"Apex legacy 150K intraday $5,000 — dynamic MES scaling, {len(trades)} trades, {yrs:.1f}yr\n")
    print(f"{'rule':<28} {'result':>16} {'final net':>10} {'~/yr':>9} {'peak sz':>8} {'med sz':>7} {'deepest':>9}")
    configs = [("flat 5 MES", 5, None), ("flat 8 MES", 8, None),
               ("base5, +1c / $1500 cush", 5, 1500), ("base5, +1c / $1000 cush", 5, 1000),
               ("base5, +1c / $750 cush", 5, 750), ("base5, +1c / $500 cush", 5, 500),
               ("base8, +1c / $750 cush", 8, 750), ("base8, +1c / $500 cush", 8, 500)]
    for name, base, R in configs:
        r = run(trades, base, R)
        st = f"BLOWN {r['blown'][:7]}" if r["blown"] else "survives"
        yr = r["final"] / yrs if not r["blown"] else 0
        print(f"{name:<28} {st:>16} ${r['final']:>+9,.0f} ${yr:>+8,.0f} {r['peak_size']:>6}c {r['med_size']:>5}c ${r['min_c']:>+8,.0f}")
    # per-year for the best surviving aggressive config
    print("\nper-year for base5 +1c/$750 cush (if survives):")
    r = run(trades, 5, 750)
    if not r["blown"]:
        print("  " + "  ".join(f"{y}:${v:+,.0f}" for y, v in sorted(r["yearly"].items())))
    else:
        print(f"  blew {r['blown']}")


if __name__ == "__main__":
    main()
