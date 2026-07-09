"""Options-structure bake-off for the STMR oversold signal, on real SPX EOD chains.

At each oversold ES signal (%K8<15 & Close>SMA100) we express the SAME bullish,
short-hold view four different ways and price each at REAL bid/ask, closing on the
futures rule's exit date (first Close>SMA5):

  1 LONG CALL           buy ~50d call            (long vega, long theta-cost)
  2 BULL CALL SPREAD    buy ~50d / sell ~25d      (debit, defined, mild long vega)
  3 BULL PUT SPREAD     sell ~30d / buy ~15d      (credit, defined, SHORT vega)
  4 SHORT PUT (CSP)     sell ~30d put             (credit, undefined, short vega)

Hypothesis: because IV is SPIKED at an oversold entry, the SHORT-vega credit
structures (3,4) get a vol-collapse tailwind while the LONG-vega debit structures
(1,2) fight a headwind. AND the winner may flip by context: premium-selling in
trading ranges (ADX low), debit/long-call in trends (ADX high) where the bounce runs.

Every signal is tagged trend/range via ES ADX(14) so we can test that split.

  python scripts/mr_options_strategies.py --year 2011      # validate on one year (+visual)
  python scripts/mr_options_strategies.py --all            # full 2010-2023
"""
import glob, argparse
from pathlib import Path
import numpy as np
import pandas as pd
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

ROOT = Path(r"c:\Users\Admin\myquant")
OPTDIR = ROOT / "data" / "optionsdx"
MULT = 100.0
COMM_LEG = 1.0        # ~$1/contract/leg


def es_signals():
    d = pd.read_csv(ROOT / "data" / "ES_stoch_daily.csv")
    d.columns = [c.strip().lstrip("﻿") for c in d.columns]
    C = d["Close"].values.astype(float); H = d["High"].values.astype(float); L = d["Low"].values.astype(float)
    n = len(d); dt = pd.to_datetime(d["DateTime"]).dt.date.astype(str).values
    sma5 = pd.Series(C).rolling(5).mean().values; sma100 = pd.Series(C).rolling(100).mean().values
    ll = pd.Series(L).rolling(8).min().values; hh = pd.Series(H).rolling(8).max().values
    K8 = 100 * (C - ll) / np.where(hh - ll == 0, 1, hh - ll)
    # ADX(14) for trend/range context
    up = np.r_[0, np.diff(H)]; dn = np.r_[0, -np.diff(L)]
    pdm = np.where((up > dn) & (up > 0), up, 0.0); ndm = np.where((dn > up) & (dn > 0), dn, 0.0)
    tr = np.maximum(H - L, np.maximum(abs(H - np.r_[C[0], C[:-1]]), abs(L - np.r_[C[0], C[:-1]])))
    a = 1 / 14
    atr = pd.Series(tr).ewm(alpha=a, adjust=False).mean().values
    pdi = 100 * pd.Series(pdm).ewm(alpha=a, adjust=False).mean().values / np.where(atr > 0, atr, np.nan)
    ndi = 100 * pd.Series(ndm).ewm(alpha=a, adjust=False).mean().values / np.where(atr > 0, atr, np.nan)
    dx = 100 * abs(pdi - ndi) / np.where((pdi + ndi) > 0, pdi + ndi, np.nan)
    adx = pd.Series(dx).ewm(alpha=a, adjust=False).mean().values
    out = []
    for i in range(250, n - 1):
        if K8[i] < 15 and C[i] > sma100[i]:
            xi = next((j for j in range(i + 1, min(n, i + 41)) if C[j] > sma5[j]), min(n - 1, i + 40))
            out.append((dt[i], dt[xi], adx[i]))
    return out


NEED = ["QUOTE_DATE", "UNDERLYING_LAST", "EXPIRE_DATE", "DTE", "STRIKE",
        "C_BID", "C_ASK", "C_DELTA", "P_BID", "P_ASK", "P_DELTA"]


def load(dates, dte, files):
    keep = []
    for f in files:
        hdr = pd.read_csv(f, nrows=0, skipinitialspace=True)
        cols = {c.strip().strip("[]").upper(): c for c in hdr.columns}
        need = {k: cols.get(k) for k in NEED}
        if any(v is None for v in need.values()):
            continue
        df = pd.read_csv(f, usecols=list(need.values()), skipinitialspace=True)
        df = df.rename(columns={v: k for k, v in need.items()})
        df["QUOTE_DATE"] = df["QUOTE_DATE"].astype(str).str.strip()
        df = df[df["QUOTE_DATE"].isin(dates)]
        if df.empty:
            continue
        for c in ["UNDERLYING_LAST", "DTE", "STRIKE", "C_BID", "C_ASK", "C_DELTA", "P_BID", "P_ASK", "P_DELTA"]:
            df[c] = pd.to_numeric(df[c], errors="coerce")
        df["EXPIRE_DATE"] = df["EXPIRE_DATE"].astype(str).str.strip()
        df = df[(df["DTE"] >= 1) & (df["DTE"] <= dte + 21)]
        keep.append(df)
    return pd.concat(keep, ignore_index=True) if keep else pd.DataFrame()


def pick(leg, col, target):
    return leg.iloc[(leg[col].abs() - target).abs().argmin()]


def fillp(bid, ask, side, slip):
    """Fill price at mid +/- slip*half-spread. slip=0 -> mid; slip=1 -> full cross."""
    mid = (bid + ask) / 2.0; half = (ask - bid) / 2.0
    return mid - slip * half if side == "sell" else mid + slip * half


def structures(entry, exitc, dte, slip):
    """Return dict {name: (pnl, max_risk)} priced at mid +/- slip*half-spread."""
    exp = entry.iloc[(entry["DTE"] - dte).abs().argmin()]["EXPIRE_DATE"]
    e = entry[(entry["EXPIRE_DATE"] == exp)]
    calls = e[e["C_DELTA"].notna() & (e["C_ASK"] > 0)]
    puts = e[e["P_DELTA"].notna() & (e["P_BID"] > 0)]
    if len(calls) < 4 or len(puts) < 4:
        return None
    xe = exitc[(exitc["EXPIRE_DATE"] == exp)] if exitc is not None else None
    und = float(e.iloc[0]["UNDERLYING_LAST"])

    def xfill(strike, opt, side):        # exit fill; None if strike missing -> caller uses intrinsic
        if xe is None: return None
        r = xe[xe["STRIKE"] == strike]
        if r.empty: return None
        return fillp(float(r.iloc[0][opt + "_BID"]), float(r.iloc[0][opt + "_ASK"]), side, slip)

    res = {}
    # 1 LONG CALL ~50d
    lc = pick(calls, "C_DELTA", 0.50)
    ecost = fillp(lc["C_BID"], lc["C_ASK"], "buy", slip)
    exv = xfill(lc["STRIKE"], "C", "sell")
    if exv is None: exv = max(0.0, und - lc["STRIKE"])
    res["long_call"] = ((exv - ecost) * MULT - 2 * COMM_LEG, ecost * MULT)
    # 2 BULL CALL SPREAD  buy50 / sell25
    lc2 = pick(calls, "C_DELTA", 0.50); sc = pick(calls, "C_DELTA", 0.25)
    if sc["STRIKE"] > lc2["STRIKE"]:
        debit = fillp(lc2["C_BID"], lc2["C_ASK"], "buy", slip) - fillp(sc["C_BID"], sc["C_ASK"], "sell", slip)
        xl = xfill(lc2["STRIKE"], "C", "sell"); xs = xfill(sc["STRIKE"], "C", "buy")
        exval = (xl - xs) if (xl is not None and xs is not None) else (max(0, und - lc2["STRIKE"]) - max(0, und - sc["STRIKE"]))
        if debit > 0:
            res["bull_call_spr"] = ((exval - debit) * MULT - 4 * COMM_LEG, debit * MULT)
    # 3 BULL PUT SPREAD  sell30 / buy15
    sp = pick(puts, "P_DELTA", 0.30); lp = pick(puts, "P_DELTA", 0.15)
    if lp["STRIKE"] < sp["STRIKE"]:
        credit = fillp(sp["P_BID"], sp["P_ASK"], "sell", slip) - fillp(lp["P_BID"], lp["P_ASK"], "buy", slip)
        xs = xfill(sp["STRIKE"], "P", "buy"); xl = xfill(lp["STRIKE"], "P", "sell")
        cost = (xs - xl) if (xs is not None and xl is not None) else (max(0, sp["STRIKE"] - und) - max(0, lp["STRIKE"] - und))
        width = sp["STRIKE"] - lp["STRIKE"]
        if credit > 0:
            res["bull_put_spr"] = ((credit - cost) * MULT - 4 * COMM_LEG, (width - credit) * MULT)
    # 4 SHORT PUT ~30d (cash-secured)
    sp2 = pick(puts, "P_DELTA", 0.30)
    credit = fillp(sp2["P_BID"], sp2["P_ASK"], "sell", slip)
    xs = xfill(sp2["STRIKE"], "P", "buy")
    cost = xs if xs is not None else max(0, sp2["STRIKE"] - und)
    res["short_put"] = ((credit - cost) * MULT - 2 * COMM_LEG, sp2["STRIKE"] * MULT * 0.2)
    return res


def run(a):
    sigs = es_signals()
    if a.year:
        sigs = [s for s in sigs if s[0].startswith(str(a.year))]
        files = sorted(glob.glob(str(OPTDIR / f"spx_eod_{a.year}*.txt")) +
                       glob.glob(str(OPTDIR / f"spx_eod_{a.year+1}01*.txt")))
        tag = str(a.year)
    else:
        files = sorted(glob.glob(str(OPTDIR / "*.txt")))
        tag = "2010-2023"
    dates = set()
    for e, x, _ in sigs:
        dates.add(e); dates.add(x)
    ch = load(dates, a.dte, files)
    if ch.empty:
        print("No chain rows for those signal dates. Files present?", len(files)); return
    by = {k: v for k, v in ch.groupby("QUOTE_DATE")}
    names = ["long_call", "bull_call_spr", "bull_put_spr", "short_put"]

    def build(slip):
        recs = []
        for edate, xdate, adx in sigs:
            en = by.get(edate)
            if en is None or en.empty: continue
            st = structures(en, by.get(xdate), a.dte, slip)
            if not st: continue
            row = {"edate": edate, "adx": adx, "ctx": "trend" if adx >= 25 else ("range" if adx <= 18 else "mid")}
            for nm in names:
                row[nm] = st.get(nm, (np.nan, np.nan))[0]
                row[nm + "_risk"] = st.get(nm, (np.nan, np.nan))[1]
            recs.append(row)
        return pd.DataFrame(recs)

    print(f"=== SPX options bake-off — {tag} — fill-quality sweep (mid -> full bid/ask cross) ===")
    for slip in (0.0, 0.25, 0.5):
        t = build(slip)
        if t.empty: continue
        lab = {0.0: "MID (0.00)", 0.25: "REALISTIC (0.25)", 0.5: "FULL-CROSS (0.50)"}[slip]
        print(f"\n-- fills @ {lab} --   ({len(t)} signals)")
        print(f"   {'structure':16}{'win%':>6}{'PF':>6}{'exp$':>9}{'total$':>11}")
        for nm in names:
            s = t[nm].dropna()
            if len(s) == 0: continue
            pf = s[s > 0].sum() / -s[s < 0].sum() if (s < 0).any() else np.inf
            print(f"   {nm:16}{(s>0).mean()*100:>5.0f}%{pf:>6.2f}{s.mean():>9.0f}{s.sum():>11,.0f}")

    t = build(a.slip)   # realistic for the context split + visual
    if t.empty:
        print("No trades built."); return
    print(f"\n=== context split @ realistic fills (slip {a.slip}) — avg $/trade ===")
    print(f"{'ctx':8}" + "".join(f"{nm.split('_')[0][:5]:>9}" for nm in names) + f"{'n':>5}")
    for ctx in ["trend", "mid", "range"]:
        g = t[t.ctx == ctx]
        if len(g) == 0: continue
        print(f"{ctx:8}" + "".join(f"{g[nm].mean():>9.0f}" for nm in names) + f"{len(g):>5}")

    # ---------- visual report ----------
    fig, ax = plt.subplots(2, 2, figsize=(14, 9))
    col = {"long_call": "tab:red", "bull_call_spr": "tab:orange", "bull_put_spr": "tab:green", "short_put": "tab:blue"}
    for nm in names:
        s = t[nm].dropna()
        if len(s): ax[0, 0].plot(range(1, len(s) + 1), s.cumsum().values, marker="o", ms=3, label=nm, color=col[nm])
    ax[0, 0].axhline(0, color="gray", lw=.8); ax[0, 0].legend(fontsize=8); ax[0, 0].grid(alpha=.3)
    ax[0, 0].set_title(f"Cumulative $ P&L per structure ({tag})"); ax[0, 0].set_xlabel("trade #")
    # bar: total + win%
    tot = [t[nm].sum() for nm in names]; win = [(t[nm] > 0).mean() * 100 for nm in names]
    ax[0, 1].bar(range(len(names)), tot, color=[col[n] for n in names])
    ax[0, 1].set_xticks(range(len(names))); ax[0, 1].set_xticklabels([n.replace("_", "\n") for n in names], fontsize=8)
    for i, (tt, w) in enumerate(zip(tot, win)): ax[0, 1].text(i, tt, f"{w:.0f}%win", ha="center", va="bottom", fontsize=8)
    ax[0, 1].axhline(0, color="gray", lw=.8); ax[0, 1].set_title("Total $ P&L (label = win%)"); ax[0, 1].grid(alpha=.3, axis="y")
    # context split heat
    ctxs = ["range", "mid", "trend"]
    M = np.array([[t[t.ctx == c][nm].mean() for nm in names] for c in ctxs])
    im = ax[1, 0].imshow(M, cmap="RdYlGn", aspect="auto")
    ax[1, 0].set_xticks(range(len(names))); ax[1, 0].set_xticklabels([n.split("_")[0] for n in names], fontsize=8)
    ax[1, 0].set_yticks(range(len(ctxs))); ax[1, 0].set_yticklabels(ctxs)
    for i in range(len(ctxs)):
        for j in range(len(names)):
            ax[1, 0].text(j, i, f"{M[i,j]:.0f}", ha="center", va="center", fontsize=8)
    ax[1, 0].set_title("avg $/trade by context (green=better)")
    # per-trade scatter best structure
    ax[1, 1].axhline(0, color="gray", lw=.8)
    for nm in ["bull_put_spr", "long_call"]:
        ax[1, 1].scatter(t["adx"], t[nm], s=20, alpha=.7, label=nm, color=col[nm])
    ax[1, 1].axvline(25, color="k", ls=":", lw=1); ax[1, 1].axvline(18, color="k", ls=":", lw=1)
    ax[1, 1].set_xlabel("ADX at entry (range<18 | trend>25)"); ax[1, 1].set_ylabel("$ P&L"); ax[1, 1].legend(fontsize=8); ax[1, 1].grid(alpha=.3)
    ax[1, 1].set_title("put-spread vs long-call by trend strength")
    plt.tight_layout()
    out = ROOT / "docs" / "living" / f"mr_options_bakeoff_{tag}.png"
    plt.savefig(out, dpi=110); print(f"\nvisual report: {out}")
    t.to_parquet(ROOT / "docs" / "living" / f"mr_options_bakeoff_{tag}.parquet")


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--year", type=int, default=2011)
    ap.add_argument("--all", action="store_true")
    ap.add_argument("--dte", type=int, default=30)
    ap.add_argument("--slip", type=float, default=0.25)   # realistic fill (fraction of half-spread)
    args = ap.parse_args()
    if args.all: args.year = None
    run(args)
