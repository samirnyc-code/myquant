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
            return float(rough_spot(ib))
        except Exception:
            pass
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


def run_live(pct, secs, stop_hhmm):
    """ROLLING window: ±pct around CURRENT spot, re-centered as price drifts.

    Why rolling (2026-08-04): our entries are struck at the open, but the dataset
    must also support retro-testing LATER entry times — which needs quotes around
    wherever spot is at that moment. A window frozen at the open misses those
    strikes after a trend move; a rolling one covers them with ~80 bounded lines
    (new strikes subscribe as they come into range, far ones unsubscribe)."""
    import ib_conn
    from ib_async import Option
    ib = ib_conn.connect(client_id=71)          # distinct from daemons (avoid clientId clash)
    ib.reqMarketDataType(1)
    date = now_ct().strftime("%Y%m%d")
    expiry = date                                # 0DTE: today's SPXW expiry
    spot = spot_now(ib)
    if spot is None:
        raise SystemExit("no spot available — is the feed live?")

    tick = {}                                    # (strike, right) -> streaming ticker

    def retune(center):
        """Subscribe strikes inside ±pct of `center`; drop ones that left."""
        want = set(strike_window(center, pct))
        have = {k for k, _ in tick}
        for k in sorted(have - want):
            for r in ("P", "C"):
                t = tick.pop((k, r), None)
                if t is not None:
                    try:
                        ib.cancelMktData(t.contract)
                    except Exception:
                        pass
        new = sorted(want - have)
        if new:
            cs = [Option("SPX", expiry, k, r, "SMART", tradingClass="SPXW")
                  for k in new for r in ("P", "C")]
            for c in ib.qualifyContracts(*cs):
                if c and c.conId:
                    tick[(c.strike, c.right)] = ib.reqMktData(c, "", snapshot=False)
            ib.sleep(4)
        return len(new)

    retune(spot)
    center = spot
    print(f"recording ±{pct}% ROLLING window around spot ({len(tick)} lines), "
          f"exp {expiry}, every {secs}s until {stop_hhmm} CT")

    stop = dt.time(*map(int, stop_hhmm.split(":")))
    p = out_path(date)
    while now_ct().time() < stop:
        spot = spot_now(ib) or spot
        # re-center once spot drifts >20% of the window from the current center
        if abs(spot - center) > center * pct / 100.0 * 0.20:
            n = retune(spot)
            center = spot
            if n:
                print(f"  window rolled to {center:.0f} (+{n} strikes)")
        ts = dt.datetime.now(ET).strftime("%Y-%m-%d %H:%M:%S")
        rows = []
        for (k, r), t in tick.items():
            b, a = t.bid, t.ask
            b = b if (b == b and b >= 0) else ""
            a = a if (a == a and a >= 0) else ""
            rows.append([ts, round(spot, 2), expiry, k, r, b, a])
        append_rows(p, rows)
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
