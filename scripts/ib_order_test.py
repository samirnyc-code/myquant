"""PAPER-account order-path test (S73). Proves the full API lifecycle:
connect → account summary → live quote → BUY 1 far-OTM SPXW put (marketable
limit) → confirm fill → SELL it back → positions flat. Costs a few paper $.

ib_conn refuses anything that is not a DU… paper account, so this cannot
touch the live account.

Run:  .venv/Scripts/python.exe scripts/ib_order_test.py
"""
import datetime as dt
import sys
from pathlib import Path
from zoneinfo import ZoneInfo

from ib_async import Index, LimitOrder, Option

sys.path.insert(0, str(Path(__file__).resolve().parent))
import ib_conn

ET = ZoneInfo("America/New_York")


def round_tick(px, up):
    """SPX options tick: 0.05 under $3, 0.10 above. Round marketable-safe."""
    tick = 0.05 if px < 3 else 0.10
    import math
    n = px / tick
    n = math.ceil(n - 1e-9) if up else math.floor(n + 1e-9)  # epsilon: 1.2/0.05 = 23.999…
    return round(n * tick, 2)


def marketable(ib, contract, action, qty, px, timeout=45):
    # limit = exactly the NBBO (buy at ask / sell at bid), tick-rounded toward
    # marketable. Crossing further trips IB's aggressive-limit rejects (err 202).
    lim = round_tick(px, up=(action == "BUY"))
    o = LimitOrder(action, qty, lim, tif="DAY", outsideRth=False)
    tr = ib.placeOrder(contract, o)
    print(f"  {action} {qty} @ lim {lim:.2f} -> orderId {o.orderId}", flush=True)
    waited = 0
    while not tr.isDone() and waited < timeout:
        ib.sleep(1)
        waited += 1
    st = tr.orderStatus
    print(f"  status={st.status} filled={st.filled} avgPrice={st.avgFillPrice}")
    if st.status != "Filled":
        for e in tr.log:
            if e.message or e.errorCode:
                print(f"    [{e.status}] code={e.errorCode} {e.message}")
        ib.cancelOrder(o)
        ib.sleep(2)
    _audit(contract, action, qty, px, lim, tr)
    return tr


def _audit(contract, action, qty, px, lim, tr):
    """Every order (filled, cancelled, rejected) -> data/options_log/orders.csv."""
    import csv
    import datetime as _dt
    from pathlib import Path as _P
    from zoneinfo import ZoneInfo as _Z
    f = _P(__file__).resolve().parents[1] / "data" / "options_log" / "orders.csv"
    f.parent.mkdir(parents=True, exist_ok=True)
    new = not f.exists()
    st = tr.orderStatus
    reasons = "; ".join(f"{e.errorCode}:{e.message[:80]}" for e in tr.log
                        if e.errorCode or e.message)[:300]
    with open(f, "a", newline="", encoding="utf-8") as fh:
        w = csv.writer(fh)
        if new:
            w.writerow(["ts_et", "localSymbol", "action", "qty", "quote_px", "limit",
                        "status", "filled", "avg_fill", "order_id", "log"])
        w.writerow([_dt.datetime.now(_Z("America/New_York")).strftime("%Y-%m-%d %H:%M:%S"),
                    contract.localSymbol, action, qty, px, lim,
                    st.status, st.filled, st.avgFillPrice, tr.order.orderId, reasons])


def main():
    ib = ib_conn.connect()  # paper 4002, DU… enforced
    ib.errorEvent += lambda reqId, code, msg, *a: print(f"    [ib {code}] {str(msg)[:160]}", flush=True)
    try:
        acct = ib.managedAccounts()[0]
        rows = {r.tag: r.value for r in ib.accountSummary(acct)
                if r.tag in ("NetLiquidation", "AvailableFunds", "BuyingPower")}
        print(f"account {acct}: {rows}")

        ib.reqMarketDataType(4)
        spx = Index("SPX", "CBOE", "USD")
        ib.qualifyContracts(spx)
        t = ib.reqMktData(spx, "", snapshot=False)
        ib.sleep(4)
        ib.cancelMktData(spx)
        spot = next((x for x in (t.last, t.close) if x == x and x), None)
        print(f"delayed SPX ~ {spot}")

        chains = ib.reqSecDefOptParams("SPX", "", "IND", spx.conId)
        chain = next(c for c in chains if c.tradingClass == "SPXW" and c.exchange == "SMART")
        today = dt.datetime.now(ET).strftime("%Y%m%d")
        expiry = min(e for e in chain.expirations if e >= today)
        k = min((s for s in chain.strikes if s <= spot * 0.97), key=lambda s: abs(s - spot * 0.97))
        opt = ib.qualifyContracts(Option("SPX", expiry, k, "P", "SMART", tradingClass="SPXW"))[0]

        ib.reqMarketDataType(1)  # OPRA realtime
        q = ib.reqMktData(opt, "", snapshot=False)
        ib.sleep(6)
        print(f"test contract: SPXW {expiry} {k:.0f}P  bid/ask {q.bid}/{q.ask}")
        if not (q.ask == q.ask and q.ask > 0):
            raise SystemExit("No live ask on the test option — OPRA entitlement problem on paper?")

        print("\nBUY leg:")
        b = marketable(ib, opt, "BUY", 1, q.ask)
        if b.orderStatus.status != "Filled":
            raise SystemExit("Buy did not fill — order path works up to routing, check message above.")
        print("\nSELL back:")
        s = marketable(ib, opt, "SELL", 1, q.bid if q.bid == q.bid and q.bid > 0 else q.ask * 0.8)

        ib.sleep(2)
        pos = [p for p in ib.positions() if p.contract.conId == opt.conId and p.position != 0]
        cost = (b.orderStatus.avgFillPrice - (s.orderStatus.avgFillPrice or 0)) * 100
        print(f"\n=== VERDICT ===\nround-trip cost ${cost:.2f} (the spread, as expected)"
              f"\nresidual position: {pos if pos else 'FLAT ✓'}"
              f"\nORDER API: {'WORKING' if s.orderStatus.status == 'Filled' else 'buy ok, sell pending — check TWS'}")
    finally:
        ib.disconnect()


if __name__ == "__main__":
    main()
