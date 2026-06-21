"""confirm_balance_day.py — OOS + confound check for the balance-day finding.

Phase B (in-sample, whole history): CC breakouts on a "balance day" (opened INSIDE
prior range AND still inside at signal = rotation) averaged ~$149 vs $87 baseline,
and held in 2022. Two ways that could be fake:
  (1) time-concentration — it only worked in a couple of periods.
  (2) TOD confound — "rotation/inside" just means "early", and early already wins.

This confirms against both, no optimizer (the rule is FIXED, so every OOS window is a
genuine test of the same rule):
  • CHECK 1 — across the WFA's OOS folds (is=252 / oos=63 signal-days): balance-day
    expectancy & PF vs the ER>=0.30 baseline, per fold + aggregate.
  • CHECK 2 — within each time-of-day band: balance vs NON-balance expectancy. If
    balance still wins inside the same band, the edge is the state, not the clock.

Run: .venv/Scripts/python.exe scripts/confirm_balance_day.py
Out: docs/living/confirm_balance_day_<date>.md
"""
from __future__ import annotations

import sys
from datetime import datetime
from pathlib import Path

import numpy as np
import pandas as pd

_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(_ROOT))

import massive                                                       # noqa: E402
import regime_filter as rf                                          # noqa: E402
import wfa                                                          # noqa: E402
from simulation_engine import simulate_trades                       # noqa: E402
from scripts.regime_overlay_phaseB import (BASE, CHOP_MIN, tag_states,  # noqa: E402
                                           stats, _SIGNALS, _BARS, _SESS)

_OUT = _ROOT / "docs" / "living"
IS_DAYS, OOS_DAYS = 252, 63


def log(m: str) -> None:
    print(f"[confirm] {datetime.now():%H:%M:%S} {m}", flush=True)


def line(label: str, pnl: np.ndarray) -> str:
    s = stats(pnl)
    if s["n"] == 0:
        return f"| {label} | 0 | — | — | — |"
    pf = "∞" if s["pf"] == float("inf") else f"{s['pf']:.2f}"
    return f"| {label} | {s['n']} | ${s['net']:,.0f} | ${s['exp']:.0f} | {pf} |"


def main() -> int:
    log("loading + ER>=0.30 + tagging...")
    sig = pd.read_parquet(_SIGNALS)
    bars = pd.read_parquet(_BARS).drop(columns=["Contract"], errors="ignore")
    sess = pd.read_parquet(_SESS)
    bars_by_date = {d: g.reset_index(drop=True) for d, g in bars.groupby(bars["DateTime"].dt.date)}

    tagged, _ = rf.tag_and_bucket(sig, bars)
    er = tagged["ER_intra_6"].astype(float).fillna(0)
    sigf = sig[er >= CHOP_MIN].reset_index(drop=True).copy()
    states = tag_states(sigf, bars, sess)
    sigf = pd.concat([sigf, states], axis=1)

    log("loading ticks + simulating (pinned 1.0R)...")
    ticks_by_date = {d: massive.load_continuous_ticks(d) for d in sorted(sigf["Date"].unique())}
    ticks_by_date = {d: t for d, t in ticks_by_date.items() if not t.empty}
    res = simulate_trades(signals=sigf, ticks_by_date=ticks_by_date, bars_by_date=bars_by_date, **BASE)
    f = res[res["Filled"] == True].copy()
    # carry state + date + TOD onto filled rows
    f["balance"] = ((sigf.loc[f.index, "open_loc"] == "inside") &
                    (sigf.loc[f.index, "disc"] == "rotation")).values
    dt = pd.to_datetime(sigf.loc[f.index, "DateTime"])
    f["Date"] = dt.dt.date.values
    f["mod"] = (dt.dt.hour * 60 + dt.dt.minute).values
    log(f"filled: {len(f)} | balance-day: {int(f['balance'].sum())}")

    md = [f"# Confirm — balance-day filter ({datetime.now():%Y-%m-%d})\n",
          f"ER>=0.30 single-leg pinned 1.0R. Filled {len(f)}, balance-day {int(f['balance'].sum())} "
          f"({f['balance'].mean()*100:.0f}%). Balance = opened inside prior range AND still inside at signal.\n"]

    # ── CHECK 1 — across OOS folds ────────────────────────────────────────────
    all_dates = sorted(f["Date"].unique())
    folds = wfa.build_folds(all_dates, IS_DAYS, OOS_DAYS)
    md += ["## Check 1 — out-of-sample folds (does it persist over time?)\n",
           "Each fold's OOS window; balance-day vs baseline (all ER>=0.30). 'lift' = bal exp − base exp.\n",
           "| fold | OOS dates | base n | base exp | bal n | bal exp | lift | bal PF |",
           "|---|---|---|---|---|---|---|---|"]
    wins = 0
    bal_all, base_all = [], []
    for fold in folds:
        oos = set(fold["oos_dates"])
        sub = f[f["Date"].isin(oos)]
        base_pnl = sub["NetPnL"].to_numpy()
        bal_pnl = sub.loc[sub["balance"], "NetPnL"].to_numpy()
        if len(bal_pnl) < 10:
            continue
        be, bx = base_pnl.mean(), bal_pnl.mean()
        lift = bx - be
        wins += int(lift > 0)
        bs = stats(bal_pnl)
        pf = "∞" if bs["pf"] == float("inf") else f"{bs['pf']:.2f}"
        d0, d1 = min(oos), max(oos)
        md.append(f"| {fold['fold_id']} | {d0}→{d1} | {len(base_pnl)} | ${be:.0f} "
                  f"| {len(bal_pnl)} | ${bx:.0f} | ${lift:+.0f} | {pf} |")
        bal_all.append(bal_pnl); base_all.append(base_pnl)
    n_folds = len(bal_all)
    md += ["",
           f"**Balance-day beat baseline in {wins}/{n_folds} OOS folds.**  "
           f"Pooled OOS — baseline exp ${np.concatenate(base_all).mean():.0f}, "
           f"balance exp ${np.concatenate(bal_all).mean():.0f}.\n"]

    # ── CHECK 2 — within time-of-day bands (confound control) ──────────────────
    bands = [("Open 08:30–10:00", 510, 600), ("Mid 10:00–11:30", 600, 690),
             ("Lunch 11:30–13:00", 690, 780), ("PM 13:00–15:15", 780, 915)]
    md += ["## Check 2 — within time-of-day band (is it the state, or just 'early'?)\n",
           "If balance still beats NON-balance inside the same TOD band, the edge is the balance state.\n",
           "| band | grp | n | net | exp | PF |", "|---|---|---|---|---|---|"]
    for name, lo, hi in bands:
        b = f[(f["mod"] >= lo) & (f["mod"] < hi)]
        md.append(line(f"{name} · balance", b.loc[b["balance"], "NetPnL"].to_numpy()))
        md.append(line(f"{name} · non-bal", b.loc[~b["balance"], "NetPnL"].to_numpy()))
    md += [""]

    out = _OUT / f"confirm_balance_day_{datetime.now():%Y%m%d}.md"
    out.write_text("\n".join(md), encoding="utf-8")
    log(f"wrote -> {out}")
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    print("\n" + "\n".join(md))
    return 0


if __name__ == "__main__":
    sys.exit(main())
