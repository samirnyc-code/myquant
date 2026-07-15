"""Approach-fade vs touch-fade, done HONESTLY (S73, user request).

Two designs, real fills only:
  TOUCH    : limit at the level. Fills when price TRADES at level (res High>=level).
             Entry = level. Thesis: fade the tag.
  APPROACH : limit TOL(=3pt) short of the level. Fills when price comes within TOL
             (res High>=level-TOL). Entry = level-TOL (a real price price traded
             through). Thesis: the heavy wall rejects the APPROACH; never miss the
             reversal, accept a worse fill.
Both: virgin first approach from the correct side (open on correct side, level not
reached earlier). Stop/target measured in points FROM THE ENTRY PRICE. $50/pt ES etc.
Full per-trade audit printed for the focus market; metrics table for all.

Run: .venv/Scripts/python.exe scripts/approach_fade.py [--tol 3] [--focus ES:cr]
"""
import sys
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
STOP, TGT, FRIC = 8.0, 10.0, 1.25
TOL = float(sys.argv[sys.argv.index("--tol") + 1]) if "--tol" in sys.argv else 3.0
FOCUS = sys.argv[sys.argv.index("--focus") + 1] if "--focus" in sys.argv else "ES:cr"
BARF = {"ES": "_continuous_unadj.parquet", "NQ": "_continuous_NQ_unadj.parquet",
        "GC": "_continuous_GC_unadj.parquet"}
POINT = {"ES": 50, "NQ": 20, "GC": 100}
SCALE = {"ES": 1.0, "NQ": 3.0, "GC": 1.6}  # ~range vs ES, to scale TOL & brackets


def load_lv():
    return pd.read_csv(ROOT / "data" / "menthorq" / "levels_history.csv")


def bars(mkt):
    b = pd.read_parquet(ROOT / "data" / "bars" / BARF[mkt])
    b["DateTime"] = pd.to_datetime(b["DateTime"])
    b["date"] = b.DateTime.dt.strftime("%Y-%m-%d")
    b["hm"] = b.DateTime.dt.strftime("%H:%M")
    return b


def sim(mkt, col, kind, mode, lv, b, sc):
    """mode: 'touch' or 'approach'. Returns list of trade dicts."""
    tol = TOL * sc
    stop, tgt, fric = STOP * sc, TGT * sc, FRIC * sc
    sub = lv[lv.symbol == mkt][["date", col]].dropna()
    lm = {str(r.date): getattr(r, col) for r in sub.itertuples()}
    trades = []
    for d in sorted(set(b.date)):
        if d not in lm:
            continue
        day = b[b.date == d].reset_index(drop=True)
        if len(day) < 10:
            continue
        lvl = lm[d]
        H, L, Cl, O, hm = day.High.values, day.Low.values, day.Close.values, day.Open.values, day.hm.values
        if (kind == "res" and O[0] >= lvl) or (kind == "sup" and O[0] <= lvl):
            continue
        trig = lvl if mode == "touch" else (lvl - tol if kind == "res" else lvl + tol)
        ti = None
        for i in range(1, len(day)):
            reached = (np.max(H[:i]) >= trig) if kind == "res" else (np.min(L[:i]) <= trig)
            hit = (H[i] >= trig) if kind == "res" else (L[i] <= trig)
            if hit and not reached:
                ti = i
                break
        if ti is None:
            continue
        entry = trig
        sp = entry + stop if kind == "res" else entry - stop
        tp = entry - tgt if kind == "res" else entry + tgt
        reason, exit_px = "close", Cl[-1]
        for j in range(ti + 1, len(day)):
            hs = (H[j] >= sp) if kind == "res" else (L[j] <= sp)
            ht = (L[j] <= tp) if kind == "res" else (H[j] >= tp)
            if hs:
                reason, exit_px = "stop", sp; break
            if ht:
                reason, exit_px = "target", tp; break
        pts = ((entry - exit_px) if kind == "res" else (exit_px - entry)) - fric
        trades.append({"date": d, "lvl": lvl, "entry": entry, "reason": reason,
                       "exit_px": exit_px, "pts": pts, "hm": hm[ti], "open": O[0]})
    return trades


def stats(tr, mult):
    if not tr:
        return None
    p = np.array([t["pts"] for t in tr]) * mult
    w, l = p[p > 0], p[p < 0]
    pf = w.sum() / -l.sum() if len(l) else np.inf
    eq = np.cumsum(p); dd = (eq - np.maximum.accumulate(eq)).min()
    return dict(n=len(p), win=round((p > 0).mean() * 100), pf=round(pf, 2),
                exp=round(p.mean()), tot=round(p.sum()), dd=round(dd),
                aw=round(w.mean()) if len(w) else 0, al=round(l.mean()) if len(l) else 0)


def main():
    lv, fm, fc = load_lv(), *FOCUS.split(":")
    print(f"TOL={TOL}pt (scaled per mkt), stop{STOP}/tgt{TGT} from entry, ${FRIC}/RT friction\n")
    print(f"{'mkt':4s} {'lvl':4s} {'mode':9s} {'n':>4s} {'win':>4s} {'PF':>5s} {'exp$':>6s} {'avgW':>6s} {'avgL':>6s} {'tot$':>8s} {'maxDD':>8s}")
    kinds = {"cr": "res", "cr0": "res", "ps": "sup", "ps0": "sup"}
    for mkt in ["ES", "NQ", "GC"]:
        b = bars(mkt); sc = SCALE[mkt]
        for col in ["cr", "ps"]:
            for mode in ["touch", "approach"]:
                tr = sim(mkt, col, kinds[col], mode, lv, b, sc)
                st = stats(tr, POINT[mkt])
                if st:
                    print(f"{mkt:4s} {col:4s} {mode:9s} {st['n']:4d} {st['win']:3d}% {st['pf']:5.2f} "
                          f"{st['exp']:+6d} {st['aw']:+6d} {st['al']:+6d} {st['tot']:+8,} {st['dd']:+8,}")
    # focus audit
    b = bars(fm); sc = SCALE[fm]
    print(f"\n=== TRADE-BY-TRADE AUDIT: {fm} {fc} APPROACH (limit {TOL*sc:.0f}pt short of level) ===")
    print(f"{'date':11s} {'level':>7s} {'open':>8s} {'entry':>8s} {'result':>7s} {'exit':>8s} {'pts':>7s}")
    tr = sim(fm, fc, kinds[fc], "approach", lv, b, sc)
    for t in tr:
        print(f"{t['date']:11s} {t['lvl']:7.0f} {t['open']:8.1f} {t['entry']:8.1f} {t['reason']:>7s} "
              f"{t['exit_px']:8.1f} {t['pts']:+7.2f}")
    st = stats(tr, POINT[fm])
    print(f"  -> n={st['n']} win={st['win']}% PF={st['pf']} exp=${st['exp']} total=${st['tot']:,} maxDD=${st['dd']:,}")


if __name__ == "__main__":
    main()
