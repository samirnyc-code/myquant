#!/usr/bin/env python
"""tick_at_hwb_test.py — #2 done at DH's ACTUAL location: the 50% pullback.

Halsey reads the NYSE TICK ONLY at the 50% HWB pullback of a measured move (entry
timing), not at arbitrary swings. So the ONLY honest conditioning test is:

  Among measured-move 50%-HWB entries, does TICK confluence at the pullback bar
  SEPARATE winners from losers?

This is NOT a P&L / standalone-edge claim (that prior engine died on fill realism).
It is a conditioning split on a well-defined EVENT set, measured leg-relative so the
continuous-contract roll/back-adjust offset cannot corrupt it.

MEASURED MOVE (surviving definition from eminiaddict/scripts/find_mm_trades.py):
  up leg  L->H, R=H-L :  hwb=L+0.5R (entry, tag low<=hwb)
                          fail=L+0.382R (61.8% retr; stop if breached)
                          tgt =L+1.236R (123.6% ext; target)   [mirror for down legs]
  Timeframe = 15M (Halsey's 50% setup TF). Bars from the 5M master (open-labeled).

OUTCOME (order-independent, conservative):
  walk bars after the entry-tag; SAME-bar ambiguity -> count as STOP (worst case).
  target_first = target reached before fail breached, within HORIZON bars & same day-ish.
  also record MFE / MAE (leg-relative points) to compare reward vs heat.

TICK CONFLUENCE at the entry (fill) bar (Ch10/11):
  long  : oversold  tick_low  <= -THRESH   (buy a low tick in an up-series)
  short : overbought tick_high >= +THRESH  (sell a high tick in a down-series)
  tested at THRESH in {400, 800}. Split entries confluent vs not; compare.

Usage: python scripts/tick_at_hwb_test.py [ZZ_PCT=0.5] [HORIZON=60]
Outputs (dated):
  data/nt_internals/tick_method/hwb_entries_<stamp>.csv      every entry + flags + outcome
  data/nt_internals/tick_method/hwb_conditioning_<stamp>.csv confluent-vs-not summary
"""
from __future__ import annotations

import sys
from pathlib import Path
import glob as _glob

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parent.parent
MASTER = ROOT / "data" / "nt_internals" / "master"
OUT = ROOT / "data" / "nt_internals" / "tick_method"


def zigzag(highs, lows, pct):
    """Percent ZigZag (verbatim from find_mm_trades.py)."""
    thr = pct / 100.0
    n = len(highs); piv = []; d = 0
    hi_i, hi = 0, highs[0]; lo_i, lo = 0, lows[0]
    for i in range(1, n):
        if d == 1:
            if highs[i] > hi:
                hi, hi_i = highs[i], i
            elif lows[i] <= hi * (1 - thr):
                piv.append((hi_i, hi, 'H')); d = -1; lo, lo_i = lows[i], i
        elif d == -1:
            if lows[i] < lo:
                lo, lo_i = lows[i], i
            elif highs[i] >= lo * (1 + thr):
                piv.append((lo_i, lo, 'L')); d = 1; hi, hi_i = highs[i], i
        else:
            if highs[i] > hi:
                hi, hi_i = highs[i], i
            if lows[i] < lo:
                lo, lo_i = lows[i], i
            if lows[i] <= hi * (1 - thr):
                piv.append((hi_i, hi, 'H')); d = -1; lo, lo_i = lows[i], i
            elif highs[i] >= lo * (1 + thr):
                piv.append((lo_i, lo, 'L')); d = 1; hi, hi_i = highs[i], i
    return piv


def build_15m():
    f = sorted(_glob.glob(str(MASTER / "internals_es_5m_*.parquet")))[-1]
    m = pd.read_parquet(f).set_index("DateTime").sort_index()
    agg = {"es_open": "first", "es_high": "max", "es_low": "min", "es_close": "last",
           "tick_high": "max", "tick_low": "min"}
    g = m.resample("15min").agg(agg).dropna(subset=["es_open", "es_close"]).reset_index()
    g["day"] = g["DateTime"].dt.normalize()
    return g, Path(f).name


def scan(g, zz_pct, horizon):
    H = g["es_high"].to_numpy(); L = g["es_low"].to_numpy()
    tkh = g["tick_high"].to_numpy(); tkl = g["tick_low"].to_numpy()
    dt = g["DateTime"]
    piv = zigzag(H, L, zz_pct)
    rows = []
    for k in range(len(piv) - 1):
        (i0, p0, k0), (i1, p1, k1) = piv[k], piv[k + 1]
        if k0 == 'L' and k1 == 'H':
            lo, hi, up = p0, p1, True
        elif k0 == 'H' and k1 == 'L':
            hi, lo, up = p0, p1, False
        else:
            continue
        R = hi - lo
        if R <= 0:
            continue
        if up:
            hwb = lo + 0.5 * R; fail = lo + 0.382 * R; tgt = lo + 1.236 * R
        else:
            hwb = hi - 0.5 * R; fail = hi - 0.382 * R; tgt = hi - 1.236 * R
        # entry: first bar after leg-end tagging the 50% HWB
        j0, j1 = i1 + 1, min(len(g), i1 + 1 + horizon)
        i_entry = None
        for j in range(j0, j1):
            if (up and L[j] <= hwb) or (not up and H[j] >= hwb):
                i_entry = j; break
        if i_entry is None:
            continue
        # outcome from entry: target-before-stop, conservative same-bar=stop
        outcome = "open"; i_out = None; mfe = 0.0; mae = 0.0
        for j in range(i_entry, min(len(g), i_entry + horizon)):
            if up:
                mfe = max(mfe, H[j] - hwb); mae = max(mae, hwb - L[j])
                stop_hit = L[j] < fail; tgt_hit = H[j] >= tgt
            else:
                mfe = max(mfe, hwb - L[j]); mae = max(mae, H[j] - hwb)
                stop_hit = H[j] > fail; tgt_hit = L[j] <= tgt
            if stop_hit:                      # same-bar ambiguity -> stop wins (worst case)
                outcome = "stop"; i_out = j; break
            if tgt_hit:
                outcome = "target"; i_out = j; break
        rows.append({
            "up": up, "dt_entry": dt[i_entry], "day": dt[i_entry].normalize(),
            "R_pts": round(R, 2), "hwb": round(hwb, 2),
            "entry_tick_low": tkl[i_entry], "entry_tick_high": tkh[i_entry],
            "conf400": (tkl[i_entry] <= -400) if up else (tkh[i_entry] >= 400),
            "conf800": (tkl[i_entry] <= -800) if up else (tkh[i_entry] >= 800),
            "outcome": outcome, "target_first": outcome == "target",
            "resolved": outcome in ("target", "stop"),
            "mfe_pts": round(mfe, 2), "mae_pts": round(mae, 2),
            "bars_to_out": (i_out - i_entry) if i_out is not None else np.nan,
        })
    return pd.DataFrame(rows)


def summarize(e: pd.DataFrame) -> pd.DataFrame:
    def block(df, label):
        res = df[df["resolved"]]
        n = len(df); nr = len(res)
        return {
            "group": label, "n_entries": n, "n_resolved": nr,
            "target_first_%": round(100 * res["target_first"].mean(), 1) if nr else np.nan,
            "med_mfe": round(df["mfe_pts"].median(), 2),
            "med_mae": round(df["mae_pts"].median(), 2),
            "mfe/mae": round(df["mfe_pts"].median() / df["mae_pts"].median(), 2)
            if df["mae_pts"].median() else np.nan,
        }
    rows = [block(e, "ALL 50%-HWB entries")]
    for thr, col in ((400, "conf400"), (800, "conf800")):
        rows.append(block(e[e[col]], f"TICK-confluent (|tick|>={thr})"))
        rows.append(block(e[~e[col]], f"NOT confluent (<{thr})"))
    return pd.DataFrame(rows)


def main() -> int:
    zz = float(sys.argv[1]) if len(sys.argv) > 1 else 0.5
    horizon = int(sys.argv[2]) if len(sys.argv) > 2 else 60
    g, src = build_15m()
    print(f"source: {src}  15M bars={len(g):,}  "
          f"{g['DateTime'].iloc[0].date()} -> {g['DateTime'].iloc[-1].date()}  "
          f"(ZZ={zz}%, horizon={horizon} bars)")
    e = scan(g, zz, horizon)
    if e.empty:
        raise SystemExit("! no HWB entries found")
    summ = summarize(e)

    print(f"\n=== 50%-HWB ENTRIES: does TICK confluence separate winners? "
          f"(n={len(e)}, {e['resolved'].mean()*100:.0f}% resolved) ===")
    with pd.option_context("display.max_columns", None, "display.width", 220):
        print(summ.to_string(index=False))
    print("\n  target_first_% = target(123.6%) reached before stop(61.8%) breach, of RESOLVED.")
    print("  DH's claim holds only if confluent > not-confluent on target_first_% and mfe/mae.")

    # per-year stability of the confluent split (long+short pooled, thr 400)
    e2 = e.copy(); e2["yr"] = e2["day"].dt.year
    yr = (e2[e2["resolved"]].groupby(["yr", "conf400"])["target_first"]
          .agg(["size", "mean"]).reset_index())
    yr["mean"] = (100 * yr["mean"]).round(1)
    print("\n=== per-year target_first_% (conf400 True vs False) ===")
    with pd.option_context("display.width", 160):
        print(yr.rename(columns={"size": "n", "mean": "target_first_%"}).to_string(index=False))

    OUT.mkdir(parents=True, exist_ok=True)
    stamp = pd.Timestamp(g["DateTime"].iloc[-1]).strftime("%Y%m%d")
    e.to_csv(OUT / f"hwb_entries_{stamp}.csv", index=False)
    summ.to_csv(OUT / f"hwb_conditioning_{stamp}.csv", index=False)
    print(f"\nwrote hwb_entries_{stamp}.csv + hwb_conditioning_{stamp}.csv under {OUT.relative_to(ROOT)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
