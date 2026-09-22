"""Reproduce the DASHBOARD CALENDAR/Analytics P&L basis, then reconstruct it with
the review's removals. Matches options_dashboard.py exactly:

  basis = _shown(tlog.load())            # SPX only (trades.parquet); XSP is a
          - EXCLUDE_DAYS 08-04/08-05      #   separate book, NOT in the calendar
          - dedupe_mirrors                # drop real_paper legs duplicating sim
  pnl   = realized (closed) OR last unrealized mark (open)   # open trades COUNT
  tiles = statAll(): n / total / win / PF / expectancy / avgROI  (JS l.1290)
  maxDD = end-of-day daily-bucket drawdown

Then removes EOD flies (eodfly_*) + Open condors (openic_*). XSP + orphan are
already outside this basis, so no extra step needed for them.

Read-only. Writes a DATED CSV. Changes NOTHING.
  .venv/Scripts/python.exe scripts/calendar_pnl_reconstruct.py
"""
from __future__ import annotations
import sys
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
import options_trade_log as tlog  # noqa: E402

SIM = ROOT / "data" / "options_sim"
OUT = SIM
EXCLUDE_DAYS = {"2026-08-04", "2026-08-05"}          # == options_dashboard.EXCLUDE_DAYS
REMOVE_PREFIX = ("eodfly", "openic")                  # EOD flies + Open condors


def shown(trades):
    ed = pd.to_datetime(trades.entry_dt, errors="coerce").dt.strftime("%Y-%m-%d")
    t = trades[~ed.isin(EXCLUDE_DAYS)].copy()
    return tlog.dedupe_mirrors(t)


def rows_with_pnl(trades, marks_last):
    """One dict/trade with the calendar's pnl rule (open->mark, closed->realized)."""
    out = []
    for _, r in trades.iterrows():
        is_open = pd.isna(r.exit_dt)
        if is_open:
            pnl = marks_last.unreal_pnl.get(r.trade_id) if marks_last is not None else None
        else:
            pnl = float(r.pnl) if pd.notna(r.pnl) else None
        coll = float(r.collateral) if pd.notna(r.collateral) else None
        entry = str(r.entry_dt) if pd.notna(r.entry_dt) else ""
        exitd = str(r.exit_dt) if pd.notna(r.exit_dt) else ""
        bucket = exitd[:10] if (not is_open and exitd) else entry[:10]
        out.append({
            "strategy": r.strategy_id, "open": bool(is_open),
            "pnl": None if pnl is None else float(pnl),
            "roi": None if (pnl is None or not coll) else float(pnl) / coll * 100.0,
            "date": bucket,
        })
    return out


def stat_all(rows):
    """Replicates the JS statAll() tile math (options_dashboard.py ~l.1290)."""
    p = [r["pnl"] for r in rows if r["pnl"] is not None]
    w = [x for x in p if x >= 0]
    losses = [x for x in p if x < 0]
    tot = sum(p)
    pf = (sum(w) / -sum(losses)) if losses else None
    rois = [r["roi"] for r in rows if r["roi"] is not None]
    avgroi = (sum(rois) / len(rois)) if rois else None
    # end-of-day daily-bucket drawdown (the tile's maxDD source)
    byday = {}
    for r in rows:
        if r["pnl"] is None or not r["date"]:
            continue
        byday[r["date"]] = byday.get(r["date"], 0.0) + r["pnl"]
    eq = peak = dd = 0.0
    for d in sorted(byday):
        eq += byday[d]; peak = max(peak, eq); dd = min(dd, eq - peak)
    return {
        "n": len(p), "total": round(tot, 2),
        "win%": round(100.0 * len(w) / len(p), 1) if p else None,
        "PF": round(pf, 2) if pf else None,
        "expectancy": round(tot / len(p), 2) if p else None,
        "avgROI%": round(avgroi, 2) if avgroi is not None else None,
        "maxDD": round(dd, 2),
    }


def show(label, s):
    print(f"  {label:28} n={s['n']:>3}  total=${s['total']:>10,.2f}  win={s['win%']}%  "
          f"PF={s['PF']}  exp=${s['expectancy']}  avgROI={s['avgROI%']}%  maxDD=${s['maxDD']:,.2f}")


def main() -> int:
    trades = shown(tlog.load())
    marks_last = None
    mf = SIM / "marks.csv"
    if mf.exists():
        mk = pd.read_csv(mf)
        if len(mk):
            marks_last = mk.groupby("trade_id").last()

    rows = rows_with_pnl(trades, marks_last)
    kept = [r for r in rows if not r["strategy"].startswith(REMOVE_PREFIX)]
    removed = [r for r in rows if r["strategy"].startswith(REMOVE_PREFIX)]

    print("=== CALENDAR BASIS (should match the dashboard card) ===")
    show("full calendar (as shown)", stat_all(rows))
    print("\n=== REMOVED (EOD flies + Open condors) ===")
    for pre, name in (("eodfly", "EOD flies"), ("openic", "Open condors")):
        show(name, stat_all([r for r in rows if r["strategy"].startswith(pre)]))
    print("\n=== RECONSTRUCTED (calendar basis minus EOD flies minus Open condors) ===")
    s = stat_all(kept)
    show("kept book", s)

    df = pd.DataFrame(kept)
    outp = OUT / "calendar_pnl_reconstruct.csv"
    df.to_csv(outp, index=False)
    print(f"\nremoved {len(removed)} rows;  saved kept rows -> {outp.relative_to(ROOT)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
