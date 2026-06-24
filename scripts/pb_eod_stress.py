"""EOD stress test for the PB scale-in add, across depths and session phase.

The add value = leg-2's contribution over PB-touched signals (leg-1 cancels vs
the single-leg baseline). Resolved adds (pb_then_1r / pb_then_stop) are
policy-independent; only the UNRESOLVED pb_eod adds depend on how we mark leg-2:
    close : mark at session close      (optimistic — current model)
    be    : flat leg-2 at its entry    (0)
    stop  : count as a full stop       (worst case)
add value (per depth/policy/phase) = sum over touched (leg2_gross - LEG_COST).
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
PB_LEVELS = [0.25, 0.33, 0.50, 0.66, 0.75]

_PHASES = [("Open", 510, 690), ("Mid", 690, 780), ("Late", 780, 885), ("Close", 885, 915)]
def phase_of(ts):
    m = ts.hour * 60 + ts.minute
    for nm, lo, hi in _PHASES:
        if lo <= m < hi:
            return nm
    return "Other"


def log(m): print(f"[stress] {m}", flush=True)


def buckets_for(prices, e1, stop_px, is_long):
    if prices.size == 0:
        return None, np.nan
    R = abs(e1 - stop_px)
    if R <= 0:
        return None, np.nan
    sgn = 1.0 if is_long else -1.0
    tgt, stp = e1 + sgn * R, e1 - sgn * R
    tgt_hit = (prices >= tgt) if is_long else (prices <= tgt)
    stop_hit = (prices <= stp) if is_long else (prices >= stp)
    i_tgt = int(np.argmax(tgt_hit)) if tgt_hit.any() else None
    out = {}
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
    return out, float(prices[-1])


def main():
    sig = pd.read_parquet(_SIGNALS)
    sig["DateTime"] = pd.to_datetime(sig["DateTime"])
    sig["is_long"] = sig["Direction"].astype(str).str.upper().str.startswith("L")
    ph = sig["DateTime"].apply(phase_of)
    sig["phase2"] = np.where(ph.isin(["Open","Mid"]), "Open+Mid",
                    np.where(ph.isin(["Late","Close"]), "Late+Close", "Other"))

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
            il = bool(s["is_long"])
            b, eod = buckets_for(tp[st:], e1, stp, il)
            if b is None:
                continue
            rec = {"phase2": s["phase2"], "R": abs(e1-stp),
                   "sgn": 1.0 if il else -1.0, "e1": e1, "eod": eod}
            for p in PB_LEVELS:
                rec[f"b_{p}"] = b[p]
            rows.append(rec)
        del t, tt, tp; gc.collect()
        if (di + 1) % 250 == 0:
            log(f"  {di+1}/{len(days)} days")
    r = pd.DataFrame(rows)
    log(f"Done. N={len(r)}\n")

    def add_value(df, p, policy):
        b = df[f"b_{p}"]
        touched = b.isin(["pb_then_1r", "pb_then_stop", "pb_eod"])
        R = df["R"]; sgn = df["sgn"]; pb = df["e1"] - sgn * p * R
        leg2 = pd.Series(0.0, index=df.index)
        leg2[b == "pb_then_1r"]   = (1 + p) * R[b == "pb_then_1r"] * PT_VALUE
        leg2[b == "pb_then_stop"] = -(1 - p) * R[b == "pb_then_stop"] * PT_VALUE
        m = b == "pb_eod"
        if policy == "close":
            leg2[m] = sgn[m] * (df["eod"][m] - pb[m]) * PT_VALUE
        elif policy == "be":
            leg2[m] = 0.0
        elif policy == "stop":
            leg2[m] = -(1 - p) * R[m] * PT_VALUE
        return (leg2[touched] - LEG_COST).sum()

    for scope, df in [("ALL", r), ("Open+Mid", r[r["phase2"] == "Open+Mid"]),
                      ("Late+Close", r[r["phase2"] == "Late+Close"])]:
        print("=" * 78)
        print(f"ADD VALUE ($) — {scope}  (N={len(df)})")
        print(f"{'PB':>6} {'close':>12} {'breakeven':>12} {'stop(worst)':>12}")
        for p in PB_LEVELS:
            print(f"{p:>6.2f} {add_value(df,p,'close'):>+12,.0f} "
                  f"{add_value(df,p,'be'):>+12,.0f} {add_value(df,p,'stop'):>+12,.0f}")
        print()


if __name__ == "__main__":
    main()
