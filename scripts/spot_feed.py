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
Exits ~15:20 CT; writes state:"closed" on exit. The app polls live.json.
"""
import datetime as dt
import glob
import json
import sys
import threading
import time
from pathlib import Path
from zoneinfo import ZoneInfo

sys.path.insert(0, str(Path(__file__).resolve().parent))
import ib_conn
from ib_async import ContFuture, Index
from options_sim_daemon import SpotRig, get_chain, rough_spot

CT = ZoneInfo("America/Chicago")  # exchange time (Chicago / Central)
SIM = Path(__file__).resolve().parents[1] / "data" / "options_sim"
OUT = SIM / "live.json"

# ── ES basis, sourced from MenthorQ's own candle feed ────────────────────────
# es_est = spx_live (fast OPRA parity) + basis, where basis = ES1! − SPX taken
# CONTEMPORANEOUSLY from MenthorQ's candles (same source MQ's Conversion
# indicator uses). Runs on a BACKGROUND thread refreshed every few minutes so a
# slow MQ call (or a Playwright re-auth) can never stall the fast SPX tick —
# that stall was exactly why the old IB-based basis was disabled. The basis
# drifts only fractions of a point per minute, so a few-min-old value is plenty
# fresh; es_est itself re-derives every ~5s off the live parity spot.
BASIS_REFRESH_S = 180                 # how often to re-measure ES1!−SPX
BASIS_STALE_S = 300                   # reject basis if SPX bar is older than this
BASIS_BAND = (-100.0, 200.0)          # sanity clamp; reject garbage measurements
_basis = {"basis": None, "ratio": None, "ts": None}   # shared, updated by worker


def _mq_pair():
    """Latest contemporaneous (SPX, ES1!, spx_bar_ms) from MenthorQ 1m candles.
    spx_bar_ms is the SPX bar's own timestamp so the caller can reject a stale
    index print (pre/post-market the index freezes while ES keeps trading — a
    basis off that mismatch is meaningless)."""
    from mq_api import MQ, GW
    mq = MQ()
    while True:
        now_ms = int(time.time() * 1000)
        frm = now_ms - 30 * 60 * 1000
        h = {"accept": "application/json", "authorization": mq.token}
        bars = {}
        for sym in ("SPX", "ES1!"):
            r = mq.s.get(f"{GW}/tickers/{sym}/candles", headers=h,
                         params={"interval": "1m", "from": frm, "to": now_ms,
                                 "countBack": 40}, timeout=30)
            r.raise_for_status()
            bars[sym] = r.json()[-1]
        yield float(bars["SPX"]["c"]), float(bars["ES1!"]["c"]), int(bars["SPX"]["t"])


def basis_worker():
    """Refresh the shared basis/ratio every BASIS_REFRESH_S. Never raises."""
    while True:
        try:
            gen = _mq_pair()          # (re)builds the MQ session/token on entry
            for spx_mq, es_mq, spx_ms in gen:
                stale_s = time.time() - spx_ms / 1000
                b = round(es_mq - spx_mq, 2)
                if stale_s > BASIS_STALE_S:
                    print(f"basis: SPX bar {stale_s / 60:.0f}m stale "
                          f"(index not printing) — hold {_basis['basis']}")
                elif BASIS_BAND[0] <= b <= BASIS_BAND[1]:
                    _basis.update(basis=b, ratio=round(es_mq / spx_mq, 6),
                                  ts=now().strftime("%H:%M:%S"))
                    print(f"basis {b:+.2f} (ES1! {es_mq:.2f} / SPX {spx_mq:.2f}, "
                          f"ratio {es_mq / spx_mq:.5f})")
                time.sleep(BASIS_REFRESH_S)
        except Exception as e:
            print(f"basis worker: {str(e)[:120]} — retry in {BASIS_REFRESH_S}s")
            time.sleep(BASIS_REFRESH_S)


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
    return dt.datetime.now(CT)


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


def run_session(ib, end, tape):
    """One connected feed session. Returns normally at `end`; raises on any
    error or stall so the outer loop can reconnect (S75M — on 7/17 a midday IB
    drop made the old single-shot main() crash out at 12:59 ET and the desk ran
    blind for 36 min)."""
    spx_idx, rough = seed_spot(ib)
    chain = get_chain(ib, spx_idx)
    rig = SpotRig(ib, chain, rough)
    vix_idx = Index("VIX", "CBOE", "USD")
    ib.qualifyContracts(vix_idx)
    ib.reqMarketDataType(1)
    vix = None
    vix_ts = tape_ts = dt.datetime(2000, 1, 1, tzinfo=CT)
    last_spx, last_change = None, now()
    while now() < end:
        spx = rig.spot()
        if spx and spx != last_spx:
            last_spx, last_change = spx, now()
        # a parity mid frozen to the tick for 5 min = dead tickers, not a quiet
        # tape; no spot at all for 2 min = same. Either way: reconnect.
        stalled_s = (now() - last_change).total_seconds()
        if not ib.isConnected() or stalled_s > (300 if spx else 120):
            raise ConnectionError(
                f"feed stalled (connected={ib.isConnected()}, {stalled_s:.0f}s no change)")
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
        b = _basis["basis"]
        es_est = round(spx + b, 2) if (spx and b is not None) else None
        # NB "ts_et" is historically CT (every consumer treats it as CT and the
        # dashboard labels it CT) — kept for compat; ts_epoch is the robust field.
        write({"ts_et": now().strftime("%H:%M:%S"), "ts_epoch": int(time.time()),
               "spx": round(spx, 2) if spx else None,
               "vix": vix,
               "es_est": es_est, "basis": b, "ratio": _basis["ratio"],
               "basis_ts": _basis["ts"],
               "state": "live" if spx else "no-quotes"})
        ib.sleep(5)


def main():
    # ES-est/basis comes from MenthorQ's candle feed on a background thread
    # (see basis_worker) — decoupled from the fast loop so it can't stall it.
    threading.Thread(target=basis_worker, daemon=True).start()
    tape = SIM / f"underlying_{now():%Y%m%d}.csv"
    if not tape.exists():
        tape.write_text("ts_et,und\n", encoding="utf-8")
    end = now().replace(hour=15, minute=20, second=0, microsecond=0)
    print(f"feed running until {end:%H:%M} CT -> {OUT}")
    try:
        while now() < end:
            ib = None
            try:
                ib = ib_conn.connect()
                run_session(ib, end, tape)          # returns only at `end`
            except Exception as e:
                print(f"feed error: {str(e)[:150]} — reconnecting in 20s")
                write({"ts_et": now().strftime("%H:%M:%S"), "ts_epoch": int(time.time()),
                       "state": "reconnecting", "spx": None, "vix": None,
                       "es_est": None, "basis": None})
                time.sleep(20)
            finally:
                if ib is not None:
                    try:
                        ib.disconnect()
                    except Exception:
                        pass
    finally:
        write({"ts_et": now().strftime("%H:%M:%S"), "ts_epoch": int(time.time()),
               "state": "closed", "spx": None, "vix": None, "es_est": None, "basis": None})


if __name__ == "__main__":
    main()
