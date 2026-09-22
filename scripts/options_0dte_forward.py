"""options_0dte_forward.py — FORWARD paper sim of IC + BPS, from today on.

Separate from the historical backtest. Runs each SETTLED session from START_DATE
onward, UNFILTERED (takes every day), open-anchored, and records that day's gap%
in the ledger so we can slice by gap later. Baseline = hold-to-expiry (no early
exits yet — profit-taking / leg management are the next layer).

Data: uses the parsed parquet if present (historical days), else pulls that single
day live via timeseries.get_range (cheap ~$0.01/day; only works once the day has
settled to historical — pending days are skipped and retried next run).

Ledger: data/options_0dte/forward_pnl.csv  (idempotent; skips dates already logged)
Run daily: .venv/Scripts/python.exe scripts/options_0dte_forward.py
"""
from __future__ import annotations
import csv
import json
import math
from pathlib import Path
import datetime as dt

import databento as db
import pandas as pd

ROOT = Path(__file__).resolve().parent.parent
KEYFILE = Path(r"C:\Users\Admin\AppData\Local\myquant\databento.json")
PARSED = ROOT / "data" / "databento" / "0dte_parsed"
SPX = ROOT / "data" / "spx_daily_ohlc.csv"
VIX = ROOT / "data" / "vix_daily_full.csv"
LEDGER = ROOT / "data" / "options_0dte" / "forward_pnl.csv"

START_DATE = "2026-08-05"          # forward sim begins the day after the backtest window
SQRT252 = math.sqrt(252)
WIDTH = 25
COMM_LEG = 1.30
MULT = 100
BAND = 120                         # +/- pts around prior close (covers EM + wing + buffer)


def load_daily():
    spx = pd.read_csv(SPX, parse_dates=["Date"]).set_index("Date")
    vix = pd.read_csv(VIX, parse_dates=["Date"]).set_index("Date")["vix"]
    d = spx.join(vix, how="inner")
    d["prior_close"] = d["Close"].shift(1)
    d["prior_vix"] = d["vix"].shift(1)
    return d


def construct(date_iso, center, band=BAND, step=5):
    d = dt.date.fromisoformat(date_iso); yy = d.strftime("%y%m%d")
    lo = int((center - band) // step * step); hi = int((center + band) // step * step)
    out = []
    for k in range(lo, hi + step, step):
        kk = f"{int(k*1000):08d}"
        out += [f"SPXW  {yy}C{kk}", f"SPXW  {yy}P{kk}"]
    return out


def parse_symbol(sym):
    core = sym.replace("SPXW", "").strip()
    return core[6], int(core[7:]) / 1000.0        # right, strike


def get_day_quotes(client, date_iso, center):
    """Return {(strike,right):(bid,ask)} at 09:30 ET. Parquet if present else live pull."""
    pq = PARSED / f"{date_iso}.parquet"
    if pq.exists():
        df = pd.read_parquet(pq)
        df["ts"] = pd.to_datetime(df["ts"], utc=True)
    else:
        syms = construct(date_iso, center)
        end = (dt.date.fromisoformat(date_iso) + dt.timedelta(days=1)).isoformat()
        data = client.timeseries.get_range(dataset="OPRA.PILLAR", schema="cbbo-1m",
                                           symbols=syms, stype_in="raw_symbol",
                                           start=date_iso, end=end)
        d = data.to_df(map_symbols=True)
        if d.empty:
            return None
        rp = d["symbol"].map(parse_symbol)
        df = pd.DataFrame({"ts": d.index, "right": [x[0] for x in rp],
                           "strike": [x[1] for x in rp],
                           "bid": d["bid_px_00"].values, "ask": d["ask_px_00"].values})
    t = pd.Timestamp(f"{date_iso} 09:30", tz="America/New_York").tz_convert("UTC")
    sub = df[df["ts"] >= t]
    if sub.empty:
        return None
    snap = df[df["ts"] == sub["ts"].iloc[0]]
    return {(r.strike, r.right): (r.bid, r.ask) for r in snap.itertuples()}


def credit(q, ks, kl, right):
    s = q.get((ks, right)); l = q.get((kl, right))
    if not s or not l:
        return None
    bs, as_, bl, al = s[0], s[1], l[0], l[1]
    if any(v != v for v in (bs, as_, bl, al)) or bs <= 0 or as_ <= 0:
        return None
    return (bs - al, (bs + as_) / 2 - (bl + al) / 2)   # cross, mid


def leg_loss(cl, ks, right):
    return min(max((ks - cl) if right == "P" else (cl - ks), 0.0), WIDTH)


def main():
    key = json.load(open(KEYFILE, encoding="utf-8-sig"))["key"]
    client = db.Historical(key)
    daily = load_daily()

    logged = set()
    if LEDGER.exists():
        logged = set(pd.read_csv(LEDGER)["date"].astype(str))

    # settled sessions we can attempt: in daily index, >= START, < today, not logged
    today = daily.index.max()
    targets = [d for d in daily.index if d >= pd.Timestamp(START_DATE) and str(d.date()) not in logged]
    if not targets:
        print("forward sim: no new settled sessions to log."); return

    rows = []
    for date in targets:
        r = daily.loc[date]
        pc, pv, op, cl = r["prior_close"], r["prior_vix"], r["Open"], r["Close"]
        if any(pd.isna(x) for x in (pc, pv, op, cl)):
            continue
        try:
            q = get_day_quotes(client, str(date.date()), pc)
        except Exception as e:
            print(f"  {date.date()} pending/err ({str(e)[:50]}) — retry next run"); continue
        if q is None:
            print(f"  {date.date()} no quotes yet — retry next run"); continue
        strikes = sorted({k for k, _ in q})
        em = pc * (pv / 100) / SQRT252
        gap = (op - pc) / pc * 100
        snap = lambda tgt: min(strikes, key=lambda s: abs(s - tgt))
        lo, hi = snap(op - em), snap(op + em)          # open-anchored edges

        rec = {"date": str(date.date()), "gap_pct": round(gap, 3), "vix_prior": round(pv, 2),
               "em": round(em, 1), "open": round(op, 1), "close": round(cl, 1),
               "em_low": lo, "em_high": hi}
        # BPS
        cb = credit(q, lo, snap(lo - WIDTH), "P")
        # IC = BPS + BCS
        cc = credit(q, hi, snap(hi + WIDTH), "C")
        for tag, legs in [("bps", [("P", lo)]), ("ic", [("P", lo), ("C", hi)])]:
            crs = [credit(q, ks, snap(ks - WIDTH) if rt == "P" else snap(ks + WIDTH), rt)
                   for rt, ks in legs]
            if any(c is None for c in crs):
                rec[f"{tag}_pnl_mid"] = ""; rec[f"{tag}_pnl_cross"] = ""; continue
            cross = sum(c[0] for c in crs); mid = sum(c[1] for c in crs)
            loss = sum(leg_loss(cl, ks, rt) for rt, ks in legs)
            comm = COMM_LEG * 2 * len(legs) / MULT
            rec[f"{tag}_credit_mid"] = round(mid, 2)
            rec[f"{tag}_pnl_mid"] = round((mid - loss - comm) * MULT, 2)
            rec[f"{tag}_pnl_cross"] = round((cross - loss - comm) * MULT, 2)
        rows.append(rec)
        print(f"  logged {date.date()}  gap {gap:+.2f}%  "
              f"IC ${rec.get('ic_pnl_mid','-')}  BPS ${rec.get('bps_pnl_mid','-')}")

    if not rows:
        return
    new = pd.DataFrame(rows)
    if LEDGER.exists():
        new = pd.concat([pd.read_csv(LEDGER), new], ignore_index=True)
    new.to_csv(LEDGER, index=False)
    # running totals
    for tag in ("ic", "bps"):
        col = pd.to_numeric(new[f"{tag}_pnl_mid"], errors="coerce")
        print(f"{tag.upper()} forward: {col.notna().sum()} days, cum mid ${col.sum():.0f}")
    print(f"ledger -> {LEDGER}")


if __name__ == "__main__":
    main()
