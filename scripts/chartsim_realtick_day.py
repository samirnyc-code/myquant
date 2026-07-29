"""chartsim_realtick_day.py — build a ChartSim (book_review) day JSON from the REAL
continuous ticks (data/ticks_continuous/<date>.parquet), using the SAME phase machine
that was verified pivot-identical to the NT RegimePhaseMachine indicator.

Unlike book_review_prep.py (Databento 5m + proxy ticks), this uses the real
tick-granularity continuous contract, so the pivots shown match NT exactly.

  python scripts/chartsim_realtick_day.py 2026-07-28 [more dates...]

Writes data/annotations/book_review/<date>.json (bars/regime/pivots/obs/ibs/prior/ib)
and inserts the date into index.json so it appears in the ChartSim day selector.
Trades are left empty (this view is the engine/pivots, not the 2E book).
"""
import sys, json
from pathlib import Path
from bisect import bisect_right
import numpy as np, pandas as pd

WT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(WT / "scripts"))
from regime_second_entry_study import phase_transitions   # noqa: E402
TICKS = Path(r"c:/Users/Admin/myquant/data/ticks_continuous")
OUT = WT / "data" / "annotations" / "book_review"


def bars_from_ticks(ds):
    t = pd.read_parquet(TICKS / f"{ds}.parquet", columns=["DateTime", "Price"]).sort_values("DateTime").set_index("DateTime")
    o = t["Price"].resample("5min", label="left", closed="left").first()
    h = t["Price"].resample("5min", label="left", closed="left").max()
    l = t["Price"].resample("5min", label="left", closed="left").min()
    c = t["Price"].resample("5min", label="left", closed="left").last()
    bars = pd.DataFrame({"O": o, "H": h, "L": l, "C": c})
    bars["C"] = bars["C"].ffill()
    for col in ("O", "H", "L"):
        bars[col] = bars[col].fillna(bars["C"])
    return bars.reset_index(), t


def daily_close(ds):
    """RTH close of a stored tick-day (for prior close / sma20)."""
    p = TICKS / f"{ds}.parquet"
    if not p.exists():
        return None
    t = pd.read_parquet(p, columns=["Price"])
    return float(t["Price"].iloc[-1]) if len(t) else None


def build(ds):
    if not (TICKS / f"{ds}.parquet").exists():
        print(f"! {ds}: no real ticks — skip"); return None
    bars, t = bars_from_ticks(ds)
    n = len(bars); H = bars["H"].values; L = bars["L"].values; C = bars["C"].values; O = bars["O"].values
    b0 = bars["DateTime"].iloc[0]
    tt = t.reset_index(); tt["b"] = ((tt["DateTime"] - b0).dt.total_seconds() // 300).astype(int)
    tt = tt[(tt.b >= 0) & (tt.b < n)]
    tP = tt["Price"].values.astype(float); tbar = tt["b"].values.astype(int)

    tr = {}
    trans = phase_transitions(H, L, n, tP, tbar, trace=tr)
    tr_ix = [x for (x, _) in trans]; tr_md = [m for (_, m) in trans]
    seg = []
    for i in range(n):
        z = int(np.searchsorted(tbar, i, "right"))
        mode = tr_md[bisect_right(tr_ix, z - 1) - 1] if z else "NEUTRAL"
        if seg and seg[-1]["mode"] == mode:
            seg[-1]["to"] = i
        else:
            seg.append({"from": i, "to": i, "mode": mode})
    pivots = [{"b": int(p["bar"]), "side": p["side"], "tag": p["tag"],
               "lab": (p.get("majlab") or p.get("disp") or p["tag"]).upper(),
               "major": p.get("major") is not None}
              for p in tr.get("piv", []) if 0 <= p["bar"] < n]
    for _s in ("H", "L"):
        _f = next((q for q in pivots if q["side"] == _s), None)
        if _f:
            _f["lab"] = "O" + _s; _f["open"] = True; _f["major"] = True

    # continuous EMA20 seeded across prior stored days (for the EMA overlay)
    alldays = sorted(p.stem for p in TICKS.glob("2*.parquet") if p.stem <= ds)
    hist = alldays[-25:]
    closes = []
    for d in hist:
        bd, _ = bars_from_ticks(d)
        closes += list(bd["C"].values)
    ema = pd.Series(closes).ewm(span=20, adjust=False).mean().values[-n:]

    bars_out = [[i, pd.Timestamp(bars.DateTime.values[i]).strftime("%H:%M"),
                 round(float(O[i]), 2), round(float(H[i]), 2), round(float(L[i]), 2),
                 round(float(C[i]), 2), round(float(ema[i]), 2)] for i in range(n)]
    obs = [i for i in range(1, n) if H[i] >= H[i - 1] and L[i] <= L[i - 1] and (H[i] > H[i - 1] or L[i] < L[i - 1])]
    ibs = [i for i in range(1, n) if H[i] <= H[i - 1] and L[i] >= L[i - 1]]

    # prior day + sma20 from stored tick-days
    prior_day = alldays[alldays.index(ds) - 1] if alldays.index(ds) > 0 else None
    pC = daily_close(prior_day) if prior_day else None
    pH = pL = None; ptail = []
    if prior_day:
        pbars, _ = bars_from_ticks(prior_day)
        pH = round(float(pbars["H"].max()), 2); pL = round(float(pbars["L"].min()), 2)
        pt = pbars.tail(20)
        ptail = [[round(float(r.O), 2), round(float(r.H), 2), round(float(r.L), 2), round(float(r.C), 2),
                  0.0, pd.Timestamp(r.DateTime).strftime("%H:%M")] for r in pt.itertuples()]
    prior20 = [daily_close(d) for d in alldays[max(0, alldays.index(ds) - 20):alldays.index(ds)]]
    prior20 = [x for x in prior20 if x]
    sma20 = round(float(np.mean(prior20)), 2) if len(prior20) >= 20 else None
    gapPct = round((O[0] - pC) / pC * 100, 3) if pC else None

    ibmask = bars.DateTime.dt.strftime("%H:%M").between("08:30", "09:29")
    ib = bars[ibmask]
    rec = {
        "date": ds, "bars": bars_out, "regime": seg, "trades": [], "prior_tail": ptail,
        "pivots": pivots, "obs": obs, "ibs": ibs, "today_open": round(float(O[0]), 2),
        "sma20": sma20,
        "prior": {"H": pH, "L": pL, "C": round(pC, 2) if pC else None,
                  "gap_pts": round(float(O[0] - pC), 2) if pC else None, "gap_pct": gapPct},
        "ib": {"hi": round(float(ib.H.max()), 2), "lo": round(float(ib.L.min()), 2)} if len(ib) else None,
        "skipTD": False, "adr10": None, "source": "real-ticks",
    }
    (OUT / f"{ds}.json").write_text(json.dumps(rec))
    print(f"  {ds}: {n} bars, {len(pivots)} pivots, {len(seg)} regime segs -> {ds}.json")
    return {"date": ds, "n_trades": 0, "n_in_book": 0, "net": 0.0, "skipTD": False}


def main():
    dates = sys.argv[1:] or ["2026-07-28"]
    idxf = OUT / "index.json"
    index = json.loads(idxf.read_text()) if idxf.exists() else []
    bydate = {x["date"]: x for x in index}
    for ds in dates:
        r = build(ds)
        if r:
            bydate[ds] = r
    index = [bydate[k] for k in sorted(bydate)]
    idxf.write_text(json.dumps(index))
    print(f"index.json now {len(index)} days (through {index[-1]['date']})")


if __name__ == "__main__":
    main()
