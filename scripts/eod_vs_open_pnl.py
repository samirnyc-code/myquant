"""Compare realized PnL of EOD-centered vs Open-centered premium-selling trades.

The sim arms every structure in parallel (see options_gameplan.py). The clean A/B
is CENTER anchoring: EOD-centered strikes = prior close +/- EM (strategy_id
eodic_*/eodfly_*), Open-centered = open spot +/- the SAME EM (openic_*/openfly_*).
This reads the realized trade logs, buckets by center, and reports PnL/win/PF.

Read-only. Writes a DATED summary CSV; changes NOTHING in any strategy.
  .venv/Scripts/python.exe scripts/eod_vs_open_pnl.py
"""
from __future__ import annotations
import datetime as dt
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
LOG = ROOT / "data" / "options_log"
OUT = ROOT / "data" / "options_sim"

SRC = [("SPX", LOG / "trades.parquet"), ("XSP", LOG / "trades_xsp.parquet")]


def center(sid: str) -> str:
    if sid.startswith("eod"):
        return "EOD"
    if sid.startswith("open"):
        return "Open"
    return "other"


def kind(sid: str) -> str:
    if "ic_" in sid:
        return "condor"
    if "fly" in sid:
        return "fly"
    return "other"


def stats(g: pd.DataFrame) -> dict:
    pnl = pd.to_numeric(g["pnl"], errors="coerce")
    wins = pnl[pnl > 0].sum()
    losses = -pnl[pnl < 0].sum()
    return {
        "n": len(g),
        "pnl": round(float(pnl.sum()), 2),
        "avg": round(float(pnl.mean()), 2) if len(g) else 0.0,
        "win%": round(100.0 * (pnl > 0).mean(), 1) if len(g) else 0.0,
        "PF": round(float(wins / losses), 2) if losses > 0 else float("inf"),
        "roc%": round(100.0 * pd.to_numeric(g["roc"], errors="coerce").mean(), 2),
    }


def main() -> int:
    frames = []
    for sym, p in SRC:
        if not p.exists():
            continue
        t = pd.read_parquet(p)
        t = t[t["exit_dt"].notna()].copy()          # closed trades only
        t["sym"] = sym
        t["center"] = t["strategy_id"].map(center)
        t["kind"] = t["strategy_id"].map(kind)
        frames.append(t)
    if not frames:
        print("no trade logs found")
        return 1
    df = pd.concat(frames, ignore_index=True)
    ab = df[df["center"].isin(["EOD", "Open"])].copy()

    rows = []
    print(f"Closed trades: {len(df)} total | EOD/Open A/B universe: {len(ab)}")
    print(f"Date range: {df['entry_dt'].min()} .. {df['entry_dt'].max()}\n")

    def block(title, sub):
        print(f"=== {title} ===")
        if not len(sub):
            print("  (none)\n"); return
        for c in ("EOD", "Open"):
            s = stats(sub[sub["center"] == c])
            s.update({"scope": title, "center": c})
            rows.append(s)
            print(f"  {c:5} n={s['n']:>3}  pnl=${s['pnl']:>10,.2f}  avg=${s['avg']:>8,.2f}"
                  f"  win={s['win%']:>5}%  PF={s['PF']:>5}  roc={s['roc%']:>6}%")
        print()

    # per symbol, condor-only (cleanest A/B), then fly, then all-centered
    for sym in ("SPX", "XSP"):
        s = ab[ab["sym"] == sym]
        block(f"{sym} condor (eodic vs openic)", s[s["kind"] == "condor"])
        block(f"{sym} fly (eodfly vs openfly)", s[s["kind"] == "fly"])
    block("ALL symbols, condor only", ab[ab["kind"] == "condor"])
    block("ALL symbols, condor + fly", ab)

    stamp = df["entry_dt"].max()
    stamp = str(stamp)[:10] if pd.notna(stamp) else "unknown"
    outp = OUT / f"eod_vs_open_pnl_{stamp}.csv"
    pd.DataFrame(rows).to_csv(outp, index=False)
    print(f"saved -> {outp.relative_to(ROOT)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
