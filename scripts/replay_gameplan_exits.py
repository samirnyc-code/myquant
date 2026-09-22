"""replay_gameplan_exits.py — reconstruct a day's missed desk entries AND replay the
LIVE exit rules against the real intraday path, using ThetaData per-leg NBBO.

Why this exists: on 2026-09-21 NT/gateway/spot-feed were down at the open, so the desk
booked nothing and the spot feed only recorded from 10:10 ET. But ThetaData has EVERY
leg's NBBO at EVERY minute of the session, so the day is fully reconstructable:

  1. ENTRY  — each gameplan vertical fires at its not_before (08:30 CT = 09:30 ET open);
              realistic credit = SELL short @ bid, BUY long @ ask (S113 worst-touch model).
  2. SPOT   — derived from ThetaData itself via put-call parity at 7650 (both C and P
              exist there): S = K + (C_mid - P_mid).  No spot feed needed.
  3. EXITS  — replays scripts/options_trigger_daemon.thesis_broken EXACTLY:
              (a) level acceptance: spot holds BEYOND the short strike >=10 min -> cut;
              (b) time stop 14:45 CT (15:45 ET) -> flat.
              (regime invalidation is inactive today: HVL is None + none of these setups
               are in PIN_SETUPS.)
  4. FILL   — close cost = BUY short @ ask, SELL long @ bid (worst-touch). Realistic only.
              4 executions/spread round-trip * $1.63.

Grid is capped at min(15:45 ET, now) — spreads still open at the cap are marked to now
and flagged. Writes data/options_log/replay_20260921_exits.json. READ-ONLY re: the book.

    python scripts/replay_gameplan_exits.py
    python scripts/replay_gameplan_exits.py --date 20260921 --entry-et 09:31 --step-min 2
"""
from __future__ import annotations
import argparse
import csv
import datetime as dt
import io
import json
import urllib.parse
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
V3 = "http://127.0.0.1:25503"
ROOT_SYM = "SPXW"

MULT = 100.0
FEE = 1.63                # $/contract/execution
MIN_CREDIT = 0.10         # sim's min_credit_abs
LEVEL_ACCEPT_MIN = 10     # DEFAULT_EXITS level_accept_mins
TIME_STOP_CT = "14:45"    # DEFAULT_EXITS time_stop (CT); ET = +1h in Sep
PARITY_K = 7650.0         # strike with BOTH a call and put in the plan -> spot via parity


def _at(expiry, strike, right, et_hms):
    q = urllib.parse.urlencode({
        "symbol": ROOT_SYM, "expiration": expiry, "strike": f"{float(strike):.3f}",
        "right": right, "start_date": expiry, "end_date": expiry,
        "time_of_day": et_hms, "format": "csv"})
    url = f"{V3}/v3/option/at_time/quote?{q}"
    try:
        raw = urllib.request.urlopen(url, timeout=30).read().decode()
    except Exception as e:
        return {"error": f"{type(e).__name__}: {e}"}
    rows = list(csv.DictReader(io.StringIO(raw)))
    if not rows:
        return {"error": "no data"}
    r = rows[-1]
    try:
        return {"bid": float(r["bid"]), "ask": float(r["ask"]), "stamp": r.get("timestamp")}
    except Exception:
        return {"error": f"bad row {r}"}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--date", default="20260921")
    ap.add_argument("--entry-et", default="09:31")   # 08:31 CT open (not_before 08:30)
    ap.add_argument("--step-min", type=int, default=2)
    a = ap.parse_args()
    exp = a.date

    cache = {}
    def leg(strike, right, et):
        k = (right, float(strike), et)
        if k not in cache:
            cache[k] = _at(exp, strike, right, et)
        return cache[k]
    def mid(strike, right, et):
        q = leg(strike, right, et)
        return None if "error" in q else (q["bid"] + q["ask"]) / 2.0
    def spot_at(et):
        c, p = mid(PARITY_K, "C", et), mid(PARITY_K, "P", et)
        return None if (c is None or p is None) else PARITY_K + (c - p)

    # time grid: entry -> min(15:45 ET time-stop, now ET)
    et_now = (dt.datetime.now() - dt.timedelta(hours=6))
    hh, mm = map(int, a.entry_et.split(":"))
    t0 = et_now.replace(hour=hh, minute=mm, second=0, microsecond=0)
    ts_h, ts_m = map(int, TIME_STOP_CT.split(":"))
    stop_et = et_now.replace(hour=ts_h + 1, minute=ts_m, second=0, microsecond=0)  # CT->ET
    ceiling = min(stop_et, et_now.replace(second=0, microsecond=0))
    grid = []
    t = t0
    while t <= ceiling:
        grid.append(t)
        t += dt.timedelta(minutes=a.step_min)
    entry_et = t0.strftime("%H:%M:%S")

    # spot path
    spath = [(g, spot_at(g.strftime("%H:%M:%S"))) for g in grid]
    spath = [(g, s) for g, s in spath if s is not None]

    gp = json.loads((ROOT / "data" / "options_sim" / f"gameplan_{a.date}.json").read_text())
    verts = []
    for tr in gp.get("triggers", []):
        s = tr.get("structure", {})
        if s.get("kind") == "vertical" and s.get("short") and s.get("long"):
            fatal = "above" if s["right"] == "C" else "below"
            verts.append((tr["id"], tr["name"], s["right"], float(s["short"]), float(s["long"]), fatal))

    def find_exit(short, fatal):
        """Replay thesis_broken: first time spot holds BEYOND short >=10min, else time-stop."""
        beyond_since = None
        for g, s in spath:
            beyond = (s > short) if fatal == "above" else (s < short)
            if not beyond:
                beyond_since = None
                continue
            if beyond_since is None:
                beyond_since = g
                continue
            if (g - beyond_since).total_seconds() / 60.0 >= LEVEL_ACCEPT_MIN:
                return g, "level_accepted", s
        # never accepted through the grid ceiling
        last_g, last_s = spath[-1]
        reached_stop = ceiling >= stop_et
        return (stop_et if reached_stop else last_g,
                "time_stop_1445CT" if reached_stop else "open_marked_to_now",
                last_s)

    print(f"replay {a.date} — entry {entry_et} ET (08:31 CT open) | grid {a.step_min}min -> "
          f"{ceiling.strftime('%H:%M')} ET | level-accept {LEVEL_ACCEPT_MIN}min + {TIME_STOP_CT}CT stop")
    if spath:
        print(f"  spot (parity@{PARITY_K:.0f}): {spath[0][1]:.1f} @ {entry_et}  ->  "
              f"{spath[-1][1]:.1f} @ {spath[-1][0].strftime('%H:%M')}  (min {min(s for _,s in spath):.1f} / "
              f"max {max(s for _,s in spath):.1f})")
    print(f"\n{'trigger':<9}{'structure':<22}{'entry_cr':>9}{'exit@':>8}{'reason':<20}"
          f"{'spot':>7}{'close':>8}{'PnL':>8}  take?")

    out, total = [], 0.0
    for tid, name, right, short, long, fatal in verts:
        se, le = leg(short, right, entry_et), leg(long, right, entry_et)
        if "error" in se or "error" in le:
            print(f"{tid:<9}{name[:21]:<22} entry NBBO error"); out.append({"id": tid, "error": True}); continue
        entry_cr = se["bid"] - le["ask"]                 # realistic worst-touch credit
        take = entry_cr >= MIN_CREDIT
        gx, reason, spot_x = find_exit(short, fatal)
        et_x = gx.strftime("%H:%M:%S")
        sx, lx = leg(short, right, et_x), leg(long, right, et_x)
        if "error" in sx or "error" in lx:
            print(f"{tid:<9}{name[:21]:<22} exit NBBO error"); out.append({"id": tid, "error": True}); continue
        close_cost = sx["ask"] - lx["bid"]               # realistic worst-touch buy-back
        pnl = (entry_cr - close_cost) * MULT - 4 * FEE   # 2 open + 2 close executions
        if take:
            total += pnl
        struct = f"{right} {short:.0f}/{long:.0f}"
        print(f"{tid:<9}{struct:<22}{entry_cr:>9.2f}{gx.strftime('%H:%M'):>8}{reason:<20}"
              f"{spot_x:>7.0f}{close_cost:>8.2f}{pnl:>8.0f}  {'YES' if take else 'no(<.10)'}")
        out.append({"id": tid, "name": name, "struct": struct, "entry_cr": round(entry_cr, 2),
                    "exit_et": et_x, "reason": reason, "spot_at_exit": round(spot_x, 1),
                    "close_cost": round(close_cost, 2), "pnl": round(pnl, 2), "taken": take})

    print(f"\n  TOTAL P&L (1-lot, taken trades only, realistic worst-touch fills, incl 4 fees/spread):  {total:+,.0f}")
    open_marked = [o for o in out if o.get("reason") == "open_marked_to_now"]
    if open_marked:
        print(f"  NOTE: {len(open_marked)} spread(s) still open at {ceiling.strftime('%H:%M')} ET (before the "
              f"{TIME_STOP_CT} CT stop) — marked to now; deep-OTM, will ride to the stop.")

    rep = {"date": a.date, "entry_et": entry_et, "grid_step_min": a.step_min,
           "ceiling_et": ceiling.strftime("%H:%M:%S"), "stop_et": stop_et.strftime("%H:%M:%S"),
           "level_accept_min": LEVEL_ACCEPT_MIN, "time_stop_ct": TIME_STOP_CT,
           "spot_open": round(spath[0][1], 1) if spath else None,
           "spot_last": round(spath[-1][1], 1) if spath else None,
           "verticals": out, "total_pnl": round(total, 2),
           "fill_model": "worst-touch (S113): sell short@bid/buy long@ask in, buy short@ask/sell long@bid out",
           "reconstructed_at": dt.datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
           "note": "READ-ONLY replay of live exit rules vs ThetaData intraday NBBO; NOT booked."}
    p = ROOT / "data" / "options_log" / f"replay_{a.date}_exits.json"
    p.write_text(json.dumps(rep, indent=1), encoding="utf-8")
    print(f"\nwrote {p} (report only — live book untouched)")


if __name__ == "__main__":
    main()
