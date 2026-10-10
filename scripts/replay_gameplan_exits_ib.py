"""replay_gameplan_exits_ib.py — IB-sourced sibling of replay_gameplan_exits.py.

Same reconstruction (entry at the open + live exit-rule replay) for a day the desk
missed, but sourced from IB Gateway's reqHistoricalData instead of ThetaData's
at_time/quote REST API — ThetaData's endpoint now requires a paid "value"
subscription we don't have (confirmed 2026-10-10: FREE tier returns
"Requesting an option endpoint requiring a value subscription").

VERIFIED before trusting any fill math (scratch probe against SPXW 7765P 2026-10-09,
390/390 1-min bars compared):
  - whatToShow='BID_ASK' bars: BA.high == max(ASK) EXACTLY (mean/max abs diff 0.0) and
    BA.low == min(BID) EXACTLY (mean/max abs diff 0.0) — but BA.open/close are NOT plain
    snapshots of BID.open/close (mean abs diff $0.05-0.09, max $1.05 across the 390 bars).
    They are some other averaged quantity, not a trustworthy point-in-time quote. We
    therefore do NOT use the combined BID_ASK series for fills.
  - Instead we request whatToShow='BID' and whatToShow='ASK' as two SEPARATE 1-min bar
    series per leg (unambiguous: a BID bar's OHLC is literally the bid-price path over
    that minute; an ASK bar's is literally the ask) and use each bar's .close as the
    point-in-time NBBO sample for that minute — the same "last quote at/before timestamp"
    semantics ThetaData's at_time/quote gave us. ONE reqHistoricalData call per
    leg-per-side covers the WHOLE day (durationStr="1 D", barSizeSetting="1 min"), so a
    ~10-vertical gameplan (20 unique legs) costs ~40 option requests total, not one call
    per grid timepoint.
  - SPX spot: IB serves the index directly (Index('SPX','CBOE'), whatToShow='TRADES',
    1-min, useRTH=True) — no put-call-parity trick needed (ThetaData had no direct index
    access). Cross-checked against postmortem_20261009.json's OHLC (open 7788.05 / high
    7821.18 / low 7781.25 / close 7811.52): IB's 1-min TRADES series gave open 7786.36 /
    high 7820.57 / low 7779.34 / close 7811.09 — all within ~1-2 points, consistent with
    1-min-bar vs tick-level OHLC granularity, not a data error.
  - IB historical bar timestamps for this login come back tz-aware in US/Central (i.e.
    already CT) — confirmed from real returned bars. All grid/lookup math here is done
    natively in CT; the schema's "_et" fields are produced by formatting CT+1h for display
    only, to keep the JSON schema IDENTICAL to the ThetaData script's output.

Same entry/exit/fill logic as replay_gameplan_exits.py: entry at the 08:31 CT open
(worst-touch: sell short@bid, buy long@ask); exit replays options_trigger_daemon's
thesis_broken (level-accept: spot holds beyond the short strike >=10min -> cut; else
14:45 CT time-stop); close worst-touch (buy short@ask, sell long@bid). The reconstructed
date is always a COMPLETED historical session here (not a live same-day replay), so the
grid ceiling is simply the 14:45 CT stop — same convention as replay_intraday_dd_breaker.py.

Writes data/options_log/replay_<date>_exits.json — SAME schema as the ThetaData script.
READ-ONLY re: the live book; never touches trades.parquet.

    python scripts/replay_gameplan_exits_ib.py --date 20261009
    python scripts/replay_gameplan_exits_ib.py --date 20261009 --entry-et 09:31 --step-min 2
"""
from __future__ import annotations
import argparse
import datetime as dt
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(Path(__file__).resolve().parent))
import ib_conn
from ib_async import Index, Option

MULT = 100.0
FEE = 1.63                # $/contract/execution
MIN_CREDIT = 0.10         # sim's min_credit_abs
LEVEL_ACCEPT_MIN = 10     # DEFAULT_EXITS level_accept_mins
TIME_STOP_CT = "14:45"    # DEFAULT_EXITS time_stop (CT)
PACING_SLEEP = 1.5        # s between reqHistoricalData calls (60 req / 10 min cap)
LOOKBACK_TOL_MIN = 5      # tolerance for "last quote at/before" when a minute is missing


def qualify_option(ib, expiry, strike, right):
    c = Option("SPX", expiry, float(strike), right, "SMART", tradingClass="SPXW",
               multiplier="100", currency="USD")
    q = ib.qualifyContracts(c)
    if not q:
        c = Option("SPX", expiry, float(strike), right, "CBOE", tradingClass="SPXW",
                   multiplier="100", currency="USD")
        q = ib.qualifyContracts(c)
    return q[0] if q else None


def fetch_side_series(ib, contract, expiry, side):
    """One reqHistoricalData call -> {naive CT datetime (minute): close price}."""
    bars = ib.reqHistoricalData(
        contract, endDateTime=f"{expiry}-20:00:00", durationStr="1 D",
        barSizeSetting="1 min", whatToShow=side, useRTH=True, formatDate=1)
    ib.sleep(PACING_SLEEP)
    return {b.date.replace(tzinfo=None, second=0, microsecond=0): b.close for b in bars}


def quote_at(bid_series, ask_series, target_ct):
    """Last known bid/ask at/before target_ct (tolerant of small gaps), else error dict."""
    for back in range(0, LOOKBACK_TOL_MIN + 1):
        k = target_ct - dt.timedelta(minutes=back)
        if k in bid_series and k in ask_series:
            return {"bid": bid_series[k], "ask": ask_series[k], "stamp": k.strftime("%H:%M:%S")}
    return {"error": f"no BID/ASK bar within {LOOKBACK_TOL_MIN}min of {target_ct.strftime('%H:%M:%S')} CT"}


def fmt_et(ct_dt):
    """Display-only: CT -> ET label (+1h), matching the ThetaData script's '_et' fields."""
    return (ct_dt + dt.timedelta(hours=1)).strftime("%H:%M:%S")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--date", default="20261009")
    ap.add_argument("--entry-et", default="09:31")   # 08:31 CT open (not_before 08:30)
    ap.add_argument("--step-min", type=int, default=2)
    a = ap.parse_args()
    expiry = a.date

    gp = (ROOT / "data" / "options_sim" / f"gameplan_{a.date}.json")
    gp = __import__("json").loads(gp.read_text())
    verts = []
    for tr in gp.get("triggers", []):
        s = tr.get("structure", {})
        if s.get("kind") == "vertical" and s.get("short") and s.get("long"):
            fatal = "above" if s["right"] == "C" else "below"
            verts.append((tr["id"], tr["name"], s["right"], float(s["short"]), float(s["long"]), fatal))

    legs_needed = sorted({(v[2], v[3]) for v in verts} | {(v[2], v[4]) for v in verts})

    # time grid, native CT (the historical date is a COMPLETED session)
    ref = dt.datetime.strptime(a.date, "%Y%m%d")
    hh, mm = map(int, a.entry_et.split(":"))
    t0_ct = ref.replace(hour=hh - 1, minute=mm, second=0, microsecond=0)   # ET -> CT
    ts_h, ts_m = map(int, TIME_STOP_CT.split(":"))
    stop_ct = ref.replace(hour=ts_h, minute=ts_m, second=0, microsecond=0)
    ceiling_ct = stop_ct
    grid = []
    t = t0_ct
    while t <= ceiling_ct:
        grid.append(t)
        t += dt.timedelta(minutes=a.step_min)
    entry_ct = t0_ct

    ib = ib_conn.connect()
    try:
        print(f"IB: fetching SPX index spot (1-min TRADES, {expiry})...")
        spx = Index("SPX", "CBOE", "USD")
        qspx = ib.qualifyContracts(spx)
        spx_bars = ib.reqHistoricalData(
            qspx[0], endDateTime=f"{expiry}-20:00:00", durationStr="1 D",
            barSizeSetting="1 min", whatToShow="TRADES", useRTH=True, formatDate=1)
        ib.sleep(PACING_SLEEP)
        spot_series = {b.date.replace(tzinfo=None, second=0, microsecond=0): b.close for b in spx_bars}

        print(f"IB: fetching BID+ASK 1-min series for {len(legs_needed)} legs "
              f"({len(legs_needed)*2} requests)...")
        leg_cache = {}
        for right, strike in legs_needed:
            c = qualify_option(ib, expiry, strike, right)
            if c is None:
                print(f"  {right}{strike:.0f}: COULD NOT QUALIFY CONTRACT")
                leg_cache[(right, strike)] = ({}, {})
                continue
            bid_s = fetch_side_series(ib, c, expiry, "BID")
            ask_s = fetch_side_series(ib, c, expiry, "ASK")
            leg_cache[(right, strike)] = (bid_s, ask_s)
            print(f"  {right}{strike:.0f}: {len(bid_s)} BID / {len(ask_s)} ASK bars")
    finally:
        ib.disconnect()

    def leg(strike, right, ct):
        bid_s, ask_s = leg_cache[(right, float(strike))]
        return quote_at(bid_s, ask_s, ct)

    def spot_at(ct):
        for back in range(0, LOOKBACK_TOL_MIN + 1):
            k = ct - dt.timedelta(minutes=back)
            if k in spot_series:
                return spot_series[k]
        return None

    spath = [(g, spot_at(g)) for g in grid]
    spath = [(g, s) for g, s in spath if s is not None]

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
        last_g, last_s = spath[-1]
        reached_stop = ceiling_ct >= stop_ct
        return (stop_ct if reached_stop else last_g,
                "time_stop_1445CT" if reached_stop else "open_marked_to_now",
                last_s)

    print(f"\nreplay {a.date} — entry {fmt_et(entry_ct)} ET (08:31 CT open) | grid "
          f"{a.step_min}min -> {fmt_et(ceiling_ct)} ET | level-accept {LEVEL_ACCEPT_MIN}min "
          f"+ {TIME_STOP_CT}CT stop  [source: IB historical]")
    if spath:
        print(f"  spot (IB SPX index): {spath[0][1]:.1f} @ {fmt_et(entry_ct)}  ->  "
              f"{spath[-1][1]:.1f} @ {fmt_et(spath[-1][0])}  (min {min(s for _, s in spath):.1f} "
              f"/ max {max(s for _, s in spath):.1f})")
    print(f"\n{'trigger':<9}{'structure':<22}{'entry_cr':>9}{'exit@':>8}{'reason':<20}"
          f"{'spot':>7}{'close':>8}{'PnL':>8}  take?")

    out, total = [], 0.0
    for tid, name, right, short, long, fatal in verts:
        se, le = leg(short, right, entry_ct), leg(long, right, entry_ct)
        if "error" in se or "error" in le:
            print(f"{tid:<9}{name[:21]:<22} entry NBBO error ({se.get('error') or le.get('error')})")
            out.append({"id": tid, "error": True})
            continue
        entry_cr = se["bid"] - le["ask"]                 # realistic worst-touch credit
        take = entry_cr >= MIN_CREDIT
        gx, reason, spot_x = find_exit(short, fatal)
        sx, lx = leg(short, right, gx), leg(long, right, gx)
        if "error" in sx or "error" in lx:
            print(f"{tid:<9}{name[:21]:<22} exit NBBO error ({sx.get('error') or lx.get('error')})")
            out.append({"id": tid, "error": True})
            continue
        close_cost = sx["ask"] - lx["bid"]               # realistic worst-touch buy-back
        pnl = (entry_cr - close_cost) * MULT - 4 * FEE   # 2 open + 2 close executions
        if take:
            total += pnl
        struct = f"{right} {short:.0f}/{long:.0f}"
        et_x = fmt_et(gx)
        print(f"{tid:<9}{struct:<22}{entry_cr:>9.2f}{et_x[:5]:>8}{reason:<20}"
              f"{spot_x:>7.0f}{close_cost:>8.2f}{pnl:>8.0f}  {'YES' if take else 'no(<.10)'}")
        out.append({"id": tid, "name": name, "struct": struct, "entry_cr": round(entry_cr, 2),
                    "exit_et": et_x, "reason": reason, "spot_at_exit": round(spot_x, 1),
                    "close_cost": round(close_cost, 2), "pnl": round(pnl, 2), "taken": take})

    print(f"\n  TOTAL P&L (1-lot, taken trades only, realistic worst-touch fills, incl 4 fees/spread):  {total:+,.0f}")
    open_marked = [o for o in out if o.get("reason") == "open_marked_to_now"]
    if open_marked:
        print(f"  NOTE: {len(open_marked)} spread(s) still open at {fmt_et(ceiling_ct)} ET (before the "
              f"{TIME_STOP_CT} CT stop) — marked to now; deep-OTM, will ride to the stop.")

    rep = {"date": a.date, "entry_et": fmt_et(entry_ct), "grid_step_min": a.step_min,
           "ceiling_et": fmt_et(ceiling_ct), "stop_et": fmt_et(stop_ct),
           "level_accept_min": LEVEL_ACCEPT_MIN, "time_stop_ct": TIME_STOP_CT,
           "spot_open": round(spath[0][1], 1) if spath else None,
           "spot_last": round(spath[-1][1], 1) if spath else None,
           "verticals": out, "total_pnl": round(total, 2),
           "fill_model": "worst-touch (S113): sell short@bid/buy long@ask in, buy short@ask/sell long@bid out",
           "reconstructed_at": dt.datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
           "note": "READ-ONLY replay of live exit rules vs IB historical BID/ASK 1-min bars "
                   "(ThetaData value-tier lapsed to free 2026-10-10); NOT booked."}
    import json
    p = ROOT / "data" / "options_log" / f"replay_{a.date}_exits.json"
    p.write_text(json.dumps(rep, indent=1), encoding="utf-8")
    print(f"\nwrote {p} (report only — live book untouched)")


if __name__ == "__main__":
    main()
