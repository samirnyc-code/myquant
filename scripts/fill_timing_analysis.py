"""fill_timing_analysis.py — answer the timing/size questions behind the fill-realism report.

(1) LATENCY: we don't persist the sim's ORDER-SUBMIT time (that needs the IB Flex "Order Time"
    field, or a submit log). What we CAN measure now: our own recorded fill time
    (orders.csv ts_et = machine wall-clock at the fill callback, ET) vs IB's TRUE execution time
    (Flex dateTime). Their gap = our clock+callback offset — the timestamp uncertainty the at_time
    pull lives with. Reported as a distribution.
(2) SIZE AT TOUCH: the real bid_size/ask_size at each fill (from at_time_results) — the ACTUAL
    number of contracts resting at our price, not just a >=1 flag.

Read-only. Writes a DATED CSV.
  .venv/Scripts/python.exe scripts/fill_timing_analysis.py
"""
from __future__ import annotations
import datetime as dt
import re
from pathlib import Path
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
OL = ROOT / "data" / "options_log"
TD = ROOT / "data" / "thetadata"
SIM = ROOT / "data" / "options_sim"


def _sec(hms: str):
    try:
        h, m, s = str(hms).split(":")
        return int(h) * 3600 + int(m) * 60 + float(s)
    except (ValueError, AttributeError):
        return None


def latency() -> pd.DataFrame:
    """orders.csv (our callback time) vs Flex (IB true exec time), matched by contract+action+nearest."""
    od = pd.read_csv(OL / "orders.csv")
    od = od[od.status == "Filled"].copy()
    fx = pd.read_csv(sorted(OL.glob("ib_flex_executions_*.csv"))[-1])
    fx = fx[fx.symbol.astype(str).str.startswith("SPXW")].drop_duplicates("exec_id")

    # parse flex -> (expiry, right, strike, action, exec_sec, date)
    frows = []
    for _, r in fx.iterrows():
        dtm = str(r.ib_exec_time)
        if ";" not in dtm:
            continue
        ymd, hms = dtm.split(";")
        frows.append({"expiry": ymd, "right": str(r.put_call).upper()[:1],
                      "strike": float(r.strike), "action": str(r.side).upper(),
                      "date": ymd, "exec_sec": int(hms[:2]) * 3600 + int(hms[2:4]) * 60 + int(hms[4:6])})
    F = pd.DataFrame(frows)

    out = []
    for _, r in od.iterrows():
        m = re.match(r"^([A-Z]+)\s+(\d{6})([CP])(\d{8})$", str(r.localSymbol).strip())
        if not m:
            continue
        _, yy, right, k8 = m.groups()
        expiry = "20" + yy
        strike = int(k8) / 1000.0
        action = str(r.action).upper()
        ts = str(r.ts_et)
        our_sec = _sec(ts[11:]) if len(ts) >= 19 else None
        if our_sec is None:
            continue
        cand = F[(F.expiry == expiry) & (F.right == right) & (abs(F.strike - strike) < 1e-6)
                 & (F.action == action)]
        if cand.empty:
            continue
        best = cand.iloc[(cand.exec_sec - our_sec).abs().argmin()]
        out.append({"localSymbol": r.localSymbol, "action": action,
                    "our_ts_et": ts, "our_sec": our_sec, "ib_exec_sec": best.exec_sec,
                    "delta_s": round(our_sec - best.exec_sec, 3)})
    return pd.DataFrame(out)


def size_stats() -> dict:
    at = pd.read_csv(sorted(TD.glob("at_time_results_*.csv"))[-1])
    at = at[at.quote_status == "ok"].copy()
    def touch_size(r):
        return r.ask_size if str(r.side_action).upper() == "BUY" else r.bid_size
    at["touch_size"] = at.apply(touch_size, axis=1)
    s = pd.to_numeric(at.touch_size, errors="coerce").dropna()
    return {"n": len(s), "median": s.median(), "min": s.min(), "max": s.max(),
            "pct_zero": round(100 * (s == 0).mean(), 1), "pct_ge1": round(100 * (s >= 1).mean(), 1),
            "pct_ge10": round(100 * (s >= 10).mean(), 1), "pct_ge_our": round(100 * (s >= 1).mean(), 1)}


def main() -> int:
    lat = latency()
    print("=== LATENCY: our recorded fill time - IB true exec time (seconds) ===")
    if len(lat):
        d = lat.delta_s
        print(f"  matched fills: {len(lat)}")
        print(f"  median: {d.median():+.2f}s   mean: {d.mean():+.2f}s")
        print(f"  p10: {d.quantile(.1):+.2f}s   p90: {d.quantile(.9):+.2f}s   "
              f"min: {d.min():+.2f}s   max: {d.max():+.2f}s")
        print(f"  within +/-1s: {100*(d.abs()<=1).mean():.0f}%   within +/-2s: {100*(d.abs()<=2).mean():.0f}%")
        print("  NOTE: this is our clock+callback offset, NOT order-submit latency (needs Flex 'Order Time').")
    else:
        print("  no matches (orders.csv vs Flex).")
    print("\n=== SIZE AT TOUCH: actual contracts resting at our price ===")
    ss = size_stats()
    print(f"  n={ss['n']}  median={ss['median']:.0f}  min={ss['min']:.0f}  max={ss['max']:.0f}")
    print(f"  size=0: {ss['pct_zero']}%   >=1: {ss['pct_ge1']}%   >=10: {ss['pct_ge10']}%")

    stamp = dt.datetime.now().strftime("%Y%m%d")
    outp = SIM / f"fill_timing_analysis_{stamp}.csv"
    lat.to_csv(outp, index=False)
    print(f"\nsaved -> {outp.relative_to(ROOT)}  ({len(lat)} matched fills)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
