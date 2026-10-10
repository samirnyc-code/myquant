"""replay_intraday_dd_breaker_ib.py — IB-sourced sibling of replay_intraday_dd_breaker.py.

Same intraday equity curve / max-DD / circuit-breaker replay (companion to
replay_gameplan_exits_ib.py), sourced from IB Gateway's reqHistoricalData instead of
ThetaData's at_time/quote REST API (lapsed to a free tier, see replay_gameplan_exits_ib.py's
docstring for the full BID_ASK-field-mapping verification and SPX-index-spot rationale —
same method here: separate whatToShow='BID'/'ASK' 1-min series per leg, used via each bar's
.close as the point-in-time NBBO; SPX index TRADES 1-min bars for spot).

Method (portfolio-level, 1 book) — identical to the ThetaData version:
  - each taken vertical enters at the open (08:31 CT = 09:31 ET), realistic worst-touch;
  - exits replay options_trigger_daemon.thesis_broken (level-accept >=10min + 14:45 CT stop);
  - at every step-min grid point, each spread is marked:
        open  -> MTM = (entry_cr - close_cost_t)*100 - 2*FEE   (entry fees only)
        closed-> realized = (entry_cr - exit_cost)*100 - 4*FEE  (round-trip fees)
  - cumulative(t) = sum over spreads -> the intraday equity curve.
  - max intraday DD = trough of cumulative(t) AND peak->trough (both reported).
  - circuit breaker (cap X): the FIRST t where cumulative(t) <= -X, flatten every still
    open spread at t (round-trip fees). The day's P&L = cumulative-at-flatten.

Writes data/options_log/replay_<date>_dd_breaker.json + _curve.csv — SAME schema as the
ThetaData script. READ-ONLY re: the book.

    python scripts/replay_intraday_dd_breaker_ib.py --date 20261009
"""
from __future__ import annotations
import argparse
import csv
import datetime as dt
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(Path(__file__).resolve().parent))
import ib_conn
from ib_async import Index, Option

MULT, FEE, MIN_CREDIT = 100.0, 1.63, 0.10
LEVEL_ACCEPT_MIN, TIME_STOP_CT = 10, "14:45"
BREAKER_CAPS = (2000.0, 3000.0)
PACING_SLEEP = 1.5
LOOKBACK_TOL_MIN = 5


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
    bars = ib.reqHistoricalData(
        contract, endDateTime=f"{expiry}-20:00:00", durationStr="1 D",
        barSizeSetting="1 min", whatToShow=side, useRTH=True, formatDate=1)
    ib.sleep(PACING_SLEEP)
    return {b.date.replace(tzinfo=None, second=0, microsecond=0): b.close for b in bars}


def quote_at(bid_series, ask_series, target_ct):
    for back in range(0, LOOKBACK_TOL_MIN + 1):
        k = target_ct - dt.timedelta(minutes=back)
        if k in bid_series and k in ask_series:
            return {"bid": bid_series[k], "ask": ask_series[k]}
    return {"error": f"no BID/ASK bar within {LOOKBACK_TOL_MIN}min of {target_ct.strftime('%H:%M:%S')} CT"}


def fmt_et(ct_dt):
    return (ct_dt + dt.timedelta(hours=1)).strftime("%H:%M:%S")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--date", default="20261009")
    ap.add_argument("--entry-et", default="09:31")
    ap.add_argument("--step-min", type=int, default=2)
    a = ap.parse_args()
    expiry = a.date

    gp = json.loads((ROOT / "data" / "options_sim" / f"gameplan_{a.date}.json").read_text())
    verts = []
    for tr in gp.get("triggers", []):
        s = tr.get("structure", {})
        if s.get("kind") == "vertical" and s.get("short") and s.get("long"):
            fatal = "above" if s["right"] == "C" else "below"
            verts.append({"id": tr["id"], "right": s["right"], "short": float(s["short"]),
                          "long": float(s["long"]), "fatal": fatal})

    legs_needed = sorted({(v["right"], v["short"]) for v in verts} | {(v["right"], v["long"]) for v in verts})

    ref = dt.datetime.strptime(a.date, "%Y%m%d")
    hh, mm = map(int, a.entry_et.split(":"))
    t0_ct = ref.replace(hour=hh - 1, minute=mm, second=0, microsecond=0)
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
    finally:
        ib.disconnect()

    def leg(strike, right, ct):
        bid_s, ask_s = leg_cache[(right, float(strike))]
        return quote_at(bid_s, ask_s, ct)

    def close_cost(short, long, right, ct):
        s, l = leg(short, right, ct), leg(long, right, ct)
        if "error" in s or "error" in l:
            return None
        return s["ask"] - l["bid"]

    def spot_at(ct):
        for back in range(0, LOOKBACK_TOL_MIN + 1):
            k = ct - dt.timedelta(minutes=back)
            if k in spot_series:
                return spot_series[k]
        return None

    spath = {g: spot_at(g) for g in grid}
    spath = {g: s for g, s in spath.items() if s is not None}
    grid = [g for g in grid if g in spath]

    for v in verts:
        se, le = leg(v["short"], v["right"], entry_ct), leg(v["long"], v["right"], entry_ct)
        if "error" in se or "error" in le:
            v["entry_cr"], v["taken"] = None, False
            continue
        v["entry_cr"] = se["bid"] - le["ask"]
        v["taken"] = v["entry_cr"] >= MIN_CREDIT
        beyond_since, exit_g = None, None
        for g in grid:
            s = spath[g]
            beyond = (s > v["short"]) if v["fatal"] == "above" else (s < v["short"])
            if not beyond:
                beyond_since = None
                continue
            if beyond_since is None:
                beyond_since = g
                continue
            if (g - beyond_since).total_seconds() / 60.0 >= LEVEL_ACCEPT_MIN:
                exit_g = g
                v["exit_reason"] = "level_accepted"
                break
        if exit_g is None:
            exit_g = grid[-1]
            v["exit_reason"] = "time_stop_1445CT" if ceiling_ct >= stop_ct else "open_marked_to_now"
        v["exit_g"] = exit_g
        v["exit_cost"] = close_cost(v["short"], v["long"], v["right"], exit_g)

    taken = [v for v in verts if v["taken"]]

    curve = []
    for g in grid:
        cum = 0.0
        for v in taken:
            if g < v["exit_g"]:
                cc = close_cost(v["short"], v["long"], v["right"], g)
                if cc is None:
                    continue
                cum += (v["entry_cr"] - cc) * MULT - 2 * FEE
            else:
                cum += (v["entry_cr"] - v["exit_cost"]) * MULT - 4 * FEE
        curve.append((g, spath[g], cum))

    final_pnl = curve[-1][2] if curve else 0.0
    trough_g, trough_spot, trough = min(curve, key=lambda r: r[2])
    run_peak, p2t_dd, p2t_g = -1e9, 0.0, None
    for g, s, c in curve:
        run_peak = max(run_peak, c)
        if run_peak - c > p2t_dd:
            p2t_dd = run_peak - c
            p2t_g = g

    breakers = {}
    for cap in BREAKER_CAPS:
        trig_g = None
        for g, s, c in curve:
            if c <= -cap:
                trig_g = g
                break
        if trig_g is None:
            breakers[int(cap)] = {"triggered": False, "pnl": round(final_pnl, 2),
                                  "note": f"never reached -{cap:,.0f} intraday"}
        else:
            pnl = 0.0
            for v in taken:
                if trig_g < v["exit_g"]:
                    cc = close_cost(v["short"], v["long"], v["right"], trig_g)
                    pnl += (v["entry_cr"] - cc) * MULT - 4 * FEE
                else:
                    pnl += (v["entry_cr"] - v["exit_cost"]) * MULT - 4 * FEE
            breakers[int(cap)] = {"triggered": True, "at": fmt_et(trig_g),
                                  "spot": round(spath[trig_g], 1), "pnl": round(pnl, 2)}

    print(f"intraday DD + breakers {a.date} | entry {fmt_et(entry_ct)} ET | grid {a.step_min}min -> "
          f"{fmt_et(ceiling_ct)} ET | {len(taken)} taken spreads  [source: IB historical]")
    print(f"  spot {curve[0][1]:.1f} -> {curve[-1][1]:.1f}")
    print(f"  FINAL P&L:            {final_pnl:>+9,.0f}")
    print(f"  intraday TROUGH (worst cumulative):  {trough:>+9,.0f}  @ {fmt_et(trough_g)} ET "
          f"(spot {trough_spot:.0f})")
    print(f"  peak->trough max DD:  {p2t_dd:>9,.0f}  (trough @ {fmt_et(p2t_g) if p2t_g else '-'} ET)")
    print(f"\n  CIRCUIT BREAKERS (real intraday-path flatten):")
    for cap in BREAKER_CAPS:
        b = breakers[int(cap)]
        if b["triggered"]:
            print(f"    -${int(cap):,}: TRIGGERED @ {b['at']} ET (spot {b['spot']:.0f}) -> day P&L {b['pnl']:+,.0f}")
        else:
            print(f"    -${int(cap):,}: not triggered ({b['note']}) -> day P&L {b['pnl']:+,.0f}")

    curve_csv = ROOT / "data" / "options_log" / f"replay_{a.date}_curve.csv"
    with open(curve_csv, "w", newline="") as f:
        w = csv.writer(f)
        w.writerow(["et", "spot", "cum_pnl"])
        for g, s, c in curve:
            w.writerow([fmt_et(g), round(s, 2), round(c, 2)])

    rep = {"date": a.date, "entry_et": fmt_et(entry_ct), "grid_step_min": a.step_min,
           "final_pnl": round(final_pnl, 2),
           "intraday_trough": round(trough, 2), "trough_at_et": fmt_et(trough_g),
           "intraday_dd_peak_to_trough": round(p2t_dd, 2),
           "breaker_2k": breakers[2000], "breaker_3k": breakers[3000],
           "spot_open": round(curve[0][1], 1) if curve else None,
           "spot_close": round(curve[-1][1], 1) if curve else None,
           "fill_model": "worst-touch (S113)", "reconstructed": True,
           "note": "READ-ONLY intraday-path DD + Stage-2 circuit-breaker replay vs IB historical "
                   "BID/ASK 1-min bars (ThetaData value-tier lapsed to free 2026-10-10); NOT booked."}
    out = ROOT / "data" / "options_log" / f"replay_{a.date}_dd_breaker.json"
    out.write_text(json.dumps(rep, indent=1), encoding="utf-8")
    print(f"\nwrote {out}\nwrote {curve_csv}")


if __name__ == "__main__":
    main()
