"""Reconstruct sim PnL after removing three buckets the review flagged:
  - EOD flies      (strategy_id eodfly_*)   -> off-center fly on a stale price
  - Open condors   (strategy_id openic_*)   -> the losing arm of the EM-center A/B
  - all XSP        (trades_xsp.parquet)      -> dropped entirely

Keeps everything else in the SPX book (EOD condors, Open flies, gexlog walls, ...).
Reports the kept book vs the full book so the effect of the removals is explicit.
'incident_orphan' (a one-off error trade, not a strategy) is shown separately and
excluded from the kept-book total.

Read-only. Writes a DATED CSV. Changes NOTHING in any strategy.
  .venv/Scripts/python.exe scripts/sim_pnl_reconstruct.py
"""
from __future__ import annotations
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
LOG = ROOT / "data" / "options_log"
OUT = ROOT / "data" / "options_sim"

REMOVE_PREFIX = ("eodfly", "openic")   # EOD flies + Open condors
NONSTRAT = ("incident_orphan",)         # error trade, not a book strategy


def stats(g: pd.DataFrame) -> dict:
    pnl = pd.to_numeric(g["pnl"], errors="coerce")
    wins, losses = pnl[pnl > 0].sum(), -pnl[pnl < 0].sum()
    return {
        "n": int(len(g)),
        "pnl": round(float(pnl.sum()), 2),
        "avg": round(float(pnl.mean()), 2) if len(g) else 0.0,
        "win%": round(100.0 * (pnl > 0).mean(), 1) if len(g) else 0.0,
        "PF": round(float(wins / losses), 2) if losses > 0 else float("inf"),
    }


def main() -> int:
    # SPX only — XSP dropped entirely per the request
    spx = pd.read_parquet(LOG / "trades.parquet")
    spx = spx[spx["exit_dt"].notna()].copy()
    xsp = pd.read_parquet(LOG / "trades_xsp.parquet")
    xsp = xsp[xsp["exit_dt"].notna()]

    full_pnl = float(pd.to_numeric(spx["pnl"], errors="coerce").sum())
    xsp_pnl = float(pd.to_numeric(xsp["pnl"], errors="coerce").sum())

    removed = spx[spx["strategy_id"].str.startswith(REMOVE_PREFIX)]
    orphan = spx[spx["strategy_id"].isin(NONSTRAT)]
    kept = spx[~spx["strategy_id"].str.startswith(REMOVE_PREFIX)
               & ~spx["strategy_id"].isin(NONSTRAT)]

    print(f"Date range: {spx['entry_dt'].min()} .. {spx['entry_dt'].max()}\n")

    print("=== REMOVED ===")
    for sid, g in removed.groupby("strategy_id"):
        s = stats(g)
        print(f"  {sid:10} n={s['n']:>3}  pnl=${s['pnl']:>9,.2f}  win={s['win%']:>5}%  PF={s['PF']}")
    print(f"  {'XSP (all)':10} n={len(xsp):>3}  pnl=${xsp_pnl:>9,.2f}")
    print(f"  {'orphan':10} n={len(orphan):>3}  pnl=${float(pd.to_numeric(orphan['pnl'],errors='coerce').sum()):>9,.2f}  (error trade, excluded from kept)\n")

    print("=== KEPT (reconstructed book) ===")
    rows = []
    for sid, g in kept.groupby("strategy_id"):
        s = stats(g); s["strategy_id"] = sid; rows.append(s)
        print(f"  {sid:10} n={s['n']:>3}  pnl=${s['pnl']:>9,.2f}  avg=${s['avg']:>7,.2f}  win={s['win%']:>5}%  PF={s['PF']}")

    k = stats(kept)
    print("\n=== TOTALS ===")
    print(f"  Full SPX book (as-logged)      : ${full_pnl:>10,.2f}  (n={len(spx)})")
    print(f"  + XSP book (dropped)           : ${xsp_pnl:>10,.2f}  (n={len(xsp)})")
    print(f"  Reconstructed KEPT book (SPX)  : ${k['pnl']:>10,.2f}  (n={k['n']}, win {k['win%']}%, PF {k['PF']})")

    outp = OUT / f"sim_pnl_reconstruct_{str(spx['entry_dt'].max())[:10]}.csv"
    pd.DataFrame(rows).to_csv(outp, index=False)
    print(f"\nsaved -> {outp.relative_to(ROOT)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
