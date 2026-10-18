"""dtdb_ibs_inspect.py — inspect the bar-by-bar detail (incl. IBS = Internal Bar
Strength = (Close-Low)/(High-Low)) around one confirmed DT/DB instance, pulling the
instance's own row (p1/p2/confirm/retest bars + CVD divergence numbers) straight from
a dtdb_cvd_backtest.py CSV so nothing is hand-retyped. Marks P1, P2, the NECKLINE BREAK
bar (= the confirm bar -- confirmation IS the neckline break, same bar, same thing),
and the RETEST bar (if one was found) directly in the printed table. Saves a dated CSV.

Look up an instance by day + p1_bar (unique per day in practice):
    python scripts/dtdb_ibs_inspect.py --day 2026-10-13 --p1-bar 675 --window 15
"""
from __future__ import annotations

import argparse
from datetime import datetime
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parent.parent
import sys
sys.path.insert(0, str(ROOT))
from bid_ask_volume_ratio_renko import load_day, rth_only, L1_DIR
from dtdb_cvd_backtest import (build_tick_bars, cvd_hist, CVD_PERIOD, CVD_MODE,
                                neckline_low, neckline_high, RETEST_TOLERANCE_TICKS, TICK)

OUT = L1_DIR / "_analysis"


def find_row(day: str, p1_bar: int) -> pd.Series:
    import glob
    hits = sorted(glob.glob(str(OUT / f"dtdb_cvd_backtest_*.csv")))
    for f in hits:
        df = pd.read_csv(f)
        m = df[(df["day"] == day) & (df["p1_bar"] == p1_bar)]
        if not m.empty:
            return m.iloc[0]
    raise SystemExit(f"no instance found for day={day} p1_bar={p1_bar} in {hits} -- run dtdb_cvd_backtest.py first")


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--day", required=True)
    ap.add_argument("--p1-bar", type=int, required=True)
    ap.add_argument("--ticks", type=int, default=2000)
    ap.add_argument("--window", type=int, default=15, help="bars of context before p1 and after the retest/confirm")
    ap.add_argument("--no-chart", action="store_true")
    a = ap.parse_args()

    row = find_row(a.day, a.p1_bar)
    p1_bar, p2_bar, confirm_bar = int(row.p1_bar), int(row.p2_bar), int(row.confirm_bar)
    retest_bar = None if pd.isna(row.retest_bar) else int(row.retest_bar)

    df = load_day(a.day)
    rth = rth_only(df, a.day)
    bars = build_tick_bars(rth, a.ticks)
    hist = cvd_hist(bars, CVD_PERIOD, CVD_MODE)
    is_top = row.kind == "DT"
    neck = neckline_low(bars, p1_bar, p2_bar) if is_top else neckline_high(bars, p1_bar, p2_bar)
    neck_price = neck[1] if neck else float("nan")
    tol_rt = RETEST_TOLERANCE_TICKS * TICK

    print(f"=== {row.kind}  day={a.day}  P1@{p1_bar}={row.p1_price}  P2@{p2_bar}={row.p2_price}  "
          f"NECKLINE={neck_price:.2f} (bar {neck[0] if neck else '?'}) ===")
    print(f"CVD at P1={row.cvd1:.0f}  CVD at P2={row.cvd2:.0f}  delta={row.cvd_delta:+.0f}  "
          f"agrees={'YES' if row.agrees else 'NO'}")
    if retest_bar is not None:
        band = (f"Low<={neck_price+tol_rt:.2f} & Close>={neck_price:.2f}" if not is_top
                else f"High>={neck_price-tol_rt:.2f} & Close<={neck_price:.2f}")
        print(f"RETEST found at bar {retest_bar} ({retest_bar - confirm_bar} bars after neckline break)  "
              f"CVD delta since break={row.retest_cvd_delta:+.0f}  (retest band: {band})")
    else:
        print(f"no retest found within the watch window")
    print()

    lo = max(0, p1_bar - a.window)
    hi_anchor = retest_bar if retest_bar is not None else confirm_bar
    hi = min(len(bars) - 1, hi_anchor + a.window)
    w = bars.iloc[lo:hi + 1].copy()
    w["bar"] = w.index
    w["delta"] = w["askVol"] - w["bidVol"]
    w["cvd_hist"] = hist[lo:hi + 1]
    rng = (w["high"] - w["low"]).replace(0, pd.NA)
    w["ibs"] = ((w["close"] - w["low"]) / rng).astype(float)
    w["role"] = ""
    roles = [(p1_bar, "<<< P1 (trough 1)"),
             (p2_bar, "<<< P2 (trough 2)"),
             (confirm_bar, "<<< NECKLINE BREAK (confirm)")]
    if retest_bar is not None:
        roles.append((retest_bar, "<<< RETEST"))
    for b, label in roles:
        w.loc[w["bar"] == b, "role"] = label

    cols = ["bar", "t", "open", "high", "low", "close", "ibs", "askVol", "bidVol", "delta", "cvd_hist", "role"]
    out = w[cols].round({"ibs": 2})
    pd.set_option("display.width", 200)
    pd.set_option("display.max_rows", 200)
    print(out.to_string(index=False))

    price_at_confirm = bars["close"].iat[confirm_bar]
    price_20later = bars["close"].iat[min(len(bars) - 1, confirm_bar + 20)]
    price_50later = bars["close"].iat[min(len(bars) - 1, confirm_bar + 50)]
    print(f"\nclose@neckline-break={price_at_confirm:.2f}  +20bars={price_20later:.2f} ({price_20later-price_at_confirm:+.2f})"
          f"  +50bars={price_50later:.2f} ({price_50later-price_at_confirm:+.2f})")

    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    csv_out = OUT / f"dtdb_ibs_inspect_{a.day}_{p1_bar}_{p2_bar}_{stamp}.csv"
    out.to_csv(csv_out, index=False)
    print(f"\nsaved: {csv_out}")

    if not a.no_chart:
        png_out = OUT / f"dtdb_breakdown_{a.day}_{p1_bar}_{p2_bar}_{stamp}.png"
        chart_breakdown(w, row, p1_bar, p2_bar, confirm_bar, retest_bar, neck_price, neck[0], tol_rt, png_out)
        print(f"chart: {png_out}")
        try:
            import subprocess
            subprocess.Popen(["code", "-r", str(png_out)], shell=True)
        except Exception:
            pass
    return 0


def chart_breakdown(w: pd.DataFrame, row: pd.Series, p1_bar: int, p2_bar: int, confirm_bar: int,
                     retest_bar: int | None, neck_price: float, neck_bar: int, tol_rt: float, path: Path):
    """One annotated PNG: price candles + DT/DB structure + CVD rolling-hist + per-bar
    delta, all on the SAME x (bar index), every marker direct-labeled with a leader so
    nothing has to be cross-referenced against a separate table."""
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    plt.style.use("dark_background")
    up_c, dn_c = "#2f6fed", "#f2f2f2"      # same up/down convention as every other chart in this repo
    agree_c, disagree_c = "#00e5ff", "#888888"
    is_top = row.kind == "DT"

    x0 = int(w["bar"].iloc[0])
    xs = (w["bar"] - x0).to_numpy()
    n = len(w)

    fig, (axp, axc, axd) = plt.subplots(
        3, 1, figsize=(max(16, n * 0.55), 13), sharex=True,
        gridspec_kw={"height_ratios": [2.2, 1, 0.8]})
    fig.patch.set_facecolor("black")
    agree_txt = "CVD AGREES" if row.agrees else "CVD DISAGREES"
    fig.suptitle(f"ES {row.day}  ·  {row.kind} @ bar {p1_bar}->{p2_bar}  ·  {agree_txt} "
                 f"(ΔCVD {row.cvd_delta:+.0f})", fontsize=14, color="white", fontweight="bold")

    # ---- panel 1: price ----
    for i, r in w.iterrows():
        xi = r["bar"] - x0
        c = up_c if r["close"] >= r["open"] else dn_c
        axp.plot([xi, xi], [r["low"], r["high"]], color=c, lw=1.2, zorder=2)
        blo, bhi = min(r["open"], r["close"]), max(r["open"], r["close"])
        from matplotlib.patches import Rectangle
        axp.add_patch(Rectangle((xi - 0.33, blo), 0.66, max(bhi - blo, 0.01), facecolor=c, edgecolor=c, lw=0.3, zorder=3))

    p1x, p2x, cx = p1_bar - x0, p2_bar - x0, confirm_bar - x0
    p1y, p2y = row.p1_price, row.p2_price
    struct_c = "#e74c3c" if is_top else "#2ecc71"
    axp.plot([p1x, neck_bar - x0, p2x], [p1y, neck_price, p2y], color=struct_c, lw=1.8, zorder=4, alpha=0.9)
    peak = max(p1y, p2y) if is_top else min(p1y, p2y)
    axp.plot([p1x, p2x], [peak, peak], color="white", lw=2.2, zorder=4)
    axp.hlines(neck_price, neck_bar - x0, cx, colors="yellow", linestyles="dashed", lw=1.5, zorder=4)

    def label(ax, x, y, text, dx, dy, color):
        ax.annotate(text, xy=(x, y), xytext=(x + dx, y + dy), color=color, fontsize=10, fontweight="bold",
                     ha="left" if dx >= 0 else "right", va="center", zorder=6,
                     arrowprops=dict(arrowstyle="-", color=color, lw=1.0, alpha=0.8),
                     bbox=dict(boxstyle="round,pad=0.3", fc="black", ec=color, alpha=0.85))

    yr = w["high"].max() - w["low"].min()
    label(axp, p1x, p1y, f"P1 trough  {p1y:.2f}", -2, -yr * 0.18 if is_top else -yr * 0.22, struct_c)
    label(axp, p2x, p2y, f"P2 trough  {p2y:.2f}", 1.5, -yr * 0.14, struct_c)
    label(axp, (neck_bar - x0 + cx) / 2, neck_price, f"NECKLINE {neck_price:.2f}", 0, yr * 0.10, "yellow")
    label(axp, cx, w.loc[w["bar"] == confirm_bar, "close"].iat[0],
          f"NECKLINE BREAK (confirm)\nclose {w.loc[w['bar']==confirm_bar,'close'].iat[0]:.2f}", 1.5, yr * 0.20, "white")
    if retest_bar is not None:
        rx = retest_bar - x0
        ry = w.loc[w["bar"] == retest_bar, "close"].iat[0]
        label(axp, rx, ry, f"RETEST\nclose {ry:.2f}  ΔCVD {row.retest_cvd_delta:+.0f}", 1.5, yr * 0.12, agree_c)

    axp.set_ylabel("price", color="white")
    axp.grid(alpha=0.15, color="gray")
    axp.tick_params(colors="white")

    # ---- panel 2: rolling CVD hist (the actual divergence line) ----
    axc.plot(xs, w["cvd_hist"], color="#f1c40f", lw=1.8, zorder=3)
    axc.axhline(0, color="gray", lw=0.6, alpha=0.5)
    axc.scatter([p1x, p2x], [row.cvd1, row.cvd2], color=struct_c, s=60, zorder=5)
    cvd_span = max(w["cvd_hist"].max() - w["cvd_hist"].min(), 1000)
    axc.annotate(f"CVD@P1 {row.cvd1:.0f}", (p1x, row.cvd1), xytext=(p1x - 4, row.cvd1 + cvd_span * 0.30),
                 color=struct_c, fontsize=9, ha="center",
                 bbox=dict(boxstyle="round,pad=0.25", fc="black", ec=struct_c, alpha=0.9),
                 arrowprops=dict(arrowstyle="-", color=struct_c, lw=0.8))
    axc.annotate(f"CVD@P2 {row.cvd2:.0f}\n(Δ {row.cvd_delta:+.0f})", (p2x, row.cvd2),
                 xytext=(p2x, row.cvd2 - cvd_span * 0.45),
                 color=struct_c, fontsize=9, ha="center",
                 bbox=dict(boxstyle="round,pad=0.25", fc="black", ec=struct_c, alpha=0.9),
                 arrowprops=dict(arrowstyle="-", color=struct_c, lw=0.8))
    axc.axvline(cx, color="white", lw=0.8, ls="dotted", alpha=0.6)
    if retest_bar is not None:
        axc.axvline(retest_bar - x0, color=agree_c, lw=0.8, ls="dotted", alpha=0.6)
    axc.set_ylabel(f"CVD (rolling {CVD_PERIOD}-bar sum)", color="white", fontsize=9)
    axc.grid(alpha=0.15, color="gray")
    axc.tick_params(colors="white")

    # ---- panel 3: per-bar delta (what's actually happening bar to bar) ----
    colors = [up_c if d >= 0 else dn_c for d in w["delta"]]
    axd.bar(xs, w["delta"], color=colors, width=0.7, zorder=3)
    axd.axhline(0, color="gray", lw=0.6)
    axd.set_ylabel("per-bar delta\n(ask-bid vol)", color="white", fontsize=9)
    axd.set_xlabel("bar", color="white")
    axd.grid(alpha=0.15, color="gray")
    axd.tick_params(colors="white")
    step = max(1, n // 25)
    ticks = list(range(0, n, step))
    axd.set_xticks([xs[i] for i in ticks])
    axd.set_xticklabels([str(w["bar"].iloc[i]) for i in ticks], rotation=0, fontsize=8, color="white")

    fig.tight_layout(rect=[0, 0, 1, 0.96])
    fig.savefig(path, dpi=150, bbox_inches="tight", facecolor="black")
    plt.close(fig)


if __name__ == "__main__":
    raise SystemExit(main())
