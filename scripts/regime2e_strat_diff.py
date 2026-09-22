"""Validate Regime2EStrategy signals vs the python causal engine (signal parity).

Strategy CSV cols: date,time,event,seq,dir,trig,limit,regime,sma20d,reason
(both FIRE and SKIP rows are DETECTED 2E signals; reason is the strategy's gate).
Python py_signals(date) = detect_entries_causal cnt==2, regime at trigger touch.

Matches each strategy signal to a python signal by dir + trig (within 1 tick).
Reports detection parity + regime agreement. (Gate reasons are the strategy's own
layer; py_signals is pre-gate, so we check DETECTION + regime, not the SMA/gap gate.)

  python scripts/regime2e_strat_diff.py [strat_csv]
"""
import sys
from pathlib import Path
import numpy as np
import pandas as pd

TICK = 0.25
REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO / "scripts"))
from regime2e_nt_diff import py_signals                          # noqa: E402


def main():
    p = Path(sys.argv[1]) if len(sys.argv) > 1 else (Path.home() / "Documents" / "regime2e_strat_signals_ES.csv")
    df = pd.read_csv(p).fillna({"reason": ""})
    df = df[df.event.isin(["FIRE", "SKIP"])].copy()
    df["date"] = df["date"].astype(str)
    dates = sorted(df["date"].unique())
    tot = dict(strat=0, py=0, match=0, reg=0, days=0, noticks=0)
    lines = []
    for d in dates:
        sd = df[df.date == d].to_dict("records")
        py = py_signals(d)
        if py is None:
            tot["noticks"] += 1
            lines.append(f"{d}: no trove ticks ({len(sd)} strat signals unchecked)")
            continue
        used = set(); m = reg = 0
        for r in sd:
            best = None
            for j, q in enumerate(py):
                if j in used or q["dir"] != r["dir"]:
                    continue
                if abs(q["trig"] - r["trig"]) <= 1.01 * TICK:
                    best = j; break
            if best is not None:
                used.add(best); m += 1
                if str(r["regime"]) == py[best]["regime"]:
                    reg += 1
        tot["strat"] += len(sd); tot["py"] += len(py); tot["match"] += m; tot["reg"] += reg
        tot["days"] += 1
        lines.append(f"{d}: strat {len(sd):2d} / py {len(py):2d} -> match {m:2d}"
                     f"  (strat-only {len(sd)-m}, py-only {len(py)-m})")
    print("\n".join(lines))
    print("\n===== SIGNAL PARITY: Regime2EStrategy vs python =====")
    print(f"days {tot['days']} (no-ticks {tot['noticks']})")
    print(f"strat signals {tot['strat']}  |  python signals {tot['py']}")
    if tot["strat"] and tot["py"]:
        print(f"matched {tot['match']}  ({100*tot['match']/tot['strat']:.1f}% of strat, "
              f"{100*tot['match']/tot['py']:.1f}% of py)")
    if tot["match"]:
        print(f"regime agreement on matched: {tot['reg']}/{tot['match']} "
              f"({100*tot['reg']/tot['match']:.1f}%)")
    # FIRE (OK) entries specifically
    fires = df[df.event == "FIRE"]
    print(f"\nstrategy took {len(fires)} FIRE entries (OnePerDay-filtered, gated OK):")
    for _, r in fires.iterrows():
        print(f"  {r['date']} {r['time']} {r['dir']} trig {r['trig']} -> lim {r['limit']} ({r['regime']})")


if __name__ == "__main__":
    main()
