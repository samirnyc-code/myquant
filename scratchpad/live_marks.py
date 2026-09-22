"""Live mark-to-market of OPEN positions straight from IB NBBO (marks.csv is stale)."""
import sys, json
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
import pandas as pd
import ib_conn
from ib_async import Option

d = pd.read_parquet(Path(__file__).resolve().parents[1] / "data/options_log/trades.parquet")
op = d[d.exit_dt.isna()].copy()
ib = ib_conn.connect(client_id=121); ib.reqMarketDataType(1)

# gather unique legs
def legs_of(r):
    return json.loads(r.legs) if isinstance(r.legs, str) else r.legs

want = {}
for _, r in op.iterrows():
    for lg in legs_of(r):
        key = (lg["expiry"], float(lg["strike"]), lg["right"])
        want[key] = None
cons = {k: Option("SPX", k[0], k[1], k[2], "SMART", tradingClass="SPXW") for k in want}
q = ib.qualifyContracts(*cons.values())
qmap = {(c.lastTradeDateOrContractMonth, float(c.strike), c.right): c for c in q if c and c.conId}
tks = {k: ib.reqMktData(c, "", snapshot=True) for k, c in qmap.items()}
ib.sleep(6)
mid = {}
for k, t in tks.items():
    b, a = t.bid, t.ask
    mid[k] = (b + a) / 2 if (b == b and a == a and b >= 0 and a >= 0) else None

print(f"{'strategy':<12} {'credit':>7} {'now_close':>10} {'LIVE P&L$':>10}")
tot = 0.0
for _, r in op.iterrows():
    cost = 0.0; ok = True
    for lg in legs_of(r):
        k = (lg["expiry"], float(lg["strike"]), lg["right"])
        m = mid.get(k)
        if m is None: ok = False; break
        cost += m if lg["side"] == "sell" else -m   # buy back shorts, sell longs
    if not ok:
        print(f"{r.strategy_id:<12}  (no quote)"); continue
    qty = int(legs_of(r)[0].get("qty", 1))
    pnl = (float(r.credit) - cost) * 100 * qty
    tot += pnl
    print(f"{r.strategy_id:<12} {float(r.credit):>7.2f} {cost:>10.2f} {pnl:>10.0f}")
print(f"\nLIVE unrealized TOTAL: ${tot:,.0f}")
ib.disconnect()
