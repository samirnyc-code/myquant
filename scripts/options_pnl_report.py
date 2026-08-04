"""Clean P&L report for the premium-selling forward test.

Attributes every closed trade to its STREAM (algo / gexlog / stmr) and the day's
GexLog signal (GO / CAUTION / WAIT), then reports:
  1. per single-leg spread (each strategy_id)
  2. per STREAM  (algo vs gexlog vs stmr)
  3. reconstructed STRUCTURES  (algo iron condor / iron fly, gexlog iron condor)
     = the two legs summed per day
  4. by GexLog signal bucket
  5. the cross-tab  STREAM x SIGNAL  (the headline comparison)

stream is derived from strategy_id (no schema change): gx_* -> gexlog,
sell_bps/bcs[/_atm] -> algo, bps_stmr -> stmr, everything else -> legacy (old MQ).
The signal is joined from data/options_sim/gameplan_YYYYMMDD.json (gexlog block).

Headline metric is P&L WITH TAILS (PF, total, maxDD, worst-5% mean), never
win-rate alone. Writes data/options_sim/pnl_report_<rundate>.csv.

  .venv/Scripts/python.exe scripts/options_pnl_report.py [--since YYYY-MM-DD] [--all]
"""
import argparse
import json
import sys
from functools import lru_cache
from pathlib import Path

import numpy as np
import pandas as pd

try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

ROOT = Path(__file__).resolve().parents[1]
SIM = ROOT / "data" / "options_sim"
TRADES = ROOT / "data" / "options_log" / "trades.parquet"

ALGO = {"sell_bps", "sell_bcs", "sell_bps_atm", "sell_bcs_atm"}
GEXLOG = {"gx_bps", "gx_bcs"}
# structures reconstructed by summing their two legs' P&L per day
STRUCTS = {
    "algo iron condor": ("algo", {"sell_bps", "sell_bcs"}),
    "algo iron fly":    ("algo", {"sell_bps_atm", "sell_bcs_atm"}),
    "gexlog iron condor": ("gexlog", {"gx_bps", "gx_bcs"}),
}


def stream_of(sid):
    sid = str(sid)
    if sid in GEXLOG:
        return "gexlog"
    if sid in ALGO:
        return "algo"
    if sid == "bps_stmr":
        return "stmr"
    return "legacy"


@lru_cache(maxsize=None)
def signal_for(date_ymd):
    """GO/CAUTION/WAIT for a date (YYYYMMDD) from that day's gameplan JSON."""
    p = SIM / f"gameplan_{date_ymd}.json"
    if not p.exists():
        return "unknown"
    try:
        d = json.loads(p.read_text(encoding="utf-8"))
        return d.get("gexlog", {}).get("signal_bucket", "unknown")
    except Exception:
        return "unknown"


def stats(pnl):
    p = np.asarray(pnl, float)
    p = p[~np.isnan(p)]
    if len(p) == 0:
        return dict(n=0, win=np.nan, pf=np.nan, total=0.0, avg=np.nan, mdd=np.nan, tail=np.nan)
    eq = np.cumsum(p)
    mdd = float((eq - np.maximum.accumulate(eq)).min())
    wins, losses = p[p > 0].sum(), -p[p < 0].sum()
    pf = wins / losses if losses > 0 else np.inf
    tail = float(np.mean(np.sort(p)[:max(1, len(p) // 20)]))
    return dict(n=len(p), win=(p > 0).mean() * 100, pf=pf, total=p.sum(),
                avg=p.mean(), mdd=mdd, tail=tail)


def row(label, s):
    if s["n"] == 0:
        return f"  {label:22} {'—':>5}"
    pf = "inf" if np.isinf(s["pf"]) else f"{s['pf']:.2f}"
    return (f"  {label:22}{s['n']:>4}{s['total']:>+11,.0f}{pf:>7}{s['win']:>6.0f}%"
            f"{s['mdd']:>+11,.0f}{s['tail']:>+10,.0f}{s['avg']:>+9,.0f}")


HEAD = f"  {'':22}{'n':>4}{'total$':>11}{'PF':>7}{'win':>7}{'maxDD$':>11}{'tail$':>10}{'avg$':>9}"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--since", help="only trades entered on/after this date (YYYY-MM-DD)")
    ap.add_argument("--all", action="store_true", help="include legacy/MQ strategies too")
    args = ap.parse_args()

    if not TRADES.exists():
        print("no trades.parquet yet."); return
    df = pd.read_parquet(TRADES)
    df = df[df.exit_dt.notna()].copy()                      # closed only
    if df.empty:
        print("no closed trades yet."); return
    df["entry_date"] = df.entry_dt.astype(str).str[:10]
    if args.since:
        df = df[df.entry_date >= args.since]
    df["stream"] = df.strategy_id.map(stream_of)
    df["ymd"] = df.entry_date.str.replace("-", "", regex=False)
    df["signal"] = df.ymd.map(signal_for)
    df["pnl"] = pd.to_numeric(df.pnl, errors="coerce")
    if not args.all:
        df = df[df.stream != "legacy"]
    if df.empty:
        print("no premium-selling trades yet (run with --all for legacy)."); return

    rng = f"{df.entry_date.min()}..{df.entry_date.max()}"
    print(f"\nPREMIUM-SELLING P&L REPORT   {len(df)} closed trades   {rng}\n")

    print("1) PER SPREAD (strategy_id)"); print(HEAD)
    for sid in sorted(df.strategy_id.unique()):
        print(row(sid, stats(df[df.strategy_id == sid].pnl)))

    print("\n2) PER STREAM"); print(HEAD)
    for st in ("algo", "gexlog", "stmr"):
        print(row(st, stats(df[df.stream == st].pnl)))

    print("\n3) RECONSTRUCTED STRUCTURES (two legs summed per day)"); print(HEAD)
    for label, (stream, legs) in STRUCTS.items():
        sub = df[df.strategy_id.isin(legs)]
        daily = sub.groupby("entry_date").pnl.sum()      # both legs same day = the structure
        print(row(label, stats(daily.values)))

    print("\n4) BY GEXLOG SIGNAL (all premium trades)"); print(HEAD)
    for sig in ("GO", "CAUTION", "WAIT", "unknown"):
        s = stats(df[df.signal == sig].pnl)
        if s["n"]:
            print(row(sig, s))

    print("\n5) STREAM x SIGNAL  (total$ / PF / n)")
    print(f"  {'stream':10}" + "".join(f"{sig:>18}" for sig in ("GO", "CAUTION", "WAIT")))
    for st in ("algo", "gexlog", "stmr"):
        cells = []
        for sig in ("GO", "CAUTION", "WAIT"):
            s = stats(df[(df.stream == st) & (df.signal == sig)].pnl)
            cells.append(f"{'—':>18}" if s["n"] == 0 else
                         f"{s['total']:+,.0f}/{('inf' if np.isinf(s['pf']) else f'{s['pf']:.1f}')}/{s['n']:>18}"[-18:])
        print(f"  {st:10}" + "".join(cells))

    out = SIM / f"pnl_report_{pd.Timestamp.today():%Y%m%d}.csv"
    df[["trade_id", "entry_date", "strategy_id", "stream", "signal", "structure",
        "credit", "pnl", "roc", "win", "close_reason"]].to_csv(out, index=False)
    print(f"\nwrote {out.relative_to(ROOT)}")


if __name__ == "__main__":
    main()
