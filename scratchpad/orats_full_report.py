"""Full STMR barrage on SPX + XSP ORATS -> JSON for the report.
Signal (SPX daily, close entry, one-at-a-time): %K8<15 & C>SMA100; exit C>SMA5.
Instruments: BPS(short/long put delta), BCS(long/short call delta), long call.
Fills: MID / realistic (1.25% spread) / conservative (2.5%). Fees $1.30/ct/side.
XSP = 1/10 SPX notional (same signal dates; XSP chains; underlying = SPX/10).
"""
import glob, json
from pathlib import Path
import numpy as np
import pandas as pd

ROOT = Path(r"c:\Users\Admin\myquant")
DTE_T, FEE = 14, 1.30
FILLS = {"mid": 0.0, "realistic": 0.0125, "conservative": 0.025}

# ---- signal on SPX daily (shared by both tickers) ----
d = pd.read_csv(ROOT / "data" / "spx_daily_full.csv")
d["Date"] = pd.to_datetime(d["Date"]).dt.strftime("%Y-%m-%d")
d = d[(d.Date >= "2007-01-01") & (d.Date <= "2026-12-31")].reset_index(drop=True)
C, H, L = d.Close, d.High, d.Low
d["sma100"] = C.rolling(100).mean()
for n in (3, 5, 8, 10):
    d[f"sma{n}"] = C.rolling(n).mean()
d["k8"] = 100 * (C - L.rolling(8).min()) / (H.rolling(8).max() - L.rolling(8).min()).replace(0, np.nan)
close_by = dict(zip(d.Date, d.Close)); k8_by = dict(zip(d.Date, d.k8))


def episodes(oversold, exsma):
    ent = (d.k8 < oversold) & (C > d.sma100) & d.k8.notna() & d.sma100.notna()
    exi = C > d[f"sma{exsma}"]
    out, inpos, cur = [], False, None
    for i in range(len(d)):
        if not inpos and ent.iloc[i]:
            cur = {"entry": d.Date.iloc[i], "mid": []}; inpos = True
        elif inpos:
            if exi.iloc[i]:
                cur["exit"] = d.Date.iloc[i]; out.append(cur); inpos = False
            else:
                cur["mid"].append(d.Date.iloc[i])
    if inpos:
        cur["exit"] = None; out.append(cur)
    return out


def load_chains(ticker):
    need = set()
    for ov in (10, 15, 20, 25):
        for ex in (3, 5, 8, 10):
            for e in episodes(ov, ex):
                need.add(e["entry"]); need.update(e["mid"])
                if e["exit"]:
                    need.add(e["exit"])
    cols = ["tradeDate", "expirDate", "dte", "strike", "delta", "putValue", "callValue"]
    ch = {}
    for f in sorted(glob.glob(str(ROOT / "data" / "orats" / ticker / f"{ticker}_*.parquet"))):
        yr = Path(f).stem.split("_")[-1]
        nd = {x for x in need if x[:4] == yr}
        if not nd:
            continue
        df = pd.read_parquet(f, columns=cols)
        df = df[(df.dte >= 5) & (df.dte <= 25) & df.tradeDate.isin(nd)]
        for dt_, g in df.groupby("tradeDate"):
            ch[dt_] = g
    return ch


def _exp(ch):
    return None if ch.empty else ch.iloc[(ch.dte - DTE_T).abs().argsort()].iloc[0].expirDate


def px(mid, side, sp):
    return mid * (1 - sp / 2) if side == "sell" else mid * (1 + sp / 2)


def one(entry, exitd, kind, p1, p2, chains, undf, sp):
    ch = chains.get(entry)
    if ch is None:
        return None
    exp = _exp(ch)
    if exp is None:
        return None
    if kind == "bps":
        e = ch[(ch.expirDate == exp) & ch.putValue.notna() & (ch.putValue > 0)]
        if len(e) < 2:
            return None
        s = e.iloc[(e.delta - p1).abs().argsort()].iloc[0]
        below = e[e.strike < s.strike]
        if below.empty:
            return None
        lo = below.iloc[(below.delta - p2).abs().argsort()].iloc[0]
        cr = px(s.putValue, "sell", sp) - px(lo.putValue, "buy", sp)
        if cr <= 0:
            return None
        risk = (s.strike - lo.strike) * 100 - cr * 100
        if exitd and exitd <= exp:
            ce = chains.get(exitd); v = None
            if ce is not None:
                a = ce[(ce.expirDate == exp) & (ce.strike == s.strike)]
                b = ce[(ce.expirDate == exp) & (ce.strike == lo.strike)]
                if not a.empty and not b.empty:
                    v = px(a.iloc[0].putValue, "buy", sp) - px(b.iloc[0].putValue, "sell", sp)
            if v is None:
                S = undf(exitd); v = (max(0, s.strike-S)-max(0, lo.strike-S)) if S else cr
            return (cr - v) * 100 - 4 * FEE, risk
        S = undf(exp)
        if S is None:
            return None
        return (cr - (max(0, s.strike-S)-max(0, lo.strike-S))) * 100 - 2 * FEE, risk
    # call / bcs (debit)
    e = ch[(ch.expirDate == exp) & ch.callValue.notna() & (ch.callValue > 0)]
    if e.empty:
        return None
    lc = e.iloc[(e.delta - p1).abs().argsort()].iloc[0]
    Kl = None
    if kind == "bcs":
        up = e[e.strike > lc.strike]
        if up.empty:
            return None
        sc = up.iloc[(up.delta - p2).abs().argsort()].iloc[0]
        cost = px(lc.callValue, "buy", sp) - px(sc.callValue, "sell", sp); Kl = sc.strike
    else:
        cost = px(lc.callValue, "buy", sp)
    if cost <= 0:
        return None
    risk = cost * 100; Ks = lc.strike
    if exitd and exitd <= exp:
        ce = chains.get(exitd); v = None
        if ce is not None:
            a = ce[(ce.expirDate == exp) & (ce.strike == Ks)]
            if not a.empty:
                v = px(a.iloc[0].callValue, "sell", sp)
                if Kl is not None:
                    b = ce[(ce.expirDate == exp) & (ce.strike == Kl)]
                    v = v - px(b.iloc[0].callValue, "buy", sp) if not b.empty else v
        if v is None:
            S = undf(exitd); v = (max(0, S-Ks)-(max(0, S-Kl) if Kl else 0)) if S else 0
        return (v - cost) * 100 - (4 if Kl else 2) * FEE, risk
    S = undf(exp)
    if S is None:
        return None
    pay = max(0, S-Ks) - (max(0, S-Kl) if Kl else 0)
    return (pay - cost) * 100 - (2 if Kl else 1) * FEE, risk


def run(eps, kind, p1, p2, chains, undf, sp):
    rows = []
    for ep in eps:
        r = one(ep["entry"], ep["exit"], kind, p1, p2, chains, undf, sp)
        if r:
            rows.append({"entry": ep["entry"], "exit": ep["exit"] or ep["entry"],
                         "year": int(ep["entry"][:4]), "pnl": r[0], "risk": r[1]})
    return pd.DataFrame(rows)


def metrics(g):
    if g.empty:
        return {"n": 0}
    eq = g.sort_values("exit").pnl.cumsum()
    gp, gl = g.pnl[g.pnl > 0].sum(), -g.pnl[g.pnl < 0].sum()
    return {"n": int(len(g)), "win": round((g.pnl > 0).mean()*100),
            "PF": round(gp/gl, 2) if gl else None, "avg": round(g.pnl.mean()),
            "roc": round(g.pnl.mean()/g.risk.mean()*100, 1), "tot": round(g.pnl.sum()),
            "maxDD": round((eq.cummax()-eq).max()), "maxRisk": round(g.risk.max()),
            "medRisk": round(g.risk.median())}


INSTR = {"BPS 30/10": ("bps", 0.70, 0.90), "BPS 40/15": ("bps", 0.60, 0.85),
         "BCS 50/30": ("bcs", 0.50, 0.30), "Call ATM": ("call", 0.50, None),
         "Call ITM": ("call", 0.65, None)}
HEAD = ["BPS 30/10", "BCS 50/30", "Call ATM"]

base = episodes(15, 5)
out = {"meta": {"spx_range": "2007-2026", "xsp_range": "2020-2026",
                "n_base_entries": len(base), "fills": FILLS, "fee": FEE}, "tickers": {}}

for ticker, undf in [("SPX", lambda dd: close_by.get(dd)),
                     ("XSP", lambda dd: (close_by.get(dd)/10 if close_by.get(dd) else None))]:
    print(f"loading {ticker} chains...")
    chains = load_chains(ticker)
    print(f"  {len(chains)} chain-days")
    T = {"fill_sensitivity": {}, "delta_sweep": {}, "exit_sweep": {}, "per_year": {}, "double_down": {}}

    # fill sensitivity: headline instruments x 3 fills
    for lbl in HEAD:
        k, p1, p2 = INSTR[lbl]
        T["fill_sensitivity"][lbl] = {fn: metrics(run(base, k, p1, p2, chains, undf, sp))
                                      for fn, sp in FILLS.items()}
    # delta sweep at realistic fill
    sp = FILLS["realistic"]
    for lbl, (k, p1, p2) in INSTR.items():
        T["delta_sweep"][lbl] = metrics(run(base, k, p1, p2, chains, undf, sp))
    # exit sweep at realistic
    for lbl in HEAD:
        k, p1, p2 = INSTR[lbl]
        T["exit_sweep"][lbl] = {f"SMA{e}": metrics(run(episodes(15, e), k, p1, p2, chains, undf, sp))
                                for e in (3, 5, 8, 10)}
    # per year (realistic)
    runs = {lbl: run(base, *INSTR[lbl], chains, undf, sp) for lbl in HEAD}
    yrs = {}
    for y in range(2007, 2027):
        row = {}
        for lbl, g in runs.items():
            gy = g[g.year == y]
            if len(gy):
                row[lbl] = {"n": int(len(gy)), "pnl": round(gy.pnl.sum())}
        if row:
            yrs[str(y)] = row
    T["per_year"] = yrs
    # equity curves + drawdown series (realistic) for the 3 headline instruments
    T["equity"] = {}
    for lbl in HEAD:
        g = run(base, *INSTR[lbl], chains, undf, sp).sort_values("exit").reset_index(drop=True)
        eq = g.pnl.cumsum()
        peak = eq.cummax()
        T["equity"][lbl] = {"dates": list(g.exit), "equity": [round(x) for x in eq],
                            "dd": [round(x) for x in (eq - peak)]}
    # fee drag (realistic): fee as % of gross credit/debit
    fr = {}
    for lbl in HEAD:
        k, p1, p2 = INSTR[lbl]
        g = run(base, k, p1, p2, chains, undf, sp)
        # gross = risk+? approximate gross premium from risk for report note; store avg pnl & n
        fr[lbl] = {"n": int(len(g)), "avg": round(g.pnl.mean()), "medRisk": round(g.risk.median())}
    T["fee_note"] = fr

    # double-down on BPS (realistic)
    def dd(mode, kind="bps", p1=0.70, p2=0.90):
        units, peak = [], 0.0
        for ep in base:
            adds = [ep["entry"]]
            if mode != "base":
                e0 = close_by[ep["entry"]]; prev = e0
                for m in ep["mid"]:
                    cm_, kk = close_by.get(m), k8_by.get(m)
                    if cm_ is None:
                        continue
                    if mode == "weak" and cm_ < prev and kk is not None and kk < 15 and len(adds) < 3:
                        adds.append(m); prev = cm_
                    if mode == "strong" and cm_ > e0 and len(adds) < 3:
                        adds.append(m)
            coll = 0.0
            for a in adds:
                r = one(a, ep["exit"], kind, p1, p2, chains, undf, sp)
                if r:
                    units.append({"exit": ep["exit"] or a, "pnl": r[0], "risk": r[1]}); coll += r[1]
            peak = max(peak, coll)
        g = pd.DataFrame(units); m = metrics(g)
        m["maxConcColl"] = round(peak)
        return m
    T["double_down"] = {}
    for lbl in HEAD:
        k, p1, p2 = INSTR[lbl]
        T["double_down"][lbl] = {"baseline": dd("base", k, p1, p2), "add_weak": dd("weak", k, p1, p2),
                                 "add_strong": dd("strong", k, p1, p2)}
    out["tickers"][ticker] = T
    print(f"  {ticker} done")

def _conv(o):
    if isinstance(o, np.floating):
        return float(o)
    if isinstance(o, np.integer):
        return int(o)
    raise TypeError(str(type(o)))
(ROOT / "scratchpad" / "stmr_report_data.json").write_text(json.dumps(out, indent=1, default=_conv))
print("wrote scratchpad/stmr_report_data.json")
# quick console proof
for tk in ("SPX", "XSP"):
    b = out["tickers"][tk]["fill_sensitivity"]["BPS 30/10"]
    print(f"{tk} BPS30/10  mid PF {b['mid'].get('PF')} -> realistic PF {b['realistic'].get('PF')} "
          f"-> conservative PF {b['conservative'].get('PF')}  (n {b['realistic'].get('n')})")
