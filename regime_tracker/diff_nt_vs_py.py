#!/usr/bin/env python3
"""Diff the NT8 RegimeTracker indicator against the Python regime engine.

The NT8 indicator (nt8/indicators/RegimeTracker.cs) exports a CSV whose BAR rows
carry OHLC + the NT regime label, and whose EVT rows carry the BOS/ChoCh events.
Because the CSV is a *self-sufficient bar source*, we replay the Python engine
(compute_mywedge -> compute_regime) on those EXACT bars: any regime mismatch is
then a logic difference between the C# port and the reference, NOT chart-vs-parquet
bar drift.

    python diff_nt_vs_py.py regime_tracker_ES.csv [--session date|eth]
        [--lookback 12] [--wedge-symmetry 4] [--ol-sensitivity 1]
        [--no-ctsb-ignore] [--no-ib-ignore] [--signal-bar-ibs 66]
        [--lag 3] [--out DIR]

Defaults mirror the RegimeTracker.cs SetDefaults (LookBack 12, WedgeSymmetry 4,
OLSensitivity 1, CTSB_Ignore/IB_Ignore on, SignalBarIBS 66). Set these to
whatever the indicator was actually configured with, or the pivots will diverge.

LAG (canonical = 1). The indicator commits a bar's regime `Lag` bars after it
closes, acting on the pivots as they stand THEN -- `compute_mywedge(lag=...)`
snapshots exactly that (`swing_*_asof`). At lag>=2 every MyWedge retro-reset
(max depth 2) has already fired, so the snapshot equals the finalised array (the
old lag-3 / non-repainting view). At lag=1 the state machine can still act on a
pivot a later bar removes -- the live chart's behaviour. Pass --lag to match the
indicator's Lag setting; 1 reproduces the current chart exactly (100% both
exports 2026-09-24).

SESSION MODE must match the file's timezone: a CT-time export uses --session eth
(ETH opens 17:00 CT); a Berlin-time export uses --session date (ETH open falls at
Berlin midnight). Wrong pairing mis-segments sessions and injects phantom diffs.

NOTE on the tail: the last `Lag` BAR rows have no future context here, so their
snapshot falls back to the finalised value; the diff flags them as the tail zone
rather than counting them as logic failures.
"""
import argparse
import csv
import datetime as _dt
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from mywedge import compute_mywedge
from regime_tracker import compute_regime


def parse_nt_csv(path):
    bars, nt_regime, events = [], [], []
    with open(path, newline="") as f:
        r = csv.DictReader(f)
        for row in r:
            t = (row.get("type") or "").strip()
            if t == "BAR":
                bars.append((
                    row["time"].strip(),
                    float(row["o"]), float(row["h"]), float(row["l"]), float(row["c"]),
                ))
                nt_regime.append((row["regime"] or "").strip())
            elif t == "EVT":
                events.append((
                    int(row["bar"]),
                    (row["kind"] or "").strip(),
                    (row["dir"] or "").strip(),
                ))
    return bars, nt_regime, events


def new_session_flags(times, mode):
    """times: list of 'YYYY-MM-DD HH:MM:SS' strings. Returns bool list."""
    dts = [_dt.datetime.strptime(t, "%Y-%m-%d %H:%M:%S") for t in times]
    out, prev = [], None
    for d in dts:
        if mode == "eth":
            day = d.date() + _dt.timedelta(days=1) if d.hour >= 17 else d.date()
        else:  # 'date' — one session per calendar day (RTH-style chart)
            day = d.date()
        out.append(day != prev)
        prev = day
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("csv", help="RegimeTracker.cs export CSV")
    ap.add_argument("--session", choices=["date", "eth"], default="date")
    ap.add_argument("--lookback", type=int, default=12)
    ap.add_argument("--wedge-symmetry", type=int, default=4)
    ap.add_argument("--ol-sensitivity", type=int, default=1)
    ap.add_argument("--no-ctsb-ignore", action="store_true")
    ap.add_argument("--no-ib-ignore", action="store_true")
    ap.add_argument("--signal-bar-ibs", type=float, default=66.0)
    ap.add_argument("--tick-size", type=float, default=0.25)
    ap.add_argument("--lag", type=int, default=1)
    ap.add_argument("--show", type=int, default=30, help="max divergences to print")
    ap.add_argument("--out", default=os.path.dirname(os.path.abspath(__file__)))
    a = ap.parse_args()

    bars, nt_regime, nt_events = parse_nt_csv(a.csv)
    n = len(bars)
    if n == 0:
        sys.exit("no BAR rows in CSV — enable 'Export validation CSV' on the indicator and rerun")

    times = [b[0] for b in bars]
    O = [b[1] for b in bars]; H = [b[2] for b in bars]
    L = [b[3] for b in bars]; C = [b[4] for b in bars]
    ins = new_session_flags(times, a.session)

    w = compute_mywedge(
        O, H, L, C, tick_size=a.tick_size, is_new_session=ins,
        lookback=a.lookback, warmup_floor=4, show_w2l=True,
        wedge_symmetry=a.wedge_symmetry, ol_sensitivity=a.ol_sensitivity,
        ctsb_ignore=not a.no_ctsb_ignore, ib_ignore=not a.no_ib_ignore,
        show_wedge_sb=True, signal_bar_ibs=a.signal_bar_ibs,
        continue_mc=False, continue_on_gap=False, lag=a.lag,
    )
    # Feed the state machine the pivot flags as of `lag` bars later -- the exact
    # value NT8 acts on (SwingLow[Lag]). At lag>=2 these equal w.swing_low.
    r = compute_regime(w.swing_low_asof, w.swing_high_asof, L, H, bar_dir=w.bar_dir)
    py_regime = r.regime

    # --- per-bar regime diff ---
    tail_start = n - a.lag           # last `lag` compared bars = truncation-edge zone
    matches = tail_mismatch = core_mismatch = 0
    diverge = []
    for j in range(n):
        agree = nt_regime[j] == py_regime[j]
        if agree:
            matches += 1
        else:
            if j >= tail_start:
                tail_mismatch += 1
            else:
                core_mismatch += 1
            diverge.append((j, times[j], nt_regime[j], py_regime[j], j >= tail_start))

    # --- event diff (bar, kind, dir) ---
    py_events = set((i, k, d) for i, k, d, _lv in r.events)
    nt_ev = set(nt_events)
    both = py_events & nt_ev
    only_py = sorted(py_events - nt_ev)
    only_nt = sorted(nt_ev - py_events)

    stamp = _dt.datetime.now().strftime("%Y%m%d_%H%M%S")
    base = os.path.splitext(os.path.basename(a.csv))[0]
    out_csv = os.path.join(a.out, f"regime_diff_{base}_{stamp}.csv")
    with open(out_csv, "w", newline="") as f:
        wri = csv.writer(f)
        wri.writerow(["bar", "time", "nt_regime", "py_regime", "agree", "tail_zone"])
        for j in range(n):
            wri.writerow([j, times[j], nt_regime[j], py_regime[j],
                          int(nt_regime[j] == py_regime[j]), int(j >= tail_start)])

    pct = 100.0 * matches / n
    core_n = tail_start if tail_start > 0 else n
    core_pct = 100.0 * (core_n - core_mismatch) / core_n if core_n else 0.0
    lines = []
    lines.append(f"NT-vs-Python regime diff  —  {a.csv}")
    lines.append(f"bars compared: {n}   session-mode: {a.session}   lag: {a.lag}")
    lines.append(f"MyWedge params: lookback={a.lookback} sym={a.wedge_symmetry} ol={a.ol_sensitivity} "
                 f"ctsb_ignore={not a.no_ctsb_ignore} ib_ignore={not a.no_ib_ignore} sb_ibs={a.signal_bar_ibs}")
    lines.append("")
    lines.append(f"REGIME AGREEMENT: {matches}/{n} = {pct:.2f}%")
    lines.append(f"  core (excl. last {a.lag} tail bars): {core_n - core_mismatch}/{core_n} = {core_pct:.2f}%")
    lines.append(f"  tail-zone mismatches (truncation edge, informational): {tail_mismatch}")
    lines.append("")
    lines.append(f"EVENTS  NT={len(nt_ev)}  PY={len(py_events)}  agree={len(both)}  "
                 f"NT-only={len(only_nt)}  PY-only={len(only_py)}")
    if only_nt:
        lines.append("  NT-only events: " + ", ".join(f"b{i}:{k}/{d}" for i, k, d in only_nt[:20]))
    if only_py:
        lines.append("  PY-only events: " + ", ".join(f"b{i}:{k}/{d}" for i, k, d in only_py[:20]))
    if diverge:
        lines.append("")
        lines.append(f"first {min(a.show, len(diverge))} regime divergences (bar | time | NT | PY | tail?):")
        for j, t, nt, py, tail in diverge[:a.show]:
            lines.append(f"  {j:>4} | {t} | NT={nt:<6} PY={py:<6} {'(tail)' if tail else ''}")

    report = "\n".join(lines)
    out_txt = os.path.join(a.out, f"regime_diff_{base}_{stamp}.txt")
    with open(out_txt, "w") as f:
        f.write(report + "\n")

    print(report)
    print(f"\nsaved: {out_csv}\n       {out_txt}")
    # exit non-zero if any CORE (non-tail) regime bar or any event disagrees
    sys.exit(0 if (core_mismatch == 0 and not only_nt and not only_py) else 1)


if __name__ == "__main__":
    main()
