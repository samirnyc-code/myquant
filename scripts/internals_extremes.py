#!/usr/bin/env python
"""internals_extremes.py — S92-EA Phase 1 (rebuilt): internals at MARKET-STRUCTURE EXTREMES.

Turning points defined THREE ways (user's call), each MULTI-TIER, to test whether the
internals signal STRENGTHENS as the turn gets more significant (monotonicity):

  1. SESSION extremes  — the day's High/Low, and the AM (08:30-11:30 CT) & PM
     (12:30-15:00 CT) session High/Low. The Halsey-faithful anchor: his TICK divergence
     is literally "high TICK of the DAY vs high in PRICE of the DAY".
  2. N-BAR FRACTAL pivots — a swing high = strict highest high within +/-N bars.
     Tiers N = 3 (fine) / 5 (medium) / 10 (coarse). NOTE centered => uses future bars,
     so these are DESCRIPTIVE (not live signals); fine for characterizing where extremes were.
  3. ATR-MAGNITUDE swings — raw alternating pivots filtered so each leg >= k * DR,
     DR = trailing-20d median RTH day-range (a volatility scale). Tiers k = 0.25/0.5/1.0.

For every turning point we record internals AT the pivot bar and the REVERSAL EXCURSION:
how far price traveled the reversal way (down from a high / up from a low) before the pivot
was BROKEN (a later bar trades beyond it), within the same RTH day (censored = not broken).

Halsey internal markers at the pivot:
  - matching TICK divergence near (px new day-extreme w/o new matching TICK extreme; Ch 11)
  - CONFIRMATION bar (TICK & price new day-extreme TOGETHER) = his "traditional" reversal
  - TICK bar-extreme >= 800 / 1000

Outputs (dated, committed):
  data/nt_internals/master/extremes_pivots_<stamp>.csv       every turning point + flags
  data/nt_internals/master/extremes_summary_<stamp>.csv      def x tier vs baseline
  eminiaddict/figures/extremes_monotonicity_<stamp>.png
  eminiaddict/figures/extremes_marked_<YYYYMMDD>.png         example days

Usage: python scripts/internals_extremes.py [n_example_days=4]
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
FRACTAL_TIERS = [3, 5, 10]
ATR_TIERS = [0.25, 0.5, 1.0]
AM = ("08:30", "11:30")
PM = ("12:30", "15:00")

C_UP, C_DN = "#26a65b", "#e2453c"
C_BULLDIV = "#22d3ee"; C_BEARDIV = "#f59e0b"; C_CONFIRM = "#a855f7"
C_PIVH, C_PIVL = "#ff5566", "#33dd88"


# ---------- pivot detectors ----------
def struct_swings(H, L, minbars=0):
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


def fractal_pivots(H, L, N):
    """Centered N-bar fractals. High at i if H[i] is the strict max of H[i-N..i+N]."""
    n = len(H); out = []
    for i in range(N, n - N):
        win = slice(i - N, i + N + 1)
        if H[i] == H[win].max() and (H[win] == H[i]).sum() == 1:
            out.append((i, H[i], 'H'))
        if L[i] == L[win].min() and (L[win] == L[i]).sum() == 1:
            out.append((i, L[i], 'L'))
    return out


def atr_filtered(H, L, thresh):
    """Alternating structural pivots filtered so each retained leg >= thresh (points)."""
    raw = struct_swings(H, L, 0)
    if not raw:
        return []
    kept = [raw[0]]
    for i, p, k in raw[1:]:
        li, lp, lk = kept[-1]
        if k == lk:  # same kind: keep the more extreme
            if (k == 'H' and p >= lp) or (k == 'L' and p <= lp):
                kept[-1] = (i, p, k)
            continue
        if abs(p - lp) >= thresh:
            kept.append((i, p, k))
    return kept


# ---------- features ----------
def add_flags(m: pd.DataFrame) -> pd.DataFrame:
    m = m.copy()
    day = m["DateTime"].dt.normalize()
    for src, dst in (("bull_div", "bull_div_near"), ("bear_div", "bear_div_near")):
        flag = m[src].fillna(False).astype(int)
        m[dst] = flag.groupby(day).transform(
            lambda s: s.rolling(DIV_WINDOW + 1, min_periods=1).max()).astype(bool)
    m["confirm_hi"] = m["px_new_hi"] & m["tick_new_hi"]
    m["confirm_lo"] = m["px_new_lo"] & m["tick_new_lo"]
    return m


def day_scale(m: pd.DataFrame) -> pd.Series:
    """Trailing-20d median RTH day-range per calendar day (volatility scale for ATR tiers)."""
    day = m["DateTime"].dt.normalize()
    rng = m.groupby(day).apply(lambda x: x["es_high"].max() - x["es_low"].min())
    dr = rng.rolling(20, min_periods=5).median().shift(1)
    dr = dr.bfill()
    return dr  # indexed by normalized day


def reversal_excursion(g, j, kind):
    H = g["es_high"].values; L = g["es_low"].values; n = len(g)
    broken = False; brk_off = n - 1 - j
    if kind == "H":
        best = np.inf
        for off, k in enumerate(range(j + 1, n), start=1):
            best = min(best, L[k])
            if H[k] > g["es_high"].values[j]:
                broken = True; brk_off = off; break
        exc = (g["es_high"].values[j] - best) if np.isfinite(best) else 0.0
    else:
        best = -np.inf
        for off, k in enumerate(range(j + 1, n), start=1):
            best = max(best, H[k])
            if L[k] < g["es_low"].values[j]:
                broken = True; brk_off = off; break
        exc = (best - g["es_low"].values[j]) if np.isfinite(best) else 0.0
    return max(exc, 0.0), brk_off, broken


def session_pivots(g):
    """Return [(local_idx, price, kind, subtype)] for day/AM/PM H&L."""
    out = []
    t = g["DateTime"].dt.strftime("%H:%M")
    def hl(mask, tag):
        sub = g[mask]
        if sub.empty:
            return
        hi = sub["es_high"].idxmax(); lo = sub["es_low"].idxmin()
        out.append((g.index.get_loc(hi), g.loc[hi, "es_high"], 'H', tag))
        out.append((g.index.get_loc(lo), g.loc[lo, "es_low"], 'L', tag))
    hl(pd.Series(True, index=g.index), "day")
    hl((t >= AM[0]) & (t <= AM[1]), "AM")
    hl((t >= PM[0]) & (t <= PM[1]), "PM")
    return out


def build(m: pd.DataFrame):
    dr = day_scale(m)
    day = m["DateTime"].dt.normalize()
    recs = []
    for d, g in m.groupby(day):
        g = g.reset_index(drop=True)
        if len(g) < 22:
            continue
        H = g["es_high"].values; L = g["es_low"].values
        scale = float(dr.get(d, np.nan))
        defs = []
        # session
        for j, price, kind, sub in session_pivots(g):
            defs.append(("session", sub, j, kind))
        # fractal tiers
        for N in FRACTAL_TIERS:
            for j, price, kind in fractal_pivots(H, L, N):
                defs.append(("fractal", f"N{N}", j, kind))
        # atr tiers
        if np.isfinite(scale):
            for k in ATR_TIERS:
                for j, price, kind in atr_filtered(H, L, k * scale):
                    defs.append(("atr", f"{k:g}xDR", j, kind))
        for fam, tier, j, kind in defs:
            exc, brk, broken = reversal_excursion(g, j, kind)
            r = g.loc[j]
            match_div = bool(r["bull_div_near"]) if kind == "H" else bool(r["bear_div_near"])
            match_conf = bool(r["confirm_hi"]) if kind == "H" else bool(r["confirm_lo"])
            recs.append({
                "DateTime": r["DateTime"], "family": fam, "tier": tier, "kind": kind,
                "price": r["es_close"], "excursion_pts": round(exc, 2),
                "bars_to_break": brk, "broken_same_day": broken,
                "match_div": match_div, "match_confirm": match_conf,
                "tick_800": bool(r["tick_extreme_800"]), "tick_1000": bool(r["tick_extreme_1000"]),
                "trin": r["trin_level"], "vix": r["vix_level"],
                "breadth_slope": r["breadth_slope"],
            })
    return pd.DataFrame(recs)


def summarize(ex: pd.DataFrame, m: pd.DataFrame) -> pd.DataFrame:
    def blk(df, fam, tier):
        return {
            "family": fam, "tier": tier, "n": len(df),
            "%TICK>=800": round(100 * df["tick_800"].mean(), 1),
            "%TICK>=1000": round(100 * df["tick_1000"].mean(), 1),
            "%match_div": round(100 * df["match_div"].mean(), 1),
            "%confirm_bar": round(100 * df["match_confirm"].mean(), 1),
            "med_exc_pts": round(df["excursion_pts"].median(), 2),
            "p75_exc_pts": round(df["excursion_pts"].quantile(0.75), 2),
            "%broken_sameday": round(100 * df["broken_same_day"].mean(), 1),
        }
    rows = []
    # baseline (all bars) for the rate features
    base = {
        "family": "BASELINE", "tier": "all bars", "n": len(m),
        "%TICK>=800": round(100 * m["tick_extreme_800"].mean(), 1),
        "%TICK>=1000": round(100 * m["tick_extreme_1000"].mean(), 1),
        "%match_div": round(100 * ((m["bull_div_near"] | m["bear_div_near"]).mean()), 1),
        "%confirm_bar": round(100 * ((m["confirm_hi"] | m["confirm_lo"]).mean()), 1),
        "med_exc_pts": np.nan, "p75_exc_pts": np.nan, "%broken_sameday": np.nan,
    }
    rows.append(base)
    order = [("session", "day"), ("session", "AM"), ("session", "PM"),
             ("fractal", "N3"), ("fractal", "N5"), ("fractal", "N10"),
             ("atr", "0.25xDR"), ("atr", "0.5xDR"), ("atr", "1xDR")]
    for fam, tier in order:
        d = ex[(ex["family"] == fam) & (ex["tier"] == tier)]
        if len(d):
            rows.append(blk(d, fam, tier))
    return pd.DataFrame(rows)


# ---------- chart: marked example day ----------
def draw_day(m, day, out, fractalN=5):
    g = m[m["DateTime"].dt.normalize() == day].reset_index(drop=True)
    if len(g) < 22:
        return False
    H = g["es_high"].values; L = g["es_low"].values; O = g["es_open"].values; C = g["es_close"].values
    n = len(g)
    frac = fractal_pivots(H, L, fractalN)
    sess = session_pivots(g)

    fig, (ax, axt) = plt.subplots(2, 1, figsize=(16, 9), height_ratios=[3, 1.15],
                                  sharex=True, facecolor="#0b0b0b")
    for a in (ax, axt):
        a.set_facecolor("#0b0b0b"); a.tick_params(colors="#aaa")
        for sp in a.spines.values():
            sp.set_color("#333")
        a.grid(True, color="#141414", lw=0.5)
    for i in range(n):
        col = C_UP if C[i] >= O[i] else C_DN
        ax.plot([i, i], [L[i], H[i]], color=col, lw=0.9, zorder=2)
        ax.add_patch(Rectangle((i - .32, min(O[i], C[i])), .64, abs(C[i] - O[i]) or .05,
                               facecolor=col, edgecolor=col, zorder=3))
        if bool(g.loc[i, "bull_div"]):
            ax.axvspan(i - .5, i + .5, color=C_BULLDIV, alpha=.14, zorder=1)
        if bool(g.loc[i, "bear_div"]):
            ax.axvspan(i - .5, i + .5, color=C_BEARDIV, alpha=.14, zorder=1)
    # medium fractal pivots (small)
    for j, price, kind in frac:
        m_, c = ("v", C_PIVH) if kind == "H" else ("^", C_PIVL)
        y = H[j] if kind == "H" else L[j]
        ax.scatter([j], [y], marker=m_, s=55, color=c, alpha=.65, zorder=5)
    # session extremes (big, labeled)
    for j, price, kind, sub in sess:
        if sub != "day":
            continue
        y = H[j] if kind == "H" else L[j]
        ax.scatter([j], [y], marker=("v" if kind == "H" else "^"), s=200, color="#fff",
                   edgecolor="#000", zorder=7)
        ax.annotate(f"day {kind}", (j, y), textcoords="offset points",
                    xytext=(0, 12 if kind == "H" else -18), color="#fff", ha="center",
                    fontsize=9, fontweight="bold")
    # TICK panel
    tkh = g["tick_high"].values; tkl = g["tick_low"].values; tkc = g["tick_close"].values
    for i in range(n):
        if np.isnan(tkh[i]):
            continue
        axt.plot([i, i], [tkl[i], tkh[i]], color="#666", lw=0.8, zorder=2)
        axt.scatter([i], [tkc[i]], s=7, color="#ccc", zorder=3)
        if bool(g.loc[i, "bull_div"]):
            axt.scatter([i], [tkh[i]], s=24, color=C_BULLDIV, zorder=5)
        if bool(g.loc[i, "bear_div"]):
            axt.scatter([i], [tkl[i]], s=24, color=C_BEARDIV, zorder=5)
        if bool(g.loc[i, "confirm_hi"]):
            axt.scatter([i], [tkh[i]], marker="*", s=70, color=C_CONFIRM, zorder=6)
        if bool(g.loc[i, "confirm_lo"]):
            axt.scatter([i], [tkl[i]], marker="*", s=70, color=C_CONFIRM, zorder=6)
    for lv in (1000, 800, -800, -1000):
        axt.axhline(lv, color="#e2453c", ls="--" if abs(lv) == 800 else "-", lw=0.8, alpha=.6)
    axt.axhline(0, color="#444", lw=0.6); axt.set_ylabel("NYSE TICK", color="#aaa", fontsize=10)

    from matplotlib.lines import Line2D
    from matplotlib.patches import Patch
    handles = [
        Line2D([], [], marker="v", color="none", markerfacecolor="#fff", markeredgecolor="#000",
               markersize=12, label="session day H/L"),
        Line2D([], [], marker="v", color="none", markerfacecolor=C_PIVH, markersize=9,
               label=f"fractal N{fractalN} high"),
        Line2D([], [], marker="^", color="none", markerfacecolor=C_PIVL, markersize=9,
               label=f"fractal N{fractalN} low"),
        Patch(facecolor=C_BULLDIV, alpha=.5, label="bull div (px new-hi, no new hi-TICK)"),
        Patch(facecolor=C_BEARDIV, alpha=.5, label="bear div (px new-lo, no new lo-TICK)"),
        Line2D([], [], marker="*", color="none", markerfacecolor=C_CONFIRM, markersize=13,
               label="TICK+px new extreme together"),
    ]
    ax.legend(handles=handles, facecolor="#111", labelcolor="#ddd", fontsize=8, loc="best")
    ax.set_title(f"ES 5M — {pd.Timestamp(day).date()}   structure extremes + color-coded TICK "
                 f"divergences", color="#eee", loc="left", fontsize=12)
    step = max(1, n // 14)
    axt.set_xticks(range(0, n, step))
    axt.set_xticklabels([g["DateTime"][i].strftime("%H:%M") for i in range(0, n, step)],
                        color="#aaa", fontsize=8)
    ax.set_xlim(-1, n + 1)
    fig.tight_layout(); fig.savefig(out, dpi=115, facecolor=fig.get_facecolor()); plt.close(fig)
    return True


def draw_monotonicity(summ, out):
    fig, axes = plt.subplots(1, 2, figsize=(15, 5.5), facecolor="#0b0b0b")
    for ax in axes:
        ax.set_facecolor("#0b0b0b"); ax.tick_params(colors="#aaa")
        for sp in ax.spines.values():
            sp.set_color("#333")
        ax.grid(True, color="#141414", lw=0.5)
    fam_order = [("fractal", ["N3", "N5", "N10"]), ("atr", ["0.25xDR", "0.5xDR", "1xDR"])]
    for ax, (fam, tiers) in zip(axes, fam_order):
        sub = summ[summ["family"] == fam].set_index("tier").reindex(tiers)
        x = np.arange(len(tiers))
        ax.plot(x, sub["med_exc_pts"], "o-", color="#ffd400", label="median reversal exc (pts)")
        ax.set_xticks(x); ax.set_xticklabels(tiers, color="#aaa")
        ax.set_ylabel("median excursion (ES pts)", color="#ffd400")
        ax2 = ax.twinx(); ax2.tick_params(colors="#aaa")
        ax2.plot(x, sub["%TICK>=800"], "s--", color="#22d3ee", label="%TICK>=800")
        ax2.plot(x, sub["%confirm_bar"], "^--", color="#a855f7", label="%confirm bar")
        ax2.set_ylabel("% of pivots", color="#22d3ee")
        ax.set_title(f"{fam}: signal vs tier (fine->coarse)", color="#eee", loc="left")
        l1, la1 = ax.get_legend_handles_labels(); l2, la2 = ax2.get_legend_handles_labels()
        ax.legend(l1 + l2, la1 + la2, facecolor="#111", labelcolor="#ddd", fontsize=8, loc="best")
    fig.tight_layout(); fig.savefig(out, dpi=115, facecolor=fig.get_facecolor()); plt.close(fig)


def main() -> int:
    n_days = int(sys.argv[1]) if len(sys.argv) > 1 else 4
    files = sorted(MASTER_DIR.glob("internals_es_5m_*.parquet"))
    if not files:
        raise SystemExit("! run ingest_nt_internals.py first")
    m = pd.read_parquet(files[-1]).reset_index(drop=True)
    m = add_flags(m)
    stamp = pd.Timestamp(m["DateTime"].max()).strftime("%Y%m%d")

    ex = build(m)
    summ = summarize(ex, m)
    print(f"turning points: {len(ex):,} across {ex.groupby(['family','tier']).ngroups} def/tiers")
    print("\n=== INTERNALS AT STRUCTURE EXTREMES vs BASELINE (excursion = reversal pts before break) ===")
    with pd.option_context("display.max_columns", None, "display.width", 220):
        print(summ.to_string(index=False))

    MASTER_DIR.mkdir(parents=True, exist_ok=True); FIG_DIR.mkdir(parents=True, exist_ok=True)
    # within-tier conditional excursion: does the internal ADD? (skip 'day' = never broken)
    cond_rows = []
    for fam, tier in [("session", "AM"), ("fractal", "N10"), ("atr", "0.5xDR"), ("atr", "1xDR")]:
        d = ex[(ex["family"] == fam) & (ex["tier"] == tier)]
        if not len(d):
            continue
        for cond, name in [(d["match_confirm"], "confirm bar"), (d["tick_800"], "TICK>=800"),
                           (d["match_div"], "matching div")]:
            w, wo = d[cond], d[~cond]
            cond_rows.append({
                "family/tier": f"{fam}/{tier}", "condition": name,
                "n_with": len(w), "med_exc_with": round(w["excursion_pts"].median(), 2),
                "n_without": len(wo), "med_exc_without": round(wo["excursion_pts"].median(), 2),
                "lift_pts": round(w["excursion_pts"].median() - wo["excursion_pts"].median(), 2),
            })
    cond = pd.DataFrame(cond_rows)
    print("\n=== WITHIN-TIER: does the internal ADD reversal excursion? (median ES pts) ===")
    with pd.option_context("display.max_columns", None, "display.width", 200):
        print(cond.to_string(index=False))
    cond.to_csv(MASTER_DIR / f"extremes_conditional_{stamp}.csv", index=False)

    ex.to_csv(MASTER_DIR / f"extremes_pivots_{stamp}.csv", index=False)
    summ.to_csv(MASTER_DIR / f"extremes_summary_{stamp}.csv", index=False)
    draw_monotonicity(summ, FIG_DIR / f"extremes_monotonicity_{stamp}.png")
    print(f"\nwrote extremes_pivots/summary_{stamp}.csv + monotonicity chart")

    # example days: biggest day-High/Low reversal excursion that also had a confirm/div
    sess = ex[(ex["family"] == "session") & (ex["tier"] == "day")].copy()
    sess["d"] = sess["DateTime"].dt.normalize()
    pick = (sess[sess["match_confirm"] | sess["match_div"]]
            .groupby("d")["excursion_pts"].max().sort_values(ascending=False).head(n_days).index)
    for day in pick:
        out = FIG_DIR / f"extremes_marked_{pd.Timestamp(day).strftime('%Y%m%d')}.png"
        if draw_day(m, day, out):
            print(f"wrote {out.relative_to(ROOT)}")
    print("example days:", [pd.Timestamp(d).date().isoformat() for d in pick])
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
