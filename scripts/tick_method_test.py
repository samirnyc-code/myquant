#!/usr/bin/env python
"""tick_method_test.py — Phase A: DESCRIPTIVE test of Halsey's TICK method.

No fills, no measured-move construction, no discretion — just: do the TICK
signals Halsey defines actually MARK turning points (better than a random bar),
and does a TICK DIVERGENCE actually mean "trend continues"?

Ground truth turns = objective structural swings (reversal-bar detector, reset
daily because NYSE internals reset daily). All TICK states come straight from
the master parquet flags (built by the internals ingest).

Two questions, both answerable without inventing an MM:

  A. REVERSAL MARKERS. For each signed TICK state, P(a matching swing pivot sits
     within +/-W bars | state) vs the unconditional base rate. lift = ratio.
       - positive TICK extreme (+800/+1000) & confirm_hi  -> should mark swing HIGHs
       - negative TICK extreme (-800/-1000) & confirm_lo  -> should mark swing LOWs
     This is COINCIDENCE (symmetric window), stated as descriptive, not tradeable.

  B. DIVERGENCE = CONTINUATION (causal, forward-only). Among bars sitting at a new
     day extreme, does an ACTIVE divergence produce more trend continuation over
     the next K bars than a CONFIRM bar (where tick+price make the extreme
     together, i.e. the divergence has ended)? Halsey: divergence keeps you in.

Outputs (all dated):
  data/nt_internals/tick_method/markerA_reversal_<stamp>.csv
  data/nt_internals/tick_method/markerB_continuation_<stamp>.csv

Usage: python scripts/tick_method_test.py [minbars=3] [W=2] [K=6]
"""
from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parent.parent
MASTER = ROOT / "data" / "nt_internals" / "master"
OUT = ROOT / "data" / "nt_internals" / "tick_method"


def struct_swings(H, L, minbars=0):
    """Reversal-bar structural swings -> [(i, price, 'H'|'L')] (verbatim from deep script)."""
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


def build_bar_flags(m: pd.DataFrame, minbars: int, W: int) -> pd.DataFrame:
    """Per-day: mark near-swing-H / near-swing-L windows and signed TICK states."""
    parts = []
    for _day, g in m.groupby("Date"):
        g = g.reset_index(drop=True)
        n = len(g)
        near_H = np.zeros(n, bool); near_L = np.zeros(n, bool)
        is_H = np.zeros(n, bool); is_L = np.zeros(n, bool)
        if n >= 6:
            piv = struct_swings(g["es_high"].values, g["es_low"].values, minbars)
            for j, _p, kind in piv:
                lo, hi = max(0, j - W), min(n - 1, j + W)
                if kind == "H":
                    is_H[j] = True; near_H[lo:hi + 1] = True
                else:
                    is_L[j] = True; near_L[lo:hi + 1] = True
        g["near_swing_H"] = near_H; g["near_swing_L"] = near_L
        g["is_swing_H"] = is_H; g["is_swing_L"] = is_L
        parts.append(g)
    out = pd.concat(parts, ignore_index=True)

    # signed TICK states from the raw bar high/low of the TICK
    th, tl = out["tick_high"], out["tick_low"]
    out["tick_pos_800"] = th >= 800
    out["tick_pos_1000"] = th >= 1000
    out["tick_neg_800"] = tl <= -800
    out["tick_neg_1000"] = tl <= -1000
    # confirm bars: tick AND price make a new day extreme together (divergence ends)
    out["confirm_hi"] = out["px_new_hi"] & out["tick_new_hi"]
    out["confirm_lo"] = out["px_new_lo"] & out["tick_new_lo"]
    return out


def marker_A(m: pd.DataFrame) -> pd.DataFrame:
    """Lift of each signed TICK state for coinciding with the matching swing type."""
    valid = m["tick_high"].notna()   # only bars with a real TICK reading
    base_H = m.loc[valid, "near_swing_H"].mean()
    base_L = m.loc[valid, "near_swing_L"].mean()
    rows = []

    def row(state_col, target_col, base, label):
        sel = valid & m[state_col]
        n = int(sel.sum())
        if n == 0:
            return
        rate = m.loc[sel, target_col].mean()
        rows.append({
            "marker": label, "target": target_col.replace("near_swing_", "swing "),
            "n_bars": n, "p_near": round(rate, 3),
            "base_rate": round(base, 3), "lift": round(rate / base, 2) if base else np.nan,
        })

    for st, lab in (("tick_pos_800", "TICK >= +800"), ("tick_pos_1000", "TICK >= +1000"),
                    ("confirm_hi", "confirm HI (tick+px new-high together)")):
        row(st, "near_swing_H", base_H, lab)
    for st, lab in (("tick_neg_800", "TICK <= -800"), ("tick_neg_1000", "TICK <= -1000"),
                    ("confirm_lo", "confirm LO (tick+px new-low together)")):
        row(st, "near_swing_L", base_L, lab)
    # divergence bars (continuation) - expect LOW reversal-marking = low lift on OPPOSITE turn
    row("bull_div", "near_swing_H", base_H, "bull_div active (expect LOW: continuation)")
    row("bear_div", "near_swing_L", base_L, "bear_div active (expect LOW: continuation)")
    return pd.DataFrame(rows)


def _episodes_side(g: pd.DataFrame, up: bool):
    """Reconstruct divergence EPISODES on one side of one day (faithful to Ch 11).

    Episode start (ENTRY) = the FIRST bar that makes a new day price extreme WITHOUT a
    new day TICK extreme (a divergence bar) that follows a simultaneous tick+price
    extreme (confirm). Episode end (EXIT) = the NEXT confirm (tick+price new extreme
    together) after entry, i.e. "the next new high/low tick of the day"; if none, EXIT
    = last bar of the day (you'd hold to EOD). This is exactly the rule "stay long
    through a bullish divergence until the next new high tick of the day."

    Returns list of dicts. `up=True` -> bullish divergence (long); else bearish (short).
    """
    n = len(g)
    C = g["es_close"].values; H = g["es_high"].values; L = g["es_low"].values
    div = g["bull_div"].values if up else g["bear_div"].values
    confirm = g["confirm_hi"].values if up else g["confirm_lo"].values
    recs = []
    i = 0
    seen_confirm = False
    while i < n:
        if confirm[i]:
            seen_confirm = True; i += 1; continue
        # entry: first divergence bar after we've seen at least one confirm (episode origin)
        if div[i] and seen_confirm:
            entry = i
            # find exit = next confirm strictly after entry, else EOD
            j = entry + 1
            while j < n and not confirm[j]:
                j += 1
            exit_i = j if j < n else n - 1
            ended_by = "confirm" if j < n else "eod"
            hold = g.iloc[entry:exit_i + 1]
            if up:
                cont = C[exit_i] - C[entry]
                mfe = H[entry:exit_i + 1].max() - C[entry]
                mae = C[entry] - L[entry:exit_i + 1].min()
            else:
                cont = C[entry] - C[exit_i]
                mfe = C[entry] - L[entry:exit_i + 1].min()
                mae = H[entry:exit_i + 1].max() - C[entry]
            recs.append({
                "side": "UP (bull div, long)" if up else "DN (bear div, short)",
                "entry_dt": g["DateTime"].iloc[entry], "bars_held": exit_i - entry,
                "continuation_pts": round(cont, 2), "mfe_pts": round(mfe, 2),
                "mae_pts": round(mae, 2), "ended_by": ended_by,
                "profitable": cont > 0,
            })
            i = exit_i  # jump past this episode; next confirm re-arms seen_confirm
            seen_confirm = confirm[exit_i]
            continue
        i += 1
    return recs


def _baseline_hold(g: pd.DataFrame, up: bool, horizons):
    """Matched-horizon null: from EVERY new-day-extreme bar, the fwd move over the same
    number of bars an episode would hold. Answers 'is the divergence-hold better than
    just holding after any new extreme for the same time?'"""
    n = len(g); C = g["es_close"].values
    px_new = g["px_new_hi"].values if up else g["px_new_lo"].values
    out = []
    for i in range(n):
        if not px_new[i]:
            continue
        h = horizons[i % len(horizons)] if horizons else 6
        j = min(n - 1, i + h)
        cont = (C[j] - C[i]) if up else (C[i] - C[j])
        out.append(round(cont, 2))
    return out


def marker_B(m: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Episode-level divergence test + matched-horizon baseline."""
    ep = []
    for _day, g in m.groupby("Date"):
        g = g.reset_index(drop=True)
        if len(g) < 6:
            continue
        ep += _episodes_side(g, up=True)
        ep += _episodes_side(g, up=False)
    ep = pd.DataFrame(ep)

    # baseline: sample holds using the observed episode-length distribution per side
    base_rows = []
    for side, up in (("UP (bull div, long)", True), ("DN (bear div, short)", False)):
        horizons = ep.loc[ep["side"] == side, "bars_held"].tolist() or [6]
        vals = []
        for _day, g in m.groupby("Date"):
            g = g.reset_index(drop=True)
            if len(g) < 6:
                continue
            vals += _baseline_hold(g, up, horizons)
        s = pd.Series(vals)
        base_rows.append({
            "side": side, "n_newextreme_bars": len(s),
            "med_baseline_pts": round(s.median(), 2),
            "mean_baseline_pts": round(s.mean(), 2),
            "%positive": round(100 * (s > 0).mean(), 1),
        })
    base = pd.DataFrame(base_rows)

    summ = ep.groupby("side").agg(
        n_episodes=("continuation_pts", "size"),
        med_continuation_pts=("continuation_pts", lambda s: round(s.median(), 2)),
        mean_continuation_pts=("continuation_pts", lambda s: round(s.mean(), 2)),
        med_mfe_pts=("mfe_pts", lambda s: round(s.median(), 2)),
        med_mae_pts=("mae_pts", lambda s: round(s.median(), 2)),
        med_bars_held=("bars_held", lambda s: int(s.median())),
        pct_profitable=("profitable", lambda s: round(100 * s.mean(), 1)),
        pct_ended_by_confirm=("ended_by", lambda s: round(100 * (s == "confirm").mean(), 1)),
    ).reset_index()
    summ = summ.merge(base, on="side", how="left")
    return summ, ep


def main() -> int:
    minbars = int(sys.argv[1]) if len(sys.argv) > 1 else 3
    W = int(sys.argv[2]) if len(sys.argv) > 2 else 2
    files = sorted(MASTER.glob("internals_es_5m_*.parquet"))
    if not files:
        raise SystemExit("! no master parquet - run the internals ingest first")
    m = pd.read_parquet(files[-1])
    stamp = pd.Timestamp(m["DateTime"].max()).strftime("%Y%m%d")
    print(f"master: {files[-1].name}  rows={len(m):,}  "
          f"{m['DateTime'].min().date()} -> {m['DateTime'].max().date()}  "
          f"(minbars={minbars}, W={W})")

    m = build_bar_flags(m, minbars, W)
    A = marker_A(m)
    B, episodes = marker_B(m)

    print("\n=== A. REVERSAL MARKERS — coincidence with a matching swing (+/-{} bars) ===".format(W))
    with pd.option_context("display.max_columns", None, "display.width", 200):
        print(A.to_string(index=False))
    print("\n  lift > 1 = marks the turn more than a random bar; ~1 = no info; < 1 = anti-marker")

    print("\n=== B. DIVERGENCE EPISODES — 'stay in until the next opposing new tick' ===")
    print("    (entry = first divergence bar after a confirm; exit = next confirm, else EOD)")
    with pd.option_context("display.max_columns", None, "display.width", 240):
        print(B.to_string(index=False))
    print("\n  Halsey rule earns its keep if med_continuation > med_baseline (matched hold)"
          "\n  AND pct_profitable comfortably > 50%.")

    OUT.mkdir(parents=True, exist_ok=True)
    A.to_csv(OUT / f"markerA_reversal_{stamp}.csv", index=False)
    B.to_csv(OUT / f"markerB_episodes_summary_{stamp}.csv", index=False)
    episodes.to_csv(OUT / f"markerB_episodes_{stamp}.csv", index=False)
    print(f"\nwrote markerA_reversal_{stamp}.csv, markerB_episodes_summary_{stamp}.csv, "
          f"markerB_episodes_{stamp}.csv  under {OUT.relative_to(ROOT)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
