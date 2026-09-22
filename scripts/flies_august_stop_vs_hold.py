"""flies_august_stop_vs_hold.py — the ATM flys in August: ACTUAL P&L (with the desk
stop) vs the counterfactual with the stop REMOVED (held to settlement).

Real trades only (eodfly_p/c, openfly_p/c from trades.parquet). No model. Held-to-settle
= (real credit - short-strike intrinsic at SPX close) clamped [0,wing]. SELF-CHECK: any
fly NOT stopped must have realized == held (up to a constant fee); printed.
"""
from __future__ import annotations
import json
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
TRADES = ROOT / "data" / "options_log" / "trades.parquet"
SPXF = ROOT / "data" / "options_sim" / "spx_daily_yahoo.csv"
WING, MULT = 25.0, 100.0
FLIES = ["eodfly_p", "eodfly_c", "openfly_p", "openfly_c"]


def main() -> int:
    spx = pd.read_csv(SPXF)
    close = dict(zip(spx["Date"].astype(str).str[:10], pd.to_numeric(spx["Close"], errors="coerce")))
    t = pd.read_parquet(TRADES)
    g = t[t["strategy_id"].isin(FLIES) & t["exit_dt"].notna()].copy()
    g["date"] = g["entry_dt"].astype(str).str[:10]
    g = g[g["date"] >= "2026-08-01"]

    rows = []
    for _, r in g.iterrows():
        legs = r["legs"] if isinstance(r["legs"], list) else json.loads(r["legs"])
        sh = next((l for l in legs if l.get("side") == "sell"), None)
        sc = close.get(r["date"])
        if not sh or sc is None or pd.isna(r.get("credit")):
            continue
        K, right = float(sh["strike"]), (sh.get("right") or "").upper()
        liab = min(WING, max(0.0, (K - sc) if right == "P" else (sc - K)))
        rows.append({
            "date": r["date"], "strat": r["strategy_id"], "K": K, "right": right,
            "spx_close": sc, "credit": float(r["credit"]),
            "realized_WITH_stop": round(float(r["pnl"]), 2),
            "held_NO_stop_gross": round((float(r["credit"]) - liab) * MULT, 2),
            "stopped": "ACCEPT" in str(r.get("close_reason", "")).upper(),
        })
    d = pd.DataFrame(rows)
    if not len(d):
        print("no August fly trades found"); return 1

    held = d[~d["stopped"]]
    off = (held["realized_WITH_stop"] - held["held_NO_stop_gross"]).mean() if len(held) else 0.0
    ok = bool(len(held) and (held["realized_WITH_stop"] - held["held_NO_stop_gross"]).std() < 30)
    d["held_NO_stop"] = d["held_NO_stop_gross"] + off       # fee-consistent

    print(f"August fly trades: {len(d)}  (stopped {int(d.stopped.sum())}, held-to-settle {len(held)})")
    print(f"self-check (non-stopped realized == held): {'PASS' if ok else 'FAIL — VOID'}  (fee offset {off:+.1f})\n")

    print(f"{'strat':11}{'n':>4}{'WITH stop $':>13}{'NO stop (held) $':>18}{'stop effect':>13}")
    tot_w = tot_h = 0.0
    for s in FLIES:
        x = d[d["strat"] == s]
        if not len(x):
            continue
        w, h = x["realized_WITH_stop"].sum(), x["held_NO_stop"].sum()
        tot_w += w; tot_h += h
        print(f"{s:11}{len(x):>4}{w:>13,.0f}{h:>18,.0f}{w-h:>13,.0f}")
    print(f"{'ALL FLIES':11}{len(d):>4}{tot_w:>13,.0f}{tot_h:>18,.0f}{tot_w-tot_h:>13,.0f}")

    print("\nstopped fly trades (what the stop did to each):")
    for _, r in d[d["stopped"]].sort_values("date").iterrows():
        eff = r["realized_WITH_stop"] - r["held_NO_stop"]
        print(f"  {r.date} {r.strat:10} {r.right} {r.K:.0f}  with_stop {r.realized_WITH_stop:>8.0f}  "
              f"no_stop {r.held_NO_stop:>8.0f}  stop {'SAVED' if eff>=0 else 'COST'} {eff:>8.0f}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
