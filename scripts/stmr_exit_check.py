"""Standalone near-close STMR exit check (S106 missed-exit fix).

WHY THIS EXISTS
  The STMR exit rule (first day the 15:59 spot closes back above SMA5 -> buy the
  BPS back) used to live ONLY inside options_sim_daemon.py, an all-day process that
  launches 08:28 CT and must survive to 15:59 ET to ever evaluate the exit. On
  2026-08-25 the desk came up late (gateway ~08:42 CT); the 08:28 daemon run died
  before the decision block, headless/silent (pythonw, no output capture), and the
  exit — which the rule says should have fired that day (spot 7679 > SMA5 7671) —
  was missed. The position sat open, unmanaged.

WHAT THIS DOES
  A lightweight, OBSERVABLE checker that needs only a ~1-minute connection near the
  close (the gateway is reliably up by mid-day), reusing the daemon's own tested
  signal + exit code:
    * realtime spot via SpotRig (put-call parity), session H/L from the day's tape
    * sig = signal_1559(...); exit_sig = spot(15:59) > SMA5
    * on exit_sig with open bps_stmr rows -> do_exits() (REAL = real buy-to-close,
      sim = NBBO window) — the SAME function the daemon uses
    * ALWAYS writes data/options_sim/stmr_exit_heartbeat.json + a decisions.csv row
    * Telegram alert on: exit fired, error, or no realtime spot
  Own lock port (49734) so it runs safely ALONGSIDE the main daemon; idempotent
  (driven by open_trades) so if the daemon already closed, this is a clean no-op.

RUN
  live (real close + sim write):  .venv/Scripts/python.exe scripts/stmr_exit_check.py
  dry  (no writes, no orders):    ... scripts/stmr_exit_check.py --now
  sim-only (no real IB order):    ... scripts/stmr_exit_check.py --no-live
  Scheduled ~14:57 CT via run_at_ct (belt-and-suspenders to the 15:59 daemon exit).
"""
from __future__ import annotations
import argparse
import datetime as dt
import json
import sys
from pathlib import Path

import options_sim_daemon as sd
import options_trade_log as tlog
import ib_conn

OUT = sd.OUT
CLIENT_ID = 78  # distinct from the daemon (default) and recorders (72/73)


def alert(msg, key="stmr_exit"):
    try:
        import notify_telegram as tg
        tg.send(msg, level="alert", dedup_key=key, cooldown_s=300)
    except Exception as e:
        print(f"(telegram failed: {e})")


def session_hl(spot):
    """Session H/L from today's underlying tape (K8 needs it; exit_sig does not)."""
    import csv
    sh = sl = spot
    uf = OUT / f"underlying_{sd.now_et():%Y%m%d}.csv"
    if uf.exists():
        try:
            vals = [float(r["und"]) for r in csv.DictReader(open(uf, newline="")) if r.get("und")]
            if vals:
                sh, sl = max(sh, *vals), min(sl, *vals)
        except Exception as e:
            print(f"! tape H/L reconstruct failed ({e}) — seeding from spot")
    return sh, sl


def write_heartbeat(**kw):
    kw["ts_et"] = sd.now_et().isoformat()
    (OUT / "stmr_exit_heartbeat.json").write_text(json.dumps(kw, indent=2))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--port", type=int, default=None, help="IB port (default env/4002 paper)")
    ap.add_argument("--now", action="store_true", help="dry-run: decide + print, no writes/orders")
    ap.add_argument("--no-live", action="store_true", help="sim close only, do NOT place the real IB order")
    a = ap.parse_args()
    dry = a.now
    place_real = not a.no_live and not dry

    # own lock so we can run alongside the all-day daemon (its lock is 49733)
    if not dry:
        import socket
        lock = socket.socket()
        try:
            lock.bind(("127.0.0.1", 49734))
        except OSError:
            print("another stmr_exit_check already holds the lock (49734) — exiting")
            return 0

    today = sd.now_et().date().isoformat()
    try:
        daily = sd.refresh_spx_daily()
        ib = None
        for attempt in range(3):
            try:
                ib = ib_conn.connect(port=a.port, client_id=CLIENT_ID)
                break
            except Exception as e:
                print(f"connect attempt {attempt + 1} failed: {e!r}")
                if attempt == 2:
                    raise
                import time
                time.sleep(20)
    except Exception as e:
        write_heartbeat(state="error", stage="connect", err=repr(e), open_before=None)
        alert(f"STMR exit check FAILED to connect {today}: {e!r} — exit NOT evaluated")
        print(f"FATAL connect: {e!r}")
        return 1

    try:
        spx, rspot = sd.rough_spot(ib)
        chain = sd.get_chain(ib, spx)
        ib.reqMarketDataType(1)  # OPRA realtime (the daemon gets this via open_put_ladder, which we skip)
        rig = sd.SpotRig(ib, chain, rspot)
        ib.sleep(10)
        spot = rig.spot()
        if spot is None:
            write_heartbeat(state="error", stage="spot", spot=None, open_before=len(tlog.open_trades(sd.STRATEGY)))
            alert(f"STMR exit check {today}: NO realtime spot (OPRA) — exit NOT evaluated, positions left open")
            print("! no realtime spot — cannot evaluate the causal exit")
            return 1

        sh, sl = session_hl(spot)
        sig = sd.signal_1559(daily, spot, sh, sl, today)
        opens = tlog.open_trades(sd.STRATEGY)
        print(f"\n=== {today} STMR EXIT-ONLY CHECK ({sd.now_et():%H:%M} ET) ===\n"
              f"spot {sig['spot']:.2f}  SMA5 {sig['sma5']}  EXIT signal: {sig['exit_sig']}  "
              f"open trades: {len(opens)}  (dry={dry})")

        if not dry:  # don't pollute the causal decision log with pre-close dry reads
            sd.append_decision({"date": today, "ts": sd.now_et().strftime("%H:%M:%S"), **sig,
                                "sess_h": round(sh, 2), "sess_l": round(sl, 2),
                                "open_trades": len(opens), "sampled_from": "exit-only", "note": "exit-only"})
        sd.settle_expired(daily, today, dry)

        closed = 0
        if sig["exit_sig"] and len(opens):
            closed = sd.do_exits(ib, chain, {}, opens, today, place_real, dry)
            print(f"exit fired — closed {closed}/{len(opens)}")

        write_heartbeat(state="ok", spot=round(sig["spot"], 2), sma5=sig["sma5"],
                        exit_sig=sig["exit_sig"], open_before=len(opens), closed=closed, dry=dry)
        if sig["exit_sig"] and len(opens) and not dry:
            alert(f"STMR exit FIRED {today}: spot {sig['spot']:.2f} > SMA5 {sig['sma5']} "
                  f"— closed {closed}/{len(opens)} bps_stmr", key="stmr_exit_fired")
        return 0
    except Exception as e:
        write_heartbeat(state="error", stage="run", err=repr(e))
        alert(f"STMR exit check ERROR {today}: {e!r} — verify positions manually")
        print(f"FATAL run: {e!r}")
        return 1
    finally:
        try:
            ib.disconnect()
        except Exception:
            pass


if __name__ == "__main__":
    sys.exit(main())
