"""spy_bounce_quote.py — live SPY chain + price the 4 bounce structures (S119, one-off).

Pulls a live SPY stock quote + near-dated option chain via the IB gateway, CONFIRMS
whether the ticks are realtime (marketDataType 1) or delayed (3), and prices the four
$300-budget bounce structures against the real bid/ask. Saves a dated JSON.

Usage: python scripts/spy_bounce_quote.py
"""
from __future__ import annotations
import datetime as dt
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))
OUT = ROOT / "data" / "spy_bounce"
OUT.mkdir(parents=True, exist_ok=True)
MDT = {1: "REALTIME", 2: "frozen", 3: "DELAYED", 4: "delayed-frozen"}


def mid(t):
    b, a = t.get("bid"), t.get("ask")
    if b and a and b > 0 and a > 0:
        return round((b + a) / 2, 2)
    return t.get("last") or None


def main():
    from ib_conn import connect
    from ib_async import Stock, Option
    import math
    ib = connect(allow_live=True, market_data_type=1, timeout=20)

    spy = Stock("SPY", "SMART", "USD")
    ib.qualifyContracts(spy)

    def spot_try(mdt):
        ib.reqMarketDataType(mdt)
        t = ib.reqMktData(spy, "", True, False); ib.sleep(3)
        px = None
        for v in (t.last, t.close, mid({"bid": t.bid, "ask": t.ask})):
            if v and not math.isnan(v) and v > 0:
                px = v; break
        return px, MDT.get(t.marketDataType, t.marketDataType)

    spot, spot_mdt = spot_try(1)                 # realtime
    if spot is None:
        spot, spot_mdt = spot_try(3)             # fall back to delayed
    print(f"SPY spot: {spot}  data={spot_mdt}")
    if spot is None:
        print("no SPY spot at all — aborting"); ib.disconnect(); return

    ib.reqMarketDataType(1)                       # options: try realtime OPRA
    chains = ib.reqSecDefOptParams(spy.symbol, "", spy.secType, spy.conId)
    # merge every standard SPY/SMART chain (single-chain pick returned a stale strike range)
    sc = [c for c in chains if c.tradingClass == "SPY" and c.multiplier in ("100", "", None)] or chains
    allstrikes = sorted({s for c in sc for s in c.strikes})
    allexps = sorted({e for c in sc for e in c.expirations})
    today = dt.date.today().strftime("%Y%m%d")
    exps = [e for e in allexps if e >= today]
    exp0 = exps[0] if exps else None
    exp_wk = exps[1] if len(exps) > 1 else exp0
    # strikes near spot only (in $1 grid)
    atm = min(allstrikes, key=lambda s: abs(s - spot))
    near = [s for s in allstrikes if atm - 4 <= s <= atm + 4]
    print(f"strikes span {allstrikes[0]}-{allstrikes[-1]} n={len(allstrikes)} | "
          f"expiries {exps[:4]} | ATM {atm} | near {near}")

    # qualify a batch of option contracts first (populates conId), then quote
    want = [(exp0, s, r) for s in near for r in ("C", "P")] + \
           [(exp_wk, s, "C") for s in (atm, atm + 1, atm + 2, atm + 3)]
    contracts = {(e, s, r): Option("SPY", e, s, r, "SMART", tradingClass="SPY") for (e, s, r) in want}
    ib.qualifyContracts(*contracts.values())
    # stream all at once, then wait so quotes populate (snapshot-in-loop was too fast)
    tick = {}
    for (e, s, r), c in contracts.items():
        if c.conId:
            tick[(e, s, r)] = ib.reqMktData(c, "", False, False)
    ib.sleep(6)
    q = {}
    import math as _m
    def val(x):
        return x if (x is not None and not _m.isnan(x) and x > 0) else None
    for (e, s, r), t in tick.items():
        b, a = val(t.bid), val(t.ask)
        two = b is not None and a is not None
        q[f"{e}:{s}{r}"] = {"exp": e, "strike": s, "right": r, "bid": b, "ask": a,
                            "last": val(t.last), "mid": round((b + a) / 2, 2) if two else None,
                            "two_sided": two, "mdt": MDT.get(t.marketDataType, t.marketDataType)}
    mdts = {v["mdt"] for v in q.values()}
    print(f"OPTION data types seen: {mdts}")
    print(f"\n{'exp':>9} {'strike':>7} {'R':>2} {'bid':>7} {'ask':>7} {'mid':>7} {'2-sided':>7}")
    for k in sorted(q):
        v = q[k]
        if v["exp"] in (exp0, exp_wk) and (v["strike"] in near[:9] or v["right"] == "C"):
            print(f"{v['exp']:>9} {v['strike']:>7} {v['right']:>2} "
                  f"{str(v['bid']):>7} {str(v['ask']):>7} {str(v['mid']):>7} {str(v['two_sided']):>7}")

    def m(exp, s, r):
        v = q.get(f"{exp}:{s}{r}")
        return v["mid"] if v and v["mid"] else None

    structs = []
    # #1 long 0DTE call ~1 strike OTM
    s1 = atm + 1
    c1 = m(exp0, s1, "C")
    if c1:
        structs.append({"name": "#1 Long 0DTE call ~1 OTM", "legs": [f"BUY {s1}C {exp0}"],
                        "debit_$": round(c1 * 100, 0), "max_risk_$": round(c1 * 100, 0),
                        "note": "uncapped up; zeros fast if bounce stalls",
                        "fits_300": c1 * 100 <= 300})
    # #2 0DTE call debit spread ATM / +2
    cb, cs = m(exp0, atm, "C"), m(exp0, atm + 2, "C")
    if cb and cs:
        deb = cb - cs
        structs.append({"name": "#2 0DTE call debit spread ATM/+2", "legs": [f"BUY {atm}C", f"SELL {atm+2}C"],
                        "debit_$": round(deb * 100, 0), "max_risk_$": round(deb * 100, 0),
                        "max_val_$": 200, "max_profit_$": round((2 - deb) * 100, 0),
                        "fits_300": deb * 100 <= 300})
    # #3 0DTE put credit spread (sell atm-1, buy atm-3) $2 wide
    ps, pb = m(exp0, atm - 1, "P"), m(exp0, atm - 3, "P")
    if ps and pb:
        cr = ps - pb
        structs.append({"name": "#3 0DTE put credit spread -1/-3", "legs": [f"SELL {atm-1}P", f"BUY {atm-3}P"],
                        "credit_$": round(cr * 100, 0), "max_risk_$": round((2 - cr) * 100, 0),
                        "note": "wins if SPY holds/bounces/chops up", "fits_300": (2 - cr) * 100 <= 300})
    # #4 weekly ATM call
    c4 = m(exp_wk, atm, "C")
    if c4:
        structs.append({"name": "#4 Long weekly ATM call", "legs": [f"BUY {atm}C {exp_wk}"],
                        "debit_$": round(c4 * 100, 0), "max_risk_$": round(c4 * 100, 0),
                        "note": "more time for mean-reversion", "fits_300": c4 * 100 <= 300})

    out = {"pulled_ct": dt.datetime.now().isoformat(timespec="seconds"),
           "spot": spot, "spot_data": spot_mdt, "atm": atm, "exp0": exp0, "exp_wk": exp_wk,
           "quotes": q, "structures": structs}
    p = OUT / f"spy_bounce_{today}.json"
    p.write_text(json.dumps(out, indent=2), encoding="utf-8")
    print(f"\nsaved {p}")
    print("=== STRUCTURES (live) ===")
    for s in structs:
        print(json.dumps(s))
    ib.disconnect()


if __name__ == "__main__":
    main()
