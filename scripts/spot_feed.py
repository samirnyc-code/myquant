"""Live SPX / ES / VIX feed for the dashboard (S73) -> data/options_sim/live.json.

Every ~5s during RTH writes:
  { ts_et, spx, vix, es_est, basis, basis_ts, state }

Sources (all covered by existing subscriptions, $0 incremental):
  spx    — realtime via put-call parity on 0DTE SPXW ATM pairs (OPRA sub)
  vix    — IB delayed (15-min) VIX index, refreshed every ~60s
  basis  — measured: delayed ES front future minus delayed SPX index (BOTH are
           15-min delayed => same timestamp => their difference is a valid,
           current basis). Refreshed every ~5 min. ES_live = spx_live + basis.
           (ES = SPX + fair-value basis; it drifts with rates/divs and decays
           to ~0 into each quarterly expiry — measure, don't model.)

Run all day (Task Scheduler or manually, after Gateway login):
  .venv/Scripts/python.exe scripts/spot_feed.py
Exits ~16:20 ET; writes state:"closed" on exit. The app polls live.json.
"""
import datetime as dt
import json
import sys
from pathlib import Path
from zoneinfo import ZoneInfo

sys.path.insert(0, str(Path(__file__).resolve().parent))
import ib_conn
from ib_async import ContFuture, Index
from options_sim_daemon import SpotRig, get_chain, rough_spot

ET = ZoneInfo("America/New_York")
OUT = Path(__file__).resolve().parents[1] / "data" / "options_sim" / "live.json"


def now():
    return dt.datetime.now(ET)


def write(payload):
    OUT.parent.mkdir(parents=True, exist_ok=True)
    tmp = OUT.with_suffix(".tmp")
    tmp.write_text(json.dumps(payload), encoding="utf-8")
    tmp.replace(OUT)  # atomic — the app never reads a half-written file


def delayed_pair(ib, es, spx):
    """Delayed ES + delayed SPX (same 15-min lag) -> (es, spx) or None."""
    ib.reqMarketDataType(4)
    te = ib.reqMktData(es, "", snapshot=False)
    ts = ib.reqMktData(spx, "", snapshot=False)
    ib.sleep(5)
    ib.cancelMktData(es)
    ib.cancelMktData(spx)
    pe = next((x for x in (te.last, te.close) if x == x and x), None)
    ps = next((x for x in (ts.last, ts.close) if x == x and x), None)
    return (float(pe), float(ps)) if pe and ps else None


def delayed_vix(ib, vix):
    ib.reqMarketDataType(4)
    t = ib.reqMktData(vix, "", snapshot=False)
    ib.sleep(4)
    ib.cancelMktData(vix)
    v = next((x for x in (t.last, t.close) if x == x and x), None)
    return float(v) if v else None


def main():
    ib = ib_conn.connect()
    try:
        spx_idx, rough = rough_spot(ib)
        chain = get_chain(ib, spx_idx)
        rig = SpotRig(ib, chain, rough)
        vix_idx = Index("VIX", "CBOE", "USD")
        es_fut = ContFuture("ES", "CME")
        ib.qualifyContracts(vix_idx, es_fut)
        ib.reqMarketDataType(1)

        vix = basis = ratio = None
        basis_ts = vix_ts = dt.datetime(2000, 1, 1, tzinfo=ET)
        end = now().replace(hour=16, minute=20, second=0, microsecond=0)
        print(f"feed running until {end:%H:%M} ET -> {OUT}")
        while now() < end:
            spx = rig.spot()
            if (now() - vix_ts).total_seconds() > 60:
                v = delayed_vix(ib, vix_idx)
                if v:
                    vix, vix_ts = v, now()
                ib.reqMarketDataType(1)
            if (now() - basis_ts).total_seconds() > 300:
                pair = delayed_pair(ib, es_fut, spx_idx)
                if pair:
                    basis, basis_ts = round(pair[0] - pair[1], 2), now()
                    ratio = round(pair[0] / pair[1], 5)
                ib.reqMarketDataType(1)
            write({"ts_et": now().strftime("%H:%M:%S"),
                   "spx": round(spx, 2) if spx else None,
                   "vix": vix,
                   "es_est": round(spx + basis, 2) if (spx and basis is not None) else None,
                   "basis": basis, "ratio": ratio,
                   "basis_ts": basis_ts.strftime("%H:%M") if basis is not None else None,
                   "state": "live" if spx else "no-quotes"})
            ib.sleep(5)
    finally:
        write({"ts_et": now().strftime("%H:%M:%S"), "state": "closed",
               "spx": None, "vix": None, "es_est": None, "basis": None})
        ib.disconnect()


if __name__ == "__main__":
    main()
