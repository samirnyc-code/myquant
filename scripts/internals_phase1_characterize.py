#!/usr/bin/env python
"""internals_phase1_characterize.py — S92-EA Phase 1.

Q1: at TURNING POINTS, what do the NYSE internals look like vs ordinary bars?
Turning points here = STRUCTURAL swing highs/lows (bar-by-bar reversal-bar detector,
NOT a %-zigzag), detected PER RTH DAY (so daily-reset internals — TICK extremes,
divergence — are meaningful). Rev-indicator signals are characterized in a later step.

For every swing pivot we record the internals AT THE PIVOT BAR (descriptive; the bar's
internals are all known at its own close — no look-ahead) and compare the pivot
population to the all-bars baseline. Also tests Halsey's Ch-11 divergence directly:
at swing HIGHS, did price make a new day-high WITHOUT a new day high-tick (bull_div)?

Outputs (dated, committed report + charts):
  data/nt_internals/master/phase1_pivots_<stamp>.csv       per-pivot internals
  data/nt_internals/master/phase1_summary_<stamp>.csv      pivot vs baseline table
  eminiaddict/figures/phase1_*.png                          distributions + examples

Usage: python scripts/internals_phase1_characterize.py [minbars=3]
"""
from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pandas as pd
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

ROOT = Path(__file__).resolve().parent.parent
MASTER_DIR = ROOT / "data" / "nt_internals" / "master"
FIG_DIR = ROOT / "eminiaddict" / "figures"

DIV_WINDOW = 3            # bars: divergence "near" the pivot (pivot bar or up to N before)
TRIN_HI, TRIN_LO = 2.0, 0.5     # exhaustion thresholds
VIX_RISK_ON = 18.85


def struct_swings(H, L, minbars=0):
    """Bar-by-bar structural swings (reversal-bar rule). Copied verbatim from
    eminiaddict/scripts/swings_test.py (validated detector) to avoid its import chain.
    Returns list of (bar_index, price, 'H'|'L')."""
    n = len(H)
    piv = []
    d = 0
    hi_i, hi = 0, H[0]
    lo_i, lo = 0, L[0]

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


def latest_master() -> Path:
    files = sorted(MASTER_DIR.glob("internals_es_5m_*.parquet"))
    if not files:
        raise SystemExit("! no master parquet — run scripts/ingest_nt_internals.py first")
    return files[-1]


def collect_pivots(m: pd.DataFrame, minbars: int) -> pd.DataFrame:
    """Detect structural swings per RTH day; return rows of pivot bars with a 'kind' col."""
    recs = []
    for _day, g in m.groupby(m["DateTime"].dt.normalize()):
        g = g.reset_index()  # keep original index in 'index'
        if len(g) < 5:
            continue
        piv = struct_swings(g["es_high"].values, g["es_low"].values, minbars)
        for bar_i, _price, kind in piv:
            row = g.loc[bar_i].to_dict()
            row["kind"] = kind
            recs.append(row)
    return pd.DataFrame(recs)


def add_divergence_near(m: pd.DataFrame) -> pd.DataFrame:
    """Add per-bar bull/bear-divergence-near flags to EVERY bar (pivot and baseline use
    the identical definition): true if bull_div/bear_div fired on this bar or in the prior
    DIV_WINDOW bars WITHIN THE SAME DAY. No look-ahead (only current + past bars)."""
    m = m.copy()
    day = m["DateTime"].dt.normalize()
    for src, dst in (("bull_div", "bull_div_near"), ("bear_div", "bear_div_near")):
        if src not in m:
            continue
        # rolling-OR over DIV_WINDOW+1 bars, reset each day
        flag = m[src].fillna(False).astype(int)
        near = flag.groupby(day).transform(
            lambda s: s.rolling(DIV_WINDOW + 1, min_periods=1).max())
        m[dst] = near.astype(bool)
    return m


def summarize(m: pd.DataFrame, piv: pd.DataFrame) -> pd.DataFrame:
    """Compare swing-highs / swing-lows / all-bars baseline across internals features."""
    base = m
    hi = piv[piv["kind"] == "H"]
    lo = piv[piv["kind"] == "L"]

    def feats(df, is_high=None):
        d = {}
        d["n"] = len(df)
        tk = df["tick_bar_ext"].abs()
        d["|TICK| mean"] = tk.mean()
        d["|TICK| p90"] = tk.quantile(0.90)
        d["%TICK>=800"] = 100 * df["tick_extreme_800"].mean()
        d["%TICK>=1000"] = 100 * df["tick_extreme_1000"].mean()
        d["TRIN mean"] = df["trin_level"].mean()
        d["%TRIN>=2"] = 100 * (df["trin_level"] >= TRIN_HI).mean()
        d["%TRIN<=0.5"] = 100 * (df["trin_level"] <= TRIN_LO).mean()
        d["VIX mean"] = df["vix_level"].mean()
        d["breadth mean"] = df["breadth_ratio"].mean()
        d["breadth slope mean"] = df["breadth_slope"].mean()
        # divergence: relevant one per side
        if "bull_div_near" in df:
            d["%bull_div_near"] = 100 * df["bull_div_near"].mean()
            d["%bear_div_near"] = 100 * df["bear_div_near"].mean()
        return d

    rows = {
        "swing_HIGH": feats(hi),
        "swing_LOW": feats(lo),
        "baseline(all)": feats(base),
    }
    out = pd.DataFrame(rows).T
    return out


def main() -> int:
    minbars = int(sys.argv[1]) if len(sys.argv) > 1 else 3
    mp = latest_master()
    m = pd.read_parquet(mp).reset_index(drop=True)
    stamp = pd.Timestamp(m["DateTime"].max()).strftime("%Y%m%d")
    print(f"master: {mp.name}  {len(m):,} bars  {m['DateTime'].min()}..{m['DateTime'].max()}")

    m = add_divergence_near(m)
    piv = collect_pivots(m, minbars)
    nH = (piv["kind"] == "H").sum(); nL = (piv["kind"] == "L").sum()
    ndays = m["DateTime"].dt.normalize().nunique()
    print(f"structural swings (minbars={minbars}): {len(piv):,} pivots "
          f"({nH:,} highs / {nL:,} lows) over {ndays} days "
          f"= {len(piv)/ndays:.1f}/day")

    summ = summarize(m, piv)
    print("\n=== INTERNALS AT TURNING POINTS vs BASELINE (minbars=%d) ===" % minbars)
    with pd.option_context("display.max_columns", None, "display.width", 220,
                           "display.float_format", lambda x: f"{x:,.2f}"):
        print(summ.to_string())

    MASTER_DIR.mkdir(parents=True, exist_ok=True)
    FIG_DIR.mkdir(parents=True, exist_ok=True)
    pcols = ["DateTime", "bar", "kind", "es_close", "tick_bar_ext", "tick_extreme_800",
             "tick_extreme_1000", "bull_div_near", "bear_div_near", "trin_level",
             "vix_level", "breadth_ratio", "breadth_slope"]
    pcols = [c for c in pcols if c in piv.columns]
    piv_out = MASTER_DIR / f"phase1_pivots_{stamp}.csv"
    piv[pcols].to_csv(piv_out, index=False)
    summ_out = MASTER_DIR / f"phase1_summary_{stamp}.csv"
    summ.to_csv(summ_out)
    print(f"\nwrote {piv_out.relative_to(ROOT)}")
    print(f"wrote {summ_out.relative_to(ROOT)}")

    # ---- chart: |TICK| distribution at pivots vs baseline ----
    fig, axes = plt.subplots(1, 2, figsize=(15, 5.5), facecolor="#0b0b0b")
    for ax in axes:
        ax.set_facecolor("#0b0b0b")
        ax.tick_params(colors="#aaa")
        for sp in ax.spines.values():
            sp.set_color("#333")
    bins = np.arange(0, 1600, 50)
    ax = axes[0]
    ax.hist(m["tick_bar_ext"].abs().dropna(), bins=bins, density=True, alpha=.5,
            color="#888", label=f"baseline (n={m['tick_bar_ext'].notna().sum():,})")
    ax.hist(piv["tick_bar_ext"].abs().dropna(), bins=bins, density=True, alpha=.6,
            color="#ffd400", label=f"swing pivots (n={piv['tick_bar_ext'].notna().sum():,})")
    ax.axvline(800, color="#e2453c", ls="--", lw=1); ax.axvline(1000, color="#e2453c", lw=1)
    ax.set_title("|NYSE TICK bar-extreme| — pivots vs baseline", color="#eee", loc="left")
    ax.set_xlabel("|TICK|", color="#aaa"); ax.legend(facecolor="#111", labelcolor="#ddd")
    # bar chart of key % features
    ax = axes[1]
    cats = ["%TICK>=800", "%TICK>=1000", "%TRIN>=2", "%TRIN<=0.5"]
    x = np.arange(len(cats)); w = 0.27
    ax.bar(x - w, [summ.loc["swing_HIGH", c] for c in cats], w, color="#e2453c", label="swing HIGH")
    ax.bar(x, [summ.loc["swing_LOW", c] for c in cats], w, color="#26a65b", label="swing LOW")
    ax.bar(x + w, [summ.loc["baseline(all)", c] for c in cats], w, color="#888", label="baseline")
    ax.set_xticks(x); ax.set_xticklabels(cats, color="#aaa", fontsize=9)
    ax.set_ylabel("% of bars", color="#aaa")
    ax.set_title("Extreme-internals rate at pivots vs baseline", color="#eee", loc="left")
    ax.legend(facecolor="#111", labelcolor="#ddd")
    fig.tight_layout()
    fig_path = FIG_DIR / f"phase1_internals_at_pivots_{stamp}.png"
    fig.savefig(fig_path, dpi=115, facecolor=fig.get_facecolor())
    print(f"wrote {fig_path.relative_to(ROOT)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
