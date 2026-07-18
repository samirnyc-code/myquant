"""Stop/target sweep for the neg-GEX-morning CR fade (S73). Same 18 entries
(signal unchanged); only exits vary. Purpose = ROBUSTNESS CHECK: a real edge
stays positive across most of the grid; a fluke lives in one lucky cell.
NOT for picking the max cell (that would overfit n=18)."""
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
FRIC, CUTOFF = 1.25, "10:30"
STOPS = [3, 4, 5, 6, 8, 10]
TGTS = [6, 8, 10, 12, 15, 20]


def load():
    lv = pd.read_csv(ROOT / "data" / "menthorq" / "levels_history.csv")
    lv = lv[lv.symbol == "ES"].copy(); lv["date"] = lv.date.astype(str)
    b = pd.read_parquet(ROOT / "data" / "bars" / "_continuous_unadj.parquet")
    b["DateTime"] = pd.to_datetime(b["DateTime"]); b["date"] = b.DateTime.dt.strftime("%Y-%m-%d")
    b["hm"] = b.DateTime.dt.strftime("%H:%M")
    gi = pd.read_csv(ROOT / "data" / "menthorq" / "gex_insights_ES1.csv").sort_values("date")
    gi["date"] = gi.date.astype(str)
    return lv, b, gi


def entries(lv, bars, gi):
    levels = {r.date: r for r in lv.itertuples()}
    out = []
    for d in sorted(set(bars.date)):
        if d not in levels or not np.isfinite(levels[d].cr):
            continue
        p = gi[gi.date < d]
        if p.empty or p.iloc[-1].gex >= 0:
            continue
        day = bars[bars.date == d].reset_index(drop=True)
        if len(day) < 10:
            continue
        npre = int((day.hm <= CUTOFF).sum())
        H, L, Cl = day.High.values, day.Low.values, day.Close.values
        cr = levels[d].cr
        ti = None
        for i in range(1, npre):  # approach-from-below required (user catch)
            k = max(0, i - 3)
            if np.max(Cl[k:i]) < cr - 0.5 and (L[i] - 1.0) <= cr <= (H[i] + 1.0):
                ti = i
                break
        if ti is not None:
            out.append((d, day, cr, ti))
    return out


def pnl_for(day, cr, ti, stop, tgt):
    H, L, Cl = day.High.values, day.Low.values, day.Close.values
    sp, tp = cr + stop, cr - tgt
    for j in range(ti + 1, len(day)):
        if H[j] >= sp:
            return -stop - FRIC
        if L[j] <= tp:
            return tgt - FRIC
    return (cr - Cl[-1]) - FRIC


def main():
    lv, bars, gi = load()
    ents = entries(lv, bars, gi)
    print(f"{len(ents)} entries (signal fixed)\n")
    print("E[$/trade] matrix (rows=stop, cols=target); win% in parens\n")
    hdr = "stop\\tgt " + "".join(f"{t:>14d}" for t in TGTS)
    print(hdr)
    pos_cells = 0
    for s in STOPS:
        cells = []
        for t in TGTS:
            p = np.array([pnl_for(day, cr, ti, s, t) for _, day, cr, ti in ents])
            e = p.mean() * 50
            pos_cells += e > 0
            cells.append(f"{e:+7.0f} ({(p > 0).mean() * 100:3.0f}%)")
        print(f"{s:>7}  " + " ".join(f"{c:>13s}" for c in cells))
    total = len(STOPS) * len(TGTS)
    print(f"\npositive cells: {pos_cells}/{total} ({pos_cells / total * 100:.0f}%)")
    print("read: robust edge = mostly green; one lucky corner = fragile/overfit.")


if __name__ == "__main__":
    main()
