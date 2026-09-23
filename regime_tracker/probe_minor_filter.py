#!/usr/bin/env python3
"""Probe: should a swing that broke nothing be dropped from the setup sequence?

Prompted by 2026-05-06 b5. Before it the swings are L1 7388.50, H2 7406.25,
L3 7398.75, H4 7405.75. b3 never broke b1's low and b4 missed b2's high by
0.50, so by the document ("minor pivots ... typically fail to break the
opposing major structure") both are minor. Drop them and the sequence is
L1 -> H2 -> L5, b5's low is a higher low, its high clears b2, and b5 is a BOS
up into Bull -- the hand-marked reading. The engine instead builds a bear setup
on b4 and fires BOS down + ChoCh up inside b5, a zero-length Bear.

CANDIDATE RULE: when two same-kind swings are separated by an opposite-kind
swing that FAILED to break its own previous same-kind swing, the separator is
minor -- drop it and merge the two same-kind swings to their extreme. Applied
on top of the committed outside-bar rule, and only to the setup sequence.

Runs every reference session through the committed engine and the variant and
prints the diff. Changes nothing on disk.

    python probe_minor_filter.py [date ...]
"""
import json, pathlib, sys, types
import pandas as pd

HERE = pathlib.Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
from mywedge import compute_mywedge                       # noqa: E402
from regime_tracker import compute_regime                 # noqa: E402
from run_all_sessions import SESSIONS                     # noqa: E402

PARQUET = HERE.parent / "data" / "bars" / "_continuous_1m.parquet"

ANCHOR = """        out = []
        for t, (idx, k, price) in enumerate(zz):
            nxt = zz[t + 1] if t + 1 < len(zz) else None
            pair = nxt is not None and nxt[0] == idx and nxt[1] != k
            if pair and not (extends(out, k, price) and extends(out, *nxt[1:])):
                continue                 # one-sided bar: its later extreme wins
            if out and out[-1][1] == k:
                if (price > out[-1][2]) if k == "H" else (price < out[-1][2]):
                    out[-1] = (idx, k, price)
            else:
                out.append((idx, k, price))
        return out"""

VARIANT = """        out = []
        for t, (idx, k, price) in enumerate(zz):
            nxt = zz[t + 1] if t + 1 < len(zz) else None
            pair = nxt is not None and nxt[0] == idx and nxt[1] != k
            if pair and not (extends(out, k, price) and extends(out, *nxt[1:])):
                continue                 # one-sided bar: its later extreme wins
            # CANDIDATE: a separator that broke nothing is minor -- drop it and
            # let the two same-kind swings around it merge into one pullback.
            if len(out) >= 2 and out[-1][1] != k and out[-2][1] == k:
                sep = out[-1]
                prev = None
                for cand in reversed(out[:-1]):
                    if cand[1] == sep[1]:
                        prev = cand
                        break
                if prev is not None:
                    failed = (sep[2] <= prev[2]) if sep[1] == "H" else (sep[2] >= prev[2])
                    if failed:
                        out.pop()
            if out and out[-1][1] == k:
                if (price > out[-1][2]) if k == "H" else (price < out[-1][2]):
                    out[-1] = (idx, k, price)
            else:
                out.append((idx, k, price))
        return out"""


def variant_compute_regime():
    src = (HERE / "regime_tracker.py").read_text(encoding="utf-8")
    assert ANCHOR in src, "swings() body moved -- update ANCHOR"
    mod = types.ModuleType("regime_tracker_variant")
    mod.__dict__["__file__"] = "<variant>"
    exec(compile(src.replace(ANCHOR, VARIANT), "<variant>", "exec"), mod.__dict__)
    return mod.compute_regime


def load(date, df):
    target = pd.Timestamp(date)
    d = df[df["DateTime"].dt.normalize() == target]
    rs = d.set_index("DateTime").resample("5min", label="left", closed="left").agg(
        Open=("Open", "first"), High=("High", "max"),
        Low=("Low", "min"), Close=("Close", "last")).dropna().reset_index()
    O, H, L, C = (list(rs[c]) for c in ("Open", "High", "Low", "Close"))
    ins = [True] + [False] * (len(O) - 1)
    w = compute_mywedge(O, H, L, C, tick_size=0.25, is_new_session=ins,
                        lookback=0, warmup_floor=0, show_w2l=True, wedge_symmetry=4,
                        ol_sensitivity=1, ctsb_ignore=True, ib_ignore=True,
                        show_wedge_sb=True, signal_bar_ibs=66.0,
                        continue_mc=False, continue_on_gap=False)
    return w, L, H


def shape(r):
    out, cur, start = [], r.regime[0], 0
    for i in range(1, len(r.regime)):
        if r.regime[i] != cur:
            out.append(f"{cur[:2]}{start + 1}")
            cur, start = r.regime[i], i
    out.append(f"{cur[:2]}{start + 1}")
    return " ".join(out)


def main():
    dates = sys.argv[1:] or SESSIONS
    variant = variant_compute_regime()
    df = pd.read_parquet(PARQUET).sort_values("DateTime").reset_index(drop=True)

    changed = 0
    for date in dates:
        w, L, H = load(date, df)
        a = compute_regime(w.swing_low, w.swing_high, L, H, bar_dir=w.bar_dir)
        b = variant(w.swing_low, w.swing_high, L, H, bar_dir=w.bar_dir)
        sa, sb = shape(a), shape(b)
        ea = {(i + 1, k, d, lv) for i, k, d, lv in a.events}
        eb = {(i + 1, k, d, lv) for i, k, d, lv in b.events}
        if sa == sb and ea == eb:
            print(f"{date}  unchanged")
            continue
        changed += 1
        print(f"{date}  CHANGED")
        if sa != sb:
            print(f"    now: {sa}")
            print(f"    var: {sb}")
        if eb - ea:
            print("    +   ", sorted(eb - ea))
        if ea - eb:
            print("    -   ", sorted(ea - eb))
    print(f"\n{changed} of {len(dates)} sessions change under the candidate rule")


if __name__ == "__main__":
    main()
