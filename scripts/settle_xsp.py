"""settle_xsp.py — cash-settle the XSP mirror book's expired 0DTE at the official close.

The SPX postmortem settles the SPX book; nothing settles the parallel XSP mirror book, so
its held-to-expiry positions sit open. This closes them the same way: XSP settles at the
XSP index close (= SPX close / 10), intrinsic per leg, with the REAL XSP commission
($1.22/contract, captured from live fills). Positions the mirror already closed early
(traded-to-close) are untouched. Idempotent.

    python scripts/settle_xsp.py [--date 2026-08-24] [--dry]
"""
from __future__ import annotations
import argparse, datetime as dt, json, sys, urllib.request
from pathlib import Path
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
SIM = ROOT / "data" / "options_sim"
sys.path.insert(0, str(ROOT / "scripts"))
XSP_FEE = 1.22   # $/contract — IB ACTUAL, from live-fill commissionReport


def spx_close(date_iso):
    """Official SPX close: spx_daily_yahoo cache (postmortem fills it), else fetch ^GSPC,
    else last recorded tape spot."""
    f = SIM / "spx_daily_yahoo.csv"
    try:
        d = pd.read_csv(f); row = d[d.Date == date_iso]
        if len(row):
            return float(row.Close.iloc[0]), "yahoo cache"
    except Exception:
        pass
    try:
        req = urllib.request.Request(
            "https://query1.finance.yahoo.com/v8/finance/chart/%5EGSPC?range=5d&interval=1d",
            headers={"User-Agent": "Mozilla/5.0"})
        r = json.loads(urllib.request.urlopen(req, timeout=20).read())["chart"]["result"][0]
        from zoneinfo import ZoneInfo
        et = ZoneInfo("America/New_York")
        for t, c in zip(r["timestamp"], r["indicators"]["quote"][0]["close"]):
            if c and dt.datetime.fromtimestamp(t, et).date().isoformat() == date_iso:
                return float(c), "^GSPC fetch"
    except Exception:
        pass
    tape = SIM / f"chain_{date_iso.replace('-','')}.csv"
    if tape.exists():
        t = pd.read_csv(tape)
        return float(t.groupby("ts_et").spot.first().iloc[-1]), "tape last spot (fallback)"
    return None, "none"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--date", default=dt.date.today().isoformat())
    ap.add_argument("--dry", action="store_true")
    a = ap.parse_args()
    import options_trade_log as tlog

    s_spx, src = spx_close(a.date)
    if s_spx is None:
        print("no SPX close available — cannot settle XSP"); return
    s_xsp = s_spx / 10.0
    print(f"SPX close {s_spx:.2f} ({src}) -> XSP settle {s_xsp:.2f}")

    tlog.set_book("xsp")
    d = tlog.load(); d["e"] = pd.to_datetime(d["entry_dt"], errors="coerce")
    op = d[(d["e"] >= a.date) & (d["e"] < (dt.date.fromisoformat(a.date) + dt.timedelta(1)).isoformat())
           & d.exit_dt.isna()]
    if not len(op):
        print("no open XSP positions to settle."); return
    for _, r in op.iterrows():
        legs = r["legs"] if isinstance(r["legs"], list) else json.loads(r["legs"])
        cost = sum((max(0.0, s_xsp - l["strike"]) if l["right"] == "C" else max(0.0, l["strike"] - s_xsp))
                   * (1 if l["side"] == "sell" else -1) for l in legs)
        cost = max(cost, 0.0)
        fee = len(legs) * int(legs[0].get("qty", 1)) * XSP_FEE
        exit_dt = f"{a.date} 16:00"
        if a.dry:
            pnl = (float(r["credit"]) - cost) * 100 - fee
            print(f"  [dry] {r['strategy_id']}: settle cost {cost:.3f} fee {fee:.2f} -> pnl {pnl:+.1f}")
        else:
            rr = tlog.update_exit(r["trade_id"], exit_dt, round(cost, 3), round(fee, 2),
                                  fill_model="cash_settle", close_reason="expired")
            print(f"  settled {r['strategy_id']}: pnl {rr['pnl']:+.1f}")
    if not a.dry:
        print("XSP book settled.")


if __name__ == "__main__":
    main()
