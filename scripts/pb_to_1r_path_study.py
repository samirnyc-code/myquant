"""PB->1R path study (headless).

For every MC CC signal: walk the day's ticks AFTER the signal-bar close and
classify the path relative to three levels defined off the raw signal geometry
(E1 = SignalPrice, Stop = StopPrice, R = |E1-Stop|):

    PB level  = E1 - sgn*0.5*R      (50% pullback toward stop)
    Target    = E1 + sgn*1.0*R      (original 1R of the FIRST entry)
    Stop      = E1 - sgn*1.0*R      (= StopPrice)

Buckets (mutually exclusive):
    clean_win   : Target touched BEFORE PB is ever touched (ran straight to 1R)
    pb_then_1r  : PB touched first, then Target reached before Stop   <-- headline
    pb_then_stop: PB touched first, then Stop reached before Target
    eod         : not resolved by session close (marked to close)
        - clean_eod : never pulled back to PB, never hit target
        - pb_eod    : pulled back to PB, then neither target nor stop

PnL policy = the 2-leg scale-in (leg2 added at PB), single contract per leg:
    clean_win   : +1.0R         (leg1 only)
    pb_then_1r  : +2.5R         (leg1 +1.0R, leg2 +1.5R)
    pb_then_stop: -1.5R         (leg1 -1.0R, leg2 -0.5R)
    *_eod       : mark every open leg to session close
Costs: $5 commission + 1 tick ($12.50) slippage per leg = $17.50/leg.
1R in $ = R_points * $50 (ES: $50/pt) per contract.

Also reports the no-scale-in single-leg 1R baseline for contrast.
"""
from __future__ import annotations
import sys
import gc
from pathlib import Path
import numpy as np
import pandas as pd

_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(_ROOT))
import massive  # noqa: E402

_SIGNALS = _ROOT / "saved_signals" / "ba_signals_mc.parquet"

PT_VALUE   = 50.0      # $ per ES point, per contract
LEG_COST   = 17.50     # $5 commission + 1 tick ($12.50) slippage per leg
TICK       = 0.25


def log(m): print(f"[pb1r] {m}", flush=True)


def classify(prices: np.ndarray, e1: float, stop_px: float, is_long: bool):
    """Return (bucket, exit_price_for_eod). prices = ticks strictly after entry."""
    if prices.size == 0:
        return "no_ticks", np.nan
    R = abs(e1 - stop_px)
    if R <= 0:
        return "bad_R", np.nan
    sgn = 1.0 if is_long else -1.0
    pb   = e1 - sgn * 0.5 * R
    tgt  = e1 + sgn * 1.0 * R
    stp  = e1 - sgn * 1.0 * R

    if is_long:
        pb_hit  = prices <= pb
        tgt_hit = prices >= tgt
        stop_hit = prices <= stp
    else:
        pb_hit  = prices >= pb
        tgt_hit = prices <= tgt
        stop_hit = prices >= stp

    i_pb  = int(np.argmax(pb_hit))  if pb_hit.any()  else None
    i_tgt = int(np.argmax(tgt_hit)) if tgt_hit.any() else None

    # Clean win: target reached before any pullback to PB
    if i_tgt is not None and (i_pb is None or i_tgt < i_pb):
        return "clean_win", np.nan
    # Never pulled back, never hit target -> clean EOD
    if i_pb is None:
        return "clean_eod", float(prices[-1])

    # PB touched first. Look strictly after the PB tick for target vs stop.
    j = i_pb + 1
    post_tgt  = tgt_hit[j:]
    post_stop = stop_hit[j:]
    k_tgt  = int(np.argmax(post_tgt))  if post_tgt.any()  else None
    k_stop = int(np.argmax(post_stop)) if post_stop.any() else None
    if k_tgt is not None and (k_stop is None or k_tgt < k_stop):
        return "pb_then_1r", np.nan
    if k_stop is not None and (k_tgt is None or k_stop < k_tgt):
        return "pb_then_stop", np.nan
    return "pb_eod", float(prices[-1])


def pnl_scalein(bucket, e1, stop_px, is_long, eod_px):
    """$ PnL for the scale-in policy."""
    R = abs(e1 - stop_px)
    sgn = 1.0 if is_long else -1.0
    pb = e1 - sgn * 0.5 * R
    if bucket == "clean_win":
        return 1.0 * R * PT_VALUE - LEG_COST
    if bucket == "pb_then_1r":
        return 2.5 * R * PT_VALUE - 2 * LEG_COST
    if bucket == "pb_then_stop":
        return -1.5 * R * PT_VALUE - 2 * LEG_COST
    if bucket == "clean_eod":
        return sgn * (eod_px - e1) * PT_VALUE - LEG_COST
    if bucket == "pb_eod":
        leg1 = sgn * (eod_px - e1) * PT_VALUE
        leg2 = sgn * (eod_px - pb) * PT_VALUE
        return leg1 + leg2 - 2 * LEG_COST
    return 0.0


def pnl_singleleg(bucket, e1, stop_px, is_long, eod_px):
    """$ PnL with NO scale-in: just leg1, 1R target, EOD exit."""
    R = abs(e1 - stop_px)
    sgn = 1.0 if is_long else -1.0
    if bucket in ("clean_win", "pb_then_1r"):
        # leg1 reached its 1R target in both
        return 1.0 * R * PT_VALUE - LEG_COST
    if bucket == "pb_then_stop":
        return -1.0 * R * PT_VALUE - LEG_COST
    # any EOD bucket -> leg1 marked to close
    return sgn * (eod_px - e1) * PT_VALUE - LEG_COST


def main():
    log("Loading signals...")
    sig = pd.read_parquet(_SIGNALS)
    sig["DateTime"] = pd.to_datetime(sig["DateTime"])
    sig["is_long"] = sig["Direction"].astype(str).str.upper().str.startswith("L")
    log(f"  {len(sig)} signals, CC types: {dict(sig['SignalType'].value_counts())}")

    rows = []
    days = sorted(sig["Date"].unique())
    for di, d in enumerate(days):
        ss = sig[sig["Date"] == d]
        try:
            t = massive.load_continuous_ticks(pd.to_datetime(d).date())
        except Exception as e:
            log(f"  !! {d}: {e}")
            continue
        if t is None or t.empty:
            continue
        t = t.sort_values("DateTime").reset_index(drop=True)
        tt = t["DateTime"].to_numpy()
        tp = t["Price"].to_numpy(dtype=float)
        for _, s in ss.iterrows():
            start = np.searchsorted(tt, np.datetime64(s["DateTime"]), side="right")
            prices = tp[start:]
            bucket, eod_px = classify(prices, float(s["SignalPrice"]),
                                      float(s["StopPrice"]), bool(s["is_long"]))
            rows.append({
                "SignalType": s["SignalType"],
                "is_long": bool(s["is_long"]),
                "R_pts": abs(float(s["SignalPrice"]) - float(s["StopPrice"])),
                "bucket": bucket,
                "pnl_si": pnl_scalein(bucket, float(s["SignalPrice"]),
                                      float(s["StopPrice"]), bool(s["is_long"]), eod_px),
                "pnl_sl": pnl_singleleg(bucket, float(s["SignalPrice"]),
                                        float(s["StopPrice"]), bool(s["is_long"]), eod_px),
            })
        del t, tt, tp
        gc.collect()
        if (di + 1) % 250 == 0:
            log(f"  ...{di+1}/{len(days)} days, {len(rows)} signals processed")

    r = pd.DataFrame(rows)
    r.to_parquet(_ROOT / "docs" / "living" / "pb_to_1r_paths.parquet")
    log(f"Done. {len(r)} classified. Saved paths parquet.\n")

    order = ["clean_win", "pb_then_1r", "pb_then_stop", "clean_eod", "pb_eod",
             "no_ticks", "bad_R"]

    def block(df, label):
        n = len(df)
        if n == 0:
            print(f"{label}: 0"); return
        vc = df["bucket"].value_counts()
        pb_touched = df["bucket"].isin(["pb_then_1r", "pb_then_stop", "pb_eod"]).sum()
        si = df["pnl_si"]; sl = df["pnl_sl"]
        si_win = (si > 0).mean() * 100
        pf_num = si[si > 0].sum(); pf_den = -si[si < 0].sum()
        pf = pf_num / pf_den if pf_den > 0 else float("inf")
        R_d = df["R_pts"] * PT_VALUE
        exp_r = (si / R_d.replace(0, np.nan)).mean()
        print(f"\n=== {label}  (N={n}) ===")
        for b in order:
            c = int(vc.get(b, 0))
            if c:
                print(f"   {b:<13} {c:>5}  {100*c/n:>5.1f}%")
        print(f"   {'PB touched':<13} {pb_touched:>5}  {100*pb_touched/n:>5.1f}%")
        pb1r = int(vc.get("pb_then_1r", 0))
        print(f"   --> PB then 1R : {pb1r}  ({100*pb1r/n:.1f}% of all, "
              f"{100*pb1r/pb_touched if pb_touched else 0:.1f}% of PB-touched)")
        print(f"   SCALE-IN  : net=${si.sum():>12,.0f}  exp=${si.mean():>8.2f}  "
              f"expR={exp_r:>7.3f}  win={si_win:>5.1f}%  PF={pf:>4.2f}")
        sl_win = (sl > 0).mean() * 100
        slpf_n = sl[sl > 0].sum(); slpf_d = -sl[sl < 0].sum()
        slpf = slpf_n / slpf_d if slpf_d > 0 else float("inf")
        print(f"   SINGLE-LEG: net=${sl.sum():>12,.0f}  exp=${sl.mean():>8.2f}  "
              f"win={sl_win:>5.1f}%  PF={slpf:>4.2f}")

    print("=" * 80)
    print("PB -> 1R PATH STUDY  (50% pullback then original 1R, all MC CC signals)")
    print("costs: $5 comm + 1 tick slip per leg; 1R$ = R_pts * $50")
    print("=" * 80)
    block(r, "ALL")
    for cc in ["CC1", "CC2", "CC3", "CC4", "CC5"]:
        block(r[r["SignalType"] == cc], cc)


if __name__ == "__main__":
    main()
