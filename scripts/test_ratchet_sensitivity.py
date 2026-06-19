"""Does the single-leg ratchet actually change results as R varies?

Sweeps ratchet_r over several values (plus OFF) on the single-leg engine and
reports total PnL, exit-reason mix, and — the key column — how many trades DIFFER
from the ratchet-off baseline. If many R values give identical totals AND zero
trades differ, the param is being ignored (bug). If totals/diffs move with R, it
works and any equal pair was just a coincidence for that grid.

    .venv\\Scripts\\python scripts\\test_ratchet_sensitivity.py
    .venv\\Scripts\\python scripts\\test_ratchet_sensitivity.py --dest Lock-in --lock 0.5 --target 2.0
"""
from __future__ import annotations
import argparse, sys
from pathlib import Path
import numpy as np, pandas as pd

try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT)); sys.path.insert(0, str(Path(__file__).resolve().parent))
from simulation_engine import simulate_trades  # noqa: E402
from validate_engine import _load_ticks, DEFAULTS, SIGNALS_PARQUET  # noqa: E402


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--dest", choices=["BE", "Lock-in"], default="BE")
    ap.add_argument("--lock", type=float, default=0.5)
    ap.add_argument("--target", type=float, default=2.0)
    ap.add_argument("--start", default="2021-06-18")
    ap.add_argument("--end", default="2022-06-19")
    args = ap.parse_args()

    s = pd.read_parquet(SIGNALS_PARQUET)
    s["DateTime"] = pd.to_datetime(s["DateTime"])
    if "Date" not in s.columns:
        s["Date"] = s["DateTime"].dt.date
    s = s[(s["DateTime"] >= pd.Timestamp(args.start)) & (s["DateTime"] <= pd.Timestamp(args.end))]
    tbd = {}
    for d in sorted(s["Date"].unique()):
        t = _load_ticks(d)
        if not t.empty:
            tbd[d] = t
    s = s[s["Date"].isin(tbd)].copy()
    print(f"window {args.start}->{args.end}: {len(s)} signals, {len(tbd)} days  "
          f"| dest={args.dest} lock={args.lock} target={args.target}R\n")

    common = dict(entry_slip=DEFAULTS["entry_slip"], exit_slip=DEFAULTS["exit_slip"],
                  stop_offset=DEFAULTS["stop_offset"], tick_value=DEFAULTS["tick_value"],
                  commission=DEFAULTS["commission"], contracts=1)

    def run(rr):
        return simulate_trades(s, tbd, args.target, **common,
                               ratchet_r=rr, ratchet_dest=args.dest, ratchet_lock_r=args.lock)

    base = run(0.0)
    base_f = base[base["Filled"] == True].set_index("SignalNum")

    rows = []
    for rr in [0.0, 0.25, 0.5, 0.75, 1.0, 1.5, 2.0, 3.0]:
        r = run(rr)
        f = r[r["Filled"] == True].set_index("SignalNum")
        pnl = float(f["GrossPnL"].sum())
        n_stop = int((f["ExitReason"] == "Stop").sum())
        n_tgt = int((f["ExitReason"] == "Target").sum())
        # diff vs ratchet-off: exit price or reason changed
        j = f.join(base_f[["ExitPrice", "ExitReason"]], rsuffix="_off")
        differ = int((~np.isclose(j["ExitPrice"], j["ExitPrice_off"], atol=1e-9, equal_nan=True)
                      | (j["ExitReason"] != j["ExitReason_off"])).sum())
        rows.append((rr, pnl, n_stop, n_tgt, differ))

    print(f"{'ratchet_r':>10} {'totalPnL$':>12} {'#Stop':>6} {'#Target':>8} {'#differ-from-off':>18}")
    for rr, pnl, ns, nt, d in rows:
        tag = "  (OFF baseline)" if rr == 0.0 else ""
        print(f"{rr:>10.2f} {pnl:>12.2f} {ns:>6} {nt:>8} {d:>18}{tag}")

    uniq = len(set(round(p, 2) for _, p, *_ in rows[1:]))
    print(f"\n{uniq} distinct PnL values across {len(rows)-1} ratchet settings.")
    if uniq == 1:
        print("⚠ All ratchet-ON settings give the SAME PnL — investigate (param may be inert).")
    else:
        print("✓ PnL varies with ratchet_r — the parameter is live.")


if __name__ == "__main__":
    main()
