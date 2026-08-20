"""reconcile_0dte_settlement.py — verify a day's 0DTE settled P&L against the TRUE
SPX cash close, because on 2026-08-19 spot_feed froze at 7717.6 (~12:30 CT) and the
sim may have settled the 0DTE intrinsics off that stale value instead of the real
15:00 CT close.

For each spread held to expiry it recomputes the cost-to-close at:
  (a) the FROZEN spot the sim likely used, and
  (b) the TRUE ^GSPC close fetched fresh from Yahoo,
and reports the per-trade P&L correction. Cross-checks the true close against the ES
tick trove at 15:00 CT. Saves a dated CSV.

    python scripts/reconcile_0dte_settlement.py --date 2026-08-19 --frozen 7717.6
"""
from __future__ import annotations
import argparse, datetime as dt, json, urllib.request
from pathlib import Path
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
SIM = ROOT / "data" / "options_sim"


def yahoo_close(date_iso: str):
    """True ^GSPC close for the given date, fetched fresh (not the stale cache)."""
    try:
        req = urllib.request.Request(
            "https://query1.finance.yahoo.com/v8/finance/chart/%5EGSPC?range=1mo&interval=1d",
            headers={"User-Agent": "Mozilla/5.0"})
        r = json.loads(urllib.request.urlopen(req, timeout=30).read())["chart"]["result"][0]
        ts, q = r["timestamp"], r["indicators"]["quote"][0]
        from zoneinfo import ZoneInfo
        et = ZoneInfo("America/New_York")
        for t, c in zip(ts, q["close"]):
            if c is None:
                continue
            if dt.datetime.fromtimestamp(t, et).date().isoformat() == date_iso:
                return round(float(c), 2)
    except Exception as e:
        print(f"! yahoo fetch failed: {e!r}")
    return None


def es_trove_close(date_iso: str):
    """ES last RTH tick price as an independent cross-check (not settlement-exact)."""
    p = ROOT / "data" / "ticks_continuous" / f"{date_iso}.parquet"
    if not p.exists():
        return None, None
    t = pd.read_parquet(p)
    return round(float(t.Price.iloc[-1]), 2), str(t.index[-1] if t.index.name else t.iloc[-1].name)


def cost_to_close(legs, S: float) -> float:
    """Net intrinsic owed to flatten the position at settlement price S, per share.
    short legs you pay their intrinsic; long legs you receive it."""
    tot = 0.0
    for lg in legs:
        k = float(lg["strike"])
        intr = max(S - k, 0.0) if lg["right"] == "C" else max(k - S, 0.0)
        tot += intr if lg["side"] == "sell" else -intr
    return tot


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--date", default="2026-08-19")
    ap.add_argument("--frozen", type=float, default=7717.6, help="stale spot the sim likely used")
    a = ap.parse_args()
    date_iso = a.date
    day = date_iso.replace("-", "")

    true_S = yahoo_close(date_iso)
    es_S, es_ts = es_trove_close(date_iso)
    print(f"TRUE ^GSPC close {date_iso}: {true_S}")
    print(f"frozen spot sim used        : {a.frozen}")
    print(f"ES trove last tick (x-check): {es_S}  @ {es_ts}")
    if true_S is None:
        print("cannot reconcile without the true close — abort.")
        return
    print(f"spot error: {true_S - a.frozen:+.2f} pts\n")

    d = pd.read_parquet(ROOT / "data" / "options_log" / "trades.parquet")
    d["e"] = pd.to_datetime(d["entry_dt"], errors="coerce")
    t = d[(d["e"] >= date_iso) & (d["e"] < (dt.date.fromisoformat(date_iso) + dt.timedelta(1)).isoformat())].copy()

    rows, dtot = [], 0.0
    for _, r in t.iterrows():
        legs = r["legs"] if isinstance(r["legs"], list) else json.loads(r["legs"])
        # closed intraday (exit before 15:00 CT / 16:00 ET) is a real fill, not a settlement — skip
        exitdt = pd.to_datetime(r["exit_dt"])
        settled = exitdt is not None and exitdt.strftime("%H:%M") in ("16:00", "15:00")
        if not settled:
            rows.append(dict(strategy=r["strategy_id"], logged=round(r["pnl"], 1),
                             note="intraday exit — unaffected", corrected=round(r["pnl"], 1), delta=0.0))
            continue
        c_frozen = cost_to_close(legs, a.frozen)
        c_true = cost_to_close(legs, true_S)
        delta = round((c_frozen - c_true) * 100, 1)      # +ve = sim under-charged, real P&L lower
        rows.append(dict(strategy=r["strategy_id"], logged=round(r["pnl"], 1),
                         note=f"settle {a.frozen}->{true_S}",
                         corrected=round(r["pnl"] + delta, 1), delta=delta))
        dtot += delta

    out = pd.DataFrame(rows)
    print(out.to_string(index=False))
    print(f"\nlogged total    : {t.pnl.sum():+.1f}")
    print(f"correction      : {dtot:+.1f}")
    print(f"TRUE day P&L    : {t.pnl.sum() + dtot:+.1f}")
    f = SIM / f"reconcile_settlement_{day}.csv"
    out.to_csv(f, index=False)
    print(f"\nsaved -> {f.relative_to(ROOT)}")


if __name__ == "__main__":
    main()
