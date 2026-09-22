"""Meaningful backtest of the GexLog premium-selling thesis (S-gexlog).

THESIS under test: sell the VIX-implied expected-move range as a defined-risk
iron condor; condition the band width on the VIX regime (the GexLog EM vs MQ 1D
finding: a VIX-1sigma band is breached more in high-vol regimes, so widen it).

WHY THIS DESIGN (honest constraints):
- GexLog's archive (2026-04+) does NOT overlap our historical chains (2010-2023),
  so GexLog's proprietary GO/WAIT signal CANNOT be backtested here. We test only
  the RECONSTRUCTABLE core: the EM band (VIX formula, validated exact) + VIX-regime
  band scaling. The GO/WAIT gate is forward-only (pull_archive.py, growing daily).
- True daily 0DTE SPX expiries didn't exist before ~2022, so a 0DTE program can't
  span 2018/2020. We use a WEEKLY ~7-DTE condor for regime robustness instead.
- Held to expiry => cash settlement is EXACT (no exit-fill modeling). Only ENTRY
  pays the spread; we sweep slippage {mid, mid+-0.25*half, full cross}.

METRICS: P&L, profit factor, max drawdown, avg loser, and TAIL (worst-5% mean) --
NOT win-rate as the headline. Broken out by year and VIX regime; 2018/2020/2022
(the premium-seller graveyards) are the real test.

Outputs (dated): data/options_sim/gexlog_bt_<date>.csv + printed tables.
"""
import glob
import importlib.util
import math
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(r"c:\Users\Admin\myquant")
OPT = ROOT / "data" / "optionsdx"
spec = importlib.util.spec_from_file_location("m", str(ROOT / "scripts" / "mr_options_strategies.py"))
mm = importlib.util.module_from_spec(spec)
spec.loader.exec_module(mm)

SQRT252 = 15.874507866387544
COMM = 4.0            # $ per spread round-turn (matches BPS baseline)
TARGET_DTE = 7
DTE_LO, DTE_HI = 4, 10


def load_vix():
    v = {}
    for r in pd.read_csv(ROOT / "data" / "vix_daily.csv").itertuples(index=False):
        v[str(r.date)] = float(r.close)
    return v


def vix_bucket(x):
    if x < 15: return "1 <15"
    if x < 20: return "2 15-20"
    if x < 30: return "3 20-30"
    return "4 >30"


def em_halfwidth(spot, vix, dte, k):
    """k-sigma expected move over `dte` calendar days, in index points."""
    return k * spot * (vix / 100.0) * math.sqrt(dte / 252.0)


def nearest_strike(strikes, target):
    return strikes[int(np.abs(strikes - target).argmin())]


def band_k_L0(vix):
    return 1.0


def band_k_L1(vix):
    """VIX-regime band scaling: widen the band as vol rises (stress breaches a
    flat 1-sigma band -- the MQ-wins-in-stress finding)."""
    if vix < 20: return 1.0
    if vix < 30: return 1.15
    return 1.35


def run(by, px, schedule, band_k, wing, slip):
    rows = []
    for qd in schedule:
        en = by.get(qd)
        vix = VIX.get(qd)
        if en is None or vix is None:
            continue
        spot = float(en["UNDERLYING_LAST"].iloc[0])
        # pick expiry nearest TARGET_DTE within [DTE_LO, DTE_HI]
        cand = en[(en["DTE"] >= DTE_LO) & (en["DTE"] <= DTE_HI)]
        if cand.empty:
            continue
        exp = cand.iloc[(cand["DTE"] - TARGET_DTE).abs().argmin()]["EXPIRE_DATE"]
        adte = float(cand.iloc[(cand["DTE"] - TARGET_DTE).abs().argmin()]["DTE"])
        ch = en[en["EXPIRE_DATE"] == exp]
        puts = ch[(ch["P_BID"] > 0) & (ch["P_ASK"] > 0)]
        calls = ch[(ch["C_BID"] > 0) & (ch["C_ASK"] > 0)]
        if len(puts) < 4 or len(calls) < 4:
            continue
        pk = puts["STRIKE"].values
        ck = calls["STRIKE"].values
        hw = em_halfwidth(spot, vix, adte, band_k(vix))

        sp_K = nearest_strike(pk, spot - hw)
        sc_K = nearest_strike(ck, spot + hw)
        lp_K = nearest_strike(pk, sp_K - wing)
        lc_K = nearest_strike(ck, sc_K + wing)
        if not (lp_K < sp_K < sc_K < lc_K):
            continue

        def q(df, K, cp, side):
            r = df[df["STRIKE"] == K]
            if r.empty: return None
            b, a = (r.iloc[0].P_BID, r.iloc[0].P_ASK) if cp == "P" else (r.iloc[0].C_BID, r.iloc[0].C_ASK)
            if not (np.isfinite(b) and np.isfinite(a) and a > 0): return None
            return mm.fillp(float(b), float(a), side, slip)

        sp = q(puts, sp_K, "P", "sell"); lp = q(puts, lp_K, "P", "buy")
        sc = q(calls, sc_K, "C", "sell"); lc = q(calls, lc_K, "C", "buy")
        if None in (sp, lp, sc, lc):
            continue
        credit = (sp - lp) + (sc - lc)
        if credit <= 0:
            continue
        put_w, call_w = sp_K - lp_K, lc_K - sc_K

        S_exp = px.get(str(exp))
        if S_exp is None:
            continue
        cost = (max(0, sp_K - S_exp) - max(0, lp_K - S_exp)) + \
               (max(0, S_exp - sc_K) - max(0, S_exp - lc_K))
        breach = int(S_exp < sp_K or S_exp > sc_K)
        pnl = (credit - cost) * 100 - COMM * 2
        coll = (max(put_w, call_w) - credit) * 100
        rows.append(dict(entry=qd, exp=str(exp), adte=adte, vix=vix,
                         bucket=vix_bucket(vix), spot=spot, credit=credit * 100,
                         pnl=pnl, coll=coll, breach=breach, yr=qd[:4]))
    return pd.DataFrame(rows)


def stat(t):
    if t.empty:
        return dict(n=0)
    eq = t.pnl.cumsum().values
    mdd = (eq - np.maximum.accumulate(eq)).min()
    losers = t.pnl[t.pnl < 0]
    pf = t.pnl[t.pnl > 0].sum() / (-losers.sum()) if losers.sum() < 0 else np.inf
    tail = np.mean(np.sort(t.pnl.values)[:max(1, len(t) // 20)])  # worst 5% mean
    return dict(n=len(t), win=(t.pnl > 0).mean() * 100, pf=pf, total=t.pnl.sum(),
                mdd=mdd, avg=t.pnl.mean(), avgL=(losers.mean() if len(losers) else 0),
                tail=tail, breach=t.breach.mean() * 100, roc=t.pnl.sum() / t.coll.mean() / len(t) * 100)


def show(name, t):
    s = stat(t)
    if s["n"] == 0:
        print(f"{name}: no trades"); return
    print(f"\n### {name}  (n={s['n']})")
    print(f"  total ${s['total']:+,.0f}   PF {s['pf']:.2f}   win {s['win']:.0f}%   "
          f"maxDD ${s['mdd']:+,.0f}   avgLoser ${s['avgL']:+,.0f}   tail(worst5%) ${s['tail']:+,.0f}   breach {s['breach']:.0f}%")
    print(f"  {'year':6}{'n':>4}{'total$':>10}{'PF':>7}{'win':>6}{'maxDD$':>10}{'tail$':>9}")
    for y in sorted(t.yr.unique()):
        sy = stat(t[t.yr == y])
        print(f"  {y:6}{sy['n']:>4}{sy['total']:>+10,.0f}{sy['pf']:>7.2f}{sy['win']:>5.0f}%{sy['mdd']:>+10,.0f}{sy['tail']:>+9,.0f}")
    print(f"  {'VIXreg':6}{'n':>4}{'total$':>10}{'PF':>7}{'win':>6}{'maxDD$':>10}{'tail$':>9}")
    for b in sorted(t.bucket.unique()):
        sb = stat(t[t.bucket == b])
        print(f"  {b:6}{sb['n']:>4}{sb['total']:>+10,.0f}{sb['pf']:>7.2f}{sb['win']:>5.0f}%{sb['mdd']:>+10,.0f}{sb['tail']:>+9,.0f}")


def main():
    global VIX
    VIX = load_vix()
    files = sorted(glob.glob(str(OPT / "*.txt")))
    print(f"scanning {len(files)} chain files for quote dates...")
    qdates = set()
    for f in files:
        c = pd.read_csv(f, usecols=lambda x: x.strip().strip("[]").upper() == "QUOTE_DATE",
                        skipinitialspace=True)
        c.columns = ["QUOTE_DATE"]
        qdates |= set(c["QUOTE_DATE"].astype(str).str.strip())
    print(f"loading chains ({len(qdates)} dates, DTE<={TARGET_DTE+21})...")
    ch = mm.load(qdates, TARGET_DTE, files)
    by = {k: v for k, v in ch.groupby("QUOTE_DATE")}
    px = {}
    for k, v in by.items():
        px[k] = float(v["UNDERLYING_LAST"].iloc[0])
    print(f"chains: {len(ch):,} rows, {len(by)} dates ({min(by)}..{max(by)})")

    # weekly non-overlapping schedule: >=5 trading days between entries
    alldates = sorted(by)
    schedule = []
    last_idx = -10
    for i, d in enumerate(alldates):
        if i - last_idx >= 5:
            schedule.append(d); last_idx = i
    print(f"entry schedule: {len(schedule)} weekly entries\n")

    out_rows = []
    for wing in (25, 50):
        for slip in (0.0, 0.25, 0.5):
            for lname, bk in (("L0 flat-1sigma", band_k_L0), ("L1 vix-scaled", band_k_L1)):
                t = run(by, px, schedule, bk, wing, slip)
                if t.empty:
                    continue
                s = stat(t)
                out_rows.append(dict(layer=lname, wing=wing, slip=slip, **s))
    summ = pd.DataFrame(out_rows)
    print("=" * 100)
    print("HEADLINE SWEEP (wing x slippage x layer):")
    print(summ[["layer", "wing", "slip", "n", "total", "pf", "win", "mdd", "tail", "breach"]]
          .to_string(index=False, float_format=lambda x: f"{x:,.1f}"))

    # detailed by-year/regime for the realistic case: wing=50, slip=0.25
    for lname, bk in (("L0 flat-1sigma", band_k_L0), ("L1 vix-scaled", band_k_L1)):
        show(f"{lname}  wing=50 slip=0.25", run(by, px, schedule, bk, 50, 0.25))

    outp = ROOT / "data" / "options_sim" / "gexlog_bt_20260804.csv"
    run(by, px, schedule, band_k_L1, 50, 0.25).to_csv(outp, index=False)
    print(f"\ntrade-level (L1 wing50 slip.25) -> {outp.relative_to(ROOT)}")
    summ.to_csv(ROOT / "data" / "options_sim" / "gexlog_bt_summary_20260804.csv", index=False)


if __name__ == "__main__":
    main()
