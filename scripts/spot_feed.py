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
import glob
import json
import sys
from pathlib import Path
from zoneinfo import ZoneInfo

sys.path.insert(0, str(Path(__file__).resolve().parent))
import ib_conn
from ib_async import ContFuture, Index
from options_sim_daemon import SpotRig, get_chain, rough_spot

ET = ZoneInfo("America/New_York")
SIM = Path(__file__).resolve().parents[1] / "data" / "options_sim"
OUT = SIM / "live.json"


def seed_spot(ib):
    """Rough SPX seed to center the parity strikes. Prefers the delayed index
    quote, but that intermittently 322s on paper — so fall back to today's
    underlying tape (the real spot comes from OPRA parity either way)."""
    spx = Index("SPX", "CBOE", "USD")
    ib.qualifyContracts(spx)
    try:
        rough = rough_spot(ib)  # (Index, px) via delayed index quote
        print(f"seed spot {rough[1]:.1f} (delayed index)")
        return rough
    except SystemExit:
        pass
    import csv
    for f in reversed(sorted(glob.glob(str(SIM / "underlying_*.csv")))):
        with open(f, newline="") as fh:
            rows = list(csv.DictReader(fh))
        if rows:
            px = float(rows[-1]["und"])
            print(f"seed spot {px:.1f} (underlying tape {Path(f).name}, delayed-index unavailable)")
            return spx, px
    raise SystemExit("no seed spot — no delayed index quote and no underlying tape.")


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
        spx_idx, rough = seed_spot(ib)
        chain = get_chain(ib, spx_idx)
        rig = SpotRig(ib, chain, rough)
        vix_idx = Index("VIX", "CBOE", "USD")
        ib.qualifyContracts(vix_idx)
        ib.reqMarketDataType(1)

        # ES-est/basis is DISABLED: it needs a delayed SPX index quote, which
        # 322s on this paper feed — the failed request both spams errors and
        # STALLS the loop (spot updates were lagging 10-30s). SPX parity + VIX
        # are all the dashboard and the trigger daemon actually need; a fast,
        # clean tick matters for catching level touches. Re-enable later only
        # if a working index/basis source appears.
        vix = None
        vix_ts = tape_ts = dt.datetime(2000, 1, 1, tzinfo=ET)
        tape = SIM / f"underlying_{now():%Y%m%d}.csv"
        if not tape.exists():
            tape.write_text("ts_et,und\n", encoding="utf-8")
        end = now().replace(hour=16, minute=20, second=0, microsecond=0)
        print(f"feed running until {end:%H:%M} ET -> {OUT}")
        while now() < end:
            spx = rig.spot()
            if (now() - vix_ts).total_seconds() > 60:
                v = delayed_vix(ib, vix_idx)
                if v:
                    vix, vix_ts = v, now()
                ib.reqMarketDataType(1)
            # log the day tape (1/min) so the postmortem has a full price path
            if spx and (now() - tape_ts).total_seconds() > 60:
                with open(tape, "a", encoding="utf-8") as fh:
                    fh.write(f"{now():%H:%M:%S},{spx:.2f}\n")
                tape_ts = now()
            write({"ts_et": now().strftime("%H:%M:%S"),
                   "spx": round(spx, 2) if spx else None,
                   "vix": vix,
                   "es_est": None, "basis": None, "ratio": None, "basis_ts": None,
                   "state": "live" if spx else "no-quotes"})
            ib.sleep(5)
    finally:
        write({"ts_et": now().strftime("%H:%M:%S"), "state": "closed",
               "spx": None, "vix": None, "es_est": None, "basis": None})
        ib.disconnect()


if __name__ == "__main__":
    main()
