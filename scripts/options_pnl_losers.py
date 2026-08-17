"""options_pnl_losers.py — dig into the losing trades on the CLEAN August book.

Observational only (too early to change rules — running more weeks first). Tests:
  1. which strategies actually lose on the verified-clean book
  2. the call-vs-put asymmetry (does the CALL side of each structure underperform?)
  3. per-trade detail on the worst strategy so we can see WHY (trend-through, etc.)

Saves the clean loser trade list, dated.
    python scripts/options_pnl_losers.py
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
    clean = aug[(aug["entry_valid"] == True) & (aug["strategy_id"] != "incident_orphan")].copy()
    clean = clean[clean["pnl"].notna()]
    clean["day"] = clean["entry_dt"].dt.date
    clean["side"] = clean["strategy_id"].str.endswith("_c").map({True: "CALL", False: "PUT"})

    print("=== CALL vs PUT side (clean book) ===")
    for side, g in clean.groupby("side"):
        w = (g.pnl > 0).mean()
        print(f"  {side}: n={len(g):2d}  pnl=${g.pnl.sum():,.0f}  win={100*w:.0f}%  avg=${g.pnl.mean():.0f}")

    print("\n=== per strategy, call/put paired ===")
    piv = clean.groupby("strategy_id")["pnl"].agg(["count", "sum", "mean"])
    for s in sorted(piv.index):
        r = piv.loc[s]
        print(f"  {s:<14} n={int(r['count']):<2} ${r['sum']:>7,.0f}  avg ${r['mean']:>5.0f}")

    worst = clean.groupby("strategy_id")["pnl"].sum().idxmin()
    print(f"\n=== worst strategy: {worst} — per-trade ===")
    cols = ["day", "structure", "credit", "exit_cost", "pnl", "close_reason"]
    w = clean[clean.strategy_id == worst][[c for c in cols if c in clean]].copy()
    for _, r in w.iterrows():
        cr = str(r.get("close_reason", ""))[:70]
        print(f"  {r['day']}  {str(r.get('structure','')):<14} "
              f"credit={r.get('credit')!s:>5} exit={r.get('exit_cost')!s:>5} "
              f"pnl=${r['pnl']:>6.0f}  {cr}")

    out = OUTDIR / f"pnl_losers_august_{dt.date(2026,8,17).isoformat().replace('-','')}.csv"
    clean[clean.pnl < 0].sort_values("pnl").to_csv(out, index=False)
    print(f"\nsaved loser trade list -> {out.relative_to(ROOT)}")


if __name__ == "__main__":
    main()
