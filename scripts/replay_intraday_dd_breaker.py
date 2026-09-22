"""replay_intraday_dd_breaker.py — intraday equity curve, max intraday drawdown, and
2k/3k circuit-breaker P&L for a reconstructed desk day (companion to
replay_gameplan_exits.py). Same inputs and fill model; adds the intraday path.

Method (portfolio-level, 1 book):
  - each taken vertical enters at the open (08:31 CT = 09:31 ET), realistic worst-touch;
  - exits replay options_trigger_daemon.thesis_broken (level-accept >=10min + 14:45 CT stop);
  - at every 2-min grid point, each spread is marked:
        open  -> MTM = (entry_cr - close_cost_t)*100 - 2*FEE   (entry fees only)
        closed-> realized = (entry_cr - exit_cost)*100 - 4*FEE  (round-trip fees)
  - cumulative(t) = sum over spreads  -> the intraday equity curve.
  - max intraday DD = trough of cumulative(t) AND peak->trough (both reported).
  - circuit breaker (cap X): the FIRST t where cumulative(t) <= -X, flatten every still
    open spread at t (round-trip fees). The day's P&L = cumulative-at-flatten. This is the
    Stage-2 (real intraday path) definition, not the Stage-1 clip-final approximation.

Writes data/options_log/replay_<date>_dd_breaker.json + _curve.csv. READ-ONLY re: the book.
    python scripts/replay_intraday_dd_breaker.py
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
MULT, FEE, MIN_CREDIT = 100.0, 1.63, 0.10
LEVEL_ACCEPT_MIN, TIME_STOP_CT, PARITY_K = 10, "14:45", 7650.0
BREAKER_CAPS = (2000.0, 3000.0)


def _at(expiry, strike, right, et_hms):
    q = urllib.parse.urlencode({"symbol": ROOT_SYM, "expiration": expiry,
        "strike": f"{float(strike):.3f}", "right": right, "start_date": expiry,
        "end_date": expiry, "time_of_day": et_hms, "format": "csv"})
    try:
        raw = urllib.request.urlopen(f"{V3}/v3/option/at_time/quote?{q}", timeout=30).read().decode()
    except Exception as e:
        return {"error": f"{type(e).__name__}: {e}"}
    rows = list(csv.DictReader(io.StringIO(raw)))
    if not rows:
        return {"error": "no data"}
    r = rows[-1]
    try:
        return {"bid": float(r["bid"]), "ask": float(r["ask"])}
    except Exception:
        return {"error": f"bad row {r}"}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--date", default="20260921")
    ap.add_argument("--entry-et", default="09:31")
    ap.add_argument("--step-min", type=int, default=2)
    a = ap.parse_args()
    exp = a.date

    cache = {}
    def leg(strike, right, et):
        k = (right, float(strike), et)
        if k not in cache:
            cache[k] = _at(exp, strike, right, et)
        return cache[k]
    def close_cost(short, long, right, et):     # worst-touch buy-back of a sold spread
        s, l = leg(short, right, et), leg(long, right, et)
        if "error" in s or "error" in l:
            return None
        return s["ask"] - l["bid"]
    def spot_at(et):
        c, p = leg(PARITY_K, "C", et), leg(PARITY_K, "P", et)
        if "error" in c or "error" in p:
            return None
        return PARITY_K + ((c["bid"] + c["ask"]) / 2 - (p["bid"] + p["ask"]) / 2)

    # anchor the grid to the TRADE DATE (a completed session), full open -> 14:45 CT stop.
    # (ThetaData at_time uses HH:MM:SS + the hardcoded expiry, so the calendar date of these
    #  datetimes is only used to build the grid, never sent in the query.)
    ref = dt.datetime.strptime(a.date, "%Y%m%d")
    hh, mm = map(int, a.entry_et.split(":"))
    t0 = ref.replace(hour=hh, minute=mm, second=0, microsecond=0)
    ts_h, ts_m = map(int, TIME_STOP_CT.split(":"))
    stop_et = ref.replace(hour=ts_h + 1, minute=ts_m, second=0, microsecond=0)  # CT->ET
    ceiling = stop_et
    grid = []
    t = t0
    while t <= ceiling:
        grid.append(t); t += dt.timedelta(minutes=a.step_min)
    entry_et = t0.strftime("%H:%M:%S")

    spath = {g: spot_at(g.strftime("%H:%M:%S")) for g in grid}
    spath = {g: s for g, s in spath.items() if s is not None}
    grid = [g for g in grid if g in spath]

    gp = json.loads((ROOT / "data" / "options_sim" / f"gameplan_{a.date}.json").read_text())
    verts = []
    for tr in gp.get("triggers", []):
        s = tr.get("structure", {})
        if s.get("kind") == "vertical" and s.get("short") and s.get("long"):
            fatal = "above" if s["right"] == "C" else "below"
            verts.append({"id": tr["id"], "right": s["right"], "short": float(s["short"]),
                          "long": float(s["long"]), "fatal": fatal})

    # per-spread: entry credit, taken?, exit (time,reason,cost)
    for v in verts:
        se, le = leg(v["short"], v["right"], entry_et), leg(v["long"], v["right"], entry_et)
        v["entry_cr"] = se["bid"] - le["ask"]
        v["taken"] = v["entry_cr"] >= MIN_CREDIT
        beyond_since, exit_g = None, None
        for g in grid:
            s = spath[g]
            beyond = (s > v["short"]) if v["fatal"] == "above" else (s < v["short"])
            if not beyond:
                beyond_since = None; continue
            if beyond_since is None:
                beyond_since = g; continue
            if (g - beyond_since).total_seconds() / 60.0 >= LEVEL_ACCEPT_MIN:
                exit_g = g; v["exit_reason"] = "level_accepted"; break
        if exit_g is None:
            exit_g = grid[-1]
            v["exit_reason"] = "time_stop_1445CT" if ceiling >= stop_et else "open_marked_to_now"
        v["exit_g"] = exit_g
        v["exit_cost"] = close_cost(v["short"], v["long"], v["right"], exit_g.strftime("%H:%M:%S"))

    taken = [v for v in verts if v["taken"]]

    # intraday equity curve
    curve = []
    for g in grid:
        et = g.strftime("%H:%M:%S")
        cum = 0.0
        for v in taken:
            if g < v["exit_g"]:
                cc = close_cost(v["short"], v["long"], v["right"], et)
                if cc is None:
                    continue
                cum += (v["entry_cr"] - cc) * MULT - 2 * FEE           # open, entry fees
            else:
                cum += (v["entry_cr"] - v["exit_cost"]) * MULT - 4 * FEE  # realized round-trip
        curve.append((g, spath[g], cum))

    final_pnl = curve[-1][2]
    trough_g, trough_spot, trough = min(curve, key=lambda r: r[2])
    peak = max(c for _, _, c in curve[:curve.index((trough_g, trough_spot, trough)) + 1]) \
        if curve else 0.0
    # running peak before trough for peak->trough DD
    run_peak, p2t_dd, p2t_g = -1e9, 0.0, None
    for g, s, c in curve:
        run_peak = max(run_peak, c)
        if run_peak - c > p2t_dd:
            p2t_dd = run_peak - c; p2t_g = g

    # circuit breakers (Stage-2 intraday-path)
    breakers = {}
    for cap in BREAKER_CAPS:
        trig_g = None
        for g, s, c in curve:
            if c <= -cap:
                trig_g = g; break
        if trig_g is None:
            breakers[int(cap)] = {"triggered": False, "pnl": round(final_pnl, 2),
                                  "note": f"never reached -{cap:,.0f} intraday"}
        else:
            # flatten all still-open spreads at trig_g (round-trip fees)
            et = trig_g.strftime("%H:%M:%S")
            pnl = 0.0
            for v in taken:
                if trig_g < v["exit_g"]:
                    cc = close_cost(v["short"], v["long"], v["right"], et)
                    pnl += (v["entry_cr"] - cc) * MULT - 4 * FEE
                else:
                    pnl += (v["entry_cr"] - v["exit_cost"]) * MULT - 4 * FEE
            breakers[int(cap)] = {"triggered": True, "at": trig_g.strftime("%H:%M"),
                                  "spot": round(spath[trig_g], 1), "pnl": round(pnl, 2)}

    # report
    print(f"intraday DD + breakers {a.date} | entry {entry_et} ET | grid {a.step_min}min -> "
          f"{ceiling.strftime('%H:%M')} ET | {len(taken)} taken spreads")
    print(f"  spot {curve[0][1]:.1f} -> {curve[-1][1]:.1f}")
    print(f"  FINAL P&L:            {final_pnl:>+9,.0f}")
    print(f"  intraday TROUGH (worst cumulative):  {trough:>+9,.0f}  @ {trough_g.strftime('%H:%M')} ET "
          f"(spot {trough_spot:.0f})")
    print(f"  peak->trough max DD:  {p2t_dd:>9,.0f}  (trough @ {p2t_g.strftime('%H:%M') if p2t_g else '-'} ET)")
    print(f"\n  CIRCUIT BREAKERS (real intraday-path flatten):")
    for cap in BREAKER_CAPS:
        b = breakers[int(cap)]
        if b["triggered"]:
            print(f"    -${int(cap):,}: TRIGGERED @ {b['at']} ET (spot {b['spot']:.0f}) -> day P&L {b['pnl']:+,.0f}")
        else:
            print(f"    -${int(cap):,}: not triggered ({b['note']}) -> day P&L {b['pnl']:+,.0f}")

    # persist
    curve_csv = ROOT / "data" / "options_log" / f"replay_{a.date}_curve.csv"
    with open(curve_csv, "w", newline="") as f:
        w = csv.writer(f); w.writerow(["et", "spot", "cum_pnl"])
        for g, s, c in curve:
            w.writerow([g.strftime("%H:%M:%S"), round(s, 2), round(c, 2)])
    rep = {"date": a.date, "entry_et": entry_et, "grid_step_min": a.step_min,
           "final_pnl": round(final_pnl, 2),
           "intraday_trough": round(trough, 2), "trough_at_et": trough_g.strftime("%H:%M:%S"),
           "intraday_dd_peak_to_trough": round(p2t_dd, 2),
           "breaker_2k": breakers[2000], "breaker_3k": breakers[3000],
           "spot_open": round(curve[0][1], 1), "spot_close": round(curve[-1][1], 1),
           "fill_model": "worst-touch (S113)", "reconstructed": True,
           "note": "READ-ONLY intraday-path DD + Stage-2 circuit-breaker replay; NOT booked."}
    out = ROOT / "data" / "options_log" / f"replay_{a.date}_dd_breaker.json"
    out.write_text(json.dumps(rep, indent=1), encoding="utf-8")
    print(f"\nwrote {out}\nwrote {curve_csv}")


if __name__ == "__main__":
    main()
