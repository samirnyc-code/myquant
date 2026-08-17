"""Forward 0DTE SPXW chain recorder — build our OWN intraday options dataset.

Every trading day, from the open to the close, snapshot the SPXW 0DTE NBBO for a
strike window around spot (every minute) and append to a dated CSV. This is the
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
from pathlib import Path
from zoneinfo import ZoneInfo

ROOT = Path(__file__).resolve().parents[1]
SIM = ROOT / "data" / "options_sim"
CT = ZoneInfo("America/Chicago")
ET = ZoneInfo("America/New_York")
STRIKE_STEP = 5


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

    REALTIME GUARD (2026-08-17): IB silently serves DELAYED/frozen quotes when realtime
    is denied (lines exhausted or not entitled) — it emits error 10090/10167 and the
    snapshot STILL fills, so without this the recorder would log stale prices as if live.
    We capture the contracts IB refuses realtime for and DROP them: better to write
    nothing (and let the completeness alarm page) than to poison the dataset with stale
    quotes. Returns ({(strike, right): (bid, ask)}, n_empty, n_delayed)."""
    denied = set()   # conId IB refused realtime for during this sweep -> untrustworthy
    def _on_err(reqId, code, msg, contract=None, *a):
        if code in (10090, 10091, 10167, 10197) and contract is not None:
            denied.add(contract.conId)
    ib.errorEvent += _on_err
    out, delayed, missed = {}, 0, list(contracts)
    try:
        for _ in range(2):
            pending, missed = missed, []
            for i in range(0, len(pending), batch):
                grp = pending[i:i + batch]
                tks = [(c, ib.reqMktData(c, "", snapshot=True)) for c in grp]
                ib.sleep(settle)
                for c, t in tks:
                    try:
                        ib.cancelMktData(c)   # snapshots auto-cancel; belt-and-suspenders
                    except Exception:
                        pass
                    if c.conId in denied:     # realtime refused -> DROP (never record delayed)
                        delayed += 1
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
    finally:
        ib.errorEvent -= _on_err
    return out, len(missed), delayed


def run_live(pct, secs, stop_hhmm):
    """Per-minute SNAPSHOT sweep of a rolling ±pct 0DTE strike window (+ pinned
    trade strikes). Snapshots — not persistent streams — so the recorder holds data
    lines only momentarily and COEXISTS with the live desk instead of exceeding the
    account's market-data-line quota (the 10090 line-contention that broke it)."""
    import ib_conn
    ib = ib_conn.connect(client_id=71)          # distinct from daemons (avoid clientId clash)
    ib.reqMarketDataType(1)
    date = now_ct().strftime("%Y%m%d")
    expiry = date                                # 0DTE: today's SPXW expiry
    spot = spot_now(ib)
    if spot is None:
        raise SystemExit("no spot available — is the feed live?")

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

    cache = {}                                   # (strike, right) -> qualified Contract
    stop = dt.time(*map(int, stop_hhmm.split(":")))
    p = out_path(date)
    print(f"recording ±{pct}% 0DTE SNAPSHOT sweep every {secs}s until {stop_hhmm} CT, exp {expiry}")
    while now_ct().time() < stop:
        spot = spot_now(ib) or spot
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
        msg = f"  {ts}  {len(rows)} realtime quotes"
        if delayed:
            msg += f"  ({delayed} DROPPED not-realtime)"
        if empty:
            msg += f"  ({empty} no quote)"
        print(msg)
        ib.sleep(secs)
    ib.disconnect()
    print(f"done — {p.relative_to(ROOT)}")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--pct", type=float, default=1.25,
                    help="ROLLING strike-window half-width, %% of current spot "
                         "(1.25%% ~ 78 IB data lines; window re-centers as spot drifts)")
    ap.add_argument("--secs", type=int, default=60, help="snapshot cadence (s)")
    ap.add_argument("--stop", default="15:00", help="stop time CT (HH:MM)")
    ap.add_argument("--mock", action="store_true", help="no IB — verify logic only")
    args = ap.parse_args()
    if args.mock:
        run_mock(args.pct)
    else:
        run_live(args.pct, args.secs, args.stop)


if __name__ == "__main__":
    main()
