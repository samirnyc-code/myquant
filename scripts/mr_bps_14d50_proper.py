"""S67 follow-up: PROPER standalone test of the 14DTE / 50pt-cap bull put spread.

Same 146 STMR entries (from the committed trades parquet), real OptionsDX SPX
bid/ask chains, SMA5 fast exit. Two changes the user asked for vs the S67 sweep:
  * MID fill (slip=0) as the headline  -- filled at the real (bid+ask)/2, no spread paid.
  * REALISTIC per-contract SPX options fees (not the flat $4/spread):
      fee = FEE_PC $/contract/side; entry = 2 contracts; exit = 2 contracts if closed
      early; cash-settled expiry = 0 closing fee. Default $1.30/contract all-in
      (retail SPX commission ~$0.65-1.00 + CBOE/ORF/reg ~$0.45-0.65).

Structure: short ~30-delta put, long put 50pt below (fixed width -> caps collateral).
Reports the full per-year table, capital metrics (peak concurrent collateral, RoC on
that capital), a slippage ladder (mid / mid+-0.25 / full cross) and a fee ladder so the
haircut is visible with the headline. Saves equity+DD chart and a parquet.
"""
import glob
from pathlib import Path
import numpy as np
import pandas as pd
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import importlib.util

ROOT = Path(__file__).resolve().parent.parent; OPT = ROOT/"data"/"optionsdx"
spec = importlib.util.spec_from_file_location("m", str(ROOT/"scripts"/"mr_options_strategies.py"))
mm = importlib.util.module_from_spec(spec); spec.loader.exec_module(mm)

DTE = 14
WIDTH = 50
SHORT_D = 0.30
FEE_PC = 1.30      # $/contract/side, realistic all-in retail SPX
HEAD_SLIP = 1.0    # bid/ask fill: sell the bid, buy the ask (full cross) — realistic worst case


def fp(bid, ask, side, slip):
    mid = (bid+ask)/2.0; half = (ask-bid)/2.0
    return mid - slip*half if side == "sell" else mid + slip*half


def okp(r):
    return (not r.empty) and np.isfinite(r.iloc[0].P_BID) and np.isfinite(r.iloc[0].P_ASK) and r.iloc[0].P_ASK > 0


def close_put(exc, exp, Ks, Kl, slip):
    def q(K, side):
        r = exc[(exc["EXPIRE_DATE"] == exp) & (exc["STRIKE"] == K)]
        return fp(float(r.iloc[0].P_BID), float(r.iloc[0].P_ASK), side, slip) if okp(r) else None
    xs = q(Ks, "buy"); xl = q(Kl, "sell")
    return (xs-xl) if (xs is not None and xl is not None) else None


def peak_concurrent(t):
    ev = []
    for _, r in t.iterrows():
        ev.append((pd.to_datetime(r.entry), r.coll)); ev.append((pd.to_datetime(r.exit), -r.coll))
    ev.sort(key=lambda x: (x[0], -x[1]))
    cur = pk = 0.0
    for _, d in ev:
        cur += d; pk = max(pk, cur)
    return pk


def backtest(sig, by, px, slip, fee_pc):
    rows = []
    for e, x in sig:
        en = by.get(e); ex = by.get(x)
        if en is None:
            continue
        exp = en.iloc[(en["DTE"]-DTE).abs().argmin()]["EXPIRE_DATE"]
        adte = float(en.iloc[(en["DTE"]-DTE).abs().argmin()]["DTE"])
        puts = en[(en["EXPIRE_DATE"] == exp) & en["P_DELTA"].notna() & (en["P_BID"] > 0) & (en["P_ASK"] > 0)]
        if len(puts) < 4:
            continue
        sp = puts.iloc[(puts["P_DELTA"].abs()-SHORT_D).abs().argmin()]
        avail = puts[puts["STRIKE"] <= sp.STRIKE - WIDTH]
        if avail.empty:
            continue
        lp = avail.iloc[(avail["STRIKE"]-(sp.STRIKE-WIDTH)).abs().argmin()]
        if lp.STRIKE >= sp.STRIKE:
            continue
        credit = fp(sp.P_BID, sp.P_ASK, "sell", slip) - fp(lp.P_BID, lp.P_ASK, "buy", slip)
        if credit <= 0:
            continue
        width = sp.STRIKE - lp.STRIKE
        past = pd.to_datetime(x) > pd.to_datetime(exp)
        closed_early = not past
        if past:
            S = px.get(exp)
            if S is None:
                continue
            cost = max(0, sp.STRIKE-S) - max(0, lp.STRIKE-S)
        else:
            undx = float(ex.iloc[0].UNDERLYING_LAST) if ex is not None else float(sp.UNDERLYING_LAST)
            cp = close_put(ex, exp, sp.STRIKE, lp.STRIKE, slip) if ex is not None else None
            cost = cp if cp is not None else (max(0, sp.STRIKE-undx)-max(0, lp.STRIKE-undx))
        if not (np.isfinite(credit) and np.isfinite(cost)):
            continue
        fee = 2*fee_pc + (2*fee_pc if closed_early else 0.0)   # 2 legs open, 2 to close early
        pnl = (credit-cost)*100 - fee
        coll = (width - credit)*100
        rows.append((e, x, (pd.to_datetime(x)-pd.to_datetime(e)).days, adte, int(sp.STRIKE),
                     int(lp.STRIKE), width, credit*100, pnl, coll, fee))
    t = pd.DataFrame(rows, columns=["entry", "exit", "days", "adte", "Ks", "Kl", "width",
                                    "credit", "pnl", "coll", "fee"])
    if not t.empty:
        t["yr"] = t.entry.str[:4]; t["roc"] = t.pnl/t.coll
    return t


def summ(t):
    eq = t.pnl.cumsum().values
    mdd = (eq-np.maximum.accumulate(eq)).min()
    losers = t.pnl[t.pnl < 0]
    pf = t.pnl[t.pnl > 0].sum()/(-losers.sum()) if losers.sum() < 0 else np.inf
    pk = peak_concurrent(t)
    return dict(n=len(t), win=(t.pnl > 0).mean()*100, pf=pf, total=t.pnl.sum(), mdd=mdd,
                avg=t.pnl.mean(), avgloser=(losers.mean() if len(losers) else 0.0),
                avgcoll=t.coll.mean(), roc=t.roc.mean()*100, peak=pk,
                roc_peak=(t.pnl.sum()/pk*100 if pk > 0 else np.nan),
                adte=t.adte.mean(), width=t.width.mean(), fees=t.fee.sum())


def main():
    t0 = pd.read_parquet(ROOT/"docs"/"living"/"mr_bull_put_spread_trades.parquet")
    sig = list(zip(t0.entry.tolist(), t0.exit.tolist()))
    dates = set(t0.entry) | set(t0.exit)
    files = sorted(glob.glob(str(OPT/"*.txt")))
    print(f"loading chains for {len(dates)} dates (~1 min)...")
    ch = mm.load(dates, DTE, files)
    by = {k: v for k, v in ch.groupby("QUOTE_DATE")}
    px = {}
    for f in files:
        df = pd.read_csv(f, skipinitialspace=True,
                         usecols=lambda c: c.strip().strip("[]").upper() in ("QUOTE_DATE", "UNDERLYING_LAST"))
        df.columns = [c.strip().strip("[]").upper() for c in df.columns]
        for dt, g in df.groupby("QUOTE_DATE"):
            k = str(dt).strip()
            if k not in px:
                px[k] = float(g["UNDERLYING_LAST"].iloc[0])

    # ---- HEADLINE: bid/ask fill, realistic fees ----
    t = backtest(sig, by, px, slip=HEAD_SLIP, fee_pc=FEE_PC)
    s = summ(t)
    print(f"\n{'='*78}")
    print(f"14DTE / {WIDTH}pt-cap BULL PUT SPREAD  —  BID/ASK fill, ${FEE_PC:.2f}/contract fees")
    print(f"short ~{SHORT_D:.0%} put, long {WIDTH}pt below | same 146 STMR entries | SMA5 exit")
    print(f"{'='*78}")
    print(f"trades {s['n']}   win {s['win']:.0f}%   PF {s['pf']:.2f}   total ${s['total']:+,.0f}   maxDD ${s['mdd']:+,.0f}")
    print(f"avg P&L ${s['avg']:+.0f}   avg loser ${s['avgloser']:+.0f}   avg collateral ${s['avgcoll']:,.0f}   avg width {s['width']:.0f}pt")
    print(f"per-trade RoC {s['roc']:+.1f}%   PEAK concurrent collateral ${s['peak']:,.0f}   RoC on peak cap {s['roc_peak']:+.1f}%")
    print(f"total fees paid ${s['fees']:,.0f}   avg actual DTE {s['adte']:.1f}")

    print(f"\nper-year:")
    print(f"{'yr':6}{'n':>4}{'win%':>6}{'total$':>10}{'avgRoC':>8}{'maxDD$':>9}")
    for y, g in t.groupby("yr"):
        eqy = g.pnl.cumsum().values; mddy = (eqy-np.maximum.accumulate(eqy)).min()
        print(f"{y:6}{len(g):>4}{(g.pnl>0).mean()*100:>5.0f}%{g.pnl.sum():>+10,.0f}{g.roc.mean()*100:>+7.1f}%{mddy:>+9,.0f}")

    # ---- SLIPPAGE LADDER (haircut visibility) ----
    print(f"\nSLIPPAGE LADDER (fees fixed ${FEE_PC:.2f}/contract):")
    print(f"{'fill':<18}{'total$':>10}{'PF':>7}{'win%':>7}{'RoC/pk':>9}{'avgL$':>9}")
    for slip, name in [(0.0, "mid (optimistic)"), (0.25, "mid+-0.25 half"), (0.5, "mid+-0.5 half"), (1.0, "BID/ASK (headline)")]:
        ts = backtest(sig, by, px, slip=slip, fee_pc=FEE_PC); ss = summ(ts)
        print(f"{name:<18}{ss['total']:>+10,.0f}{ss['pf']:>7.2f}{ss['win']:>6.0f}%{ss['roc_peak']:>+8.1f}%{ss['avgloser']:>+9,.0f}")

    # ---- FEE LADDER (at bid/ask) ----
    print(f"\nFEE LADDER (bid/ask fill):")
    print(f"{'fee/contract':<16}{'total$':>10}{'fees$':>9}{'PF':>7}{'RoC/pk':>9}")
    for fpc in [0.65, 1.00, 1.30, 2.00]:
        tf = backtest(sig, by, px, slip=HEAD_SLIP, fee_pc=fpc); sf = summ(tf)
        print(f"${fpc:<15.2f}{sf['total']:>+10,.0f}{sf['fees']:>+9,.0f}{sf['pf']:>7.2f}{sf['roc_peak']:>+8.1f}%")

    # ---- chart: equity + DD (headline run) ----
    eq = t.pnl.cumsum().values
    fig, (a1, a2) = plt.subplots(2, 1, figsize=(13, 8), gridspec_kw={"height_ratios": [2.4, 1]})
    a1.plot(pd.to_datetime(t.exit), eq, lw=1.7, color="tab:green")
    a1.fill_between(pd.to_datetime(t.exit), eq-np.maximum.accumulate(eq), 0, alpha=.15, color="red")
    a1.set_title(f"14DTE / {WIDTH}pt-cap bull put spread — bid/ask fill, ${FEE_PC}/contract fees "
                 f"(SPX, 2010-2023, {s['n']} trades) — cum P&L")
    a1.set_ylabel("cum $"); a1.grid(alpha=.3)
    yb = t.groupby("yr").pnl.sum()
    a2.bar(yb.index, yb.values, color=["green" if v > 0 else "red" for v in yb.values])
    a2.axhline(0, color="gray", lw=.8); a2.set_title("net $ by year"); a2.grid(alpha=.3, axis="y")
    plt.tight_layout()
    p = ROOT/"docs"/"living"/"mr_bps_14d50_proper.png"
    plt.savefig(p, dpi=120)
    t.to_parquet(ROOT/"docs"/"living"/"mr_bps_14d50_proper_trades.parquet")
    print(f"\nchart: {p}")
    print(f"trades parquet: docs/living/mr_bps_14d50_proper_trades.parquet")


if __name__ == "__main__":
    main()
