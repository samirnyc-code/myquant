"""analyze_august_trades.py — dissect the August 2026 SPX 0DTE desk P&L.

Which strategy families made/lost money, why they closed, and how they behaved by
regime. Realized (closed) trades bucketed by EXIT date (matches the calendar). Saves a
dated per-strategy CSV + prints the tables. Read-only.

Run: .venv/Scripts/python.exe scripts/analyze_august_trades.py
"""
from __future__ import annotations
import sys
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent))
import options_trade_log as tlog

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "data" / "options_sim"


def families(df):
    s = df.strategy_id.astype(str)
    df = df.copy()
    df["timing"] = np.where(s.str.startswith("eod"), "EOD",
                    np.where(s.str.startswith("open"), "Open",
                    np.where(s.str.startswith("gx"), "GexWall", "other")))
    df["structure"] = np.where(s.str.contains("fly"), "iron-fly",
                       np.where(s.str.contains("ic"), "iron-condor",
                       np.where(s.str.contains("bps|bcs"), "vertical-wall", "other")))
    df["side"] = np.where(s.str.endswith("_c") | s.str.contains("bcs"), "call",
                  np.where(s.str.endswith("_p") | s.str.contains("bps"), "put", "both"))
    return df


def stats(g):
    p = g.pnl
    return pd.Series({
        "n": len(g), "win%": round(100 * (p > 0).mean()),
        "total": round(p.sum()), "avg": round(p.mean(), 1),
        "avg_win": round(p[p > 0].mean(), 1) if (p > 0).any() else 0,
        "avg_loss": round(p[p < 0].mean(), 1) if (p < 0).any() else 0,
        "worst": round(p.min()), "best": round(p.max()),
    })


def show(df, by, title):
    if not len(df):
        print(f"\n=== {title} ===\n(no rows)")
        return pd.DataFrame()
    t = df.groupby(by, observed=True).apply(stats, include_groups=False).sort_values("total", ascending=False)
    print(f"\n=== {title} ===")
    print(t.to_string())
    return t


def main():
    d = tlog.load()
    d["pnl"] = pd.to_numeric(d["pnl"], errors="coerce")
    d["ed"] = pd.to_datetime(d["exit_dt"], errors="coerce")
    aug = d[(d.ed >= "2026-08-01") & (d.ed < "2026-09-01") & d.pnl.notna()]
    aug = aug[aug.strategy_id != "incident_orphan"]
    aug = families(aug)
    print(f"August closed trades: {len(aug)}   realized ${aug.pnl.sum():,.0f}   "
          f"win {100*(aug.pnl>0).mean():.0f}%")

    per_strat = show(aug, "strategy_id", "by STRATEGY")
    show(aug, "structure", "by STRUCTURE (fly vs condor vs wall)")
    show(aug, "timing", "by TIMING (EOD vs Open vs GexWall)")
    show(aug, "side", "by SIDE (call vs put)")

    # close reason: expired (held to settle) vs stopped (level accepted / wall broke) vs traded
    aug = aug.copy()
    cr = aug.close_reason.astype(str)
    aug["outcome"] = np.where(cr.str.startswith("expired"), "expired-held",
                     np.where(cr.str.contains("ACCEPTED|wall"), "STOPPED (wall broke)",
                     np.where(cr.str.contains("traded"), "traded-to-close", "other")))
    show(aug, "outcome", "by CLOSE REASON")

    # regime buckets
    aug["vix_bkt"] = pd.cut(pd.to_numeric(aug.vix, errors="coerce"), [0, 14, 16, 100],
                            labels=["VIX<14", "VIX14-16", "VIX>16"])
    show(aug[aug.vix_bkt.notna()], "vix_bkt", "by VIX")
    if aug.gex_regime.notna().any():
        show(aug[aug.gex_regime.astype(str) != "nan"], "gex_regime", "by GEX REGIME")

    f = OUT / "analysis_august_by_strategy.csv"
    per_strat.to_csv(f)
    print(f"\nwrote {f}")


if __name__ == "__main__":
    main()
