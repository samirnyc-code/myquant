"""FIXED-CONFIG STABILITY — is there ONE a-priori config (zero optimization, zero 2021 hindsight,
no per-year tuning) with a STABLE edge across all 16 years? A noisy over-parameterized WFA
(432 combos on 2-yr windows) picks noise and understates a real edge; a single fixed sensible
config is the fairer test of 'is there an edge at all'.

Configs are motivated by STRUCTURE, not 2021 performance:
  - long-bias (2E-continuation in an uptrend-prone index; WFA picks long 14/15 yrs unprompted)
  - vol-scaled stop 0.30xADR (theory: risk proportional to daily range)
  - standard RTH morning window; with-trend phase gate (the strategy definition)

Reports gross+net meanR and PF by 4-year BLOCK (2010-13/14-17/18-21/22-26) so stability is
visible without any optimization. If a fixed long config is positive in EVERY block gross,
there's a real (small) structural edge and the clean-room WFA understated it.

Reads oos_pertrade_full_20260725.csv (all days, gap per trade).

  python scripts/regime_2e_fixed_configs.py
"""
import sys
from pathlib import Path
import numpy as np
import pandas as pd

TICK = 0.25; PT = 50.0; COMM = 5.0; SLIP = 12.5; FLOOR = 8 * TICK
WT = Path(__file__).resolve().parent.parent
CSV = WT / "data" / "regime" / "oos_pertrade_full_20260725.csv"
WINS = {"09-13": {9, 10, 11, 12, 13}, "09-12": {9, 10, 11, 12}}
BLOCKS = [(2010, 2013), (2014, 2017), (2018, 2021), (2022, 2026)]


def pf(s):
    s = np.asarray(s, float); gp = s[s > 0].sum(); gl = -s[s < 0].sum()
    return round(gp / gl, 2) if gl > 0 else 0.0


def book(d, side, mult, win, gap):
    m = d[(d.gap <= gap) & d.dir.isin(side) & d.fh.isin(WINS[win])].copy()
    S = np.maximum(np.round(mult * m.adr.values / TICK) * TICK, FLOOR)
    move = np.where(m.mae_pts.values >= S, -S, m.eod_move.values)
    m["gross"] = move * PT; m["net"] = m.gross - COMM - SLIP
    m["Rg"] = m.gross / (S * PT); m["Rn"] = m.net / (S * PT)
    return m


def main():
    d = pd.read_csv(CSV); d = d[d.with_trend].copy(); d["fh"] = d.fill_hour.astype(int)

    configs = [
        ("FROZEN both 0.30 09-13 g.54", {"L", "S"}, 0.30, "09-13", 0.54),
        ("LONG 0.30 09-13 g.54",        {"L"},      0.30, "09-13", 0.54),
        ("LONG 0.30 09-13 NOGAP",       {"L"},      0.30, "09-13", 99),
        ("LONG 0.40 09-13 NOGAP",       {"L"},      0.40, "09-13", 99),
        ("LONG 0.30 09-12 NOGAP",       {"L"},      0.30, "09-12", 99),
    ]

    for name, side, mult, win, gap in configs:
        m = book(d, side, mult, win, gap)
        print(f"\n===== {name} =====   (n={len(m)}, full: grossR {m.Rg.sum():+.0f} netR {m.Rn.sum():+.0f} "
              f"grossPF {pf(m.gross)} netPF {pf(m.net)})")
        print(f"  {'block':<12}{'n':>4}{'grossMeanR':>11}{'netMeanR':>10}{'grossPF':>8}{'netPF':>7}{'net$':>9}")
        for (y0, y1) in BLOCKS:
            b = m[(m.yr >= y0) & (m.yr <= y1)]
            if not len(b):
                continue
            print(f"  {f'{y0}-{y1}':<12}{len(b):>4}{b.Rg.mean():>+11.3f}{b.Rn.mean():>+10.3f}"
                  f"{pf(b.gross):>8.2f}{pf(b.net):>7.2f}{b.net.sum():>+9,.0f}")

    print("\nKEY: a config positive in GROSS meanR across ALL 4 blocks = a real structural edge")
    print("(the clean-room WFA's 1.10 was then optimization noise). If gross flips negative in")
    print("early low-vol blocks, the edge genuinely isn't there pre-2018.")


if __name__ == "__main__":
    main()
