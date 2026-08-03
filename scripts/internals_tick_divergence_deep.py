#!/usr/bin/env python
"""internals_tick_divergence_deep.py — S92-EA Phase 1 deep-dive on TICK + divergence.

Answers two questions the user asked:
  A. HOW FAR did price move from each turning point before the pivot was BROKEN?
     - swing HIGH is "broken" when a later bar trades ABOVE the high (mirror for lows).
     - reversal excursion = how far price traveled the reversal way (down from a high /
       up from a low) BEFORE the break. Measured within the SAME RTH day (internals reset
       daily; no overnight-gap contamination); censored = not broken by EOD.
     - split by whether the MATCHING TICK divergence / TICK>=800 was present at the pivot,
       to preview whether internals-confirmed turns travel farther.
  B. MARK the pivot bars and COLOR-CODE the divergences on example days (candles + TICK
     panel). bull_div = price new day-high w/o new day high-tick; bear_div = mirror.

Outputs:
  data/nt_internals/master/phase1_excursion_<stamp>.csv   per-pivot excursion + flags
  data/nt_internals/master/phase1_excursion_summary_<stamp>.csv
  eminiaddict/figures/phase1_marked_<YYYYMMDD>.png         example marked days

Usage: python scripts/internals_tick_divergence_deep.py [minbars=3] [n_example_days=4]
"""
from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pandas as pd
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.patches import Rectangle

ROOT = Path(__file__).resolve().parent.parent
MASTER_DIR = ROOT / "data" / "nt_internals" / "master"
FIG_DIR = ROOT / "eminiaddict" / "figures"
DIV_WINDOW = 3
ES_TICK = 0.25  # ES point size irrelevant; excursion reported in POINTS

# colors
C_UP, C_DN = "#26a65b", "#e2453c"
C_BULLDIV = "#22d3ee"   # cyan  — price new high, NO new high-tick (bull divergence)
C_BEARDIV = "#f59e0b"   # amber — price new low,  NO new low-tick  (bear divergence)
C_CONFIRM = "#a855f7"   # purple — tick & price new extreme TOGETHER (divergence ends)
C_PIVH, C_PIVL = "#ff5566", "#33dd88"


def struct_swings(H, L, minbars=0):
    """Reversal-bar structural swings (verbatim from swings_test.py). -> [(i,price,'H'|'L')]"""
    n = len(H); piv = []; d = 0
    hi_i, hi = 0, H[0]; lo_i, lo = 0, L[0]

    def push(i, p, k):
        if piv and piv[-1][2] == k:
            if (k == 'H' and p >= piv[-1][1]) or (k == 'L' and p <= piv[-1][1]):
                piv[-1] = (i, p, k)
            return
        if minbars and piv and abs(i - piv[-1][0]) < minbars:
            return
        piv.append((i, p, k))

    for i in range(1, n):
        if d >= 0:
            if H[i] >= hi:
                hi, hi_i = H[i], i
            elif L[i] < L[hi_i]:
                push(hi_i, hi, 'H'); d = -1; lo, lo_i = L[i], i
        if d <= 0:
            if L[i] <= lo:
                lo, lo_i = L[i], i
            elif H[i] > H[lo_i]:
                push(lo_i, lo, 'L'); d = 1; hi, hi_i = H[i], i
    return piv


def add_div_flags(m: pd.DataFrame) -> pd.DataFrame:
    m = m.copy()
    day = m["DateTime"].dt.normalize()
    for src, dst in (("bull_div", "bull_div_near"), ("bear_div", "bear_div_near")):
        flag = m[src].fillna(False).astype(int)
        m[dst] = flag.groupby(day).transform(
            lambda s: s.rolling(DIV_WINDOW + 1, min_periods=1).max()).astype(bool)
    # confirmation bars: tick AND price make a new day extreme together (divergence ends)
    m["confirm_hi"] = m["px_new_hi"] & m["tick_new_hi"]
    m["confirm_lo"] = m["px_new_lo"] & m["tick_new_lo"]
    return m


def excursion_study(m: pd.DataFrame, minbars: int):
    recs = []
    for _day, g in m.groupby(m["DateTime"].dt.normalize()):
        g = g.reset_index(drop=True)
        if len(g) < 6:
            continue
        H = g["es_high"].values; L = g["es_low"].values
        piv = struct_swings(H, L, minbars)
        n = len(g)
        for j, price, kind in piv:
            fwd = range(j + 1, n)
            broken = False; brk_off = n - 1 - j; exc = 0.0
            if kind == "H":
                best = np.inf
                for off, k in enumerate(fwd, start=1):
                    best = min(best, L[k])
                    if H[k] > price:  # broken: new high above the swing high
                        broken = True; brk_off = off; break
                exc = price - best if np.isfinite(best) else 0.0
                bull = bool(g.loc[j, "bull_div_near"]); bear = bool(g.loc[j, "bear_div_near"])
                match_div = bull
                match_confirm = bool(g.loc[j, "confirm_hi"])
            else:
                best = -np.inf
                for off, k in enumerate(fwd, start=1):
                    best = max(best, H[k])
                    if L[k] < price:  # broken: new low below the swing low
                        broken = True; brk_off = off; break
                exc = best - price if np.isfinite(best) else 0.0
                bull = bool(g.loc[j, "bull_div_near"]); bear = bool(g.loc[j, "bear_div_near"])
                match_div = bear
                match_confirm = bool(g.loc[j, "confirm_lo"])
            recs.append({
                "DateTime": g.loc[j, "DateTime"], "kind": kind, "price": price,
                "excursion_pts": round(max(exc, 0.0), 2),
                "bars_to_break": brk_off, "broken_same_day": broken,
                "match_div": match_div, "match_confirm": match_confirm,
                "tick_bar_ext": g.loc[j, "tick_bar_ext"],
                "tick_800": bool(g.loc[j, "tick_extreme_800"]),
                "tick_1000": bool(g.loc[j, "tick_extreme_1000"]),
                "trin": g.loc[j, "trin_level"], "vix": g.loc[j, "vix_level"],
            })
    return pd.DataFrame(recs)


def summarize_excursion(ex: pd.DataFrame) -> pd.DataFrame:
    def block(df, label):
        return {
            "group": label, "n": len(df),
            "med_exc_pts": round(df["excursion_pts"].median(), 2),
            "mean_exc_pts": round(df["excursion_pts"].mean(), 2),
            "p75_exc_pts": round(df["excursion_pts"].quantile(0.75), 2),
            "med_bars_to_break": int(df["bars_to_break"].median()),
            "%broken_same_day": round(100 * df["broken_same_day"].mean(), 1),
        }
    rows = []
    for kind, name in (("H", "swing HIGH"), ("L", "swing LOW")):
        d = ex[ex["kind"] == kind]
        rows.append(block(d, f"{name} — ALL"))
        rows.append(block(d[d["match_div"]], f"{name} — matching DIVERGENCE"))
        rows.append(block(d[~d["match_div"]], f"{name} — no divergence"))
        rows.append(block(d[d["tick_800"]], f"{name} — TICK>=800"))
        rows.append(block(d[~d["tick_800"]], f"{name} — TICK<800"))
    return pd.DataFrame(rows)


# ---------- charting ----------
def draw_day(m: pd.DataFrame, day, minbars: int, out: Path):
    g = m[m["DateTime"].dt.normalize() == day].reset_index(drop=True)
    if len(g) < 6:
        return False
    H = g["es_high"].values; L = g["es_low"].values
    O = g["es_open"].values; C = g["es_close"].values
    piv = struct_swings(H, L, minbars)
    n = len(g)

    fig, (ax, axt) = plt.subplots(2, 1, figsize=(16, 9), height_ratios=[3, 1.15],
                                  sharex=True, facecolor="#0b0b0b")
    for a in (ax, axt):
        a.set_facecolor("#0b0b0b"); a.tick_params(colors="#aaa")
        for sp in a.spines.values():
            sp.set_color("#333")
        a.grid(True, color="#141414", lw=0.5)

    # candles + divergence-bar background shading
    for i in range(n):
        col = C_UP if C[i] >= O[i] else C_DN
        ax.plot([i, i], [L[i], H[i]], color=col, lw=0.9, zorder=2)
        ax.add_patch(Rectangle((i - .32, min(O[i], C[i])), .64, abs(C[i] - O[i]) or .05,
                               facecolor=col, edgecolor=col, zorder=3))
        # color-coded divergence shading behind the bar
        if bool(g.loc[i, "bull_div"]):
            ax.axvspan(i - .5, i + .5, color=C_BULLDIV, alpha=.16, zorder=1)
        if bool(g.loc[i, "bear_div"]):
            ax.axvspan(i - .5, i + .5, color=C_BEARDIV, alpha=.16, zorder=1)

    # pivots
    for j, price, kind in piv:
        if kind == "H":
            ax.scatter([j], [H[j]], marker="v", s=90, color=C_PIVH, zorder=6,
                       edgecolor="#000", linewidth=.4)
        else:
            ax.scatter([j], [L[j]], marker="^", s=90, color=C_PIVL, zorder=6,
                       edgecolor="#000", linewidth=.4)

    # TICK panel: high/low as a vertical range, close dot; extreme lines; div/confirm markers
    tkh = g["tick_high"].values; tkl = g["tick_low"].values; tkc = g["tick_close"].values
    for i in range(n):
        if np.isnan(tkh[i]):
            continue
        axt.plot([i, i], [tkl[i], tkh[i]], color="#666", lw=0.8, zorder=2)
        axt.scatter([i], [tkc[i]], s=8, color="#ccc", zorder=3)
        if bool(g.loc[i, "bull_div"]):
            axt.scatter([i], [tkh[i]], s=26, color=C_BULLDIV, zorder=5)
        if bool(g.loc[i, "bear_div"]):
            axt.scatter([i], [tkl[i]], s=26, color=C_BEARDIV, zorder=5)
        if bool(g.loc[i, "confirm_hi"]):
            axt.scatter([i], [tkh[i]], marker="*", s=70, color=C_CONFIRM, zorder=6)
        if bool(g.loc[i, "confirm_lo"]):
            axt.scatter([i], [tkl[i]], marker="*", s=70, color=C_CONFIRM, zorder=6)
    for lv, c in ((1000, "#e2453c"), (800, "#e2453c"), (-800, "#e2453c"), (-1000, "#e2453c")):
        axt.axhline(lv, color=c, ls="--" if abs(lv) == 800 else "-", lw=0.8, alpha=.6)
    axt.axhline(0, color="#444", lw=0.6)
    axt.set_ylabel("NYSE TICK", color="#aaa", fontsize=10)

    # legend (proxy handles)
    from matplotlib.lines import Line2D
    from matplotlib.patches import Patch
    handles = [
        Line2D([], [], marker="v", color="none", markerfacecolor=C_PIVH, markersize=10, label="swing HIGH"),
        Line2D([], [], marker="^", color="none", markerfacecolor=C_PIVL, markersize=10, label="swing LOW"),
        Patch(facecolor=C_BULLDIV, alpha=.5, label="bull div (px new-hi, no new hi-TICK)"),
        Patch(facecolor=C_BEARDIV, alpha=.5, label="bear div (px new-lo, no new lo-TICK)"),
        Line2D([], [], marker="*", color="none", markerfacecolor=C_CONFIRM, markersize=13,
               label="TICK+px new extreme together (div ends)"),
    ]
    ax.legend(handles=handles, facecolor="#111", labelcolor="#ddd", fontsize=8.5, loc="best")
    ax.set_title(f"ES 5M — {pd.Timestamp(day).date()}   structural swings + color-coded TICK "
                 f"divergences (minbars={minbars})", color="#eee", loc="left", fontsize=12)

    step = max(1, n // 14)
    axt.set_xticks(range(0, n, step))
    axt.set_xticklabels([g["DateTime"][i].strftime("%H:%M") for i in range(0, n, step)],
                        color="#aaa", fontsize=8)
    ax.set_xlim(-1, n + 1)
    fig.tight_layout()
    fig.savefig(out, dpi=115, facecolor=fig.get_facecolor())
    plt.close(fig)
    return True


def main() -> int:
    minbars = int(sys.argv[1]) if len(sys.argv) > 1 else 3
    n_days = int(sys.argv[2]) if len(sys.argv) > 2 else 4
    files = sorted(MASTER_DIR.glob("internals_es_5m_*.parquet"))
    if not files:
        raise SystemExit("! run ingest_nt_internals.py first")
    m = pd.read_parquet(files[-1]).reset_index(drop=True)
    m = add_div_flags(m)
    stamp = pd.Timestamp(m["DateTime"].max()).strftime("%Y%m%d")

    ex = excursion_study(m, minbars)
    summ = summarize_excursion(ex)
    print(f"pivots analyzed: {len(ex):,}  (minbars={minbars})")
    print("\n=== REVERSAL EXCURSION BEFORE PIVOT BROKEN (ES points, same-day) ===")
    with pd.option_context("display.max_columns", None, "display.width", 200):
        print(summ.to_string(index=False))

    MASTER_DIR.mkdir(parents=True, exist_ok=True); FIG_DIR.mkdir(parents=True, exist_ok=True)
    ex.to_csv(MASTER_DIR / f"phase1_excursion_{stamp}.csv", index=False)
    summ.to_csv(MASTER_DIR / f"phase1_excursion_summary_{stamp}.csv", index=False)
    print(f"\nwrote phase1_excursion_{stamp}.csv + summary")

    # example days: pick days with the biggest matching-divergence reversal excursion
    cand = ex[ex["match_div"] & (ex["excursion_pts"] > 0)].copy()
    cand["day"] = cand["DateTime"].dt.normalize()
    best_days = (cand.groupby("day")["excursion_pts"].max()
                 .sort_values(ascending=False).head(n_days).index)
    made = []
    for day in best_days:
        out = FIG_DIR / f"phase1_marked_{pd.Timestamp(day).strftime('%Y%m%d')}.png"
        if draw_day(m, day, minbars, out):
            made.append(out)
            print(f"wrote {out.relative_to(ROOT)}")
    print("\nexample days:", [pd.Timestamp(d).date().isoformat() for d in best_days])
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
