"""Standalone near-close STMR decision — the SOLE STMR entry+exit runner (S106).

WHY THIS EXISTS
  The STMR rule (K8<15 & spot>SMA100 -> sell a 14-DTE BPS; exit the first day the
  15:59 spot closes back above SMA5) used to live ONLY inside options_sim_daemon.py,
  an all-day process that launches 08:28 CT and must survive to 15:59 ET to ever
  decide. That process failed silently for weeks (headless pythonw, res=1, no output
  captured) — on 2026-08-25 it missed a live exit outright. The daemon runs all day
  for ONE reason: to accumulate the session High/Low the K8 stochastic needs — but
  that H/L is ALSO recorded independently in underlying_YYYYMMDD.csv, so the fragile
  6.5-hour process is unnecessary.

WHAT THIS DOES
  A lightweight, OBSERVABLE decision that needs only a ~1-minute connection near
  15:59 ET (the gateway is reliably up by mid-day), reusing the daemon's own tested
  signal + entry + exit code:
    * realtime spot via SpotRig (put-call parity); session H/L from the day's tape
    * sig = signal_1559(...): K8, SMA100, SMA5 -> fire (entry) + exit_sig (exit)
    * exit_sig & open bps_stmr  -> do_exits()  (REAL buy-to-close / sim NBBO window)
    * fire                      -> do_entry()  (sim row + real IB paper row)
    * ALWAYS writes stmr_exit_heartbeat.json + a decisions.csv row
    * Telegram alert on: any action (entry/exit), error, or no realtime spot
  Own lock port (49734); idempotent (driven by open_trades). Replaces the daemon's
  decision — schedule this at 15:59 ET (14:59 CT) and DISABLE MyQuant Sim Daemon.

RUN
  live (entry+exit, real+sim): .venv/Scripts/python.exe scripts/stmr_exit_check.py
  dry  (no writes, no orders): ... scripts/stmr_exit_check.py --now
  sim-only (no real IB order): ... scripts/stmr_exit_check.py --no-live
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
        import time
        # 14:59 CT is peak desk contention (recorders/mirror/trigger all still up, shutting
        # down ~15:00-15:05) — a single connect can TIMEOUT there (9/1 missed a run that way).
        # Retry hard like the recorder's connect_with_retry (~4 min window) so a busy-gateway
        # blip can't skip the decision; the read still lands well inside the 15:59-16:15 window.
        ATTEMPTS = 12
        for attempt in range(ATTEMPTS):
            try:
                ib = ib_conn.connect(port=a.port, client_id=CLIENT_ID)
                break
            except Exception as e:
                print(f"connect attempt {attempt + 1}/{ATTEMPTS} failed: {e!r}")
                if attempt == ATTEMPTS - 1:
                    raise
                time.sleep(15)
    except Exception as e:
        write_heartbeat(state="error", stage="connect", err=repr(e), open_before=None)
        alert(f"STMR decision FAILED to connect {today}: {e!r} — entry/exit NOT evaluated")
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
            alert(f"STMR decision {today}: NO realtime spot (OPRA) — entry/exit NOT evaluated")
            print("! no realtime spot — cannot evaluate the causal decision")
            return 1

        sh, sl = session_hl(spot)
        sig = sd.signal_1559(daily, spot, sh, sl, today)
        tags = sd.regime_tags(daily, spot, today)
        opens = tlog.open_trades(sd.STRATEGY)
        print(f"\n=== {today} STMR DECISION ({sd.now_et():%H:%M} ET) ===\n"
              f"spot {sig['spot']:.2f}  K8 {sig['k8']}  SMA100 {sig['sma100']}  SMA5 {sig['sma5']}\n"
              f"ENTRY fire: {sig['fire']}   EXIT signal: {sig['exit_sig']}   open: {len(opens)}  (dry={dry})")

        if not dry:  # don't pollute the causal decision log with pre-close dry reads
            sd.append_decision({"date": today, "ts": sd.now_et().strftime("%H:%M:%S"), **sig,
                                "sess_h": round(sh, 2), "sess_l": round(sl, 2),
                                "open_trades": len(opens), "sampled_from": "decision", "note": "decision"})
        sd.settle_expired(daily, today, dry)

        # exits first (frees collateral), then entry — same order as the daemon
        closed = 0
        if sig["exit_sig"] and len(opens):
            closed = sd.do_exits(ib, chain, {}, opens, today, place_real, dry)
            print(f"exit fired — closed {closed}/{len(opens)}")

        entered = None
        if sig["fire"]:
            expiry = sd.pick_expiry(chain)
            tickers = sd.open_put_ladder(ib, chain, expiry, spot)
            ib.sleep(10)  # let the ladder's NBBO + modelGreeks.delta populate before pick_legs
            entered = sd.do_entry(ib, chain, tickers, expiry, sig, tags, spot, today, place_real, dry)

        write_heartbeat(state="ok", spot=round(sig["spot"], 2), k8=sig["k8"], sma5=sig["sma5"],
                        fire=sig["fire"], exit_sig=sig["exit_sig"], open_before=len(opens),
                        closed=closed, entered=entered, dry=dry)
        acted = (sig["exit_sig"] and len(opens)) or sig["fire"]
        if acted and not dry:
            parts = []
            if sig["exit_sig"] and len(opens):
                parts.append(f"EXIT closed {closed}/{len(opens)}")
            if sig["fire"]:
                parts.append(f"ENTRY {'placed ' + entered if entered else 'FIRED but not placed'}")
            alert(f"STMR {today}: " + "; ".join(parts) +
                  f"  (spot {sig['spot']:.2f} K8 {sig['k8']} SMA5 {sig['sma5']})", key="stmr_decision")
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
