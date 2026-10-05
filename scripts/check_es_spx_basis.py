"""One-shot diagnostic (S128): pull a REAL delayed ES front-future quote and a
REAL delayed SPX index quote from IB at the same moment, and compare against
whatever spot_feed.py is currently writing to live.json / the dashboard.

Answers, with live numbers (not a carry-cost estimate): is the dashboard's
SPX-via-parity number sane, and what is the actual ES-SPX basis right now.

Usage: .venv/Scripts/python.exe scripts/check_es_spx_basis.py
Saves: data/options_sim/basis_check_<ts>.json
"""
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import ib_conn
from ib_async import ContFuture, Index

SIM = Path(__file__).resolve().parents[1] / "data" / "options_sim"


def main():
    ib = ib_conn.connect()
    ib.reqMarketDataType(4)  # delayed-frozen, same lag for both legs

    es = ContFuture("ES", "CME")
    spx = Index("SPX", "CBOE", "USD")
    ib.qualifyContracts(es, spx)
    print(f"ES qualified contract: {es.localSymbol} (conId {es.conId}) lastTradeDate {es.lastTradeDateOrContractMonth}")

    te = ib.reqMktData(es, "", snapshot=False)
    ts = ib.reqMktData(spx, "", snapshot=False)
    ib.sleep(8)
    ib.cancelMktData(es)
    ib.cancelMktData(spx)

    es_px = next((x for x in (te.last, te.close, te.marketPrice()) if x == x and x), None)
    spx_px = next((x for x in (ts.last, ts.close, ts.marketPrice()) if x == x and x), None)

    live_path = SIM / "live.json"
    live = json.loads(live_path.read_text()) if live_path.exists() else {}

    result = {
        "es_local_symbol": es.localSymbol,
        "es_delayed_px": es_px,
        "spx_delayed_px": spx_px,
        "measured_basis_es_minus_spx": round(es_px - spx_px, 2) if (es_px and spx_px) else None,
        "dashboard_live_json": live,
    }
    print(json.dumps(result, indent=2))

    out = SIM / f"basis_check_{es.lastTradeDateOrContractMonth}.json"
    out.write_text(json.dumps(result, indent=2), encoding="utf-8")
    print(f"saved -> {out}")

    ib.disconnect()


if __name__ == "__main__":
    main()
