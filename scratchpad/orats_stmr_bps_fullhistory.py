"""STMR over the FULL ORATS SPX set (2007-2026): delta-defined bull-put-spread
vs buying an ATM call. Close entry (user spec).

Signal (SPX daily): %K8=100*(C-LL8)/(HH8-LL8); SMA100, SMA5.
  ENTRY (flat only): %K8<15 AND C>SMA100  -> enter at CLOSE
  EXIT: first later day C>SMA5, else option expiry.
Instruments on the same entries, ~14 DTE:
  BPS : sell ~30d put (call-delta 0.70) / buy ~10d put (call-delta 0.90). Delta-defined
        wings => width auto-scales with price+vol (no fixed 50pt).
  CALL: buy ~ATM call (call-delta 0.50).
Fill = ORATS *Value (MID; no bid/ask on disk -> optimistic, flagged). Fees $1.30/ct/side.
"""
import glob
from pathlib import Path
import numpy as np
import pandas as pd

ROOT = Path(r"c:\Users\Admin\myquant")
ORATS = ROOT / "data" / "orats" / "SPX"
DTE_T, FEE = 14, 1.30
SHORT_D, LONG_D, CALL_D = 0.70, 0.90, 0.50   # call-delta targets

# ---- 1. daily signal, close entry, one-at-a-time ----
d = pd.read_csv(ROOT / "data" / "spx_daily_full.csv")
d["Date"] = pd.to_datetime(d["Date"]).dt.strftime("%Y-%m-%d")
d = d[(d.Date >= "2007-01-01") & (d.Date <= "2026-12-31")].reset_index(drop=True)
C, H, L = d.Close, d.High, d.Low
d["sma100"], d["sma5"] = C.rolling(100).mean(), C.rolling(5).mean()
d["k8"] = 100 * (C - L.rolling(8).min()) / (H.rolling(8).max() - L.rolling(8).min()).replace(0, np.nan)
d["entry_sig"] = (d.k8 < 15) & (C > d.sma100)
d["exit_sig"] = C > d.sma5
close_by = dict(zip(d.Date, d.Close))

trades, in_pos = [], False
for i in range(len(d)):
    if not in_pos and d.entry_sig.iloc[i] and np.isfinite(d.k8.iloc[i]) and np.isfinite(d.sma100.iloc[i]):
        cur = {"entry": d.Date.iloc[i], "spot": round(C.iloc[i]), "k8": round(d.k8.iloc[i], 1)}
        in_pos = True
    elif in_pos and d.exit_sig.iloc[i]:
        cur["exit_sig_date"] = d.Date.iloc[i]; trades.append(cur); in_pos = False
if in_pos:
    cur["exit_sig_date"] = None; trades.append(cur)
print(f"signal: {len(trades)} STMR entries 2007-2026 (~{len(trades)/19:.1f}/yr)")

# ---- 2. load needed ORATS chains ----
need = set()
for t in trades:
    need.add(t["entry"])
    if t["exit_sig_date"]:
        need.add(t["exit_sig_date"])
cols = ["tradeDate", "expirDate", "dte", "strike", "delta", "putValue", "callValue", "stockPrice"]
chains = {}
for f in sorted(glob.glob(str(ORATS / "SPX_*.parquet"))):
    yr = Path(f).stem.split("_")[-1]
    nd = {x for x in need if x[:4] == yr}
    if not nd:
        continue
    df = pd.read_parquet(f, columns=cols)
    for dt_, g in df[df.tradeDate.isin(nd)].groupby("tradeDate"):
        chains[dt_] = g
print(f"loaded {len(chains)} ORATS chain-days")


def exp14(ch):
    ch = ch[(ch.dte >= 1)]
    return None if ch.empty else ch.iloc[(ch.dte - DTE_T).abs().argsort()].iloc[0].expirDate


def legs_bps(ch):
    exp = exp14(ch)
    if exp is None:
        return None
    e = ch[(ch.expirDate == exp) & ch.putValue.notna() & (ch.putValue > 0)].copy()
    if len(e) < 2:
        return None
    short = e.iloc[(e.delta - SHORT_D).abs().argsort()].iloc[0]
    below = e[e.strike < short.strike]
    if below.empty:
        return None
    long = below.iloc[(below.delta - LONG_D).abs().argsort()].iloc[0]
    cr = short.putValue - long.putValue
    return None if cr <= 0 else {"exp": exp, "sK": short.strike, "lK": long.strike,
                                 "cr": cr, "w": short.strike - long.strike, "dte": int(short.dte)}


def legs_call(ch):
    exp = exp14(ch)
    if exp is None:
        return None
    e = ch[(ch.expirDate == exp) & ch.callValue.notna() & (ch.callValue > 0)].copy()
    if e.empty:
        return None
    c = e.iloc[(e.delta - CALL_D).abs().argsort()].iloc[0]
    return {"exp": exp, "K": c.strike, "cost": c.callValue, "dte": int(c.dte)}


def val_on(date, exp, K, col):
    ch = chains.get(date)
    if ch is None:
        return None
    r = ch[(ch.expirDate == exp) & (ch.strike == K)]
    return None if r.empty or not np.isfinite(r.iloc[0][col]) else r.iloc[0][col]


rows_b, rows_c = [], []
for t in trades:
    ch = chains.get(t["entry"])
    if ch is None:
        continue
    esig = t.get("exit_sig_date")
    # ---- BPS ----
    lg = legs_bps(ch)
    if lg:
        exp = lg["exp"]
        if esig and esig <= exp:
            cc = val_on(esig, exp, lg["sK"], "putValue")
            cl = val_on(esig, exp, lg["lK"], "putValue")
            cost = (cc - cl) if (cc is not None and cl is not None) else None
            if cost is None:
                S = close_by.get(esig); cost = (max(0, lg["sK"]-S) - max(0, lg["lK"]-S)) if S else lg["cr"]
            pnl = (lg["cr"] - cost) * 100 - 4 * FEE; oc = "sma5"
        else:
            S = close_by.get(exp)
            if S is not None:
                liab = max(0, lg["sK"]-S) - max(0, lg["lK"]-S)
                pnl = (lg["cr"] - liab) * 100 - 2 * FEE; oc = "expiry"
            else:
                pnl = None
        if pnl is not None:
            rows_b.append({"year": int(t["entry"][:4]), "w": round(lg["w"]), "cr": round(lg["cr"], 2),
                           "coll": round((lg["w"]-lg["cr"])*100), "oc": oc, "pnl": round(pnl, 2)})
    # ---- CALL ----
    lc = legs_call(ch)
    if lc:
        exp = lc["exp"]
        if esig and esig <= exp:
            xv = val_on(esig, exp, lc["K"], "callValue")
            if xv is None:
                S = close_by.get(esig); xv = max(0, S-lc["K"]) if S else 0
            pnl = (xv - lc["cost"]) * 100 - 2 * FEE; oc = "sma5"
        else:
            S = close_by.get(exp)
            if S is not None:
                pnl = (max(0, S-lc["K"]) - lc["cost"]) * 100 - 1 * FEE; oc = "expiry"
            else:
                pnl = None
        if pnl is not None:
            rows_c.append({"year": int(t["entry"][:4]), "cost": round(lc["cost"], 2),
                           "oc": oc, "pnl": round(pnl, 2)})

bp, cl = pd.DataFrame(rows_b), pd.DataFrame(rows_c)


def summ(g, coll_col):
    w = (g.pnl > 0).sum()
    gp, gloss = g.pnl[g.pnl > 0].sum(), -g.pnl[g.pnl < 0].sum()
    return pd.Series({"n": len(g), "win%": round(100*w/len(g)), "pnl$": round(g.pnl.sum()),
                      "avg$": round(g.pnl.mean()), "PF": round(gp/gloss, 2) if gloss else np.inf,
                      "avgcoll": round(g[coll_col].mean()) if coll_col in g else 0})


for name, g, cc in [("BULL PUT SPREAD (delta-defined wings)", bp, "coll"),
                    ("LONG ATM CALL", cl, "cost")]:
    print(f"\n===== {name} =====")
    print("--- per year ---")
    print(g.groupby("year").apply(lambda x: summ(x, cc), include_groups=False).to_string())
    s = summ(g, cc)
    eq = g.pnl.cumsum(); dd = (eq.cummax()-eq).max()
    print("--- overall ---"); print(s.to_string())
    print(f"total ${g.pnl.sum():,.0f} | avg/trade ${g.pnl.mean():,.0f} | maxDD ${dd:,.0f} | "
          f"outcomes {g.oc.value_counts().to_dict()}")
    if cc == "coll":
        print(f"avg delta-width: {g.w.mean():.0f}pt (min {g.w.min():.0f} / max {g.w.max():.0f}) — auto-scaled")

print("\nFILL = MID (ORATS has no bid/ask -> optimistic, esp. for the sold spread). "
      "Entry at daily CLOSE. One-position-at-a-time.")
bp.to_csv(ROOT/"scratchpad"/"stmr_bps_trades.csv", index=False)
cl.to_csv(ROOT/"scratchpad"/"stmr_call_trades.csv", index=False)
