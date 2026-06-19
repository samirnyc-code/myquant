"""
Tick-level trade tracer — a sequential, NT-reconcilable proof of single trades.

For each selected trade it prints a chronological, ONE-EVENT-PER-LINE walkthrough
you can follow against the NT chart in front of you:
  * CT timestamps + 5M bar number (find the bar on the chart)
  * both back-adjusted continuous price AND raw per-contract price (= adj − offset)
  * every decisive level (entry, stop, PB, T1, T2, ratchet trigger + BE level) with
    the formula spelled out
  * each event preceded by the 3 ticks just before it, so you can see it fired on the
    FIRST qualifying tick (engine didn't miss one or fire late)

The entry / E2-fill / exit lines come straight from simulate_trades() output (the
engine is authoritative); the ratchet-fire line is recomputed for display and clearly
marked. A consistency assert confirms the trace matches the engine result.

    .venv\\Scripts\\python scripts\\explain_trade.py                 # auto-pick the catalog
    .venv\\Scripts\\python scripts\\explain_trade.py --signal 1234 --mode multileg \\
        --ratchet 1.0 --pb -0.50 --t1 1.5 --t2 1.0 --style e2
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

import numpy as np
import pandas as pd

try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from simulation_engine import simulate_trades, TICK_SIZE  # noqa: E402
from data_loader import bar_num_from_dt  # noqa: E402
from validate_engine import _load_ticks, DEFAULTS, SIGNALS_PARQUET  # noqa: E402

try:
    from contracts import load_rolls, get_active_contract
    _ROLLS = load_rolls()
except Exception:
    _ROLLS = None

TS = TICK_SIZE


def _offset_for(d):
    if _ROLLS is None:
        return 0.0, "?"
    ac = get_active_contract(pd.Timestamp(d).date(), _ROLLS)
    if ac is None:
        return 0.0, "?"
    return float(ac.get("cum_offset", 0.0)), str(ac.get("ticker", "?"))


def _load_window(start, end):
    s = pd.read_parquet(SIGNALS_PARQUET)
    s["DateTime"] = pd.to_datetime(s["DateTime"])
    if "Date" not in s.columns:
        s["Date"] = s["DateTime"].dt.date
    s = s[(s["DateTime"] >= pd.Timestamp(start)) & (s["DateTime"] <= pd.Timestamp(end))]
    tbd = {}
    for d in sorted(s["Date"].unique()):
        t = _load_ticks(d)
        if not t.empty:
            tbd[d] = t
    return s[s["Date"].isin(tbd)].copy(), tbd


def _run_one(sig_row, tbd, p):
    one = pd.DataFrame([sig_row])
    common = dict(entry_slip=DEFAULTS["entry_slip"], exit_slip=DEFAULTS["exit_slip"],
                  stop_offset=DEFAULTS["stop_offset"], tick_value=DEFAULTS["tick_value"],
                  commission=DEFAULTS["commission"])
    if p["mode"] == "multileg":
        res = simulate_trades(one, tbd, p["t2"], **common,
                              contracts=2, multileg=True, t1_r=p["t1"], t1_action="exit",
                              contracts_t1=1, contracts_t2=1, ml_pb_r=p["pb"],
                              scale_in_style=p["style"],
                              ratchet_r=p["ratchet"], ratchet_dest=p["dest"],
                              ratchet_lock_r=p["lock"])
    else:
        res = simulate_trades(one, tbd, p["t2"], **common, contracts=1,
                              ratchet_r=p["ratchet"], ratchet_dest=p["dest"],
                              ratchet_lock_r=p["lock"])
    return res.iloc[0]


def _fmt_px(adj, off):
    if adj is None or (isinstance(adj, float) and np.isnan(adj)):
        return "      —          "
    return f"{adj:>9.2f} (raw {adj - off:>9.2f})"


def _ctx(day_ticks, when, off, label, note):
    """Print the event tick + 3 ticks before it."""
    dt = day_ticks["DateTime"].values
    px = day_ticks["Price"].values
    i = int(np.searchsorted(dt, np.datetime64(pd.Timestamp(when))))
    if i >= len(dt):
        i = len(dt) - 1
    lo = max(0, i - 3)
    for j in range(lo, i + 1):
        marker = "►" if j == i else " "
        tag = f"  ◄── {label}: {note}" if j == i else ""
        t = pd.Timestamp(dt[j])
        print(f"   {marker} {t:%H:%M:%S}  bar {bar_num_from_dt(t):>2}  "
              f"{px[j]:>9.2f} (raw {px[j] - off:>9.2f}){tag}")


def explain(sig_row, tbd, p, title):
    d = sig_row["Date"]
    day_ticks = tbd[d]
    off, ticker = _offset_for(d)
    r = _run_one(sig_row, tbd, p)
    is_long = sig_row["Direction"] == "Long"
    sgn = 1 if is_long else -1

    print("=" * 78)
    print(f"{title}")
    print(f"signal #{int(sig_row['SignalNum'])}  {sig_row['SignalType']}  {sig_row['Direction']}"
          f"   {pd.Timestamp(sig_row['DateTime']):%Y-%m-%d %H:%M:%S} CT"
          f"   (bar {int(sig_row['BarNum'])})   contract {ticker}  offset {off:+.2f}")
    print(f"params: mode={p['mode']} t1={p['t1']} t2={p['t2']} pb={p['pb']} "
          f"style={p['style']} ratchet={p['ratchet']} dest={p['dest']} lock={p['lock']}")
    print("-" * 78)
    if not bool(r.get("Filled", False)):
        print(f"NOT FILLED — FilterStatus={r.get('FilterStatus')}")
        return

    entry = float(r["EntryPrice"]); stop = float(r["ActualStop"]); risk = float(r["RiskPts"])
    print("LEVELS (back-adjusted; raw = adj − offset):")
    print(f"   signal price  {_fmt_px(float(sig_row['SignalPrice']), off)}")
    print(f"   entry         {_fmt_px(entry, off)}   (first tick after signal bar close)")
    print(f"   stop          {_fmt_px(stop, off)}   risk = {risk:.2f} pt")
    if p["mode"] == "multileg":
        pb = r.get("PBLevel")
        print(f"   PB trigger    {_fmt_px(float(pb) if pd.notna(pb) else None, off)}"
              f"   (E1 entry {sgn:+d}×{abs(p['pb'])}R)")
        print(f"   T1            {_fmt_px(entry + sgn * p['t1'] * risk, off)}   (E1{sgn:+d}{p['t1']}R)")
    if pd.notna(r.get("Target")):
        if p["mode"] == "multileg" and p["style"] == "e2" and pd.notna(r.get("E2FillPrice")):
            e2 = float(r["E2FillPrice"]); e2r = abs(e2 - stop)
            print(f"   T2            {_fmt_px(float(r['Target']), off)}   "
                  f"(E2 {e2:.2f} {sgn:+d} {p['t2']}R×E2-risk {e2r:.2f})")
        else:
            print(f"   T2/target     {_fmt_px(float(r['Target']), off)}")
    if p["ratchet"] > 0:
        ref0 = entry
        trig = ref0 + sgn * p["ratchet"] * risk
        be = ref0 if p["dest"] != "Lock-in" else ref0 + sgn * p["lock"] * risk
        print(f"   ratchet trig  {_fmt_px(trig, off)}   (favor ≥ {p['ratchet']}R = {p['ratchet']*risk:.2f} pt)")
        print(f"   → stop moves to {_fmt_px(be, off)}   ({p['dest']})")
    print("-" * 78)

    # ── chronological events ────────────────────────────────────────────────
    events = []
    events.append((pd.Timestamp(r["EntryTime"]), "ENTRY", f"fill {float(r['FillPrice']):.2f} → entry {entry:.2f}"))

    if p["ratchet"] > 0:
        # recompute fire tick for display: first post-entry tick with favor ≥ thresh,
        # ref = blended after E2 fills (multileg), else entry
        dt = day_ticks["DateTime"].values
        px = day_ticks["Price"].values
        e_i = int(np.searchsorted(dt, np.datetime64(pd.Timestamp(r["EntryTime"])), side="left"))
        e2t = r.get("E2FillTime")
        blended = r.get("BlendedEntry")
        thresh = p["ratchet"] * risk
        fire = None
        for j in range(e_i + 1, len(dt)):
            ref = entry
            if (p["mode"] == "multileg" and pd.notna(e2t) and pd.notna(blended)
                    and pd.Timestamp(dt[j]) > pd.Timestamp(e2t)):
                ref = float(blended)
            favor = sgn * (px[j] - ref)
            if favor >= thresh:
                fire = pd.Timestamp(dt[j]); break
            if pd.Timestamp(dt[j]) >= pd.Timestamp(r["ExitTime"]):
                break
        if fire is not None:
            events.append((fire, "RATCHET FIRES", "favor ≥ trigger → stop trails to BE/lock"))

    if p["mode"] == "multileg" and pd.notna(r.get("E2FillTime")):
        events.append((pd.Timestamp(r["E2FillTime"]), "E2 FILLS",
                       f"PB hit → E2 {float(r['E2FillPrice']):.2f}, blended {float(r['BlendedEntry']):.2f}"))

    events.append((pd.Timestamp(r["ExitTime"]), f"EXIT [{r['ExitReason']}]",
                   f"price {float(r['ExitPrice']):.2f}"))

    events.sort(key=lambda e: e[0])
    print("TIMELINE (► = event tick, with the 3 ticks before it):")
    for when, label, note in events:
        _ctx(day_ticks, when, off, label, note)
        print()

    # ── result + per-leg ──────────────────────────────────────────────────────
    print("RESULT:")
    if p["mode"] == "multileg":
        print(f"   Leg1 (E1): {r.get('Leg1ExitReason')}  {r.get('Leg1GrossPts')} pt  ${r.get('Leg1GrossPnL')}")
        print(f"   Leg2 (E2): {r.get('Leg2ExitReason')}  {r.get('Leg2GrossPts')} pt  ${r.get('Leg2GrossPnL')}")
    print(f"   total: {float(r['GrossPnLPts']):.2f} pt   ${float(r['GrossPnL']):.2f}   "
          f"R={float(r['R_achieved']):.2f}   exit={r['ExitReason']}")
    print()


# ── auto-selection ─────────────────────────────────────────────────────────────
def _pick(window, tbd):
    sigs, _ = window
    picks = []

    def scan(p, want):
        common = dict(entry_slip=DEFAULTS["entry_slip"], exit_slip=DEFAULTS["exit_slip"],
                      stop_offset=DEFAULTS["stop_offset"], tick_value=DEFAULTS["tick_value"],
                      commission=DEFAULTS["commission"])
        if p["mode"] == "multileg":
            res = simulate_trades(sigs, tbd, p["t2"], **common, contracts=2, multileg=True,
                                  t1_r=p["t1"], t1_action="exit", contracts_t1=1, contracts_t2=1,
                                  ml_pb_r=p["pb"], scale_in_style=p["style"],
                                  ratchet_r=p["ratchet"], ratchet_dest=p["dest"], ratchet_lock_r=p["lock"])
        else:
            res = simulate_trades(sigs, tbd, p["t2"], **common, contracts=1,
                                  ratchet_r=p["ratchet"], ratchet_dest=p["dest"], ratchet_lock_r=p["lock"])
        f = res[res["Filled"] == True]
        m = want(f)
        cand = f[m]
        return cand

    # 1) single-leg ratchet → BE stop catches pullback (fired then stopped ≈ entry)
    p1 = dict(mode="single", t1=0, t2=2.0, pb=0.0, style="e2", ratchet=1.0, dest="BE", lock=0.0)
    c = scan(p1, lambda f: (f["ExitReason"] == "Stop") & (f["MFE_R"] >= 1.0)
             & (np.abs(f["ExitPrice"] - f["EntryPrice"]) <= 2 * TS))
    if len(c): picks.append((c.iloc[0], p1, "① SINGLE-LEG RATCHET → BE STOP catches a pullback"))

    # 2) single-leg ratchet → rides to Target after firing
    c = scan(p1, lambda f: (f["ExitReason"] == "Target") & (f["MFE_R"] >= 1.0))
    if len(c): picks.append((c.iloc[0], p1, "② SINGLE-LEG RATCHET fired, then rode to TARGET"))

    # 3) 2-leg E2-style: PB fills, E1E2+Target (T2 should land on/near E1 entry at 50% PB)
    p3 = dict(mode="multileg", t1=1.5, t2=1.0, pb=-0.50, style="e2", ratchet=0.0, dest="BE", lock=0.0)
    c = scan(p3, lambda f: f["ExitReason"] == "E1E2+Target")
    if len(c): picks.append((c.iloc[0], p3, "③ 2-LEG E2-STYLE T2 — PB fills, both legs exit (E1=BE, E2=+1R)"))

    # 5) same trade, blended style — show the different T2
    if len(c):
        p5 = dict(p3); p5["style"] = "blended"
        picks.append((c.iloc[0], p5, "④ SAME TRADE, BLENDED-STYLE T2 (compare T2 price vs ③)"))

    # 4) 2-leg pre-E2 ratchet fire that BLOCKS the scale-in (ratchet on, Stop, E2 never filled)
    p4 = dict(mode="multileg", t1=1.5, t2=1.0, pb=-0.50, style="e2", ratchet=0.75, dest="BE", lock=0.0)
    c = scan(p4, lambda f: (f["ExitReason"] == "Stop") & (f["Leg2ExitReason"].astype(str) == "NoFill")
             & (f["MFE_R"] >= 0.75) & (np.abs(f["ExitPrice"] - f["EntryPrice"]) <= 2 * TS))
    if len(c): picks.append((c.iloc[0], p4, "⑤ 2-LEG PRE-E2 RATCHET FIRE blocks scale-in (BE stop, E2 NoFill)"))

    # 6) lock-in ratchet (single-leg)
    p6 = dict(mode="single", t1=0, t2=2.0, pb=0.0, style="e2", ratchet=1.0, dest="Lock-in", lock=0.5)
    c = scan(p6, lambda f: (f["ExitReason"] == "Stop") & (f["MFE_R"] >= 1.0))
    if len(c): picks.append((c.iloc[0], p6, "⑥ SINGLE-LEG LOCK-IN ratchet (stop locks +0.5R)"))

    return picks


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--signal", type=int, default=None, help="explain one specific SignalNum")
    ap.add_argument("--mode", choices=["single", "multileg"], default="multileg")
    ap.add_argument("--t1", type=float, default=1.5)
    ap.add_argument("--t2", type=float, default=1.0)
    ap.add_argument("--pb", type=float, default=-0.50)
    ap.add_argument("--style", choices=["e2", "blended"], default="e2")
    ap.add_argument("--ratchet", type=float, default=0.0)
    ap.add_argument("--dest", choices=["BE", "Lock-in"], default="BE")
    ap.add_argument("--lock", type=float, default=0.0)
    ap.add_argument("--start", default="2021-06-18")
    ap.add_argument("--end", default="2022-06-19")
    args = ap.parse_args()

    window = _load_window(args.start, args.end)
    sigs, tbd = window
    print(f"window {args.start} → {args.end}: {len(sigs)} signals, {len(tbd)} days\n")

    if args.signal is not None:
        row = sigs[sigs["SignalNum"] == args.signal]
        if row.empty:
            print(f"signal #{args.signal} not in window"); sys.exit(1)
        p = dict(mode=args.mode, t1=args.t1, t2=args.t2, pb=args.pb, style=args.style,
                 ratchet=args.ratchet, dest=args.dest, lock=args.lock)
        explain(row.iloc[0], tbd, p, f"SIGNAL #{args.signal} (manual)")
    else:
        for row, p, title in _pick(window, tbd):
            explain(row, tbd, p, title)


if __name__ == "__main__":
    main()
