#!/usr/bin/env python3
"""Print a session's bars, pivots, swing sequence and events around a bar range.

    python inspect_session.py 20260506 --from 1 --to 12

Shows, per bar: OHLC, bar direction, whether it is an outside bar, the mywedge
pivots on it (major starred), and how the outside-bar rule treats it. Then the
collapsed swing sequence the range-exit setup actually reads, and the events.
Use it to answer "why did/didn't a BOS fire on bar N".
"""
import argparse, json, pathlib

HERE = pathlib.Path(__file__).resolve().parent


def swings(zz):
    """Mirror of regime_tracker.swings(): outside-bar pairs collapsed."""
    def extends(out, kind, price):
        for _, k, p in reversed(out):
            if k == kind:
                return (price > p) if kind == "H" else (price < p)
        return True

    out, notes = [], {}
    for t, (idx, k, price) in enumerate(zz):
        nxt = zz[t + 1] if t + 1 < len(zz) else None
        pair = nxt is not None and nxt[0] == idx and nxt[1] != k
        if pair:
            a, b = extends(out, k, price), extends(out, nxt[1], nxt[2])
            notes[idx] = (f"outside bar: {k} extends={a}, {nxt[1]} extends={b} -> "
                          + ("both kept" if a and b else f"{nxt[1]} kept, {k} dropped"))
            if not (a and b):
                continue
        if out and out[-1][1] == k:
            if (price > out[-1][2]) if k == "H" else (price < out[-1][2]):
                out[-1] = (idx, k, price)
        else:
            out.append((idx, k, price))
    return out, notes


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("slug")
    ap.add_argument("--from", dest="lo", type=int, default=1)
    ap.add_argument("--to", dest="hi", type=int, default=20)
    a = ap.parse_args()

    d = json.load(open(HERE / f"regime_data_es_{a.slug}.json"))
    bars = d["bars"]
    piv = {}
    for p in d["pivot_highs"]:
        piv.setdefault(p["i"], []).append(("H", p["price"], p["major"]))
    for p in d["pivot_lows"]:
        piv.setdefault(p["i"], []).append(("L", p["price"], p["major"]))

    # rebuild zz the way compute_regime does: pivots in bar_dir order
    zz = []
    for i in sorted(piv):
        items = piv[i]
        if len(items) == 2:
            low_first = bars[i]["c"] >= bars[i]["o"]
            items = sorted(items, key=lambda x: x[0] != ("L" if low_first else "H"))
        for kind, price, _ in items:
            if zz and zz[-1][1] == kind:
                if (price > zz[-1][2]) if kind == "H" else (price < zz[-1][2]):
                    zz[-1] = (i, kind, price)
            else:
                zz.append((i, kind, price))

    seq, notes = swings(zz)

    print(f"== {a.slug}  bars {a.lo}-{a.hi}")
    for i in range(a.lo - 1, min(a.hi, len(bars))):
        x, pb = bars[i], bars[i - 1] if i else None
        ob = pb and x["h"] > pb["h"] and x["l"] < pb["l"]
        tag = " ".join(f"{k}{'*' if m else ''}@{pr}" for k, pr, m in piv.get(i, []))
        print(f"  b{i+1:<3} {x['t'][11:16]} O {x['o']:<8} H {x['h']:<8} L {x['l']:<8} "
              f"C {x['c']:<8} {'bull' if x['c'] >= x['o'] else 'bear'} "
              f"{'OUTSIDE' if ob else '':8} {tag}")
        if i in notes:
            print(f"        -> {notes[i]}")

    print("\n  raw zz (in range):")
    print("   ", " ".join(f"{k}{i+1}@{p}" for i, k, p in zz if a.lo <= i + 1 <= a.hi))
    print("  collapsed sequence the setup reads:")
    print("   ", " ".join(f"{k}{i+1}@{p}" for i, k, p in seq if a.lo <= i + 1 <= a.hi))
    print("\n  events in range:")
    for e in d["events"]:
        if a.lo <= e["i"] + 1 <= a.hi:
            print(f"    b{e['i']+1} {e['kind']} {e['dir']} @ {e['level']}")
    print("  regimes:", " ".join(f"{g['regime']}{g['start']+1}" for g in d["segments"]))


if __name__ == "__main__":
    main()
