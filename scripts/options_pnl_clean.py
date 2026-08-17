"""options_pnl_clean.py — August P&L on the VERIFIED-CLEAN book only.

The raw August book is contaminated by the desk's shake-out period:
  * Aug 4      blank-slate setup day, no entry_valid tracking (NA)
  * Aug 5      feed dead until 09:26 -> late/invalid entries + orphaned positions
  * Aug 6, 7   no entry_valid tracking (NA)
  * Aug 10-14  entry_valid=True, notes "ok"  <- the only certified-clean trades

CLEAN = entry_valid is True AND strategy != incident_orphan. This drops the whole
early error window (including Aug 7's +$1,367 winner, so the cut is conservative,
not cherry-picked) and every orphan. Saves the clean trade list, dated.

    python scripts/options_pnl_clean.py
"""
from __future__ import annotations
import datetime as dt
from pathlib import Path
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
TRADES = ROOT / "data" / "options_log" / "trades.parquet"
OUTDIR = ROOT / "data" / "options_sim"


def main() -> None:
    d = pd.read_parquet(TRADES)
    d["entry_dt"] = pd.to_datetime(d["entry_dt"], errors="coerce")
    aug = d[(d["entry_dt"] >= "2026-08-01") & (d["entry_dt"] < "2026-09-01")].copy()
    aug["day"] = aug["entry_dt"].dt.date

    clean = aug[(aug["entry_valid"] == True) & (aug["strategy_id"] != "incident_orphan")].copy()
    excluded = aug[~aug.index.isin(clean.index)]

    run = dt.date(2026, 8, 17).isoformat()   # stamp passed in (no Date.now in this env)
    out = OUTDIR / f"pnl_clean_august_{run.replace('-', '')}.csv"
    clean.sort_values("entry_dt").to_csv(out, index=False)

    def block(df, title):
        c = df[df["pnl"].notna()]
        print(f"\n{title}: {len(c)} closed trades")
        if not len(c):
            return
        wins = c[c.pnl > 0]; losses = c[c.pnl <= 0]
        print(f"  realized PnL: ${c.pnl.sum():,.2f}")
        print(f"  win rate: {len(wins)}/{len(c)} ({100*len(wins)/len(c):.0f}%)")
        print(f"  avg win ${wins.pnl.mean():.0f} | avg loss ${losses.pnl.mean():.0f} | "
              f"best ${c.pnl.max():.0f} | worst ${c.pnl.min():.0f}")
        print("  by strategy:")
        for s, r in c.groupby("strategy_id")["pnl"].agg(["count", "sum"]).sort_values("sum").iterrows():
            print(f"    {s:<14} n={int(r['count']):<2} ${r['sum']:,.0f}")
        print("  by day:")
        for day, r in c.groupby("day")["pnl"].agg(["count", "sum"]).iterrows():
            print(f"    {day}  n={int(r['count']):<2} ${r['sum']:,.0f}")

    print("=" * 56)
    print(f"AUGUST 2026 — VERIFIED-CLEAN BOOK (entry_valid=True, no orphans)")
    print("=" * 56)
    print(f"excluded: {len(excluded)} trades from the shake-out window "
          f"({sorted({str(x) for x in excluded['day']})})")
    block(clean, "CLEAN")
    print(f"\nsaved clean trade list -> {out.relative_to(ROOT)}")


if __name__ == "__main__":
    main()
