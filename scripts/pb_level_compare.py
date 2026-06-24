"""Compare the PB scale-in across pullback depths.

Generalizes the 50% study to PB in {0.25, 0.33, 0.50, 0.66, 0.75, 1.0}R.
For each depth p (leg2 enters p*R below E1 for a long; target = original 1R):
    scale-in win   total = +(2+p)R   (leg1 +1R, leg2 +(1+p)R)
    scale-in loss  total = -(2-p)R   (leg1 -1R, leg2 -(1-p)R)
Leg-2 marginal breakeven hit-rate (gross) = (1-p)/2.

Reports, per depth: PB-touch%, PB->1R% (of all & of touched = add hit-rate),
PB->stop%, scale-in net$, add value over single-leg (which is PB-independent),
plus by-CC add value and the Open+Mid vs Late+Close add hit-rate.
costs: $5 comm + 1 tick ($12.50) slip per leg; 1R$ = R_pts * $50.
"""
from __future__ import annotations
import sys, gc
from pathlib import Path
import numpy as np
import pandas as pd

_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(_ROOT))
try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass
import massive  # noqa: E402

_SIGNALS = _ROOT / "saved_signals" / "ba_signals_mc.parquet"
PT_VALUE, LEG_COST = 50.0, 17.50
PB_LEVELS = [0.25, 0.33, 0.50, 0.66, 0.75, 1.0]

_PHASES = [("Open", 510, 690), ("Mid", 690, 780), ("Late", 780, 885), ("Close", 885, 915)]
def phase_of(ts):
    m = ts.hour * 60 + ts.minute
    for nm, lo, hi in _PHASES:
        if lo <= m < hi:
            return nm
    return "Other"


def log(m): print(f"[pblvl] {m}", flush=True)


def classify_all(prices, e1, stop_px, is_long):
    """Return dict {p: bucket} for every PB level + the leg1-only outcome.
    leg1_out in {win, loss, eod} is PB-independent."""
    out = {}
    if prices.size == 0:
        return None, None, np.nan
    R = abs(e1 - stop_px)
    if R <= 0:
        return None, None, np.nan
    sgn = 1.0 if is_long else -1.0
    tgt = e1 + sgn * R
    stp = e1 - sgn * R
    tgt_hit = (prices >= tgt) if is_long else (prices <= tgt)
    stop_hit = (prices <= stp) if is_long else (prices >= stp)
    i_tgt = int(np.argmax(tgt_hit)) if tgt_hit.any() else None
    i_stop = int(np.argmax(stop_hit)) if stop_hit.any() else None
    # leg1-only (no scale-in) outcome
    if i_tgt is not None and (i_stop is None or i_tgt < i_stop):
        leg1 = "win"
    elif i_stop is not None and (i_tgt is None or i_stop < i_tgt):
        leg1 = "loss"
    else:
        leg1 = "eod"
    eod_px = float(prices[-1])
    for p in PB_LEVELS:
        pb = e1 - sgn * p * R
        pb_hit = (prices <= pb) if is_long else (prices >= pb)
        i_pb = int(np.argmax(pb_hit)) if pb_hit.any() else None
        if i_tgt is not None and (i_pb is None or i_tgt < i_pb):
            out[p] = "clean_win"; continue
        if i_pb is None:
            out[p] = "clean_eod"; continue
        j = i_pb + 1
        pt, ps = tgt_hit[j:], stop_hit[j:]
        k_t = int(np.argmax(pt)) if pt.any() else None
        k_s = int(np.argmax(ps)) if ps.any() else None
        if k_t is not None and (k_s is None or k_t < k_s):
            out[p] = "pb_then_1r"
        elif k_s is not None and (k_t is None or k_s < k_t):
            out[p] = "pb_then_stop"
        else:
            out[p] = "pb_eod"
    return out, leg1, eod_px


def pnl_si(bucket, p, e1, stop_px, is_long, eod_px):
    R = abs(e1 - stop_px); sgn = 1.0 if is_long else -1.0
    pb = e1 - sgn * p * R
    if bucket == "clean_win":   return 1.0 * R * PT_VALUE - LEG_COST
    if bucket == "pb_then_1r":  return (2.0 + p) * R * PT_VALUE - 2 * LEG_COST
    if bucket == "pb_then_stop":return -(2.0 - p) * R * PT_VALUE - 2 * LEG_COST
    if bucket == "clean_eod":   return sgn * (eod_px - e1) * PT_VALUE - LEG_COST
    if bucket == "pb_eod":
        return (sgn*(eod_px-e1) + sgn*(eod_px-pb)) * PT_VALUE - 2 * LEG_COST
    return 0.0


def pnl_leg1(leg1, e1, stop_px, is_long, eod_px):
    R = abs(e1 - stop_px); sgn = 1.0 if is_long else -1.0
    if leg1 == "win":  return 1.0 * R * PT_VALUE - LEG_COST
    if leg1 == "loss": return -1.0 * R * PT_VALUE - LEG_COST
    return sgn * (eod_px - e1) * PT_VALUE - LEG_COST


def main():
    sig = pd.read_parquet(_SIGNALS)
    sig["DateTime"] = pd.to_datetime(sig["DateTime"])
    sig["is_long"] = sig["Direction"].astype(str).str.upper().str.startswith("L")
    sig["phase"] = sig["DateTime"].apply(phase_of)
    sig["phase2"] = np.where(sig["phase"].isin(["Open","Mid"]), "Open+Mid",
                    np.where(sig["phase"].isin(["Late","Close"]), "Late+Close", "Other"))

    rows = []
    idx_by_date = {d: g.index.to_numpy() for d, g in sig.groupby("Date")}
    days = sorted(idx_by_date)
    for di, d in enumerate(days):
        try:
            t = massive.load_continuous_ticks(pd.to_datetime(d).date())
        except Exception:
            continue
        if t is None or t.empty:
            continue
        t = t.sort_values("DateTime")
        tt = t["DateTime"].to_numpy(); tp = t["Price"].to_numpy(dtype=float)
        for i in idx_by_date[d]:
            s = sig.loc[i]
            st = np.searchsorted(tt, np.datetime64(s["DateTime"]), side="right")
            e1, stp = float(s["SignalPrice"]), float(s["StopPrice"])
            buckets, leg1, eod = classify_all(tp[st:], e1, stp, bool(s["is_long"]))
            if buckets is None:
                continue
            rec = {"CC": s["SignalType"], "phase2": s["phase2"], "leg1": leg1,
                   "pnl_leg1": pnl_leg1(leg1, e1, stp, bool(s["is_long"]), eod)}
            for p in PB_LEVELS:
                rec[f"b_{p}"] = buckets[p]
                rec[f"pnl_{p}"] = pnl_si(buckets[p], p, e1, stp, bool(s["is_long"]), eod)
            rows.append(rec)
        del t, tt, tp; gc.collect()
        if (di + 1) % 250 == 0:
            log(f"  {di+1}/{len(days)} days, {len(rows)} signals")

    r = pd.DataFrame(rows)
    r.to_parquet(_ROOT / "docs" / "living" / "pb_level_compare.parquet")
    N = len(r)
    sl_net = r["pnl_leg1"].sum()
    log(f"Done. N={N}. Single-leg baseline net=${sl_net:,.0f} (PB-independent)\n")

    print("=" * 100)
    print(f"PB-DEPTH COMPARISON — all MC signals (N={N}).  Single-leg baseline net=${sl_net:,.0f}")
    print("=" * 100)
    print(f"{'PB':>5} {'touch%':>7} {'PB→1R%all':>9} {'hit%(1R/touch)':>14} "
          f"{'BEhit%':>7} {'PB→stop%':>8} {'SI net$':>11} {'addVal$':>10} "
          f"{'exp$':>7} {'expR':>7}")
    for p in PB_LEVELS:
        b = r[f"b_{p}"]; pnl = r[f"pnl_{p}"]
        touch = b.isin(["pb_then_1r","pb_then_stop","pb_eod"]).sum()
        p1r = (b == "pb_then_1r").sum()
        pstop = (b == "pb_then_stop").sum()
        hit = 100*p1r/touch if touch else 0
        be = (1-p)/2*100
        net = pnl.sum(); add = net - sl_net
        Rd = (r["pnl_leg1"]*0)  # placeholder
        # expR: pnl / (single R$) — approximate using leg1 win magnitude+cost back out
        print(f"{p:>5.2f} {100*touch/N:>6.1f}% {100*p1r/N:>8.1f}% {hit:>13.1f}% "
              f"{be:>6.1f}% {100*pstop/N:>7.1f}% {net:>11,.0f} {add:>+10,.0f} "
              f"{pnl.mean():>7.2f} {'':>7}")

    print("\n## Add value ($ over single-leg) by CC × PB depth")
    print(f"{'CC':>5} " + "".join(f"{p:>10.2f}" for p in PB_LEVELS))
    for cc in ["CC1","CC2","CC3","CC4","CC5"]:
        g = r[r["CC"] == cc]
        slc = g["pnl_leg1"].sum()
        line = f"{cc:>5} "
        for p in PB_LEVELS:
            line += f"{g[f'pnl_{p}'].sum()-slc:>+10,.0f}"
        print(line)

    print("\n## Add hit-rate (PB→1R / PB-touched) by session phase × PB depth")
    print(f"{'phase':>11} " + "".join(f"{p:>9.2f}" for p in PB_LEVELS))
    for ph in ["Open+Mid", "Late+Close"]:
        g = r[r["phase2"] == ph]
        line = f"{ph:>11} "
        for p in PB_LEVELS:
            b = g[f"b_{p}"]
            touch = b.isin(["pb_then_1r","pb_then_stop","pb_eod"]).sum()
            p1r = (b == "pb_then_1r").sum()
            line += f"{(100*p1r/touch if touch else 0):>8.1f}%"
        print(line)

    print("\n## Add value ($) by session phase × PB depth")
    print(f"{'phase':>11} " + "".join(f"{p:>10.2f}" for p in PB_LEVELS))
    for ph in ["Open+Mid", "Late+Close"]:
        g = r[r["phase2"] == ph]
        slc = g["pnl_leg1"].sum()
        line = f"{ph:>11} "
        for p in PB_LEVELS:
            line += f"{g[f'pnl_{p}'].sum()-slc:>+10,.0f}"
        print(line)


if __name__ == "__main__":
    main()
