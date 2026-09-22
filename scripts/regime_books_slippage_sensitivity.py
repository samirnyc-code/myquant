"""regime_books_slippage_sensitivity.py — slippage sensitivity of the 2E & RevFT books.

The MC book was swept with the app's REAL execution presets (mc_pnl_exec_modes.py).
The 2E and RevFT books use their OWN tick-driven fill (market fill at next-bar
first tick + fixed 1-tick slip, $5 RT, zero latency — the SAME assumption as the
MC study). They are NOT re-simulated here (their engines are the concurrent
session's active files); instead we apply a validated FIRST-ORDER cost model:
worse slippage subtracts a ~fixed $/trade = extra_ticks x $12.50. That model
reproduces the MC real-preset spread almost exactly (MC ALL Optimistic +$49.3 ->
Brutal +$1.7 = -$47.6/tr ~= +3.8 ticks; the +4t slip delta between those presets).

Base backtest assumes ~1 tick RT slip. Extra RT ticks to reach each app preset:
  Optimistic -0.5 | Realistic +1.0 | Conservative +2.0 | Brutal +3.5  (vs base 1t)

Inputs are STABLE SNAPSHOTS (scratchpad/_snap_*.csv) taken from the concurrent
worktree so a concurrent rewrite can't move them. Reports Exp $/tr + PF per mode,
and each book's breakeven extra-slippage (ticks) where Exp $/tr -> 0.
"""
from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pandas as pd

_ROOT = Path(__file__).resolve().parents[1]
_TICK_USD = 12.50
# extra RT ticks vs the base 1t assumption, per app preset
_MODES = [("Optimistic", -0.5), ("Realistic", +1.0),
          ("Conservative", +2.0), ("Brutal", +3.5)]


def _log(m):
    sys.stdout.buffer.write((str(m) + "\n").encode("utf-8", "replace"))
    sys.stdout.flush()


def _pf(net):
    g = net[net > 0].sum()
    l = net[net < 0].sum()
    return float(g / abs(l)) if l < 0 else float("inf")


def _sweep(net, label):
    """net = per-trade $ at base 1t slip. Print base + each mode + breakeven."""
    net = np.asarray(net, float)
    n = len(net)
    base_exp = net.mean()
    be_ticks = base_exp / _TICK_USD  # extra ticks that zero out expectancy
    cells = []
    for name, dticks in _MODES:
        adj = net - dticks * _TICK_USD
        cells.append(f"{name[:4]}:${adj.mean():+6.1f}/tr PF{_pf(adj):4.2f}")
    _log(f"{label:22s} n={n:4d} base=${base_exp:+6.1f}/tr PF{_pf(net):4.2f}  "
         f"BE=+{be_ticks:4.1f}t  | " + "  ".join(cells))
    return dict(book=label, n=n, base_exp=base_exp, base_pf=_pf(net),
                breakeven_ticks=be_ticks,
                **{name: float((net - d * _TICK_USD).mean()) for name, d in _MODES})


def main():
    _log("SLIPPAGE SENSITIVITY — 2E & RevFT books (first-order cost model, base=1t RT slip)")
    _log("BE = extra RT ticks beyond base that drive Exp $/tr to 0 (higher = more robust)")
    _log("=" * 118)

    rows = []
    # ---- 2E book (NEW engine) ----
    e = pd.read_csv(_ROOT / "scratchpad" / "_snap_2e_newengine.csv")
    e = e[e["engine"] == "NEW"]
    _log("-- REGIME-2E (second-entry, wide 0.30xADR vol stop, hold-to-EOD) --")
    rows.append(_sweep(e[e["book"] == "WT-L"]["net"], "2E WT-Long (BULL)"))
    rows.append(_sweep(e[e["book"] == "WT-S"]["net"], "2E WT-Short (BEAR)"))
    rows.append(_sweep(e[e["book"].isin(["WT-L", "WT-S"])]["net"], "2E WT combined"))
    rows.append(_sweep(e[e["book"] == "FADE"]["net"], "2E f2EL fade-short"))
    rows.append(_sweep(e["net"], "2E full 3-book"))

    # ---- RevFT: EXCLUDED ----
    # RevFT is the concurrent session's ACTIVE, in-flight workstream (its output
    # files were being rewritten minutes before this ran — revft_fade_ema_20260725
    # at 10:52, revft_2e_sequence at 10:36). The available intermediate trade lists
    # are internally inconsistent (the 107-row revft_regime_2e CSV scores the WT book
    # NEGATIVE, contradicting their committed "rescued -> +$123-145k"), so no
    # trustworthy RevFT trade list exists on our side yet. Rerun once their book is
    # frozen, or point this at their canonical per-trade file.
    _log("-- RevFT: EXCLUDED (concurrent chat's live workstream; no stable trade list) --")

    _log("=" * 118)
    _log("MC (real app presets, for comparison): ALL base Realistic +$31.4/tr BE=+2.5t "
         "(DIES by Brutal); Stack v2 +$84.4/tr BE=+6.8t (survives all modes).")
    out = pd.DataFrame(rows)
    p = _ROOT / "data" / "regime" / "regime_books_slippage_sensitivity_20260725.csv"
    out.to_csv(p, index=False)
    _log(f"WROTE {p.name}")


if __name__ == "__main__":
    main()
