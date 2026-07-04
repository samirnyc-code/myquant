"""DEEP DIVE: 'AM trade toward a prior-EOD main gamma level within 1R'.
One finding, full stress battery:
  1. the actual trades (audit list)
  2. day concentration / dependence on top days & trades
  3. definition robustness grid (distance threshold x AM cutoff) — smoothness test
  4. direction / CC-type splits
  5. magnet confirmation: does price actually REACH the level after entry?
  6. exit interaction: 1R flat exec vs 3R/BE
  7. monthly P&L path
"""
import os
import sys
from pathlib import Path

import numpy as np
import pandas as pd

sys.stdout.reconfigure(encoding="utf-8", errors="replace")
os.environ["MQ_APPLY_NEXT_DAY"] = "1"
ROOT = Path(r"c:\Users\Admin\myquant")
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
OUT = ROOT / "docs" / "living" / "menthorq_magnet_deepdive_20260704.md"
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

res = pd.read_parquet(ROOT / "data" / "menthorq" / "_study_sim_results.parquet")


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
        for name, lv in lm.items():
            d_ = (lv - entry[i]) * s[i]
            if 0 < d_ < bd:
                best, bd = name, d_
        which.append(best); dist.append(bd if np.isfinite(bd) else np.nan)
    f["near_lev"] = which
    f["near_dist_pts"] = dist
    f["near_dist_R"] = np.array(dist) / riskp
    f["s"] = s
    f["hh"] = pd.to_datetime(f["DateTime"]).dt.hour + pd.to_datetime(f["DateTime"]).dt.minute / 60
    return f


def stats(g):
    n = len(g)
    if n == 0:
        return "n=0"
    r = g["Rmult"].to_numpy(); pnl = g["PnL"].to_numpy()
    ci = 1.96 * r.std(ddof=1) / np.sqrt(n) if n > 1 else np.nan
    gw = pnl[pnl > 0].sum(); gl = abs(pnl[pnl < 0].sum())
    pf = gw / gl if gl > 0 else np.inf
    return f"n={n} ExpR {r.mean():+.3f} ±{ci:.3f} PF {pf:.2f} WR {(pnl>0).mean()*100:.0f}% ${pnl.sum():+,.0f}"


f = prep(res)
stk = f[f["stack_pass"] == True].copy()  # noqa: E712
AM = 11.0
mag = stk[(stk["hh"] < AM) & (stk["near_dist_R"] <= 1.0)].copy()
emit("# Deep dive — AM trades toward a prior-EOD main gamma level (<=1R)\n")
emit(f"Definition: stacked signal, entry-bar close before 11:00 CT, nearest main "
     f"MQ level ahead within 1R. Baseline battery on n={len(mag)}.\n")
emit(f"- magnet: {stats(mag)}")
emit(f"- rest of stack: {stats(stk.drop(mag.index))}\n")

# 1. audit list
emit("## 1. The actual trades\n")
emit("| date | time | dir | CC | toward | dist(R) | R done | exit |")
emit("|---|---|---|---|---|---|---|---|")
for _, r in mag.sort_values("DateTime").iterrows():
    emit(f"| {r['DateD'].date()} | {pd.to_datetime(r['DateTime']):%H:%M} | {r['Direction']} "
         f"| {r['SignalType']} | {r['near_lev'].replace('call_resistance','CR').replace('put_support','PS').replace('high_vol_level','HVL').replace('_0dte','0')} "
         f"| {r['near_dist_R']:.2f} | {r['Rmult']:+.2f} | {r['ExitReason']} |")

# 2. concentration
emit("\n## 2. Concentration\n")
dpnl = mag.groupby("DateD")["PnL"].sum().sort_values()
emit(f"- {len(dpnl)} distinct days carry the {len(mag)} trades; "
     f"top day ${dpnl.iloc[-1]:+,.0f}, top-3 days ${dpnl.iloc[-3:].sum():+,.0f} "
     f"of ${mag['PnL'].sum():+,.0f} total")
srt = mag.sort_values("PnL")
emit(f"- drop best single trade: {stats(srt.iloc[:-1])}")
emit(f"- drop best 3 trades: {stats(srt.iloc[:-3])}")
emit(f"- drop best day: {stats(mag[mag['DateD'] != dpnl.index[-1]])}")
emit(f"- longs {stats(mag[mag['s'] > 0])}")
emit(f"- shorts {stats(mag[mag['s'] < 0])}")
emit("- by CC type: " + "; ".join(f"{t}: {stats(g)}" for t, g in mag.groupby("SignalType")))

# 3. robustness grid
emit("\n## 3. Definition robustness (ExpR / n) — smooth or cliff?\n")
emit("| dist ≤ | AM<10:00 | AM<11:00 | AM<12:00 | all day |")
emit("|---|---|---|---|---|")
for thr in (0.5, 0.75, 1.0, 1.5, 2.0):
    cells = []
    for cut in (10.0, 11.0, 12.0, 24.0):
        g = stk[(stk["hh"] < cut) & (stk["near_dist_R"] <= thr)]
        cells.append(f"{g['Rmult'].mean():+.2f}/{len(g)}" if len(g) else "—")
    emit(f"| {thr}R | " + " | ".join(cells) + " |")

# 5. magnet confirmation — does price REACH the level after entry?
emit("\n## 5. Does price actually reach the level? (magnet confirmation)\n")
reach_all, reach = [], []
for _, r in mag.iterrows():
    db = bars[day == r["DateD"]]
    after = db[db["DateTime"] >= pd.to_datetime(r["DateTime"])]
    lv = lev[r["DateD"]][r["near_lev"]]
    hit = ((after["High"] >= lv) & (after["Low"] <= lv)).any() or \
          bool(((after["High"].max() >= lv) if r["s"] > 0 else (after["Low"].min() <= lv)))
    reach.append(hit)
mag["reached"] = reach
emit(f"- level reached before EOD: {np.mean(reach)*100:.0f}% of magnet trades")
emit(f"- winners reaching level: {mag[mag['PnL']>0]['reached'].mean()*100:.0f}%; "
     f"losers reaching: {mag[mag['PnL']<=0]['reached'].mean()*100:.0f}%")
# baseline reach rate for non-magnet stacked trades to their nearest level (any dist)
base_reach = []
for _, r in stk.drop(mag.index).dropna(subset=["near_dist_R"]).iterrows():
    db = bars[day == r["DateD"]]
    after = db[db["DateTime"] >= pd.to_datetime(r["DateTime"])]
    if after.empty: continue
    lv = lev[r["DateD"]][r["near_lev"]]
    base_reach.append(bool((after["High"].max() >= lv) if r["s"] > 0 else (after["Low"].min() <= lv)))
emit(f"- (non-magnet stacked trades reach their nearest level {np.mean(base_reach)*100:.0f}% — mostly farther away)")

# 6. exit interaction: rerun sim at 1R flat
emit("\n## 6. Exit interaction — same trades at 1R flat (fresh sim)\n")
sig = parse_signals(SIG_TXT)
win = sig[(sig["DateTime"] >= WIN_START) & (sig["DateTime"] < WIN_END + pd.Timedelta(days=1))].copy()
sc = compute_stack_columns(win, bars)
win = win.join(sc)
dates = sorted(win["Date"].unique())
ticks = {d: massive.load_continuous_ticks(d) for d in dates}
ticks = {d: t for d, t in ticks.items() if t is not None and not t.empty}
bbd = {d.date(): g.reset_index(drop=True) for d, g in bars.groupby(day)}
res1 = simulate_trades(signals=win, ticks_by_date=ticks, target_r=1.0,
                       entry_slip=1, exit_slip=1, stop_offset=1, tick_value=12.5,
                       contracts=1, commission=4.36, bars_by_date=bbd)
f1 = prep(res1)
stk1 = f1[f1["stack_pass"] == True]  # noqa: E712
mag1 = stk1[(stk1["hh"] < AM) & (stk1["near_dist_R"] <= 1.0)]
emit(f"- @1R flat magnet: {stats(mag1)}")
emit(f"- @1R flat rest of stack: {stats(stk1.drop(mag1.index))}")

# 7. monthly path
emit("\n## 7. Monthly P&L (3R/BE exec)\n")
emit("| month | n | net$ |")
emit("|---|---|---|")
for m, g in mag.groupby(mag["DateD"].dt.to_period("M")):
    emit(f"| {m} | {len(g)} | ${g['PnL'].sum():+,.0f} |")

OUT.write_text("\n".join(L), encoding="utf-8")
print(f"\nwritten {OUT}")
