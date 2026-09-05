"""Shadow daily max-loss monitor — OBSERVATIONAL ONLY (no executions, ever).

This script has NO IB connection and NO order path: it only READS the marks the
desk already writes (data/options_sim/marks.csv), reconstructs the live portfolio
P&L, and RECORDS what a daily circuit breaker WOULD have done. It never flattens
anything. Purpose: collect forward evidence on whether a -$X daily stop helps,
before anyone decides to arm a real one.

Levels are 1-LOT numbers (see stop_level_study.py for the derivation):
  WARN  -2000   heads-up ping
  STOP  -3000   the shadow trigger — logged + pinged as "would fire", not executed

Usage:
  --backfill            rebuild the full per-day shadow log from history
  (default, one pass)   update today's row + fire deduped pings; call every N min
  --loop --secs 120 --stop 15:05   run through the session (for a scheduled task)
"""
import argparse
import csv
import datetime as dt
import time
from pathlib import Path
from zoneinfo import ZoneInfo

import pandas as pd

CT = ZoneInfo("America/Chicago")
SIM = Path("data/options_sim")
MARKS = SIM / "marks.csv"
LOG = SIM / "shadow_stop_log.csv"
WARN, STOP = -2000, -3000
FIELDS = ["date", "n", "trough", "trough_ct", "crossed_warn", "warn_ct", "warn_fill",
          "crossed_stop", "stop_ct", "stop_fill", "end_pnl", "would_help", "day_swing",
          "mid_event", "vix", "updated_ct"]


def mid_session_event(day):
    """FOMC-type high-impact event that fires DURING the session (not the 8:30-ET
    pre-open batch). The 09:05 CT entry-wait does NOT protect against these, so they
    get extra attention. Returns 'Title HH:MM ET' or ''. Read from the gameplan."""
    import json as _json
    f = SIM / f"gameplan_{day.replace('-', '')}.json"
    if not f.exists():
        return ""
    try:
        cats = (_json.loads(f.read_text(encoding="utf-8")).get("gexlog") or {}).get("catalysts_today") or []
    except Exception:
        return ""
    best = None
    for c in cats:
        t, tm, imp = str(c.get("title", "")), str(c.get("time", "")), str(c.get("impact", ""))
        is_fed = any(k in t.lower() for k in ("fomc", "rate decision", "interest rate", "powell", "beige book"))
        mid = "11:00" <= tm <= "15:30"          # ET, RTH but past the open data batch
        if (is_fed or imp == "high") and mid:
            score = (2 if is_fed else 0) + (1 if imp == "high" else 0)
            if best is None or score > best[0]:
                best = (score, f"{t} {tm} ET")
    return best[1] if best else ""


def _now_ct():
    return dt.datetime.now(CT)


def portfolio_curve(day):
    """Intraday portfolio P&L series for `day` from marks (STMR excluded).
    A closed trade's last mark carries forward = its realized value."""
    if not MARKS.exists():
        return None
    m = pd.read_csv(MARKS)
    m = m[~m["trade_id"].astype(str).str.contains("stmr", case=False)]
    m["ts"] = pd.to_datetime(m["ts_et"], errors="coerce")
    m = m.dropna(subset=["ts"])
    m = m[m["ts"].dt.strftime("%Y-%m-%d") == day]
    if m.empty:
        return None
    m["unreal_pnl"] = pd.to_numeric(m["unreal_pnl"], errors="coerce")
    piv = m.pivot_table(index="ts", columns="trade_id", values="unreal_pnl", aggfunc="last")
    piv = piv.sort_index().ffill().fillna(0.0)
    vix = pd.to_numeric(m["vix"], errors="coerce").dropna()
    return piv.sum(axis=1), (round(vix.iloc[-1], 1) if len(vix) else None), m["trade_id"].nunique()


def row_for(day, final):
    """Build a shadow-log row for `day`. final=True when the day is closed."""
    res = portfolio_curve(day)
    if res is None:
        return None
    curve, vix, n = res
    trough = curve.min()
    tct = curve.idxmin().strftime("%H:%M")
    cur = curve.iloc[-1]
    warn_ct = stop_ct = warn_fill = stop_fill = ""
    below_w = curve[curve <= WARN]
    below_s = curve[curve <= STOP]
    # ACTUAL portfolio P&L at the moment DD first tripped the line = the realistic
    # flatten value (the mark is off the live option quotes). It's usually a touch
    # PAST the level (marks are ~2min apart), not exactly -level.
    if len(below_w):
        warn_ct = below_w.index[0].strftime("%H:%M")
        warn_fill = round(below_w.iloc[0])
    if len(below_s):
        stop_ct = below_s.index[0].strftime("%H:%M")
        stop_fill = round(below_s.iloc[0])
    help_txt = ""
    if final:
        help_txt = ("HELPED" if cur < stop_fill else "HURT") if stop_ct else "n/a (never triggered)"
    return {
        "date": day, "n": n, "trough": round(trough), "trough_ct": tct,
        "crossed_warn": bool(len(below_w)), "warn_ct": warn_ct, "warn_fill": warn_fill,
        "crossed_stop": bool(len(below_s)), "stop_ct": stop_ct, "stop_fill": stop_fill,
        "end_pnl": round(cur), "would_help": help_txt,
        "day_swing": round(curve.max() - curve.min()), "mid_event": mid_session_event(day),
        "vix": vix, "updated_ct": _now_ct().strftime("%H:%M:%S"),
    }


def _read_log():
    if not LOG.exists():
        return {}
    return {r["date"]: r for r in csv.DictReader(LOG.open())}


def _write_log(rows):
    with LOG.open("w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=FIELDS)
        w.writeheader()
        for d in sorted(rows):
            w.writerow(rows[d])


def backfill():
    if not MARKS.exists():
        print("no marks.csv"); return
    m = pd.read_csv(MARKS)
    m = m[~m["trade_id"].astype(str).str.contains("stmr", case=False)]
    m["day"] = pd.to_datetime(m["ts_et"], errors="coerce").dt.strftime("%Y-%m-%d")
    days = sorted(x for x in m["day"].dropna().unique())
    out = {}
    for d in days:
        r = row_for(d, final=True)
        if r:
            out[d] = r
    _write_log(out)
    fired = sum(1 for r in out.values() if r["crossed_stop"])
    helped = sum(1 for r in out.values() if r["would_help"] == "HELPED")
    print(f"backfilled {len(out)} days -> {LOG}")
    print(f"  -$3000 shadow stop would have fired {fired} time(s); HELPED {helped}, "
          f"HURT {sum(1 for r in out.values() if r['would_help']=='HURT')}")
    print(f"  worst intraday trough in log: {min(int(r['trough']) for r in out.values()):,}")


def alert(msg, key):
    try:
        from notify_telegram import send
        send(msg, level="warn", dedup_key=key, cooldown_s=6 * 3600)
    except Exception as e:
        print(f"(alert not sent: {e})")


def live_pass():
    day = _now_ct().strftime("%Y-%m-%d")
    r = row_for(day, final=False)
    if r is None:
        print(f"{day}: no marks yet"); return
    log = _read_log()
    prev = log.get(day, {})
    log[day] = r
    _write_log(log)
    cur = r["end_pnl"]
    print(f"{day} {r['updated_ct']} CT | portfolio {cur:+} | trough {r['trough']:+} @ {r['trough_ct']}"
          f" | warn={'Y' if r['crossed_warn'] else 'n'} stop={'Y' if r['crossed_stop'] else 'n'}")
    # deduped pings — fire once per condition per day
    if r.get("mid_event") and not prev.get("mid_event"):
        alert(f"⚑ Mid-session event today: {r['mid_event']}. The 09:05 entry-wait does NOT cover it — "
              f"watching intraday drawdown closely (observational).", key=f"midevent_{day}")
    if r["crossed_stop"] and str(prev.get("crossed_stop")) != "True":
        alert(f"🟡 SHADOW STOP would fire {day} at {r['stop_ct']} CT: portfolio {cur:+} (level {STOP}). "
              f"NOT executed — observational, collecting data.", key=f"shadow_stop_{day}")
    elif r["crossed_warn"] and str(prev.get("crossed_warn")) != "True":
        alert(f"🟠 Intraday P&L {cur:+} crossed the {WARN} watch line {day} at {r['warn_ct']} CT — "
              f"observing, no action.", key=f"shadow_warn_{day}")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--backfill", action="store_true")
    ap.add_argument("--loop", action="store_true")
    ap.add_argument("--secs", type=int, default=120)
    ap.add_argument("--stop", default="15:05")
    a = ap.parse_args()
    if a.backfill:
        backfill(); return
    if a.loop:
        hh, mm = map(int, a.stop.split(":"))
        while _now_ct().time() < dt.time(hh, mm):
            try:
                live_pass()
            except Exception as e:
                print(f"pass error: {e}")
            time.sleep(a.secs)
        # finalize today's row
        day = _now_ct().strftime("%Y-%m-%d")
        r = row_for(day, final=True)
        if r:
            log = _read_log(); log[day] = r; _write_log(log)
            print(f"finalized {day}: {r['would_help']}")
        return
    live_pass()


if __name__ == "__main__":
    main()
