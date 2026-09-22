"""Probe IB market-data line headroom while the live desk is running.

Question: the chain recorder fails with 10090 because its ~78 PERSISTENT streaming
lines exceed the account quota once stacked on the desk. Does a SNAPSHOT request
(which the 60s recorder cadence actually needs — no all-day line) get realtime
quotes in the headroom the desk leaves? And how many streaming lines are free?

Writes scratchpad/ib_line_probe_<ts>.txt with the verdict.
"""
import sys, datetime as dt
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
import ib_conn
from ib_async import Option
from options_chain_recorder import spot_now, strike_window

ib = ib_conn.connect(client_id=88)
ib.reqMarketDataType(1)
spot = spot_now(ib)
today = dt.datetime.now().strftime("%Y%m%d")

errs = {}
ib.errorEvent += lambda reqId, code, msg, c=None: errs.setdefault(code, 0)
def on_err(reqId, code, msg, contract=None, *a):
    errs[code] = errs.get(code, 0) + 1
ib.errorEvent += on_err

ks = strike_window(spot, 1.25)
cs = [Option("SPX", today, k, r, "SMART", tradingClass="SPXW") for k in ks for r in ("P", "C")]
cs = [c for c in ib.qualifyContracts(*cs) if c and c.conId]

# --- test 1: SNAPSHOT requests, batched (what a fixed recorder would do) ---
snap_ok = snap_bad = 0
for i in range(0, len(cs), 25):
    batch = cs[i:i+25]
    tks = [ib.reqMktData(c, "", snapshot=True) for c in batch]
    ib.sleep(3)
    for t in tks:
        good = (t.bid == t.bid and t.bid >= 0) or (t.ask == t.ask and t.ask >= 0)
        snap_ok += 1 if good else 0
        snap_bad += 0 if good else 1

out = [
    f"probe @ {dt.datetime.now():%H:%M:%S}  spot={spot}  contracts={len(cs)}",
    f"SNAPSHOT: {snap_ok} got a quote, {snap_bad} empty/blocked",
    f"IB error codes seen: {dict(sorted(errs.items()))}",
    "  (10090 = 'not subscribed/delayed' = over the line quota;"
    " 0 of these + high snap_ok => snapshots are the fix)",
]
print("\n".join(out))
p = Path(__file__).resolve().parent / f"ib_line_probe_{dt.datetime.now():%Y%m%d_%H%M%S}.txt"
p.write_text("\n".join(out), encoding="utf-8")
print("wrote", p.name)
ib.disconnect()
