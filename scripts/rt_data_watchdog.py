"""rt_data_watchdog.py — page FAST when IB real-time options data is lost.

Guards the 2026-08-17 failure: a competing login on the LIVE account (IBKR mobile
app / TWS elsewhere) steals the shared market-data session, the paper gateway drops
to DELAYED, and the whole options desk (spot feed, sim, 0DTE recorder) silently dies
with open 0DTE positions UNMANAGED. It ran ~4h before anyone noticed. This turns that
into a few-minute page.

Cheap primary signal: a FRESH parity spot in live.json proves real-time OPRA is
flowing (spot_feed can only compute it from real-time quotes). Only when that goes
stale during the session do we fire ONE IB probe to DIAGNOSE the cause and name it:
  10197        -> competing live session (close the IBKR app / TWS on the LIVE account)
  10090/10168  -> not entitled (check IB subscription / market-data agreement)
  can't connect-> gateway down
  clean quote  -> real-time actually OK (spot feed itself is the problem, not the data)
Deduped Telegram page, ESCALATED when open 0DTE positions exist. Runs inside the
5-min Alert Monitor pass (run_once) or standalone.

    python scripts/rt_data_watchdog.py
"""
from __future__ import annotations

import datetime as dt
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SIM = ROOT / "data" / "options_sim"
sys.path.insert(0, str(ROOT / "scripts"))
KEY = "rt_data"


def _in_session(now) -> bool:
    return now.weekday() < 5 and dt.time(8, 35) <= now.time() <= dt.time(15, 0)


def _live_fresh() -> bool:
    """A fresh parity spot == real-time OPRA is flowing (it can't be computed otherwise)."""
    f = SIM / "live.json"
    try:
        d = json.loads(f.read_text())
        if d.get("state") == "live" and d.get("spx"):
            age = dt.datetime.now().timestamp() - f.stat().st_mtime
            return age < 150
    except Exception:
        pass
    return False


def _open_0dte(day: str) -> int:
    try:
        import pandas as pd
        d = pd.read_parquet(ROOT / "data" / "options_log" / "trades.parquet")
        op = d[d.exit_dt.isna()]
        return int(sum(day in str(r.get("legs")) for _, r in op.iterrows()))
    except Exception:
        return 0


def _rough_spot(ib):
    try:
        d = json.loads((SIM / "live.json").read_text())
        if d.get("spx"):
            return float(d["spx"])
    except Exception:
        pass
    try:
        from ib_async import Index
        ib.reqMarketDataType(4)
        ix = ib.qualifyContracts(Index("SPX", "CBOE", "USD"))[0]
        t = ib.reqMktData(ix, "", snapshot=True)
        ib.sleep(3)
        ib.cancelMktData(ix)
        for v in (t.last, t.close):
            if v == v and v:
                return float(v)
    except Exception:
        pass
    return None


def probe(day: str):
    """Diagnose the data state. Returns (state, detail); state in ok/bad/unknown."""
    import ib_conn
    from ib_async import Option
    codes = {}
    try:
        ib = ib_conn.connect(client_id=120)
    except Exception as e:
        return "bad", f"cannot reach IB gateway 4002 ({e})"
    try:
        ib.errorEvent += lambda rid, code, msg, c=None, *a: codes.__setitem__(code, codes.get(code, 0) + 1)
        spot = _rough_spot(ib)
        if spot is None:
            return "unknown", "no spot to pick a probe strike"
        k = round(spot / 5) * 5
        cc = ib.qualifyContracts(Option("SPX", day, k, "C", "SMART", tradingClass="SPXW"))
        if not cc:
            return "unknown", f"could not qualify SPXW {k}C {day}"
        ib.reqMarketDataType(1)
        t = ib.reqMktData(cc[0], "", snapshot=True)
        ib.sleep(6)
        ib.cancelMktData(cc[0])
        if 10197 in codes:
            return "bad", "competing live session — close the IBKR app / TWS on the LIVE account"
        if 10090 in codes or 10168 in codes:
            return "bad", "real-time options data NOT entitled — check IB subscription / market-data agreement"
        got = (t.bid == t.bid and t.bid >= 0) or (t.ask == t.ask and t.ask >= 0)
        if got:
            return "ok", f"real-time OK (SPXW {k}C {t.bid}/{t.ask})"
        return "unknown", "no quote and no error (pre/post open?)"
    finally:
        try:
            ib.disconnect()
        except Exception:
            pass


def _paged() -> bool:
    try:
        import notify_telegram as tg
        return KEY in (json.loads(tg.SENT.read_text()) if tg.SENT.exists() else {})
    except Exception:
        return False


def run_once(verbose: bool = False) -> int:
    import pipeline_health as ph
    now = ph.chicago_now()
    if not _in_session(now):
        if verbose:
            print("off-session — skipping")
        return 0

    import notify_telegram as tg

    if _live_fresh():
        if _paged():                                  # was down, now recovered
            tg.clear_dedup(KEY)
            tg.send("recovered: real-time options data restored", level="ok")
        if verbose:
            print("OK — parity spot fresh (real-time flowing)")
        return 0

    # live.json stale during the session -> diagnose why
    state, detail = probe(now.strftime("%Y%m%d"))
    if state == "bad":
        n = _open_0dte(now.strftime("%Y%m%d"))
        esc = f" — {n} OPEN 0DTE POSITION(S) UNMANAGED" if n else ""
        tg.send(f"🔴 REAL-TIME DATA DOWN: {detail}{esc}", level="alert",
                dedup_key=KEY, cooldown_s=1800)
        print(f"BAD: {detail}{esc}")
        return 1
    if state == "ok":                                 # data fine, spot_feed is the problem
        if _paged():
            tg.clear_dedup(KEY)
            tg.send("recovered: real-time options data restored", level="ok")
        tg.send("⚠️ spot feed stale but real-time data IS live — spot_feed needs a kick",
                level="warn", dedup_key="spotfeed_only", cooldown_s=1800)
        print(f"data OK but spot feed stale: {detail}")
        return 0
    if verbose:
        print(f"{state}: {detail}")
    return 0


if __name__ == "__main__":
    sys.exit(run_once(verbose=True))
