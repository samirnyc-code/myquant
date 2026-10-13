#!/usr/bin/env python3
"""Diff two sets of regime_data_es_<slug>.json, session by session.

    python compare_session_sets.py DIR_A DIR_B [--out report.txt]

For every slug present in both: regime per bar, segments, BOS/ChoCh events and
pivot (index, kind, major) sets. Prints an exact-match verdict per session plus
the bar-level detail of any difference, so a rule or Lag change can be judged
against the hand-validated sessions instead of eyeballed. Writes the same
report to --out (default: dated file next to this script).
"""
import argparse, datetime as dt, json, pathlib

HERE = pathlib.Path(__file__).resolve().parent


def load(p):
    d = json.load(open(p))
    return dict(
        regime=d["regime"],
        shape=" ".join(f"{g['regime'][:2]}{g['start'] + 1}" for g in d["segments"]),
        events={(e["i"] + 1, e["kind"], e["dir"], e["level"]) for e in d["events"]},
        pivots={(p["i"] + 1, "L", p["major"]) for p in d["pivot_lows"]}
             | {(p["i"] + 1, "H", p["major"]) for p in d["pivot_highs"]},
        n=len(d["bars"]))


def runs(bars):
    """[3,4,5,9] -> 'b3-5 b9'"""
    out, s = [], None
    for b in sorted(bars):
        if s is None:
            s = e = b
        elif b == e + 1:
            e = b
        else:
            out.append(f"b{s}" if s == e else f"b{s}-{e}")
            s = e = b
    if s is not None:
        out.append(f"b{s}" if s == e else f"b{s}-{e}")
    return " ".join(out)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("a", type=pathlib.Path)
    ap.add_argument("b", type=pathlib.Path)
    ap.add_argument("--out", type=pathlib.Path,
                    default=HERE / f"compare_session_sets_{dt.date.today():%Y%m%d}.txt")
    a = ap.parse_args()

    slugs = sorted({p.name for p in a.a.glob("regime_data_es_*.json")}
                   & {p.name for p in a.b.glob("regime_data_es_*.json")})
    lines = [f"A = {a.a}", f"B = {a.b}", ""]
    same = 0
    tot_bars = tot_diff = 0
    for name in slugs:
        A, B = load(a.a / name), load(a.b / name)
        slug = name[len("regime_data_es_"):-5]
        diff_bars = [i + 1 for i, (x, y) in enumerate(zip(A["regime"], B["regime"])) if x != y]
        tot_bars += A["n"]
        tot_diff += len(diff_bars)
        identical = (not diff_bars and A["events"] == B["events"] and A["pivots"] == B["pivots"])
        if identical:
            same += 1
            lines.append(f"{slug}  IDENTICAL")
            continue
        lines.append(f"{slug}  DIFFERS  ({len(diff_bars)} of {A['n']} bars relabelled)")
        if A["shape"] != B["shape"]:
            lines.append(f"    A: {A['shape']}")
            lines.append(f"    B: {B['shape']}")
        if diff_bars:
            lines.append(f"    bars: {runs(diff_bars)}")
        if B["events"] - A["events"]:
            lines.append(f"    events only in B: {sorted(B['events'] - A['events'])}")
        if A["events"] - B["events"]:
            lines.append(f"    events only in A: {sorted(A['events'] - B['events'])}")
        pa, pb = A["pivots"], B["pivots"]
        if pa != pb:
            lines.append(f"    pivots only in A: {sorted(pa - pb)}")
            lines.append(f"    pivots only in B: {sorted(pb - pa)}")
    lines.append("")
    lines.append(f"{same} of {len(slugs)} sessions identical; "
                 f"{tot_diff} of {tot_bars} bars relabelled ({100 * tot_diff / max(tot_bars, 1):.2f}%)")
    text = "\n".join(lines)
    print(text)
    a.out.write_text(text + "\n", encoding="utf-8")
    print(f"\nreport -> {a.out}")


if __name__ == "__main__":
    main()
