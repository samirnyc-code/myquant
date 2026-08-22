"""Forward 0DTE SPXW chain recorder — build our OWN intraday options dataset.

Every trading day, from the open to the close, snapshot the SPXW 0DTE NBBO for a
strike window around spot (every 30s by default) and append to a dated CSV. This is the
data that lets us later test EVERYTHING retrospectively — any entry time (was
08:35 right?), any strike, any structure, any exit rule — from real quotes we
actually recorded, not from the handful of trades we happened to take.

It is the free, forward equivalent of buying Databento intraday history: same
NBBO, real fills, captured live off IB/OPRA. Complementary — recorder = forward,
Databento = past.

Output: data/options_sim/chain_YYYYMMDD.csv  (append-per-minute, crash-safe)
  columns: ts_et, spot, expiry, strike, right, bid, ask

Run it from ~08:25 CT (before the 08:30 open) to the close:
  .venv/Scripts/python.exe scripts/options_chain_recorder.py [--pct 2.0] [--secs 60]
  .venv/Scripts/python.exe scripts/options_chain_recorder.py --mock   # no IB; verify logic
"""
import argparse
import csv
import datetime as dt
import json
import time
import traceback
from pathlib import Path
from zoneinfo import ZoneInfo

ROOT = Path(__file__).resolve().parents[1]
SIM = ROOT / "data" / "options_sim"
CT = ZoneInfo("America/Chicago")
ET = ZoneInfo("America/New_York")
STRIKE_STEP = 5
HEARTBEAT = SIM / "chain_heartbeat.json"   # written every sweep; the supervisor reads it


def now_ct():
    return dt.datetime.now(CT)


def spot_now(ib=None):
    """Live spot: from live.json if ticking, else IB ATM parity, else None."""
    live = SIM / "live.json"
    if live.exists():
        try:
            d = json.loads(live.read_text())
            if d.get("spx"):
                return float(d["spx"])
        except Exception:
            pass
    if ib is not None:
        try:
            from options_sim_daemon import rough_spot
            _, px = rough_spot(ib)   # rough_spot returns (contract, price), NOT a float —
            return float(px)         # float(rough_spot(...)) threw & was swallowed => None,
        except Exception:            # so this fallback never worked and the recorder died at
            pass                     # launch whenever live.json was stale (2026-08-17 fix).
    return None


def strike_window(spot, pct):
    lo = (round((spot * (1 - pct / 100)) / STRIKE_STEP)) * STRIKE_STEP
    hi = (round((spot * (1 + pct / 100)) / STRIKE_STEP)) * STRIKE_STEP
    return list(range(int(lo), int(hi) + STRIKE_STEP, STRIKE_STEP))


def out_path(date):
    return SIM / f"chain_{date}.csv"


def append_rows(path, rows):
    new = not path.exists()
    with open(path, "a", newline="") as f:
        w = csv.writer(f)
        if new:
            w.writerow(["ts_et", "spot", "expiry", "strike", "right", "bid", "ask"])
        w.writerows(rows)


def run_mock(pct):
    """No IB — verify strike-set + file logic against a fake spot."""
    date = now_ct().strftime("%Y%m%d")
    spot = 7500.0
    ks = strike_window(spot, pct)
    print(f"MOCK  spot {spot:.0f}  ±{pct}%  -> {len(ks)} strikes {ks[0]}..{ks[-1]} "
          f"({len(ks) * 2} market-data lines)")
    ts = dt.datetime.now(ET).strftime("%Y-%m-%d %H:%M:%S")
    rows = [[ts, spot, date, k, r, round(k * 0.001, 2), round(k * 0.001 + 0.1, 2)]
            for k in ks for r in ("P", "C")]
    p = out_path(date + "_mock")
    append_rows(p, rows)
    print(f"wrote {len(rows)} rows -> {p.relative_to(ROOT)}  (delete when done verifying)")


def _qualified(ib, expiry, strikes, cache):
    """Qualify each (strike, right) once and reuse across cycles (qualifyContracts
    is a network round-trip; caching keeps the per-minute sweep cheap)."""
    from ib_async import Option
    need = [(k, r) for k in strikes for r in ("P", "C") if (k, r) not in cache]
    if need:
        cs = [Option("SPX", expiry, k, r, "SMART", tradingClass="SPXW") for k, r in need]
        for c in ib.qualifyContracts(*cs):
            if c and c.conId:
                cache[(c.strike, c.right)] = c
    return [cache[(k, r)] for k in strikes for r in ("P", "C") if (k, r) in cache]


def snapshot_sweep(ib, contracts, batch=30, settle=3.0):
    """One NBBO SNAPSHOT per contract, in line-friendly batches.

    THE FIX (2026-08-16): the recorder used to hold ~78 PERSISTENT streaming lines
    all day (reqMktData snapshot=False), which stacked on top of the live desk's
    streaming lines and blew past the account's market-data-line quota — IB then
    returned error 10090 ('not subscribed / delayed available') for the overflow and
    the recorder captured nothing (dead since 2026-08-07). But it only samples once a
    minute, so it never needed persistent streams. A SNAPSHOT holds a line only for
    the ~seconds it takes to fill, then releases it — so the recorder no longer
    competes all-day with the desk, and its need is 'a few at a time' (fits whatever
    headroom exists) instead of 'all 78 at once'. Blocked/empty contracts are retried
    once in a smaller batch to squeeze into tight headroom.

    REALTIME GUARD — decide realtime-vs-delayed from each ticker's marketDataType
    (1=realtime, 2=frozen, 3=delayed, 4=delayed-frozen), NOT from the 10090 error.
    (2026-08-20 fix, verified live: SPXW snapshots ROUTINELY emit error 10090 — 'part of
    requested market data is not subscribed; subscription-INDEPENDENT ticks are still
    active' — while the NBBO itself is REALTIME (marketDataType=1). The prior guard keyed
    off the 10090 code and DROPPED those good realtime quotes: on 2026-08-20 it wrote 0
    rows for 2+ hours on a fully realtime feed (8/8 probe strikes were mdType=1 with valid
    NBBO, all dropped). We now record when the ticker is realtime with a valid NBBO and
    drop ONLY when IB actually served delayed (marketDataType in (3, 4)).)
    Returns ({(strike, right): (bid, ask)}, n_empty, n_delayed)."""
    out, delayed, missed = {}, 0, list(contracts)
    for _ in range(2):
        pending, missed = missed, []
        for i in range(0, len(pending), batch):
            grp = pending[i:i + batch]
            tks = [(c, ib.reqMktData(c, "", snapshot=True)) for c in grp]
            ib.sleep(settle)
            for c, t in tks:
                try:
                    ib.cancelMktData(c)       # snapshots auto-cancel; belt-and-suspenders
                except Exception:
                    pass
                if getattr(t, "marketDataType", None) in (3, 4):  # IB actually served DELAYED
                    delayed += 1                                  # -> never record stale quotes
                    continue
                b = t.bid if (t.bid == t.bid and t.bid >= 0) else None
                a = t.ask if (t.ask == t.ask and t.ask >= 0) else None
                if b is None and a is None:
                    missed.append(c)
                else:
                    out[(c.strike, c.right)] = (b, a)
        if not missed:
            break
        batch = max(5, batch // 3)
    return out, len(missed), delayed


def validate_day(date, secs, stop_hhmm, open_hhmm="08:30"):
    """EOD completeness gate: a day only 'counts' toward the 90 if it's actually
    complete. Compares distinct snapshots captured against the full session at the
    target cadence, and finds the largest hole. Writes a report; returns the dict."""
    import numpy as np, pandas as pd
    p = out_path(date)
    oh, om = map(int, open_hhmm.split(":"))
    sh, sm = map(int, stop_hhmm.split(":"))
    session_s = ((sh * 60 + sm) - (oh * 60 + om)) * 60
    expected = max(1, session_s // secs)
    rep = {"date": date, "cadence_s": secs, "expected_snaps": int(expected),
           "actual_snaps": 0, "coverage_pct": 0.0, "first_ct": None, "last_ct": None,
           "max_gap_s": None, "holes_over_2x": 0, "complete": False}
    if p.exists():
        d = pd.read_csv(p)
        ts = pd.to_datetime(d["ts_et"])                       # ET stamps
        t = np.array(sorted(ts.dt.floor("s").unique()))
        rep["actual_snaps"] = int(len(t))
        rep["coverage_pct"] = round(100 * len(t) / expected, 1)
        rep["first_ct"] = (ts.min() - pd.Timedelta(hours=1)).strftime("%H:%M:%S")
        rep["last_ct"] = (ts.max() - pd.Timedelta(hours=1)).strftime("%H:%M:%S")
        if len(t) > 1:
            gaps = np.diff(t).astype("timedelta64[s]").astype(int)
            rep["max_gap_s"] = int(gaps.max())
            rep["holes_over_2x"] = int((gaps > 2 * secs).sum())
        # Grade on CONTINUITY (full-session span + no holes), NOT on hitting the nominal
        # cadence exactly. A wide sweep may only achieve ~10-15s even at --secs 10; that
        # must not false-flag INCOMPLETE. A day counts if it started near the open, ran to
        # the close, and has no gap beyond ~a handful of missed cycles.
        started = rep["first_ct"] is not None and rep["first_ct"] <= "08:40:00"
        ran_to_close = rep["last_ct"] is not None and rep["last_ct"] >= "14:55:00"
        no_holes = (rep["max_gap_s"] or 0) <= max(6 * secs, 90)
        rep["complete"] = bool(started and ran_to_close and no_holes)
    out = SIM / f"chain_completeness_{date}.json"
    out.write_text(json.dumps(rep, indent=2), encoding="utf-8")
    flag = "COMPLETE" if rep["complete"] else "INCOMPLETE"
    print(f"  completeness [{flag}]: {rep['actual_snaps']}/{rep['expected_snaps']} snaps "
          f"({rep['coverage_pct']}%), {rep['first_ct']}→{rep['last_ct']} CT, "
          f"max gap {rep['max_gap_s']}s, {rep['holes_over_2x']} holes  -> {out.name}")
    return rep


def write_heartbeat(date, rows, spot, state, delayed=0, empty=0, note=""):
    """One-line liveness beacon the supervisor polls. state ∈ ok / waiting_spot /
    feed_delayed / error. A FRESH heartbeat with rows==0 means 'alive but the feed
    gave us nothing' (do NOT relaunch — that's a feed issue); a STALE heartbeat means
    the process hung or died (relaunch)."""
    try:
        HEARTBEAT.write_text(json.dumps({
            "ts_ct": now_ct().strftime("%Y-%m-%d %H:%M:%S"),
            "ts_epoch": time.time(), "date": date, "rows": rows,
            "spot": spot, "state": state, "delayed": delayed, "empty": empty,
            "note": note, "pid": __import__("os").getpid(),
        }), encoding="utf-8")
    except Exception:
        pass


def connect_with_retry(client_id, tries=30, wait=10, log=print):
    """Connect to the gateway, RETRYING instead of dying. At the 08:25 launch the
    gateway may still be finishing login; a single failed connect used to kill the
    recorder for the whole day. Returns a connected ib or None after `tries`."""
    import ib_conn
    for i in range(1, tries + 1):
        try:
            ib = ib_conn.connect(client_id=client_id)
            ib.reqMarketDataType(1)
            return ib
        except Exception as e:
            log(f"  connect attempt {i}/{tries} failed: {type(e).__name__}: {e} — retry in {wait}s")
            time.sleep(wait)
    return None


def run_live(pct, secs, stop_hhmm):
    """Durable per-`secs` SNAPSHOT sweep of a rolling ±pct 0DTE window (+ pinned trade
    strikes). Rebuilt 2026-08-20 to be CRASH-PROOF: it retries the gateway connect at
    launch (never SystemExit on a cold feed), reconnects on a mid-session drop, wraps
    every sweep so one bad cycle can't kill the day, anchors the cadence to wall-clock
    (true 30s spacing, not sweep+sleep drift), and writes a heartbeat each cycle so the
    supervisor can tell 'hung/dead' (relaunch) from 'feed delayed' (alert only)."""
    import singleton
    singleton.ensure("options_chain_recorder")  # one recorder only — duplicates starve each other of IB lines
    date = now_ct().strftime("%Y%m%d")
    expiry = date                                # 0DTE: today's SPXW expiry
    stop = dt.time(*map(int, stop_hhmm.split(":")))
    p = out_path(date)
    cache = {}                                   # (strike, right) -> qualified Contract

    ib = connect_with_retry(client_id=71)        # distinct from daemons (avoid clientId clash)
    if ib is None:
        write_heartbeat(date, 0, None, "error", note="could not connect to gateway")
        raise SystemExit("gateway unreachable after retries — supervisor will relaunch")
    spot = spot_now(ib)                          # may be None on a cold feed; we WAIT, not die

    def pinned_strikes():
        """Strikes of TODAY'S armed/fired structures (gameplan verticals) — always
        swept, even when the rolling window moves away, so every real trade's full
        intraday exit path (TP/trail/MFE-MAE) is recorded. Re-read each loop: the
        daemon persists resolved open-struck strikes after the bell. (STMR is 14-DTE —
        different expiry, captured by the sim daemon's own tape.)"""
        try:
            d = json.loads((SIM / f"gameplan_{date}.json").read_text(encoding="utf-8"))
            out = set()
            for t in d.get("triggers", []):
                st = t.get("structure", {})
                if st.get("kind") == "vertical" and not st.get("dte"):
                    for key in ("short", "long"):
                        v = st.get(key)
                        if isinstance(v, (int, float)):
                            out.add(int(v))
            return out
        except Exception:
            return set()

    print(f"recording ±{pct}% 0DTE SNAPSHOT sweep every {secs}s until {stop_hhmm} CT, exp {expiry}")
    total_snaps = 0
    next_t = time.monotonic()
    while now_ct().time() < stop:
        try:
            if not ib.isConnected():             # reconnect on a silent mid-session drop
                print("  connection dropped — reconnecting…")
                write_heartbeat(date, 0, spot, "error", note="reconnecting")
                try:
                    ib.disconnect()
                except Exception:
                    pass
                ib = connect_with_retry(client_id=71)
                if ib is None:
                    raise SystemExit("gateway unreachable mid-session — supervisor will relaunch")
            s = spot_now(ib)
            if s is None:                        # feed not serving spot — stay ALIVE and wait
                write_heartbeat(date, 0, spot, "waiting_spot", note="no spot from feed")
                print(f"  {now_ct():%H:%M:%S} CT  waiting for spot…")
            else:
                spot = s
                # rolling window recomputed each cycle from current spot (+ pinned strikes),
                # so it self-recenters on a trend move — no separate drift bookkeeping needed
                strikes = sorted(set(strike_window(spot, pct)) | pinned_strikes())
                contracts = _qualified(ib, expiry, strikes, cache)
                quotes, empty, delayed = snapshot_sweep(ib, contracts)
                ts = dt.datetime.now(ET).strftime("%Y-%m-%d %H:%M:%S")
                rows = [[ts, round(spot, 2), expiry, k, r,
                         (b if b is not None else ""), (a if a is not None else "")]
                        for (k, r), (b, a) in quotes.items()]
                if rows:
                    append_rows(p, rows)
                    total_snaps += 1
                state = "ok" if rows else ("feed_delayed" if delayed else "empty")
                write_heartbeat(date, len(rows), spot, state, delayed=delayed, empty=empty)
                msg = f"  {ts}  {len(rows)} realtime quotes"
                if delayed:
                    msg += f"  ({delayed} DROPPED not-realtime)"
                if empty:
                    msg += f"  ({empty} no quote)"
                print(msg)
        except SystemExit:
            raise                                # let the supervisor relaunch
        except Exception as e:
            # one bad cycle must NEVER end the day — log, beat, keep going
            write_heartbeat(date, 0, spot, "error", note=f"{type(e).__name__}: {e}")
            print(f"  ! sweep error (continuing): {type(e).__name__}: {e}")
            traceback.print_exc()
        # anchor cadence to wall-clock so spacing stays ~secs regardless of sweep duration
        next_t += secs
        remaining = next_t - time.monotonic()
        if remaining < 0:                        # sweep took longer than secs — resync
            if -remaining > secs:
                print(f"  (behind by {-remaining:.0f}s — resyncing cadence)")
            next_t = time.monotonic()
            remaining = 0
        if remaining > 0:
            try:
                ib.sleep(remaining) if ib.isConnected() else time.sleep(remaining)
            except Exception:
                time.sleep(remaining)
    try:
        ib.disconnect()
    except Exception:
        pass
    write_heartbeat(date, 0, spot, "stopped", note=f"clean stop {stop_hhmm} CT")
    print(f"done — {total_snaps} snapshots -> {p.relative_to(ROOT)}")
    try:
        validate_day(date, secs, stop_hhmm)
    except Exception as e:
        print(f"  (completeness check error: {e})")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--pct", type=float, default=1.25,
                    help="ROLLING strike-window half-width, %% of current spot "
                         "(1.25%% ~ 78 IB data lines; window re-centers as spot drifts)")
    ap.add_argument("--secs", type=int, default=10, help="snapshot cadence (s) — target; "
                    "a wide sweep may only achieve ~10-15s, which the anchored loop tolerates")
    ap.add_argument("--stop", default="15:00", help="stop time CT (HH:MM)")
    ap.add_argument("--mock", action="store_true", help="no IB — verify logic only")
    args = ap.parse_args()
    if args.mock:
        run_mock(args.pct)
    else:
        run_live(args.pct, args.secs, args.stop)


if __name__ == "__main__":
    main()
