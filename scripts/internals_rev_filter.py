#!/usr/bin/env python
"""internals_rev_filter.py — S92-EA Phase 2: do internals FILTER the rev signals into an edge?

The rev indicator's signals (research/revsim/revft_all_signals.csv) are real entry triggers:
each has an entry (= ES bar OPEN, verified) and a stop. We build a CAUSAL outcome for every
signal (first-touch of stop vs an R-multiple target, same day) and then ask whether gating on
the NYSE internals — measured on the PRIOR complete bar (no look-ahead) — raises win rate /
expectancy, and whether the effect is stable YEAR BY YEAR (the only test that matters).

Outcome unit = R (multiple of the signal's own risk = |entry - stop|).
  target hit first -> +TARGET_R ; stop hit first -> -1 ; neither by HORIZON -> mark-to-close/risk.

Filters (direction-aware; long uses the bullish side, short mirrors):
  tick_fav      long: prior tick_low<=-800     short: prior tick_high>=+800
  confirm_bar   long: prior px&tick new day-LOW together   short: new day-HIGH together
  breadth_agree long: breadth_ratio>1          short: breadth_ratio<1
  breadth_slope long: slope>0                  short: slope<0
  trin_exhaust  long: TRIN>=2                   short: TRIN<=0.5
  vix_gate      long: VIX risk-on (<18.85)      short: VIX not risk-on
Confluence score = # of CORE filters satisfied; test for a monotonic edge.

Usage: python scripts/internals_rev_filter.py [TARGET_R=2] [HORIZON=24] [rev_types=all]
"""
from __future__ import annotations

import sys
from pathlib import Path
import glob as _glob

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parent.parent
MASTER_DIR = ROOT / "data" / "nt_internals" / "master"
REV = ROOT / "research" / "revsim" / "revft_all_signals.csv"
CORE = ["tick_fav", "confirm_bar", "breadth_agree", "trin_exhaust"]


def load():
    m = pd.read_parquet(sorted(_glob.glob(str(MASTER_DIR / "internals_es_5m_*.parquet")))[-1])
    m = m.reset_index(drop=True)
    m["confirm_lo"] = m["px_new_lo"] & m["tick_new_lo"]
    m["confirm_hi"] = m["px_new_hi"] & m["tick_new_hi"]
    r = pd.read_csv(REV); r["time"] = pd.to_datetime(r["time"])
    return m, r


def outcomes(m, r, target_r, horizon, rev_types):
    """Causal first-touch outcome per signal; internals from the PRIOR bar."""
    m = m.set_index("DateTime")
    idx = {ts: i for i, ts in enumerate(m.index)}
    arrH = m["es_high"].to_numpy(); arrL = m["es_low"].to_numpy()
    arrC = m["es_close"].to_numpy(); day = m.index.normalize()
    recs = []
    for _, s in r.iterrows():
        if rev_types != "all" and s["rev"] not in rev_types:
            continue
        t = s["time"]
        if t not in idx:
            continue
        i = idx[t]
        side = int(s["side"]); entry = float(s["entry"]); stop = float(s["stop"])
        risk = abs(entry - stop)
        if risk < 0.25:
            continue
        tgt = entry + side * target_r * risk
        # first-touch from the signal bar (entry at its open) forward, same day
        res = None
        for k in range(i, min(i + horizon, len(m))):
            if day[k] != day[i]:
                break
            if side == 1:
                if arrL[k] <= stop:
                    res = -1.0; break
                if arrH[k] >= tgt:
                    res = float(target_r); break
            else:
                if arrH[k] >= stop:
                    res = -1.0; break
                if arrL[k] <= tgt:
                    res = float(target_r); break
        if res is None:
            kk = k
            res = side * (arrC[kk] - entry) / risk  # mark-to-close in R
        # PRIOR-bar internals (strictly causal filter)
        p = i - 1
        if p < 0 or day[p] != day[i]:
            p = i  # fall back to signal bar's completed prior-session edge; rare
        pr = m.iloc[p]
        rec = {"time": t, "year": t.year, "rev": s["rev"], "side": side, "R": res}
        # direction-aware filter booleans
        if side == 1:
            rec["tick_fav"] = pr["tick_low"] <= -800
            rec["confirm_bar"] = bool(pr["confirm_lo"])
            rec["breadth_agree"] = pr["breadth_ratio"] > 1
            rec["breadth_slope"] = pr["breadth_slope"] > 0
            rec["trin_exhaust"] = pr["trin_level"] >= 2
            rec["vix_gate"] = bool(pr["vix_risk_on"])
        else:
            rec["tick_fav"] = pr["tick_high"] >= 800
            rec["confirm_bar"] = bool(pr["confirm_hi"])
            rec["breadth_agree"] = pr["breadth_ratio"] < 1
            rec["breadth_slope"] = pr["breadth_slope"] < 0
            rec["trin_exhaust"] = pr["trin_level"] <= 0.5
            rec["vix_gate"] = not bool(pr["vix_risk_on"])
        recs.append(rec)
    df = pd.DataFrame(recs)
    for c in CORE + ["breadth_slope", "vix_gate"]:
        df[c] = df[c].fillna(False).astype(bool)
    df["score"] = df[CORE].sum(axis=1)
    return df


def st(d):
    if not len(d):
        return dict(n=0, win=np.nan, expR=np.nan, pf=np.nan)
    w = d[d["R"] > 0]["R"].sum(); l = -d[d["R"] < 0]["R"].sum()
    return dict(n=len(d), win=round(100 * (d["R"] > 0).mean(), 1),
                expR=round(d["R"].mean(), 3), pf=round(w / l, 2) if l else np.inf)


def yr_pos(d):
    """# of years with positive mean R / total years (stability)."""
    g = d.groupby("year")["R"].mean()
    return f"{(g > 0).sum()}/{len(g)}"


def main():
    target_r = float(sys.argv[1]) if len(sys.argv) > 1 else 2.0
    horizon = int(sys.argv[2]) if len(sys.argv) > 2 else 24
    rev_types = "all" if len(sys.argv) < 4 else sys.argv[3].split(",")
    m, r = load()
    d = outcomes(m, r, target_r, horizon, rev_types)
    stamp = pd.Timestamp(m["DateTime"].max()).strftime("%Y%m%d")
    print(f"rev signals used: {len(d):,}  target={target_r}R  horizon={horizon} bars  "
          f"types={rev_types}")

    b = st(d)
    print(f"\nBASELINE (all rev signals):  n={b['n']}  win={b['win']}%  "
          f"exp={b['expR']:+.3f}R  PF={b['pf']}  years+={yr_pos(d)}")

    print("\n=== SINGLE FILTERS (subset that passes) vs baseline ===")
    print(f"{'filter':16s} {'n':>5s} {'win%':>6s} {'expR':>7s} {'PF':>5s} {'years+':>7s} "
          f"{'d_expR':>7s}")
    for f in CORE + ["breadth_slope", "vix_gate"]:
        sub = d[d[f]]
        s = st(sub)
        dexp = (s['expR'] - b['expR']) if s['n'] else float('nan')
        print(f"{f:16s} {s['n']:5d} {s['win']:6}  {s['expR']:+.3f} {s['pf']:5} "
              f"{yr_pos(sub):>7s} {dexp:+.3f}")

    print("\n=== CONFLUENCE SCORE (# of core filters met) — monotonic? ===")
    print(f"{'score':>5s} {'n':>6s} {'win%':>6s} {'expR':>7s} {'PF':>5s} {'years+':>7s}")
    for sc in sorted(d["score"].unique()):
        sub = d[d["score"] == sc]
        s = st(sub)
        print(f"{sc:5d} {s['n']:6d} {s['win']:6}  {s['expR']:+.3f} {s['pf']:5} {yr_pos(sub):>7s}")

    print("\n=== by REV TYPE (baseline, no filter) ===")
    for rv in d["rev"].unique():
        s = st(d[d["rev"] == rv]); print(f"  {rv:6s} n={s['n']:5d} win={s['win']}% exp={s['expR']:+.3f}R PF={s['pf']}")

    out = MASTER_DIR / f"rev_filter_outcomes_{stamp}.csv"
    d.to_csv(out, index=False)
    print(f"\nwrote {out.relative_to(ROOT)}")


if __name__ == "__main__":
    main()
