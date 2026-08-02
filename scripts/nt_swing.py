#!/usr/bin/env python
"""nt_swing.py — faithful Python port of NinjaTrader 8's built-in Swing(Strength) indicator.

Ported directly from the platform source:
  C:/Users/Admin/Documents/NinjaTrader 8/bin/Custom/Indicators/@Swing.cs  (lines 118-192)

NT's confirmed-swing rule (window = 2*Strength+1 highs/lows, candidate = middle bar, which is
`Strength` bars back from the current bar; cache[0]=oldest ... cache[2*Strength]=newest):

  SWING HIGH: candidate = cache[Strength]
    - for older bars i in [0, Strength):      if high[i] >= candidate  -> NOT a swing high
      (candidate must be STRICTLY GREATER than every bar to its LEFT/older)
    - for newer bars i in (Strength, 2*Strength]: if high[i] >  candidate -> NOT a swing high
      (candidate must be >= every bar to its RIGHT/newer; EQUAL on the newer side is allowed)

  SWING LOW is the mirror (strictly less than older, <= newer).

So a pivot is confirmed exactly `Strength` bars AFTER it prints. This asymmetric equality
handling is the difference from a plain symmetric fractal.

nt_swing(H, L, strength) returns a list of (pivot_bar_index, 'H'|'L') sorted by index —
drop-in compatible with the old fractal() used by halsey_mm50_engine.
"""
from __future__ import annotations

import numpy as np

EPS = 1e-9  # NT uses ApproxCompare (float-tolerant); ES prices are clean 0.25 ticks


def nt_swing(H, L, strength: int):
    H = np.asarray(H, float); L = np.asarray(L, float)
    n = len(H)
    constant = 2 * strength + 1
    out = []
    if n < constant:
        return out
    for cb in range(constant - 1, n):
        piv = cb - strength                 # candidate bar index
        # window highs/lows: cache[0]=oldest (cb-2*strength) ... cache[2*strength]=newest (cb)
        hw = H[cb - 2 * strength: cb + 1]
        lw = L[cb - 2 * strength: cb + 1]
        cand_h = hw[strength]
        is_h = True
        for i in range(0, strength):        # older/left: strictly less required
            if hw[i] >= cand_h - EPS:
                is_h = False; break
        if is_h:
            for i in range(strength + 1, constant):   # newer/right: <= allowed
                if hw[i] > cand_h + EPS:
                    is_h = False; break
        if is_h:
            out.append((piv, 'H'))
        cand_l = lw[strength]
        is_l = True
        for i in range(0, strength):
            if lw[i] <= cand_l + EPS:
                is_l = False; break
        if is_l:
            for i in range(strength + 1, constant):
                if lw[i] < cand_l - EPS:
                    is_l = False; break
        if is_l:
            out.append((piv, 'L'))
    out.sort()
    return out


if __name__ == "__main__":
    # self-check vs the old symmetric fractal on the 15M frame
    import sys
    from pathlib import Path
    sys.path.insert(0, str(Path(__file__).resolve().parent))
    from halsey_mm50_engine import build_15m, fractal
    g = build_15m()
    H = g["H"].to_numpy(); L = g["L"].to_numpy()
    for s in (1, 2, 3, 5):
        nt = nt_swing(H, L, s); fr = fractal(H, L, s)
        print(f"strength {s}: NT swings={len(nt):5d}  | old fractal={len(fr):5d}")
