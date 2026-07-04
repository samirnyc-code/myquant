"""MenthorQ tests on RevFT (MyReversals) signals — S54 round 5.

Pre-registered (before outcomes):
  R1 baseline + by SignalType; exits: 1R flat (primary) and 3R+BE@1R (secondary)
  R2 MAGNET REPLICATION: signal direction points at a main MQ level within 1R
     -> registered BETTER (same direction as the MC magnet lead)
  R3 backstop: main level just BEHIND entry (beyond stop side, <=1R) -> BETTER
  R4 causal gamma condition (prev-EOD row applied next day): positive gamma
     days -> reversals BETTER
  R5 IV-band-edge fade: entry within 0.25x expected-move of 1d_max (shorts) /
     1d_min (longs) -> BETTER (exhaustion at implied boundary)
Levels/scalars joined with MQ_APPLY_NEXT_DAY=1 (correct causal dating).
"""
import os
import sys
from pathlib import Path

import numpy as np
import pandas as pd

sys.stdout.reconfigure(encoding="utf-8", errors="replace")
os.environ["MQ_APPLY_NEXT_DAY"] = "1"
ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT)); sys.path.insert(0, str(ROOT / "scripts"))

import massive                                                      # noqa: E402
massive._TICKS_CONT_DIR = ROOT / "data" / "ticks_continuous"
from simulation_engine import simulate_trades                       # noqa: E402
from menthorq_edge_study import (load_mq, WIN_START, WIN_END,       # noqa: E402
                                 BARS_PQ, parse_signals)
from menthorq_sr_followup import offsets_for                        # noqa: E402

if len(sys.argv) > 2:
    REV_TXT = Path(sys.argv[1])
    OUT = ROOT / "docs" / "living" / sys.argv[2]
else:
    REV_TXT = Path(os.environ.get(
        "REVFT_SIGNAL_TXT",
        ROOT / "data" / "signals" /
        "MyReversals Signal Export - ES SEP26 - 5 Minute from 02.07.2026 - 1850 Days.txt"))
    OUT = ROOT / "docs" / "living" / "menthorq_revft_tests_20260704.md"
MAIN = ["call_resistance", "call_resistance_0dte", "put_support",
        "put_support_0dte", "high_vol_level", "gamma_wall_0dte"]
GEX = ["gex_1", "gex_2", "gex_3"]
L = []
def emit(s=""):
    print(s, flush=True); L.append(s)


def rrow(label, g):
    n = len(g)
    if n == 0:
        return f"| {label} | 0 | — | — | — | — |"
    r = g["Rmult"].to_numpy()
    ci = 1.96 * r.std(ddof=1) / np.sqrt(n) if n > 1 else np.nan
    pnl = g["PnL"].to_numpy()
    gw = pnl[pnl > 0].sum(); gl = abs(pnl[pnl < 0].sum())
    pf = gw / gl if gl > 0 else np.inf
    lo, hi = r.mean() - ci, r.mean() + ci
    mark = " ✅" if lo > 0 else (" ❌" if hi < 0 else "")
    return (f"| {label} | {n} | {r.mean():+.3f} ±{ci:.3f}{mark} | [{lo:+.3f},{hi:+.3f}] "
            f"| {pf:.2f} | ${pnl.sum():,.0f} |")


emit("# MenthorQ × RevFT (MyReversals) tests — causal join, Mar 9 – Jul 2 2026\n")
bars = pd.read_parquet(BARS_PQ)
bars["DateTime"] = pd.to_datetime(bars["DateTime"])
mq = load_mq(); mq["date"] = mq["date"].dt.normalize()
mq = mq[(mq["date"] >= WIN_START) & (mq["date"] <= WIN_END)].reset_index(drop=True)
off = offsets_for(mq, bars)
mq = mq[mq["date"].isin(off)].reset_index(drop=True)
lev = {r["date"]: {c: r[c] + off[r["date"]] for c in MAIN if pd.notna(r[c])}
       for _, r in mq.iterrows()}
levg = {r["date"]: {c: r[c] + off[r["date"]] for c in GEX if pd.notna(r[c])}
        for _, r in mq.iterrows()}
mqd = mq.set_index("date")

sig = parse_signals(REV_TXT)
win = sig[(sig["DateTime"] >= WIN_START) & (sig["DateTime"] < WIN_END + pd.Timedelta(days=1))].copy()
emit(f"{len(sig)} RevFT signals total; {len(win)} in window; types: "
     + ", ".join(f"{t}:{n}" for t, n in win["SignalType"].value_counts().items()) + "\n")

dates = sorted(win["Date"].unique())
ticks = {d: massive.load_continuous_ticks(d) for d in dates}
ticks = {d: t for d, t in ticks.items() if t is not None and not t.empty}
day = bars["DateTime"].dt.normalize()
bbd = {d.date(): g.reset_index(drop=True) for d, g in bars.groupby(day)}

BASE = dict(entry_slip=1, exit_slip=1, stop_offset=1, tick_value=12.5,
            contracts=1, commission=4.36, bars_by_date=bbd)
runs = {"1R flat": dict(target_r=1.0),
        "3R + BE@1R": dict(target_r=3.0, ratchet_r=1.0, ratchet_dest="BE")}

for exit_name, kw in runs.items():
    res = simulate_trades(signals=win, ticks_by_date=ticks, **BASE, **kw)
    f = res[res["Filled"].astype(bool)].copy()
    f["PnL"] = f["NetPnL"].astype(float)
    f["Rmult"] = f["PnL"] / f["RiskDollar"].replace(0, np.nan)
    f["DateD"] = pd.to_datetime(f["Date"]).dt.normalize()
    f = f[f["DateD"].isin(lev)].reset_index(drop=True)
    s = np.where(f["Direction"].astype(str).str.upper().str.startswith("L"), 1.0, -1.0)
    entry = f["SignalPrice"].astype(float).to_numpy()
    riskp = (f["SignalPrice"] - f["StopPrice"]).abs().to_numpy()

    d_ahead = np.full(len(f), np.nan); d_behind = np.full(len(f), np.nan)
    g_ahead = np.full(len(f), np.nan); g_behind = np.full(len(f), np.nan)
    for i in range(len(f)):
        dd = f["DateD"].iloc[i]
        lv = np.array(list(lev[dd].values()), dtype=float)
        rel = (lv - entry[i]) * s[i]
        ahead = rel[rel > 0]; behind = -rel[rel < 0]
        if len(ahead): d_ahead[i] = ahead.min()
        if len(behind): d_behind[i] = behind.min()
        gv = np.array(list(levg.get(dd, {}).values()), dtype=float)
        if len(gv):
            relg = (gv - entry[i]) * s[i]
            ga = relg[relg > 0]; gb = -relg[relg < 0]
            if len(ga): g_ahead[i] = ga.min()
            if len(gb): g_behind[i] = gb.min()
    f["toward_1R"] = d_ahead <= riskp
    f["backstop_1R"] = d_behind <= riskp
    f["gex_toward_1R"] = g_ahead <= riskp
    f["gex_backstop_1R"] = g_behind <= riskp

    # R4 gamma (row already causally dated), R5 band edge
    f["neg_gamma"] = f["DateD"].map(mqd["gamma_condition"]).astype(str).str.lower().eq("negative")
    mx = f["DateD"].map(mqd["1d_max"]) + f["DateD"].map(pd.Series(off))
    mn = f["DateD"].map(mqd["1d_min"]) + f["DateD"].map(pd.Series(off))
    em = (mx - mn) / 2
    edge_dist = np.where(s > 0, entry - mn, mx - entry)   # long fades near band low
    f["band_edge"] = pd.Series(edge_dist / em, index=f.index).abs() <= 0.25

    emit(f"## Exit: {exit_name}\n")
    emit("| cut | n | ExpR ±CI | 95% interval | PF | net$ |")
    emit("|---|---|---|---|---|---|")
    emit(rrow("R1 baseline (all RevFT)", f))
    for t, g in f.groupby("SignalType"):
        emit(rrow(f"R1 type {t}", g))
    emit(rrow("R2 TOWARD main level ≤1R [reg: better]", f[f["toward_1R"]]))
    emit(rrow("R2 not toward", f[~f["toward_1R"]]))
    emit(rrow("R3 backstop behind ≤1R [reg: better]", f[f["backstop_1R"]]))
    emit(rrow("R3 no backstop", f[~f["backstop_1R"]]))
    emit(rrow("R2g GEX1-3 toward ≤1R", f[f["gex_toward_1R"]]))
    emit(rrow("R2g GEX1-3 not toward", f[~f["gex_toward_1R"]]))
    emit(rrow("R3g GEX1-3 backstop ≤1R", f[f["gex_backstop_1R"]]))
    emit(rrow("R2/R3 near ANY main ≤1R (union)", f[f["toward_1R"] | f["backstop_1R"]]))
    emit(rrow("R2/R3 no main level within 1R", f[~(f["toward_1R"] | f["backstop_1R"])]))
    emit(rrow("R4 positive gamma (causal) [reg: better]", f[~f["neg_gamma"]]))
    emit(rrow("R4 negative gamma", f[f["neg_gamma"]]))
    emit(rrow("R5 at IV band edge ≤0.25EM [reg: better]", f[f["band_edge"]]))
    emit(rrow("R5 not at edge", f[~f["band_edge"]]))
    # magnet x AM (diagnostic, matching the MC drill)
    hh = pd.to_datetime(f["DateTime"]).dt.hour
    emit(rrow("R2 toward ≤1R, AM only (diagnostic)", f[f["toward_1R"] & (hh < 11)]))
    emit("")

OUT.write_text("\n".join(L), encoding="utf-8")
print(f"written {OUT}")
