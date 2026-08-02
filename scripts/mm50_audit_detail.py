#!/usr/bin/env python
"""mm50_audit_detail.py — S92-EA: PROVE the 50% MM trades (no edge claims, just mechanics).

Loads the trades written by halsey_mm50_engine.py, rebuilds the identical 15M frame, and for
a chosen month prints EXACT per-trade detail with timestamps + prices so each trade can be
verified by hand, plus an explicit CAUSALITY AUDIT answering:
  - Was the swing H/L KNOWN before the 50% fill?  (leg confirmation time < fill time?)
  - Any forward-looking peeks? (did price exceed the swing H during its confirmation window?)
Renders marked charts (swing H/L + 50/61.8/123 levels + fill/exit) for every day in the month.

Usage: python scripts/mm50_audit_detail.py [YYYY-MM=2026-06] [N=3]
"""
from __future__ import annotations

import sys
from pathlib import Path
import glob as _glob

import numpy as np
import pandas as pd
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.patches import Rectangle

ROOT = Path(__file__).resolve().parent.parent
MASTER_DIR = ROOT / "data" / "nt_internals" / "master"
FIG_DIR = ROOT / "eminiaddict" / "figures" / "mm50_audit"

sys.path.insert(0, str(ROOT / "scripts"))
from halsey_mm50_engine import build_15m  # identical frame  # noqa: E402


def main():
    month = sys.argv[1] if len(sys.argv) > 1 else "2026-06"
    N = int(sys.argv[2]) if len(sys.argv) > 2 else 3
    g = build_15m()
    dt = g["dt"]; H = g["H"].to_numpy(); L = g["L"].to_numpy()
    tr = pd.read_csv(sorted(_glob.glob(str(MASTER_DIR / "mm50_trades_*.csv")))[-1])
    tr = tr[tr["N"] == N].copy()
    tr["dt"] = pd.to_datetime(tr["dt"])
    tr = tr[tr["dt"].dt.strftime("%Y-%m") == month].reset_index(drop=True)
    if tr.empty:
        print(f"! no N={N} trades in {month}"); return

    # map indices -> times/prices
    def gt(i):
        return dt.iloc[int(i)]
    rows = []
    viol_cause = 0; viol_peek = 0
    for _, t in tr.iterrows():
        jL, jH, conf, fill, ex = int(t.jL), int(t.jH), int(t.conf), int(t.fill), int(t.exit)
        swingL_dt, swingH_dt = gt(jL), gt(jH)
        conf_dt, fill_dt, exit_dt = gt(conf), gt(fill), gt(ex)
        # CAUSALITY: leg fully known at conf_dt; entry must be strictly later
        known_before_fill = conf_dt < fill_dt and swingH_dt <= conf_dt and swingL_dt <= conf_dt
        if not known_before_fill:
            viol_cause += 1
        # PEEK: during confirmation window (jH+1..conf) price must NOT exceed the swing H (up)
        # / not undercut swing L (dn) — else the fractal used future info inconsistently
        if t.side == 1:
            peek_ok = H[jH + 1: conf + 1].max(initial=-1e9) <= H[jH] + 1e-9
        else:
            peek_ok = L[jH + 1: conf + 1].min(initial=1e9) >= L[jH] - 1e-9
        if not peek_ok:
            viol_peek += 1
        rows.append({
            "side": "L" if t.side == 1 else "S",
            "swingL_t": swingL_dt.strftime("%m-%d %H:%M"), "swingL_px": round(L[jL], 2),
            "swingH_t": swingH_dt.strftime("%m-%d %H:%M"), "swingH_px": round(H[jH], 2),
            "leg_confirmed": conf_dt.strftime("%m-%d %H:%M"),
            "e50": round(t.e50, 2), "stop618": round(t.stop, 2), "tgt123": round(t.tgt, 2),
            "fill_t": fill_dt.strftime("%m-%d %H:%M"), "fill_px": round(t.e50, 2),
            "exit_t": exit_dt.strftime("%m-%d %H:%M"), "why": t.why, "R": round(t.R, 2),
            "known_before_fill": known_before_fill,
        })
    det = pd.DataFrame(rows)
    print(f"=== N={N} 50% MM trades in {month}: {len(det)} ===")
    with pd.option_context("display.max_columns", None, "display.width", 260):
        print(det.to_string(index=False))
    print(f"\nCAUSALITY AUDIT: {len(det)-viol_cause}/{len(det)} trades had the swing H/L "
          f"confirmed BEFORE the 50% fill (violations={viol_cause}).")
    print(f"FORWARD-PEEK AUDIT: {len(det)-viol_peek}/{len(det)} trades: price never breached the "
          f"swing extreme during its fractal confirmation window (violations={viol_peek}).")
    print("NOTE ON ENTRY: fills are modeled as a RESTING LIMIT at the exact 50% level — filled "
          "when a later bar trades to it. Same-bar target+stop resolves as STOP first "
          "(conservative). Exit 'mtm' = marked to the 15M close at EOD.")

    FIG_DIR.mkdir(parents=True, exist_ok=True)
    det.to_csv(FIG_DIR / f"detail_{month}_N{N}.csv", index=False)

    # marked charts, one per day
    tr["day"] = tr["dt"].dt.normalize()
    for day, td in tr.groupby("day"):
        gg = g[g["day"] == day].reset_index(drop=True)
        if len(gg) < 4:
            continue
        base = g.index[g["day"] == day][0]
        fig, ax = plt.subplots(figsize=(16, 8.5), facecolor="#0b0b0b")
        ax.set_facecolor("#0b0b0b"); ax.tick_params(colors="#aaa")
        for sp in ax.spines.values():
            sp.set_color("#333")
        ax.grid(True, color="#141414", lw=0.5)
        hh = gg["H"].values; ll = gg["L"].values; oo = gg["O"].values; cc = gg["C"].values
        for i in range(len(gg)):
            col = "#26a65b" if cc[i] >= oo[i] else "#e2453c"
            ax.plot([i, i], [ll[i], hh[i]], color=col, lw=1.1, zorder=2)
            ax.add_patch(Rectangle((i - .3, min(oo[i], cc[i])), .6, abs(cc[i] - oo[i]) or .1,
                                   facecolor=col, edgecolor=col, zorder=3))
        for _, t in td.iterrows():
            jL, jH = int(t.jL) - base, int(t.jH) - base
            fk, ek = int(t.fill) - base, int(t.exit) - base
            # swing markers (may be before the day's first bar -> clip)
            if 0 <= jH < len(gg):
                ax.scatter([jH], [hh[jH]], marker="v", s=120, color="#ff5566",
                           edgecolor="#000", zorder=6)
                ax.annotate("swingH", (jH, hh[jH]), textcoords="offset points", xytext=(0, 8),
                            color="#ff5566", fontsize=8, ha="center")
            if 0 <= jL < len(gg):
                ax.scatter([jL], [ll[jL]], marker="^", s=120, color="#33dd88",
                           edgecolor="#000", zorder=6)
                ax.annotate("swingL", (jL, ll[jL]), textcoords="offset points", xytext=(0, -14),
                            color="#33dd88", fontsize=8, ha="center")
            if 0 <= fk < len(gg):
                x1 = max(fk, 0); x2 = min(max(ek, fk + 1), len(gg) - 1)
                ax.hlines(t.e50, x1, x2, color="#ffd400", lw=1.2, zorder=4)
                ax.hlines(t.stop, x1, x2, color="#e2453c", ls=":", lw=1.0, zorder=4)
                ax.hlines(t.tgt, x1, x2, color="#22d3ee", ls="--", lw=1.0, zorder=4)
                ax.scatter([fk], [t.e50], marker=("^" if t.side == 1 else "v"), s=150,
                           color="#fff", edgecolor="#000", zorder=7)
                ax.annotate(f"{t.why} {t.R:+.1f}R", (fk, t.e50), textcoords="offset points",
                            xytext=(4, 6), color="#fff", fontsize=8, fontweight="bold")
        ax.set_title(f"MM 50% trades — {pd.Timestamp(day).date()}  (yellow=50% entry, "
                     f"red:61.8% stop, cyan:123% target)", color="#eee", loc="left")
        step = max(1, len(gg) // 12)
        ax.set_xticks(range(0, len(gg), step))
        ax.set_xticklabels([gg["dt"][i].strftime("%H:%M") for i in range(0, len(gg), step)],
                           color="#aaa", fontsize=8)
        out = FIG_DIR / f"day_{pd.Timestamp(day).strftime('%Y%m%d')}.png"
        fig.tight_layout(); fig.savefig(out, dpi=110, facecolor=fig.get_facecolor()); plt.close(fig)
    print(f"\nwrote per-day marked charts -> {FIG_DIR.relative_to(ROOT)}/  + detail CSV")


if __name__ == "__main__":
    main()
