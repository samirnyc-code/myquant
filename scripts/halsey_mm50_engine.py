#!/usr/bin/env python
"""halsey_mm50_engine.py — S92-EA: the ACTUAL Halsey setup, backtested. 15M measured-move
50% pullback entries, with a swing-setting sweep and a NYSE-TICK filter.

METHOD (Ch2/6/8 of the RULEBOOK), CAUSAL:
  - Build 15M ES bars from the 5M master (open-labeled). Resample TICK too (hi=max, lo=min).
  - Detect swings on 15M with a fractal detector (sweep N). A confirmed UP leg = swing low L
    (bar jL) -> swing high H (bar jH). H is only KNOWN at jH+N (fractal confirmation) -> we
    only act from there (no look-ahead).
  - Measured move on the leg (R = H-L):  50% = L+0.5R (entry),  61.8% = L+0.382R (stop/fail),
    123% = L+1.236R (target).  Mirror for down legs (short).
  - Entry: LIMIT at 50%. After jH+N, the first bar whose low<=50% (long) fills at 50%.
    Trade dies if 61.8% breached (stop) or 123% hit (target) or EOD (mark-to-close). One
    trade per leg. Leg is abandoned if price breaks the 61.8% before ever reaching 50%.
  - Risk = |entry-stop| = 0.118R.  This is a high R:R (target ~6x risk), low win-rate setup.

  TICK filter at the pullback (Halsey: buy low ticks in an up-series / sell high ticks down):
    long  -> the fill bar's 15M tick_low  <= -TICK_OS
    short -> the fill bar's 15M tick_high >= +TICK_OS

Reports baseline vs TICK-filtered, per swing setting, with per-year stability + a
$-per-trade at ES $50/pt. Also writes an example-day chart. No anecdotes — full-sample.

Usage: python scripts/halsey_mm50_engine.py [TICK_OS=400]
"""
from __future__ import annotations

import sys
from pathlib import Path
import glob as _glob

import numpy as np
import pandas as pd
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.patches import Rectangle

sys.path.insert(0, str(Path(__file__).resolve().parent))
from nt_swing import nt_swing  # faithful NT8 Swing(Strength) port  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent
MASTER_DIR = ROOT / "data" / "nt_internals" / "master"
REV = ROOT / "research" / "revsim" / "revft_all_signals.csv"
FIG_DIR = ROOT / "eminiaddict" / "figures"
FRACTAL_N = [1, 2, 3, 5]
HORIZON_BARS = 26          # 15M bars (~6.5h) cap; also EOD-capped
ES_PT = 50.0


def build_15m():
    m = pd.read_parquet(sorted(_glob.glob(str(MASTER_DIR / "internals_es_5m_*.parquet")))[-1])
    m = m.set_index("DateTime").sort_index()
    o = m["es_open"].resample("15min").first()
    h = m["es_high"].resample("15min").max()
    l = m["es_low"].resample("15min").min()
    c = m["es_close"].resample("15min").last()
    tkh = m["tick_high"].resample("15min").max()
    tkl = m["tick_low"].resample("15min").min()
    g = pd.DataFrame({"O": o, "H": h, "L": l, "C": c, "tkh": tkh, "tkl": tkl}).dropna(subset=["O"])
    g = g[g["C"].notna()].reset_index().rename(columns={"DateTime": "dt"})
    g["day"] = g["dt"].dt.normalize()
    # keep RTH-ish 15M bars only (drop empties already gone); daily running tick extremes
    g["tick_day_hi"] = g.groupby("day")["tkh"].cummax()
    g["tick_day_lo"] = g.groupby("day")["tkl"].cummin()
    return g


def fractal(H, L, N):
    n = len(H); out = []
    for i in range(N, n - N):
        w = slice(i - N, i + N + 1)
        if H[i] == H[w].max() and (H[w] == H[i]).sum() == 1:
            out.append((i, 'H'))
        if L[i] == L[w].min() and (L[w] == L[i]).sum() == 1:
            out.append((i, 'L'))
    out.sort()
    return out


def legs_from_pivots(piv, H, L):
    """Alternating pivots -> legs. Return list of (jStart, jEnd, kind) where kind 'up'/'dn'.
    up leg: low then high; dn leg: high then low."""
    # collapse to strict alternation keeping extremes
    seq = []
    for i, k in piv:
        p = H[i] if k == 'H' else L[i]
        if seq and seq[-1][1] == k:
            pi, pk, pp = seq[-1]
            if (k == 'H' and p >= pp) or (k == 'L' and p <= pp):
                seq[-1] = (i, k, p)
            continue
        seq.append((i, k, p))
    legs = []
    for a, b in zip(seq, seq[1:]):
        (ia, ka, _), (ib, kb, _) = a, b
        if ka == 'L' and kb == 'H':
            legs.append((ia, ib, 'up'))
        elif ka == 'H' and kb == 'L':
            legs.append((ia, ib, 'dn'))
    return legs


def run(g, N, tick_os):
    H = g["H"].to_numpy(); L = g["L"].to_numpy(); C = g["C"].to_numpy()
    O = g["O"].to_numpy(); day = g["day"].to_numpy()
    tkl = g["tkl"].to_numpy(); tkh = g["tkh"].to_numpy()
    piv = nt_swing(H, L, N)   # faithful NT8 Swing(Strength=N)
    legs = legs_from_pivots(piv, H, L)
    n = len(g)
    trades = []
    for jL, jH, kind in legs:
        conf = max(jL, jH) + N          # fractal confirmation bar of the leg end
        if conf >= n:
            continue
        if kind == 'up':
            Lp, Hp = L[jL], H[jH]
            R = Hp - Lp
            if R <= 0:
                continue
            e50 = Lp + 0.5 * R; stop = Lp + 0.382 * R; tgt = Lp + 1.236 * R
            side = 1
        else:
            Hp, Lp = H[jH], L[jL]      # dn leg: high jL? no — jL is 'H', jH is 'L'
            # for dn leg jL is the high pivot, jH the low pivot
            Hp, Lp = H[jL], L[jH]
            R = Hp - Lp
            if R <= 0:
                continue
            e50 = Hp - 0.5 * R; stop = Hp - 0.382 * R; tgt = Hp - 1.236 * R
            side = -1
        # walk forward from confirmation: find the LIMIT fill at 50% before 61.8% breaks
        filled = None
        for k in range(conf + 1, min(conf + 1 + HORIZON_BARS, n)):
            if day[k] != day[conf]:
                break
            if side == 1:
                if L[k] <= stop:      # failed before reaching 50%
                    break
                if L[k] <= e50:
                    filled = k; break
            else:
                if H[k] >= stop:
                    break
                if H[k] >= e50:
                    filled = k; break
        if filled is None:
            continue
        # outcome from fill bar (fill at 50%), first-touch tgt vs stop, same day
        res = None; why = "mtm"; fk = filled
        for k in range(filled, min(filled + HORIZON_BARS, n)):
            if day[k] != day[filled]:
                fk = k - 1; break
            fk = k
            if side == 1:
                if L[k] <= stop:
                    res = -1.0; why = "stop"; break
                if H[k] >= tgt:
                    res = (tgt - e50) / (e50 - stop); why = "target"; break   # ~ +6.24R
            else:
                if H[k] >= stop:
                    res = -1.0; why = "stop"; break
                if L[k] <= tgt:
                    res = (e50 - tgt) / (stop - e50); why = "target"; break
        if res is None:
            res = side * (C[fk] - e50) / abs(e50 - stop)
        tick_ok = (tkl[filled] <= -tick_os) if side == 1 else (tkh[filled] >= tick_os)
        trades.append({"dt": g["dt"].iloc[filled], "year": g["dt"].iloc[filled].year,
                       "side": side, "R": res, "why": why, "tick_ok": bool(tick_ok),
                       "risk_pts": abs(e50 - stop),
                       "jL": jL, "jH": jH, "conf": conf, "fill": filled, "exit": fk,
                       "e50": e50, "stop": stop, "tgt": tgt, "N": N})
    return pd.DataFrame(trades)


def draw_audit(g, trades_day, day, out):
    """Audit chart: 15M candles + each trade's 50/61.8/123 lines, fill/exit markers."""
    gg = g[g["day"] == pd.Timestamp(day)].reset_index(drop=True)
    if len(gg) < 4:
        return False
    base = g.index[g["day"] == pd.Timestamp(day)][0]
    fig, ax = plt.subplots(figsize=(16, 8.5), facecolor="#0b0b0b")
    ax.set_facecolor("#0b0b0b"); ax.tick_params(colors="#aaa")
    for sp in ax.spines.values():
        sp.set_color("#333")
    ax.grid(True, color="#141414", lw=0.5)
    H = gg["H"].values; L = gg["L"].values; O = gg["O"].values; C = gg["C"].values
    for i in range(len(gg)):
        col = "#26a65b" if C[i] >= O[i] else "#e2453c"
        ax.plot([i, i], [L[i], H[i]], color=col, lw=1.1, zorder=2)
        ax.add_patch(Rectangle((i - .3, min(O[i], C[i])), .6, abs(C[i] - O[i]) or .1,
                               facecolor=col, edgecolor=col, zorder=3))
    for _, t in trades_day.iterrows():
        fk = int(t["fill"]) - base; ek = int(t["exit"]) - base
        if fk < 0 or fk >= len(gg):
            continue
        c = "#22d3ee" if t["why"] == "target" else ("#e2453c" if t["why"] == "stop" else "#aaa")
        for lv, ls, lc in [(t["e50"], "-", "#ffd400"), (t["stop"], ":", "#e2453c"),
                           (t["tgt"], "--", "#22d3ee")]:
            ax.hlines(lv, fk, max(ek, fk + 1), color=lc, ls=ls, lw=1.0, alpha=.8, zorder=4)
        ax.scatter([fk], [t["e50"]], marker=("^" if t["side"] == 1 else "v"), s=130,
                   color="#fff", edgecolor="#000", zorder=6)
        ax.annotate(t["why"], (fk, t["e50"]), textcoords="offset points", xytext=(4, 6),
                    color=c, fontsize=8, fontweight="bold")
    ax.set_title(f"MM 50% audit — {pd.Timestamp(day).date()}  (yellow=50% entry, red=61.8% "
                 f"stop, cyan=123% target)", color="#eee", loc="left", fontsize=12)
    step = max(1, len(gg) // 12)
    ax.set_xticks(range(0, len(gg), step))
    ax.set_xticklabels([gg["dt"][i].strftime("%H:%M") for i in range(0, len(gg), step)],
                       color="#aaa", fontsize=8)
    fig.tight_layout(); fig.savefig(out, dpi=115, facecolor=fig.get_facecolor()); plt.close(fig)
    return True


def st(d):
    if not len(d):
        return dict(n=0, win=np.nan, expR=np.nan, pf=np.nan, expPt=np.nan)
    w = d[d["R"] > 0]["R"].sum(); l = -d[d["R"] < 0]["R"].sum()
    expR = d["R"].mean()
    expPt = (d["R"] * d["risk_pts"]).mean()
    return dict(n=len(d), win=round(100 * (d["R"] > 0).mean(), 1), expR=round(expR, 3),
                pf=round(w / l, 2) if l else np.inf, expPt=round(expPt, 2))


def yrs(d):
    if not len(d):
        return "0/0"
    g = d.groupby("year")["R"].mean()
    return f"{(g > 0).sum()}/{len(g)}"


def main():
    tick_os = int(sys.argv[1]) if len(sys.argv) > 1 else 400
    g = build_15m()
    print(f"15M bars: {len(g):,}  {g['dt'].min().date()}..{g['dt'].max().date()}  "
          f"TICK_OS={tick_os}")
    stamp = g["dt"].max().strftime("%Y%m%d")
    allt = []
    print(f"\n{'setting':10s} {'group':12s} {'n':>5s} {'win%':>6s} {'expR':>7s} {'PF':>5s} "
          f"{'exp$/t':>7s} {'years+':>7s}")
    for N in FRACTAL_N:
        d = run(g, N, tick_os)
        d["N"] = N; allt.append(d)
        for grp, sub in [("baseline", d), (f"TICK<=-{tick_os}/>={tick_os}", d[d["tick_ok"]])]:
            s = st(sub)
            print(f"N={N:<8d} {grp:12s} {s['n']:5d} {s['win']:6}  {s['expR']:+.3f} {s['pf']:5} "
                  f"{s['expPt']*ES_PT if s['expPt']==s['expPt'] else float('nan'):+7.0f} "
                  f"{yrs(sub):>7s}")
    full = pd.concat(allt, ignore_index=True)
    out = MASTER_DIR / f"mm50_trades_{stamp}.csv"
    full.to_csv(out, index=False)
    print(f"\nwrote {out.relative_to(ROOT)}  ({len(full)} trades across settings)")

    # ---- AUDIT: outcome-type breakdown (phantom-fill / high-PF check) ----
    print("\n=== OUTCOME BREAKDOWN (per swing setting) ===")
    for N in FRACTAL_N:
        d = full[full["N"] == N]
        vc = d["why"].value_counts()
        tgt = d[d["why"] == "target"]; stp = d[d["why"] == "stop"]; mtm = d[d["why"] == "mtm"]
        print(f"N={N}: target={vc.get('target',0)} ({100*vc.get('target',0)/len(d):.0f}%, "
              f"avg {tgt['R'].mean():+.2f}R) | stop={vc.get('stop',0)} "
              f"({100*vc.get('stop',0)/len(d):.0f}%) | mtm={vc.get('mtm',0)} "
              f"({100*vc.get('mtm',0)/len(d):.0f}%, avg {mtm['R'].mean():+.2f}R)")

    # ---- AUDIT chart: the day with the most N=3 trades ----
    d3 = full[full["N"] == 3].copy()
    d3["day"] = pd.to_datetime(d3["dt"]).dt.normalize()
    if len(d3):
        aday = d3["day"].value_counts().idxmax()
        ap = FIG_DIR / f"mm50_audit_{pd.Timestamp(aday).strftime('%Y%m%d')}.png"
        if draw_audit(g, d3[d3["day"] == aday], aday, ap):
            print(f"\nwrote audit chart {ap.relative_to(ROOT)}  ({aday.date()}, "
                  f"{(d3['day']==aday).sum()} trades)")
    print("\nNote: 50% MM is high R:R (~+6R target vs -1R stop), so a <20% win rate can still "
          "be profitable. Read PF and exp$/trade, not win%.")


if __name__ == "__main__":
    main()
