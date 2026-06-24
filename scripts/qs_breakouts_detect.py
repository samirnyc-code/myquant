"""QS Breakouts — frequency-sanity gate (headless), Ver 5 PaintBar.

Compares the three real use-modes against the paper's stated frequency:
  - QSConfig()            Ver 5 PAINT default (BO, range filter @8, no FT/IBS)
  - QSConfig.research()   whitepaper BO+FT subset (FT close-beyond + IBS 69/31 + filters)
  - QSConfig.paintbar_raw() everything painted (range filter off, BO+OB+CX)

Paper: BO+FT ~5/day. No P&L here. Run: python scripts/qs_breakouts_detect.py
"""
from __future__ import annotations
import sys
from pathlib import Path
import pandas as pd

_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(_ROOT))
from qs_setups import detect, QSConfig  # noqa: E402

BARS = _ROOT / "data" / "bars" / "_continuous.parquet"


def log(m): print(f"[qsfreq] {m}", flush=True)


def summarize(name, sig, n_days):
    log(f"\n===== {name} =====")
    log(f"total signals: {len(sig):,}  ({len(sig)/n_days:.2f}/day)")
    if sig.empty:
        return
    by_type = sig.groupby("SignalType").size().sort_values(ascending=False)
    for stype, cnt in by_type.items():
        log(f"   {stype:7s}: {cnt:7,}  = {cnt/n_days:5.2f}/day")
    fs = sig["FilterStatus"].value_counts()
    if len(fs) > 1 or "ok" not in fs.index:
        log("   FilterStatus: " + ", ".join(f"{k}={v}" for k, v in fs.items()))
    ok = sig[sig["FilterStatus"] == "ok"]
    log(f"   tradeable (ok): {len(ok):,} = {len(ok)/n_days:.2f}/day")


def main():
    bars = pd.read_parquet(BARS)
    n_days = bars["DateTime"].dt.date.nunique()
    log(f"bars: {len(bars):,}  sessions: {n_days}  "
        f"{bars['DateTime'].min()} -> {bars['DateTime'].max()}")

    summarize("Ver5 PAINT default (BO, rangeFilter@8)", detect(bars, QSConfig()), n_days)
    summarize("RESEARCH (BO+FT, close-beyond + IBS 69/31 + filters)",
              detect(bars, QSConfig.research()), n_days)
    summarize("PAINTBAR RAW (BO+OB+CX, no range filter)",
              detect(bars, QSConfig.paintbar_raw()), n_days)

    log("\n========== PAPER COMPARISON ==========")
    log("  whitepaper BO+FT tradeable setup: ~5/day")
    log("  -> compare to RESEARCH 'tradeable (ok)' above")
    log("======================================")


if __name__ == "__main__":
    main()
