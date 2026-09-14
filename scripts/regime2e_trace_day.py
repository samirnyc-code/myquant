"""Trace the phase machine for one day: dump pivots + trend starts, and explain the
EXACT structural reason each regime begins.

  python scripts/regime2e_trace_day.py 2026-05-19
"""
import sys
from pathlib import Path
import numpy as np
REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO / "scripts"))
sys.path.insert(0, r"C:\Users\Admin\myquant-regime\scripts")
from regime2e_nt_diff import day_frames                          # noqa: E402
from regime_second_entry_study import phase_transitions          # noqa: E402


def main():
    date = sys.argv[1] if len(sys.argv) > 1 else "2026-05-19"
    g, tP, tbar = day_frames(date)
    H = g["High"].values; L = g["Low"].values; n = len(g)
    tr = {}
    trans = phase_transitions(H, L, n, tP, tbar, trace=tr)

    # DISPLAY is 1-indexed (bar 1 = first RTH 5-min bar); internal engine is 0-indexed.
    B1 = lambda x: x + 1
    tr_ix = [i for (i, _) in trans]; tr_md = [m for (_, m) in trans]
    print(f"=== {date} pivots (1-indexed bar: side price  tag/disp  major?) ===")
    for p in tr["piv"]:
        if p["bar"] > 60:
            break
        px = H[p["bar"]] if p["side"] == "H" else L[p["bar"]]
        mj = f"  MAJOR={p['majlab']}@{B1(p['major'])}" if p.get("major") is not None else ""
        print(f"  bar {B1(p['bar']):>3}: {p['side']} {px:8.2f}  {p['disp']:<3} (leg-tag {p['tag']}){mj}")

    print("\n=== trend starts (1-indexed bar, dir, broken-pivot-bar) ===")
    for (b, dr, brk) in tr["starts"]:
        brokenpx = L[brk] if dr == "bear" else H[brk]
        print(f"  bar {B1(b):>3}: {dr.upper()} started by breaking {'LOW' if dr=='bear' else 'HIGH'} "
              f"of bar {B1(brk)} ({brokenpx:.2f})")

    # explain each BEAR start in structural terms
    print("\n=== structural explanation ===")
    for (b, dr, brk) in tr["starts"]:
        # the qualifying counter-pivot = the pivot that got majlab LH (bear) / HL (bull) at bar b
        partner = [p for p in tr["piv"] if p.get("major") == b and p["majlab"] in ("LH", "HL")]
        brokenpx = L[brk] if dr == "bear" else H[brk]
        # trigger tick: first tick at bar b that crossed the broken level
        a = np.searchsorted(tbar, b, "left"); z = np.searchsorted(tbar, b, "right")
        seg = tP[a:z]
        cross = seg[seg < brokenpx] if dr == "bear" else seg[seg > brokenpx]
        trigpx = (cross[0] if len(cross) else (seg[-1] if len(seg) else brokenpx))
        print(f"\nbar {B1(b)} — {dr.upper()} regime begins because:")
        print(f"  1. a swing {'LOW' if dr=='bear' else 'HIGH'} stood at bar {B1(brk)} = {brokenpx:.2f} (last swing {'low' if dr=='bear' else 'high'}).")
        if partner:
            pp = partner[0]; ppx = H[pp["bar"]] if pp["side"] == "H" else L[pp["bar"]]
            print(f"  2. a {pp['majlab']} (structural {'lower high' if dr=='bear' else 'higher low'}) already existed at bar {B1(pp['bar'])} = {ppx:.2f} "
                  f"-> the 'has_{'lh' if dr=='bear' else 'hl'}' condition was TRUE.")
        else:
            print(f"  2. the has_{'lh' if dr=='bear' else 'hl'} structural flag was TRUE (a counter pivot existed).")
        print(f"  3. during bar {B1(b)}, price traded {'below' if dr=='bear' else 'above'} {brokenpx:.2f} "
              f"(hit ~{trigpx:.2f}) -> break of the swing {'low' if dr=='bear' else 'high'} confirmed the trend flip.")


if __name__ == "__main__":
    main()
