"""analyze_account_size.py — capital the SPX 0DTE desk ties up.

For defined-risk spreads the buying-power reduction = max loss = the `collateral` column.
The account must cover the PEAK CONCURRENT collateral (sum of max-loss across every
position open at the same instant). This sweeps each August day's entry/exit events, finds
each day's peak, and reports the August max for (a) the full book and (b) the book with the
EOD strategies removed. Call & put sides are booked as SEPARATE rows, so this SUMS them
(conservative — a broker may net the two sides of one iron condor to max-not-sum, ~halving
it). Read-only; saves a dated per-day CSV.

Run: .venv/Scripts/python.exe scripts/analyze_account_size.py
"""
from __future__ import annotations
import sys
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent))
import options_trade_log as tlog

OUT = Path(__file__).resolve().parents[1] / "data" / "options_sim"


def _side(sid):
    sid = str(sid)
    if sid.endswith("_c") or "bcs" in sid:
        return "call"
    if sid.endswith("_p") or "bps" in sid:
        return "put"
    return "other"


def peak_day(df):
    """Returns (gross, netted) peak concurrent collateral for one day.
    gross  = sum of every open position's max-loss (independent margining).
    netted = max(call-side sum, put-side sum) at each instant — opposing same-expiry
             spreads can't both max-loss, so an iron-condor-aware account nets them."""
    ev = []
    for _, r in df.iterrows():
        s = _side(r.strategy_id)
        ev.append((r.edt, 0, r.coll, s))
        ev.append((r.xdt, 1, -r.coll, s))
    ev.sort(key=lambda x: (x[0], x[1]))
    cur = {"call": 0.0, "put": 0.0, "other": 0.0}
    gross = netted = 0.0
    for _, _k, delta, s in ev:
        cur[s] += delta
        g = cur["call"] + cur["put"] + cur["other"]
        n = max(cur["call"], cur["put"]) + cur["other"]
        gross = max(gross, g)
        netted = max(netted, n)
    return gross, netted


def peaks(df, label):
    df = df.copy()
    df["day"] = df.edt.dt.date
    rows = []
    for day, g in df.groupby("day"):
        gr, ne = peak_day(g)
        rows.append({"day": str(day), "trades": len(g),
                     "peak_gross": round(gr), "peak_netted": round(ne)})
    t = pd.DataFrame(rows)
    print(f"\n=== {label} ===")
    print(f"August PEAK concurrent collateral:  gross ${t.peak_gross.max():,.0f}  |  "
          f"netted ${t.peak_netted.max():,.0f}  (gross on {t.loc[t.peak_gross.idxmax(),'day']})")
    print(f"median daily peak: gross ${t.peak_gross.median():,.0f}  netted ${t.peak_netted.median():,.0f}")
    print(t.sort_values('peak_gross', ascending=False).head(6).to_string(index=False))
    return t


def main():
    d = tlog.load()
    d["coll"] = pd.to_numeric(d["collateral"], errors="coerce")
    d["edt"] = pd.to_datetime(d["entry_dt"], errors="coerce")
    d["xdt"] = pd.to_datetime(d["exit_dt"], errors="coerce")
    aug = d[(d.edt >= "2026-08-01") & (d.edt < "2026-09-01")
            & (d.strategy_id != "incident_orphan") & d.coll.notna() & d.xdt.notna()].copy()

    full = peaks(aug, "FULL BOOK (all strategies)")
    no_eod = peaks(aug[~aug.strategy_id.astype(str).str.startswith("eod")], "WITHOUT EOD BOOK")

    fg, fn = full.peak_gross.max(), full.peak_netted.max()
    eg, en = no_eod.peak_gross.max(), no_eod.peak_netted.max()
    print("\n=== ACCOUNT SIZE (peak concurrent max-loss) ===")
    print(f"Full book   — gross ${fg:,.0f} / netted ${fn:,.0f}  |  +50% buffer on gross ${fg*1.5:,.0f}")
    print(f"No-EOD book — gross ${eg:,.0f} / netted ${en:,.0f}  |  +50% buffer on gross ${eg*1.5:,.0f}")
    print(f"Cutting EOD lowers the gross peak by ${fg-eg:,.0f} ({100*(fg-eg)/fg:.0f}%), "
          f"netted by ${fn-en:,.0f} ({100*(fn-en)/fn:.0f}%).")

    f = OUT / "analysis_account_size_by_day.csv"
    full.assign(book="full").to_csv(f, index=False)
    print(f"\nwrote {f}")


if __name__ == "__main__":
    main()
