"""Manual REAL paper entry of the STMR bull put spread (user-ordered 2026-07-21).
Late vs the 15:59/16:00 rule; places an actual combo on IB paper DUQ159823.
Sell ~30d SPXW put / buy 50pt lower, ~14 DTE. Marketable at bid/ask (mirrors the
sim's fill rule). Protective LONG placed first so we are never naked short.
Safety guards: won't place if quotes invalid, width!=50, or max-loss looks wrong.
"""
import sys, datetime as dt
from pathlib import Path
sys.path.insert(0, "scripts")
import ib_conn, options_sim_daemon as d, options_trade_log as tlog
from ib_async import Option, Index, LimitOrder
from zoneinfo import ZoneInfo
ET = ZoneInfo("America/New_York")

WIDTH, SHORT_D, DTE, FEE = 50, 0.30, 14, 1.30

def tick(x):  # SPX option tick 0.05
    return round(round(x / 0.05) * 0.05, 2)

ib = ib_conn.connect()
print("connected", ib.client.clientId, "accts", ib.managedAccounts())
try:
    spx, rspot = d.rough_spot(ib)   # returns (contract, spot); may seed from tape
    ib.reqMarketDataType(3)         # delayed for the option ladder
    print(f"spot ~ {rspot:.2f}")
    chain = d.get_chain(ib, spx)
    expiry = d.pick_expiry(chain, DTE)
    print("expiry", expiry, "| dte target", DTE)

    # mirror daemon open_put_ladder: valid band spot*0.93..spot, drop None contracts
    ib.reqMarketDataType(3)  # delayed
    ks = sorted([k for k in chain.strikes if rspot * 0.93 <= k <= rspot], reverse=True)
    while len(ks) > 40:
        ks = ks[::2]
    opts = [Option("SPX", expiry, k, "P", "SMART", tradingClass=chain.tradingClass) for k in ks]
    opts = [o for o in ib.qualifyContracts(*opts) if o is not None and o.conId]
    tickers = {o.strike: (o, ib.reqMktData(o, "", snapshot=False)) for o in opts}
    print(f"ladder: {len(tickers)} valid put strikes")
    ib.sleep(9)

    # pick short by |delta|~0.30 if greeks present, else by ~1.6% OTM distance
    def has_q(t): return t.bid == t.bid and t.ask == t.ask and t.ask > 0
    greeked = [(k, t) for k, (o, t) in tickers.items()
               if t.modelGreeks and t.modelGreeks.delta == t.modelGreeks.delta and has_q(t)]
    if greeked:
        short_k = min(greeked, key=lambda kt: abs(abs(kt[1].modelGreeks.delta) - SHORT_D))[0]
        why = "delta"
    else:
        target = rspot * (1 - 0.016)
        quoted = [k for k, (o, t) in tickers.items() if has_q(t)]
        short_k = min(quoted or list(tickers), key=lambda k: abs(k - target))
        why = "OTM-dist fallback (no delayed greeks)"
    long_k = max((k for k in chain.strikes if k <= short_k - WIDTH), default=None)
    if long_k not in tickers:
        lo = ib.qualifyContracts(Option("SPX", expiry, long_k, "P", "SMART",
                                        tradingClass=chain.tradingClass))[0]
        tickers[long_k] = (lo, ib.reqMktData(lo, "", snapshot=False)); ib.sleep(5)

    so, st = tickers[short_k]; lo, lt = tickers[long_k]
    sd = st.modelGreeks.delta if st.modelGreeks else float("nan")
    print(f"\nPROPOSED bull put spread ({why}):")
    print(f"  SELL {short_k}P  bid {st.bid} ask {st.ask}  delta {sd}")
    print(f"  BUY  {long_k}P  bid {lt.bid} ask {lt.ask}")
    width = short_k - long_k
    credit = (st.bid or 0) - (lt.ask or 0)
    print(f"  width {width}pt | est credit {credit:+.2f} | max loss {(width-credit):.2f} x100 = ${(width-credit)*100:,.0f}")

    # ---- GUARDS ----
    ok = has_q(st) and has_q(lt) and width == WIDTH and 0 < credit < width and (width - credit) * 100 < 6000
    if not ok:
        print("\n!! GUARD FAILED — NOT placing. (quotes/width/credit/risk out of bounds)")
        sys.exit(2)

    # ---- PLACE: protective LONG first, then SHORT ----
    buy = LimitOrder("BUY", 1, tick((lt.ask) + 0.30))   # marketable buffer
    t1 = ib.placeOrder(lo, buy); ib.sleep(4)
    for _ in range(6):
        ib.sleep(1)
        if t1.orderStatus.status in ("Filled", "Cancelled", "ApiCancelled"): break
    print("LONG leg:", t1.orderStatus.status, "filled", t1.orderStatus.filled, "@", t1.orderStatus.avgFillPrice)
    if t1.orderStatus.status != "Filled":
        print("!! long leg not filled — aborting before selling (never naked short)."); sys.exit(3)

    sell = LimitOrder("SELL", 1, tick(max(st.bid - 0.30, 0.05)))
    t2 = ib.placeOrder(so, sell); ib.sleep(4)
    for _ in range(6):
        ib.sleep(1)
        if t2.orderStatus.status in ("Filled", "Cancelled", "ApiCancelled"): break
    print("SHORT leg:", t2.orderStatus.status, "filled", t2.orderStatus.filled, "@", t2.orderStatus.avgFillPrice)

    lfill = t1.orderStatus.avgFillPrice; sfill = t2.orderStatus.avgFillPrice
    net = (sfill or 0) - (lfill or 0)
    print(f"\nNET CREDIT filled: {net:+.2f}  (${net*100:,.0f})")

    print("\n=== account positions after ===")
    for p in ib.positions():
        c = p.contract
        if c.secType == "OPT":
            print(f"  {c.localSymbol}  pos={p.position:+g} avgCost={p.avgCost}")

    # ---- LOG to trade ledger ----
    if t2.orderStatus.status == "Filled":
        tlog.append_entry({
            "trade_id": f"bps_stmr_REAL_{dt.datetime.now(ET):%Y%m%d_%H%M}",
            "strategy_id": "bps_stmr", "source": "manual_real_paper",
            "symbol": "SPX", "entry_dt": dt.datetime.now(ET).strftime("%Y-%m-%d %H:%M"),
            "exit_dt": "", "dte": DTE, "structure": f"bull put spread {WIDTH}pt {DTE}DTE",
            "legs": [{"side": "sell", "right": "P", "strike": short_k, "expiry": expiry, "qty": 1, "fill": sfill},
                     {"side": "buy", "right": "P", "strike": long_k, "expiry": expiry, "qty": 1, "fill": lfill}],
            "credit": net, "fill_model": "real_paper_ib_marketable", "slippage": "",
            "commentary": "MANUAL real paper entry, late vs 15:59 rule (7/20 signal missed on OPRA 10090)",
            "grade": "A/B", "vix": "",
        })
        print("\nlogged to trade ledger.")
finally:
    ib.disconnect()
