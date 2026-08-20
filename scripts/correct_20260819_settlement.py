"""correct_20260819_settlement.py — re-book 2026-08-19 to the TRUE official close.

On 2026-08-19 spot_feed froze at 7717.6 and the EOD-hold close used stale/wide
quotes for the near-the-money legs. This re-settles every 0DTE that was held to the
close at the correct intrinsic against the official ^GSPC close (7707.98), using the
CORRECT per-right intrinsic (calls: max(S-K,0), puts: max(K-S,0)). Trades that were
closed intraday on a real fill are left untouched. Backs up the parquet first and
rewrites the daily_summary aggregate. Idempotent: re-running lands the same values.

    python scripts/correct_20260819_settlement.py            # apply
    python scripts/correct_20260819_settlement.py --dry      # preview only
"""
from __future__ import annotations
import argparse, datetime as dt, json, shutil
from pathlib import Path
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
LOG = ROOT / "data" / "options_log"
SIM = ROOT / "data" / "options_sim"
TRADES = LOG / "trades.parquet"
DATE = "2026-08-19"
TRUE_CLOSE = 7707.98   # official ^GSPC close 2026-08-19


def intrinsic(leg, S):
    k = float(leg["strike"])
    return max(S - k, 0.0) if leg["right"] == "C" else max(k - S, 0.0)


def settle_cost(legs, S):
    """Net debit to flatten at settlement price S (short legs cost, long legs credit)."""
    return sum((intrinsic(l, S) if l["side"] == "sell" else -intrinsic(l, S)) for l in legs)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry", action="store_true")
    a = ap.parse_args()

    d = pd.read_parquet(TRADES)
    d["e"] = pd.to_datetime(d["entry_dt"], errors="coerce")
    mask_day = (d["e"] >= DATE) & (d["e"] < "2026-08-20")

    changes = []
    for i, r in d[mask_day].iterrows():
        if str(r.get("close_reason")) != "expired":
            continue                                    # intraday real fill — leave it
        legs = r["legs"] if isinstance(r["legs"], list) else json.loads(r["legs"])
        new_cost = round(max(settle_cost(legs, TRUE_CLOSE), 0.0), 4)
        old_cost = float(r["exit_cost"])
        fees = (float(r["credit"]) - old_cost) * 100 - float(r["pnl"])   # preserved
        new_pnl = round((float(r["credit"]) - new_cost) * 100 - fees, 2)
        if abs(new_pnl - float(r["pnl"])) < 0.01 and abs(new_cost - old_cost) < 0.001:
            continue                                    # already correct
        changes.append((i, r["strategy_id"], old_cost, new_cost, float(r["pnl"]), new_pnl))
        if not a.dry:
            d.at[i, "exit_cost"] = new_cost
            d.at[i, "pnl"] = new_pnl
            d.at[i, "fill_model"] = "settlement"
            note = f"reconciled to official ^GSPC close {TRUE_CLOSE} on 2026-08-20 (feed froze 7717.6)"
            d.at[i, "entry_note"] = ((str(r.get("entry_note") or "").strip() + " | ") if r.get("entry_note") else "") + note

    print(f"{'strategy':>10} {'old_cost':>9} {'new_cost':>9} {'old_pnl':>9} {'new_pnl':>9}")
    for _, sid, oc, nc, op, np_ in changes:
        print(f"{sid:>10} {oc:>9.2f} {nc:>9.2f} {op:>+9.1f} {np_:>+9.1f}")
    if not changes:
        print("no changes — book already matches the official close.")
        return

    day_after = d[mask_day]
    new_total = round(float(day_after.pnl.sum()), 1)
    print(f"\n8/19 total: {new_total:+.1f}  (was +1884.9)")

    if a.dry:
        print("\n[dry] nothing written.")
        return

    bak = TRADES.with_suffix(f".parquet.bak_{DATE.replace('-','')}")
    shutil.copy2(TRADES, bak)
    d.drop(columns=["e"]).to_parquet(TRADES, index=False)
    print(f"backup -> {bak.name}")
    print(f"written -> {TRADES.relative_to(ROOT)}")

    # --- daily_summary aggregate ---
    ds = SIM / "daily_summary.csv"
    if ds.exists():
        s = pd.read_csv(ds)
        row = s.index[s.date == DATE]
        if len(row):
            j = row[0]
            open_pnl = round(float(day_after[day_after.strategy_id.str.startswith("open")].pnl.sum()), 1)
            s.at[j, "pnl_total"] = new_total
            if "pnl_open" in s.columns:
                s.at[j, "pnl_open"] = open_pnl
            s.to_csv(ds, index=False)
            print(f"daily_summary.csv 8/19 pnl_total -> {new_total:+.1f}, pnl_open -> {open_pnl:+.1f}")


if __name__ == "__main__":
    main()
