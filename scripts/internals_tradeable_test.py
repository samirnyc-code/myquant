#!/usr/bin/env python
"""internals_tradeable_test.py — S92-EA: is "fade the TICK extreme" actually tradeable?

CAUSAL, no look-ahead. A signal is known at a bar's CLOSE; we enter on the NEXT bar and
manage with a fixed bracket (first-touch). We measure win rate + expectancy over 5 years.

Two entry styles, so we can see whether "confirmation" rescues the naive fade:
  RAW      : TICK crosses the extreme -> enter next bar open, immediately (knife-catch).
  CONFIRMED: after the extreme, wait up to K bars for price to CLOSE back through the
             signal bar (long: close > signal-bar high). Enter that bar's close. If it
             never confirms in K bars, NO trade. (This is Halsey's "wait for the turn".)

Long signal  = bar tick_low  <= -T   (oversold stab)   -> fade LONG
Short signal = bar tick_high >= +T   (overbought stab) -> fade SHORT
De-dup: no new same-side signal within COOLDOWN bars (don't count a waterfall as 20 trades).

Exit: first-touch of +/-BRACKET pts within HORIZON bars; else exit at horizon close.
Ties (both target & stop in one bar) resolved as STOP first (conservative).

Reports overall + per-year win rate, avg P&L, expectancy, profit factor. Per-year = the
out-of-sample stability check.

Usage: python scripts/internals_tradeable_test.py
"""
from __future__ import annotations

from pathlib import Path
import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parent.parent
MASTER_DIR = ROOT / "data" / "nt_internals" / "master"

THRESHOLDS = [800, 1000]
BRACKETS = [4, 8, 12]        # ES points, symmetric target/stop
HORIZON = 24                 # bars (~2h) max hold
CONFIRM_K = 3               # bars to wait for confirmation
COOLDOWN = 6                # bars between same-side signals
ES_PT = 50.0                # $ per ES point per contract (for context only)


def load():
    files = sorted(MASTER_DIR.glob("internals_es_5m_*.parquet"))
    if not files:
        raise SystemExit("! run ingest_nt_internals.py first")
    return pd.read_parquet(files[-1]).reset_index(drop=True)


def signals(m, T):
    """Return causal signal bar indices per side, de-duped by COOLDOWN, within-day."""
    day = m["DateTime"].dt.normalize()
    longs, shorts = [], []
    for _d, g in m.groupby(day):
        idx = g.index.to_numpy()
        tl = g["tick_low"].to_numpy(); th = g["tick_high"].to_numpy()
        last_l = last_s = -10**9
        for p in range(len(g)):
            gi = idx[p]
            if tl[p] <= -T and (p - last_l) >= COOLDOWN:
                longs.append(gi); last_l = p
            if th[p] >= T and (p - last_s) >= COOLDOWN:
                shorts.append(gi); last_s = p
    return longs, shorts


def same_day(m, i, j):
    return m.loc[i, "DateTime"].normalize() == m.loc[j, "DateTime"].normalize()


def first_touch(m, entry_i, entry_px, side, bracket):
    """First-touch bracket from entry bar entry_i (inclusive) over HORIZON, same day only."""
    n = len(m)
    tgt = entry_px + side * bracket
    stp = entry_px - side * bracket
    for k in range(entry_i, min(entry_i + HORIZON, n)):
        if not same_day(m, entry_i, k):
            k -= 1; break
        hi = m.loc[k, "es_high"]; lo = m.loc[k, "es_low"]
        if side == 1:
            if lo <= stp:  # stop first (conservative)
                return -bracket, k - entry_i, "stop"
            if hi >= tgt:
                return +bracket, k - entry_i, "target"
        else:
            if hi >= stp:
                return -bracket, k - entry_i, "stop"
            if lo <= tgt:
                return +bracket, k - entry_i, "target"
    # horizon exit at last valid bar close
    kk = min(entry_i + HORIZON - 1, n - 1)
    while kk > entry_i and not same_day(m, entry_i, kk):
        kk -= 1
    pnl = side * (m.loc[kk, "es_close"] - entry_px)
    return pnl, kk - entry_i, "time"


def run(m, sig_idx, side, style, bracket):
    trades = []
    n = len(m)
    for gi in sig_idx:
        if style == "RAW":
            ei = gi + 1
            if ei >= n or not same_day(m, gi, ei):
                continue
            entry_px = m.loc[ei, "es_open"]
        else:  # CONFIRMED
            sig_hi = m.loc[gi, "es_high"]; sig_lo = m.loc[gi, "es_low"]
            ei = None
            for k in range(gi + 1, min(gi + 1 + CONFIRM_K, n)):
                if not same_day(m, gi, k):
                    break
                if side == 1 and m.loc[k, "es_close"] > sig_hi:
                    ei = k; break
                if side == -1 and m.loc[k, "es_close"] < sig_lo:
                    ei = k; break
            if ei is None:
                continue
            entry_px = m.loc[ei, "es_close"]
        pnl, held, why = first_touch(m, ei, entry_px, side, bracket)
        trades.append({"dt": m.loc[gi, "DateTime"], "side": side, "pnl": pnl,
                       "held": held, "why": why, "year": m.loc[gi, "DateTime"].year})
    return pd.DataFrame(trades)


def stats(tr):
    if tr.empty:
        return dict(n=0, win=np.nan, avg=np.nan, exp=np.nan, pf=np.nan)
    wins = tr[tr["pnl"] > 0]["pnl"]; losses = tr[tr["pnl"] < 0]["pnl"]
    pf = wins.sum() / abs(losses.sum()) if losses.sum() != 0 else np.inf
    return dict(n=len(tr), win=round(100 * (tr["pnl"] > 0).mean(), 1),
                avg=round(tr["pnl"].mean(), 2), exp=round(tr["pnl"].mean(), 2),
                pf=round(pf, 2))


def main():
    m = load()
    print(f"data: {len(m):,} bars  {m['DateTime'].min().date()}..{m['DateTime'].max().date()} "
          f"| horizon {HORIZON} bars, cooldown {COOLDOWN}")
    all_rows = []
    for T in THRESHOLDS:
        longs, shorts = signals(m, T)
        print(f"\n########## TICK threshold +/-{T}   "
              f"(long signals={len(longs):,}, short signals={len(shorts):,}) ##########")
        for style in ["RAW", "CONFIRMED"]:
            for bracket in BRACKETS:
                trL = run(m, longs, 1, style, bracket)
                trS = run(m, shorts, -1, style, bracket)
                tr = pd.concat([trL, trS], ignore_index=True)
                s = stats(tr)
                print(f"  {style:9s} bracket +/-{bracket:2d}pt  "
                      f"n={s['n']:5d}  win={s['win']}%  exp={s['exp']:+.2f}pt/trade  "
                      f"PF={s['pf']}  (${s['exp']*ES_PT:+.0f}/trade)")
                # per-year expectancy for the headline config
                if T == 1000 and bracket == 8:
                    yr = tr.groupby("year")["pnl"].agg(["count", "mean"]).round(2)
                    yr["win%"] = tr.groupby("year")["pnl"].apply(lambda s: round(100*(s>0).mean(),1))
                    all_rows.append((style, yr))
                s.update(dict(T=T, style=style, bracket=bracket))
                # collect
    # per-year detail for T=1000 bracket 8
    print("\n=== PER-YEAR STABILITY (threshold +/-1000, bracket +/-8pt) ===")
    for style, yr in all_rows:
        print(f"\n  [{style}]");
        with pd.option_context("display.width", 120):
            print(yr.to_string())
    print("\nNOTE: exp>0 & PF>1 across most years = real; if it only works some years it's not.")


if __name__ == "__main__":
    main()
