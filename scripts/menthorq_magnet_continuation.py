"""Magnet mechanics: when an MC stacked trade points at a main MQ level <=1R,
what happens AT the level? Continuation stats + target ladder.

Battery:
  A. per-trade geometry: dist-to-level (R), MFE (R, bar-based), excursion BEYOND
     the level (R), share of trades that pin vs continue
  B. target ladder (fresh tick sims on the same 43 trades):
     1R flat / 2R flat / 3R+BE@1R (current) / 5R+BE@1R / EOD-only (no target)
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

import massive                                                  # noqa: E402
massive._TICKS_CONT_DIR = ROOT / "data" / "ticks_continuous"
from simulation_engine import simulate_trades                   # noqa: E402
from menthorq_edge_study import (load_mq, WIN_START, WIN_END,   # noqa: E402
                                 BARS_PQ, parse_signals, SIG_TXT)
from menthorq_sr_followup import offsets_for                    # noqa: E402
from stack_filter import compute_stack_columns                  # noqa: E402

MAIN = ["call_resistance", "call_resistance_0dte", "put_support",
        "put_support_0dte", "high_vol_level", "gamma_wall_0dte"]
OUT = ROOT / "docs" / "living" / "menthorq_magnet_continuation_20260704.md"
L = []
def emit(s=""):
    print(s, flush=True); L.append(s)


bars = pd.read_parquet(BARS_PQ)
bars["DateTime"] = pd.to_datetime(bars["DateTime"])
day = bars["DateTime"].dt.normalize()
mq = load_mq(); mq["date"] = mq["date"].dt.normalize()
mq = mq[(mq["date"] >= WIN_START) & (mq["date"] <= WIN_END)].reset_index(drop=True)
off = offsets_for(mq, bars)
mq = mq[mq["date"].isin(off)].reset_index(drop=True)
lev = {r["date"]: {c: r[c] + off[r["date"]] for c in MAIN if pd.notna(r[c])}
       for _, r in mq.iterrows()}

sig = parse_signals(SIG_TXT)
win = sig[(sig["DateTime"] >= WIN_START) & (sig["DateTime"] < WIN_END + pd.Timedelta(days=1))].copy()
sc = compute_stack_columns(win, bars)
win = win.join(sc)
dates = sorted(win["Date"].unique())
ticks = {d: massive.load_continuous_ticks(d) for d in dates}
ticks = {d: t for d, t in ticks.items() if t is not None and not t.empty}
bbd = {d.date(): g.reset_index(drop=True) for d, g in bars.groupby(day)}
BASE = dict(entry_slip=1, exit_slip=1, stop_offset=1, tick_value=12.5,
            contracts=1, commission=4.36, bars_by_date=bbd)


def prep(frame):
    f = frame[frame["Filled"].astype(bool)].copy()
    f["PnL"] = f["NetPnL"].astype(float)
    f["Rmult"] = f["PnL"] / f["RiskDollar"].replace(0, np.nan)
    f["DateD"] = pd.to_datetime(f["Date"]).dt.normalize()
    f = f[f["DateD"].isin(lev)].reset_index(drop=True)
    s = np.where(f["Direction"].astype(str).str.upper().str.startswith("L"), 1.0, -1.0)
    entry = f["SignalPrice"].astype(float).to_numpy()
    riskp = (f["SignalPrice"] - f["StopPrice"]).abs().to_numpy()
    which, dist = [], []
    for i in range(len(f)):
        lm = lev[f["DateD"].iloc[i]]
        best, bd = None, np.inf
        for name, lv_ in lm.items():
            d_ = (lv_ - entry[i]) * s[i]
            if 0 < d_ < bd:
                best, bd = name, d_
        which.append(best); dist.append(bd if np.isfinite(bd) else np.nan)
    f["near_lev"] = which
    f["near_dist_R"] = np.array(dist) / riskp
    f["s"] = s; f["riskp"] = riskp
    return f


def stats(g):
    n = len(g)
    if n == 0:
        return "n=0"
    r = g["Rmult"].to_numpy(); pnl = g["PnL"].to_numpy()
    ci = 1.96 * r.std(ddof=1) / np.sqrt(n) if n > 1 else np.nan
    gw = pnl[pnl > 0].sum(); gl = abs(pnl[pnl < 0].sum())
    pf = gw / gl if gl > 0 else np.inf
    return (f"n={n} ExpR {r.mean():+.3f} ±{ci:.3f} PF {pf:.2f} "
            f"WR {(pnl>0).mean()*100:.0f}% ${pnl.sum():+,.0f}")


res = pd.read_parquet(ROOT / "data" / "menthorq" / "_study_sim_results.parquet")
f0 = prep(res)
stk = f0[f0["stack_pass"] == True].copy()  # noqa: E712
mag = stk[stk["near_dist_R"] <= 1.0].copy()

emit("# Magnet continuation study — MC stacked trades toward a main level ≤1R (all-day, n=%d)\n" % len(mag))

# A. geometry: MFE and excursion beyond the level (bar-based, entry -> EOD)
emit("## A. What price does at the level\n")
mfe_r, beyond_r, reached = [], [], []
for _, r in mag.iterrows():
    db = bars[day == r["DateD"]]
    after = db[db["DateTime"] >= pd.to_datetime(r["DateTime"])]
    e = float(r["SignalPrice"]); rp = float(r["riskp"])
    lv_ = lev[r["DateD"]][r["near_lev"]]
    if r["s"] > 0:
        mfe = (after["High"].max() - e) / rp
        bey = (after["High"].max() - lv_) / rp
        hit = after["High"].max() >= lv_
    else:
        mfe = (e - after["Low"].min()) / rp
        bey = (lv_ - after["Low"].min()) / rp
        hit = after["Low"].min() <= lv_
    mfe_r.append(mfe); beyond_r.append(bey); reached.append(bool(hit))
mag["MFE_R"] = mfe_r; mag["beyond_R"] = beyond_r; mag["reached"] = reached

q = np.percentile(mag["MFE_R"], [25, 50, 75, 90])
emit(f"- MFE (R): p25 {q[0]:+.2f} | median {q[1]:+.2f} | p75 {q[2]:+.2f} | p90 {q[3]:+.2f}")
emit(f"- level reached: {np.mean(reached)*100:.0f}% of trades")
rch = mag[mag["reached"]]
qb = np.percentile(rch["beyond_R"], [25, 50, 75, 90])
emit(f"- excursion BEYOND the level, reached trades only (R): p25 {qb[0]:+.2f} | "
     f"median {qb[1]:+.2f} | p75 {qb[2]:+.2f} | p90 {qb[3]:+.2f}")
cont = (rch["beyond_R"] > 0.5).mean(); pin = (rch["beyond_R"] <= 0.25).mean()
emit(f"- of reached trades: {cont*100:.0f}% continue >0.5R past the level; "
     f"{pin*100:.0f}% stall within 0.25R of it (pin)")
emit(f"- MFE vs distance: dist median {mag['near_dist_R'].median():.2f}R, "
     f"MFE median {q[1]:.2f}R -> typical run is ~{q[1]-mag['near_dist_R'].median():.2f}R past the level\n")

# B. target ladder (fresh sims, same 43 signal rows)
emit("## B. Target ladder on the magnet trades\n")
keys = mag.set_index(["DateTime", "Direction"]).index
ladder = {
    "1R flat": dict(target_r=1.0),
    "2R flat": dict(target_r=2.0),
    "3R + BE@1R (current)": dict(target_r=3.0, ratchet_r=1.0, ratchet_dest="BE"),
    "5R + BE@1R": dict(target_r=5.0, ratchet_r=1.0, ratchet_dest="BE"),
    "EOD only (no target)": dict(target_r=99.0),
}
emit("| exit | stats |")
emit("|---|---|")
for name, kw in ladder.items():
    r_ = simulate_trades(signals=win, ticks_by_date=ticks, **BASE, **kw)
    fr = prep(r_)
    fr = fr[fr.set_index(["DateTime", "Direction"]).index.isin(keys)]
    emit(f"| {name} | {stats(fr)} |")

# C. goldilocks: ExpR by distance band to the level ahead (stacked, 3R/BE cached sim)
emit("\n## C. Distance bands — is there a goldilocks zone?\n")
emit("| dist to level ahead | n | ExpR | PF | net$ |")
emit("|---|---|---|---|---|")
bands = [(0.0, 0.25), (0.25, 0.5), (0.5, 0.75), (0.75, 1.0),
         (1.0, 1.5), (1.5, 2.0), (2.0, 99.0)]
for lo, hi in bands:
    g = stk[(stk["near_dist_R"] > lo) & (stk["near_dist_R"] <= hi)]
    if len(g) == 0:
        emit(f"| {lo}–{hi}R | 0 | — | — | — |"); continue
    r = g["Rmult"]; pnl = g["PnL"]
    gw = pnl[pnl > 0].sum(); gl = abs(pnl[pnl < 0].sum())
    emit(f"| {lo}–{hi if hi < 99 else '∞'}R | {len(g)} | {r.mean():+.3f} | "
         f"{(gw/gl if gl>0 else np.inf):.2f} | ${pnl.sum():+,.0f} |")
g = stk[stk["near_dist_R"].isna()]
if len(g):
    emit(f"| no main level ahead | {len(g)} | {g['Rmult'].mean():+.3f} | — | ${g['PnL'].sum():+,.0f} |")

# same bands in POINTS (chart-friendly)
emit("\n| dist (ES points) | n | ExpR | net$ |")
emit("|---|---|---|---|")
stk["near_dist_pts"] = stk["near_dist_R"] * stk["riskp"]
for lo, hi in [(0, 5), (5, 10), (10, 15), (15, 20), (20, 30), (30, 999)]:
    g = stk[(stk["near_dist_pts"] > lo) & (stk["near_dist_pts"] <= hi)]
    if len(g) == 0:
        continue
    emit(f"| {lo}–{hi if hi < 999 else '∞'} pts | {len(g)} | {g['Rmult'].mean():+.3f} | ${g['PnL'].sum():+,.0f} |")

OUT.write_text("\n".join(L), encoding="utf-8")
print(f"\nwritten {OUT}")
