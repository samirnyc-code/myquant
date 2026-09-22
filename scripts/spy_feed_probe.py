"""READ-ONLY probe: can we record SPY options alongside SPX on the same gateway?

Answers the one open question the recorder code can't: market-data ENTITLEMENT.
SPX/XSP are CBOE index options; SPY options are OPRA US equity/ETF options — a
possibly separate IB subscription. This connects a fresh client (id 73, no
orders), requests a near-ATM 0DTE-ish snapshot for BOTH SPY and SPX at the same
time, and reports realtime-vs-delayed (marketDataType 1 = subscribed/realtime;
3/4 = delayed = NOT subscribed) plus any entitlement error (354).

Run when the gateway is UP:  .venv/Scripts/python.exe scripts/spy_feed_probe.py
Prints a verdict; writes nothing, places nothing.
"""
import datetime as dt
import json
from pathlib import Path

import ib_conn
from ib_insync import Index, Option, Stock

SIM = Path("data/options_sim")


def approx_spx():
    try:
        d = json.loads((SIM / "live.json").read_text())
        return float(d["spx"])
    except Exception:
        return None


def nearest_expiry_and_strike(ib, und, tclass, spot):
    """Use option chain params to pick the nearest expiry and ATM strike."""
    det = ib.reqContractDetails(und)[0].contract
    params = ib.reqSecDefOptParams(und.symbol, "", und.secType, det.conId)
    p = next((x for x in params if x.tradingClass == tclass), params[0])
    expiry = sorted(p.expirations)[0]
    strikes = sorted(float(s) for s in p.strikes)
    atm = min(strikes, key=lambda k: abs(k - spot))
    return expiry, atm


def probe(ib, label, und, tclass, spot):
    exp, k = nearest_expiry_and_strike(ib, und, tclass, spot)
    opt = ib.qualifyContracts(Option(und.symbol, exp, k, "C", "SMART", tradingClass=tclass))
    if not opt:
        return f"{label}: could NOT qualify {und.symbol} {tclass} {k}C {exp}"
    t = ib.reqMktData(opt[0], "", snapshot=True)
    ib.sleep(4)
    mdt = getattr(t, "marketDataType", None)
    rt = {1: "REALTIME(subscribed)", 2: "frozen", 3: "DELAYED(not subscribed)",
          4: "delayed-frozen"}.get(mdt, f"unknown({mdt})")
    return (f"{label}: {und.symbol} {tclass} {k}C exp {exp} -> mdType={mdt} {rt} "
            f"bid={t.bid} ask={t.ask}")


def main():
    spx = approx_spx()
    print(f"approx SPX spot from live.json: {spx}")
    if spx is None:
        spx = 7700.0
    ib = ib_conn.connect(client_id=73, ensure=False, timeout=30)
    errs = []
    ib.errorEvent += lambda reqId, code, msg, c=None: errs.append((code, msg))
    ib.reqMarketDataType(1)
    print("\n" + probe(ib, "SPX ", Index("SPX", "CBOE", "USD"), "SPXW", spx))
    print(probe(ib, "SPY ", Stock("SPY", "SMART", "USD"), "SPY", spx / 10.0))
    ib.sleep(1)
    ent = [e for e in errs if e[0] in (354, 10089, 10090, 10091, 10197)]
    if ent:
        print("\nentitlement/feed messages:")
        for c, m in ent:
            print(f"  {c}: {m}")
    print("\nVERDICT: SPY realtime (mdType=1) => same gateway can record SPY+SPX "
          "concurrently (SPY = separate process, client_id 73, tradingClass SPY, "
          "step $1, spot_div 10). DELAYED/354 => need an OPRA equity-options "
          "market-data subscription in IB first.")
    ib.disconnect()


if __name__ == "__main__":
    main()
