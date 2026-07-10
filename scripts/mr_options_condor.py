"""S67 structure comparison: IRON CONDOR / DTE sweep / fixed-width on the SAME 146
STMR bull-put entries, SAME fill model (mid +/- 0.25*half-spread), SAME SMA5 fast exit.

This is a STRUCTURE COMPARISON, not a joint optimization. Baseline BPS is reproduced
first; every variant reuses the exact entry/exit date pairs from
docs/living/mr_bull_put_spread_trades.parquet so entries are identical by construction.

Axes (S67 spec):
  1. Baseline BPS (reproduce 146 / 84% / PF 3.78 / +$39,383 / maxDD -$2,951)
  2. Iron condor = BPS + bear-call spread, call-delta sweep {30/15, 25/10, 20/10}
  3. Exit rule: SMA5 closes BOTH sides  vs  put side only (let call ride the fade)
  4. DTE sweep {7,14,21,30,45} on BPS baseline (+ best condor)
  5. Fixed-width put variant: long leg = short_strike - {25,50}pt (vs 15-delta)

Scoring: trades, win%, PF, total$, maxDD, avg loser$, per-trade avg RoC,
RoC on PEAK CONCURRENT collateral (the capital-efficiency headline), call-side
breach rate, and mean ACTUAL dte (early years lack short-dated expiries -> surfaced).
"""
import glob
from pathlib import Path
import numpy as np
import pandas as pd
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import importlib.util

ROOT = Path(r"c:\Users\Admin\myquant"); OPT = ROOT/"data"/"optionsdx"
spec = importlib.util.spec_from_file_location("m", str(ROOT/"scripts"/"mr_options_strategies.py"))
mm = importlib.util.module_from_spec(spec); spec.loader.exec_module(mm)
SLIP = 0.25
COMM = 4.0   # $ per spread (matches BPS baseline's -4)


def fp(bid, ask, side, slip=SLIP):
    mid = (bid+ask)/2.0; half = (ask-bid)/2.0
    return mid - slip*half if side == "sell" else mid + slip*half


def okp(r):
    return (not r.empty) and np.isfinite(r.iloc[0].P_BID) and np.isfinite(r.iloc[0].P_ASK) and r.iloc[0].P_ASK > 0


def okc(r):
    return (not r.empty) and np.isfinite(r.iloc[0].C_BID) and np.isfinite(r.iloc[0].C_ASK) and r.iloc[0].C_ASK > 0


# ---- generic spread pricer -------------------------------------------------
def close_put(exc, exp, Ks, Kl, slip):
    """cost (points) to close a bull-put spread on the exit chain, or None."""
    def q(K, side):
        r = exc[(exc["EXPIRE_DATE"] == exp) & (exc["STRIKE"] == K)]
        return fp(float(r.iloc[0].P_BID), float(r.iloc[0].P_ASK), side, slip) if okp(r) else None
    xs = q(Ks, "buy"); xl = q(Kl, "sell")
    return (xs-xl) if (xs is not None and xl is not None) else None


def close_call(exc, exp, Ks, Kl, slip):
    """cost (points) to close a bear-call spread (sell Ks low / buy Kl high)."""
    def q(K, side):
        r = exc[(exc["EXPIRE_DATE"] == exp) & (exc["STRIKE"] == K)]
        return fp(float(r.iloc[0].C_BID), float(r.iloc[0].C_ASK), side, slip) if okc(r) else None
    xs = q(Ks, "buy"); xl = q(Kl, "sell")
    return (xs-xl) if (xs is not None and xl is not None) else None


def peak_concurrent(t):
    """max summed open collateral across the life of the book (capital required)."""
    ev = []
    for _, r in t.iterrows():
        ev.append((pd.to_datetime(r.entry), r.coll)); ev.append((pd.to_datetime(r.exit), -r.coll))
    ev.sort(key=lambda x: (x[0], -x[1]))  # opens before closes same day
    cur = pk = 0.0
    for _, d in ev:
        cur += d; pk = max(pk, cur)
    return pk


def stats(t, label):
    if t.empty:
        return dict(label=label, n=0)
    eq = t.pnl.cumsum().values
    mdd = (eq-np.maximum.accumulate(eq)).min()
    losers = t.pnl[t.pnl < 0]
    pf = t.pnl[t.pnl > 0].sum()/(-losers.sum()) if losers.sum() < 0 else np.inf
    pk = peak_concurrent(t)
    return dict(label=label, n=len(t), win=(t.pnl > 0).mean()*100, pf=pf,
                total=t.pnl.sum(), mdd=mdd, avg=t.pnl.mean(),
                avgloser=(losers.mean() if len(losers) else 0.0),
                avgcoll=t.coll.mean(), roc=t.roc.mean()*100,
                peak=pk, roc_peak=(t.pnl.sum()/pk*100 if pk > 0 else np.nan),
                breach=(t.breach.mean()*100 if "breach" in t else np.nan),
                adte=t.adte.mean())


# ---- one backtest variant --------------------------------------------------
def backtest(sig, by, px, dte, short_d=0.30, long_d=0.15,
             condor=False, call_sd=0.30, call_ld=0.15,
             fixed_width=None, exit_call="both"):
    """sig: list of (entry, exit). Returns per-trade DataFrame."""
    rows = []
    for e, x in sig:
        en = by.get(e); ex = by.get(x)
        if en is None:
            continue
        exp = en.iloc[(en["DTE"]-dte).abs().argmin()]["EXPIRE_DATE"]
        adte = float(en.iloc[(en["DTE"]-dte).abs().argmin()]["DTE"])
        eall = en[en["EXPIRE_DATE"] == exp]
        puts = eall[eall["P_DELTA"].notna() & (eall["P_BID"] > 0) & (eall["P_ASK"] > 0)]
        if len(puts) < 4:
            continue
        # --- put side (bull put) ---
        sp = puts.iloc[(puts["P_DELTA"].abs()-short_d).abs().argmin()]
        if fixed_width is not None:
            avail = puts[puts["STRIKE"] <= sp.STRIKE - fixed_width]
            if avail.empty:
                continue
            lp = avail.iloc[(avail["STRIKE"]-(sp.STRIKE-fixed_width)).abs().argmin()]
        else:
            lp = puts.iloc[(puts["P_DELTA"].abs()-long_d).abs().argmin()]
        if lp.STRIKE >= sp.STRIKE:
            continue
        credit_p = fp(sp.P_BID, sp.P_ASK, "sell") - fp(lp.P_BID, lp.P_ASK, "buy")
        if credit_p <= 0:
            continue
        put_w = sp.STRIKE - lp.STRIKE

        # --- call side (bear call), optional ---
        credit_c = 0.0; call_w = 0.0; Kcs = Kcl = None
        if condor:
            calls = eall[eall["C_DELTA"].notna() & (eall["C_BID"] > 0) & (eall["C_ASK"] > 0)]
            if len(calls) < 4:
                continue
            sc = calls.iloc[(calls["C_DELTA"].abs()-call_sd).abs().argmin()]
            lc = calls.iloc[(calls["C_DELTA"].abs()-call_ld).abs().argmin()]
            if lc.STRIKE <= sc.STRIKE:
                continue
            credit_c = fp(sc.C_BID, sc.C_ASK, "sell") - fp(lc.C_BID, lc.C_ASK, "buy")
            if credit_c <= 0:
                continue
            Kcs, Kcl = sc.STRIKE, lc.STRIKE; call_w = Kcl - Kcs

        credit = credit_p + credit_c
        past = pd.to_datetime(x) > pd.to_datetime(exp)
        S_exp = px.get(exp)

        # --- put exit cost ---
        if past:
            if S_exp is None:
                continue
            cost_p = max(0, sp.STRIKE-S_exp) - max(0, lp.STRIKE-S_exp)
        else:
            undx = float(ex.iloc[0].UNDERLYING_LAST) if ex is not None else float(sp.UNDERLYING_LAST)
            cp = close_put(ex, exp, sp.STRIKE, lp.STRIKE, SLIP) if ex is not None else None
            cost_p = cp if cp is not None else (max(0, sp.STRIKE-undx)-max(0, lp.STRIKE-undx))

        # --- call exit cost (condor) ---
        cost_c = 0.0; breach = 0
        if condor:
            # "put_only": let the call side ride to expiry (always intrinsic-settle at exp)
            ride = (exit_call == "put_only")
            if past or ride:
                if S_exp is None:
                    continue
                cost_c = max(0, S_exp-Kcs) - max(0, S_exp-Kcl)
                breach = int(S_exp > Kcs)
            else:
                undx = float(ex.iloc[0].UNDERLYING_LAST) if ex is not None else float(sc.UNDERLYING_LAST)
                cc = close_call(ex, exp, Kcs, Kcl, SLIP) if ex is not None else None
                cost_c = cc if cc is not None else (max(0, undx-Kcs)-max(0, undx-Kcl))
                breach = int(undx > Kcs)

        if not (np.isfinite(credit) and np.isfinite(cost_p) and np.isfinite(cost_c)):
            continue
        nspread = 2 if condor else 1
        pnl = (credit - cost_p - cost_c)*100 - COMM*nspread
        # collateral: broker margins the larger side, credit reduces it
        coll = (max(put_w, call_w) - credit)*100 if condor else (put_w - credit_p)*100
        rows.append((e, x, (pd.to_datetime(x)-pd.to_datetime(e)).days, adte,
                     credit*100, pnl, coll, breach))
    t = pd.DataFrame(rows, columns=["entry", "exit", "days", "adte", "credit", "pnl", "coll", "breach"])
    if not t.empty:
        t["yr"] = t.entry.str[:4]; t["roc"] = t.pnl/t.coll
    return t


def prow(s):
    if s.get("n", 0) == 0:
        return f"{s['label']:<26}   (no trades)"
    return (f"{s['label']:<26}{s['n']:>4}{s['win']:>6.0f}%{s['pf']:>7.2f}"
            f"{s['total']:>+10,.0f}{s['mdd']:>+9,.0f}{s['avgloser']:>+8,.0f}"
            f"{s['roc']:>+7.1f}%{s['peak']:>10,.0f}{s['roc_peak']:>+8.1f}%"
            f"{s['breach']:>7.0f}%{s['adte']:>7.1f}")


HEAD = (f"{'variant':<26}{'n':>4}{'win':>6}{'PF':>7}{'total$':>10}{'maxDD':>9}"
        f"{'avgL$':>8}{'RoC':>8}{'peakCap':>10}{'RoC/pk':>8}{'brch':>7}{'aDTE':>7}")


def main():
    t0 = pd.read_parquet(ROOT/"docs"/"living"/"mr_bull_put_spread_trades.parquet")
    sig = list(zip(t0.entry.tolist(), t0.exit.tolist()))
    dates = set(t0.entry) | set(t0.exit)
    print(f"loading chains for {len(dates)} dates (DTE<=66 window, ~1-2 min)...")
    files = sorted(glob.glob(str(OPT/"*.txt")))
    ch = mm.load(dates, 45, files)          # dte=45 -> DTE<=66 covers the 7..45 sweep
    by = {k: v for k, v in ch.groupby("QUOTE_DATE")}
    px = mm.load  # placeholder to avoid lints
    # underlying close per date for intrinsic settle
    px = {}
    for f in files:
        df = pd.read_csv(f, skipinitialspace=True,
                         usecols=lambda c: c.strip().strip("[]").upper() in ("QUOTE_DATE", "UNDERLYING_LAST"))
        df.columns = [c.strip().strip("[]").upper() for c in df.columns]
        for dt, g in df.groupby("QUOTE_DATE"):
            k = str(dt).strip()
            if k not in px:
                px[k] = float(g["UNDERLYING_LAST"].iloc[0])
    print(f"chains loaded: {len(ch):,} rows, {len(by)} dates\n")

    results = []

    # === 1. Baseline BPS (reproduce) ===
    base = backtest(sig, by, px, dte=30)
    results.append(("BASELINE", stats(base, "BPS 30/15  30DTE (base)")))

    # === 2. Iron condor call-delta sweep (30DTE, exit=both) ===
    condor_runs = {}
    for cs, cl, name in [(0.30, 0.15, "IC 30/15call"), (0.25, 0.10, "IC 25/10call"), (0.20, 0.10, "IC 20/10call")]:
        tc = backtest(sig, by, px, dte=30, condor=True, call_sd=cs, call_ld=cl, exit_call="both")
        condor_runs[name] = tc
        results.append(("CONDOR", stats(tc, f"{name} both")))

    # === 3. Exit rule: put-only (let call ride) on each condor ===
    for cs, cl, name in [(0.30, 0.15, "IC 30/15call"), (0.25, 0.10, "IC 25/10call"), (0.20, 0.10, "IC 20/10call")]:
        tc = backtest(sig, by, px, dte=30, condor=True, call_sd=cs, call_ld=cl, exit_call="put_only")
        results.append(("EXIT", stats(tc, f"{name} put-only")))

    # pick best condor (by RoC on peak cap among the 'both' variants) for the DTE sweep
    best_name = max(condor_runs, key=lambda k: stats(condor_runs[k], k).get("roc_peak", -1e9)
                    if not condor_runs[k].empty else -1e9)
    bcs, bcl = {"IC 30/15call": (0.30, 0.15), "IC 25/10call": (0.25, 0.10), "IC 20/10call": (0.20, 0.10)}[best_name]

    # === 4. DTE sweep on BPS baseline + best condor ===
    for d in [7, 14, 21, 30, 45]:
        tb = backtest(sig, by, px, dte=d)
        results.append(("DTE-BPS", stats(tb, f"BPS 30/15  {d}DTE")))
    for d in [7, 14, 21, 30, 45]:
        tc = backtest(sig, by, px, dte=d, condor=True, call_sd=bcs, call_ld=bcl, exit_call="both")
        results.append(("DTE-IC", stats(tc, f"{best_name} {d}DTE")))

    # === 5. Fixed-width put variant (open item d) ===
    for w in [25, 50]:
        tw = backtest(sig, by, px, dte=30, fixed_width=w)
        results.append(("WIDTH", stats(tw, f"BPS 30d/-{w}pt  30DTE")))

    # ---- print grouped tables ----
    order = ["BASELINE", "CONDOR", "EXIT", "DTE-BPS", "DTE-IC", "WIDTH"]
    titles = {"BASELINE": "1. BASELINE (reproduce S64/S67)",
              "CONDOR": "2. IRON CONDOR — call-delta sweep (30DTE, SMA5 closes BOTH sides)",
              "EXIT": "3. EXIT RULE — SMA5 closes put only, call side rides the fade",
              "DTE-BPS": "4a. DTE SWEEP — bull put spread baseline",
              "DTE-IC": f"4b. DTE SWEEP — best condor ({best_name}, exit=both)",
              "WIDTH": "5. FIXED-WIDTH put (kills the $22k tail collateral; open item d)"}
    print("="*len(HEAD))
    for grp in order:
        print(f"\n### {titles[grp]}")
        print(HEAD)
        for g, s in results:
            if g == grp:
                print(prow(s))
    # flat summary parquet
    df = pd.DataFrame([s for _, s in results])
    df.to_parquet(ROOT/"docs"/"living"/"mr_options_condor_summary.parquet")

    # ---- comparison chart: RoC-on-peak-capital vs total$ ----
    fig, ax = plt.subplots(figsize=(12, 7))
    colmap = {"BASELINE": "black", "CONDOR": "tab:blue", "EXIT": "tab:cyan",
              "DTE-BPS": "tab:green", "DTE-IC": "tab:orange", "WIDTH": "tab:purple"}
    for g, s in results:
        if s.get("n", 0) == 0 or not np.isfinite(s.get("roc_peak", np.nan)):
            continue
        ax.scatter(s["roc_peak"], s["total"], s=90, color=colmap[g], zorder=3,
                   edgecolor="white", linewidth=.7)
        ax.annotate(s["label"], (s["roc_peak"], s["total"]), fontsize=7,
                    xytext=(4, 3), textcoords="offset points")
    ax.axhline(0, color="gray", lw=.7)
    ax.set_xlabel("Return on PEAK concurrent collateral (%)  — capital efficiency →")
    ax.set_ylabel("Total P&L 2010-2023 ($)")
    ax.set_title("S67 options structure comparison — same 146 STMR entries, same fill model")
    ax.grid(alpha=.3)
    from matplotlib.lines import Line2D
    ax.legend(handles=[Line2D([0], [0], marker="o", color="w", markerfacecolor=colmap[k],
              label=titles[k].split(" — ")[0], markersize=9) for k in order], fontsize=8, loc="best")
    plt.tight_layout()
    p = ROOT/"docs"/"living"/"mr_options_condor_compare.png"
    plt.savefig(p, dpi=120)
    print(f"\nsummary parquet: docs/living/mr_options_condor_summary.parquet")
    print(f"chart: {p}")


if __name__ == "__main__":
    main()
