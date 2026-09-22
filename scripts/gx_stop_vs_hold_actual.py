"""gx_stop_vs_hold_actual.py — did the desk stop help or hurt the REAL gx book?

No model of the trades. Uses the LIVE book's ACTUAL gx_bps/gx_bcs trades (real strikes,
real credit, real realized P&L, real close_reason) from trades.parquet, and computes ONE
counterfactual per trade: what it would have made HELD TO SETTLEMENT (short-strike
intrinsic at the SPX close, clamped [0,wing]). Only inputs: the trade's own credit + the
SPX close. No parity, no fill guessing, no wall re-derivation.

SELF-CHECK (the whole point): for trades that were NOT stopped (expired / traded-to-close),
realized P&L MUST equal the held-to-settle computation. The script prints that match error.
If it's not ~0, the credit units / settlement logic are wrong and the numbers below are void
-- it will say so rather than pretend.

Read-only. Writes a dated CSV.
  .venv/Scripts/python.exe scripts/gx_stop_vs_hold_actual.py
"""
from __future__ import annotations
import json
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
TRADES = ROOT / "data" / "options_log" / "trades.parquet"
SPXF = ROOT / "data" / "options_sim" / "spx_daily_yahoo.csv"
OUT = ROOT / "data" / "options_sim"
WING = 25.0
MULT = 100.0


def _legs(v):
    if isinstance(v, list):
        return v
    try:
        return json.loads(v) if isinstance(v, str) and v.strip() else []
    except json.JSONDecodeError:
        return []


def main() -> int:
    spx = pd.read_csv(SPXF)
    close = dict(zip(spx["Date"].astype(str).str[:10], pd.to_numeric(spx["Close"], errors="coerce")))

    t = pd.read_parquet(TRADES)
    g = t[t["strategy_id"].isin(["gx_bps", "gx_bcs"]) & t["exit_dt"].notna()].copy()
    g["date"] = g["entry_dt"].astype(str).str[:10]

    rows = []
    for _, r in g.iterrows():
        legs = _legs(r["legs"])
        short = next((l for l in legs if l.get("side") == "sell"), None)
        if not short:
            continue
        K, right = float(short["strike"]), (short.get("right") or "").upper()
        sc = close.get(r["date"])
        if sc is None or pd.isna(r.get("credit")):
            continue
        credit = float(r["credit"])
        liab = min(WING, max(0.0, (K - sc) if right == "P" else (sc - K)))
        # try credit as POINTS; the self-check below tells us if that's right
        settle_gross = (credit - liab) * MULT
        stopped = "ACCEPT" in str(r.get("close_reason", "")).upper()
        rows.append({
            "date": r["date"], "strat": r["strategy_id"], "right": right, "K": K,
            "spx_close": sc, "credit": credit, "settle_liab": round(liab, 2),
            "settle_gross": round(settle_gross, 2), "realized": round(float(r["pnl"]), 2),
            "stopped": stopped, "close_reason": str(r.get("close_reason", ""))[:40],
        })
    d = pd.DataFrame(rows)
    if not len(d):
        print("no gx trades with credit + SPX close"); return 1

    held = d[~d["stopped"]]
    # SELF-CHECK: realized should ~= settle_gross (minus fees) for non-stopped trades
    print("=== SELF-CHECK (non-stopped trades: realized vs held-to-settle computation) ===")
    if len(held):
        err = (held["realized"] - held["settle_gross"])
        print(f"  n non-stopped = {len(held)}")
        print(f"  realized - settle_gross:  mean {err.mean():+.1f}  median {err.median():+.1f}  "
              f"std {err.std():.1f}   (should be a small ~constant = round-trip fees; NOT noisy)")
        print(f"  -> {'OK: consistent, credit is in POINTS, fees ~= the offset' if err.std() < 30 else 'FAIL: noisy/large — credit units or settle logic WRONG; numbers below are VOID'}")
    else:
        print("  (no non-stopped gx trades to check against)")

    fee_offset = held["realized"].mean() - held["settle_gross"].mean() if len(held) else 0.0
    d["settle_net"] = d["settle_gross"] + fee_offset      # apply the inferred fee offset

    print("\n=== STOPPED trades: what the stop did vs holding ===")
    stp = d[d["stopped"]].copy()
    stp["stop_minus_hold"] = stp["realized"] - stp["settle_net"]
    for _, r in stp.iterrows():
        print(f"  {r.date} {r.strat:7} {r.right} {r.K:.0f}  realized {r.realized:>8.0f}  "
              f"held~{r.settle_net:>8.0f}  stop {'SAVED' if r.stop_minus_hold>=0 else 'COST'} {r.stop_minus_hold:>8.0f}")

    print("\n=== TOTALS (actual real gx book) ===")
    print(f"  trades: {len(d)}  (stopped {int(d.stopped.sum())}, held {len(held)})")
    print(f"  ACTUAL realized (with the stop) : {d.realized.sum():>10,.0f}")
    print(f"  counterfactual HELD-to-settle   : {d.settle_net.sum():>10,.0f}")
    print(f"  stop's net effect on the book   : {d.realized.sum()-d.settle_net.sum():>10,.0f}")
    if len(stp):
        print(f"  on the {len(stp)} STOPPED trades: stop net {stp.stop_minus_hold.sum():>+,.0f} "
              f"(saved {int((stp.stop_minus_hold>0).sum())}, cost {int((stp.stop_minus_hold<0).sum())})")

    outp = OUT / f"gx_stop_vs_hold_actual_{d.date.max().replace('-','')}.csv"
    d.to_csv(outp, index=False)
    print(f"\nsaved -> {outp.relative_to(ROOT)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
