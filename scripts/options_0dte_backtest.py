"""options_0dte_backtest.py — 0DTE SPXW premium-selling backtest (desk policy).

Replicates the live desk's four 0DTE premium-selling structures, entered at the open
off the VIX expected-move (EM) band, run TWO ways per the user's ask:
  - CLOSE-anchored band: center = prior cash close
  - OPEN-anchored  band: center = today's cash open   (same EM halfwidth)
so we can compare and study the gap (open - prior_close) effect.

Structures (25-wide, from gameplan execution policy):
  bps  = bull put  spread : short put @ em_low,  long put  @ em_low-25
  bcs  = bear call spread : short call@ em_high, long call @ em_high+25
  ic   = iron condor      : bps + bcs
  ifly = iron fly         : short put & call @ ATM (band center), 25 wings

EM = prior_close * (VIX_prior/100) / sqrt(252)   [gexlog production formula]

Fills: conservative — sell shorts @ bid, buy longs @ ask (cross the spread).
Entry: first 1-min snapshot >= 09:30 ET. P&L computed two ways:
  - pnl_exp : hold to expiry, PM-settled at SPX cash close (needs no exit quote)
  - pnl_1545: close the structure at the 15:45 ET snapshot (spread mid, cross back)
Commissions: $1.30 / contract / leg.

Out: data/options_0dte/trades_all.csv  (one row per date x structure x anchor)
Run: .venv/Scripts/python.exe scripts/options_0dte_backtest.py
"""
from __future__ import annotations
import csv
import glob
from pathlib import Path
import math

import pandas as pd

ROOT = Path(__file__).resolve().parent.parent
PARSED = ROOT / "data" / "databento" / "0dte_parsed"
SPX = ROOT / "data" / "spx_daily_ohlc.csv"
VIX = ROOT / "data" / "vix_daily_full.csv"
OUTDIR = ROOT / "data" / "options_0dte"
OUTDIR.mkdir(parents=True, exist_ok=True)

SQRT252 = math.sqrt(252)          # 15.8745
WIDTH = 25
COMMISSION = 1.30                 # per contract per leg
MULT = 100                        # SPX option multiplier


def load_daily():
    spx = pd.read_csv(SPX, parse_dates=["Date"]).set_index("Date")
    vix = pd.read_csv(VIX, parse_dates=["Date"]).set_index("Date")["vix"]
    d = spx.join(vix, how="inner")
    d["prior_close"] = d["Close"].shift(1)
    d["prior_vix"] = d["vix"].shift(1)
    return d


def snap(strikes, target):
    """nearest available strike to target."""
    return min(strikes, key=lambda s: abs(s - target))


def quote_at(day_df, et_time_str):
    """the 1-min snapshot nearest (>=) et_time_str; returns {(strike,right):(bid,ask)}."""
    t = pd.Timestamp(f"{day_df['ts'].iloc[0].date()} {et_time_str}", tz="America/New_York")
    tt = t.tz_convert("UTC")
    sub = day_df[day_df["ts"] >= tt]
    if sub.empty:
        return None, None
    ts0 = sub["ts"].iloc[0]
    snap_df = day_df[day_df["ts"] == ts0]
    q = {(r.strike, r.right): (r.bid, r.ask) for r in snap_df.itertuples()}
    return q, ts0


def vspread_credit(q, k_short, k_long, right):
    """Returns (credit_cross, credit_mid) or None.
    cross = short bid - long ask (worst fill); mid = short mid - long mid (fair fill)."""
    s = q.get((k_short, right)); l = q.get((k_long, right))
    if not s or not l:
        return None
    bid_s, ask_s = s; bid_l, ask_l = l
    vals = [bid_s, ask_s, bid_l, ask_l]
    if any(v is None or v != v for v in vals):   # reject NaN/None quotes
        return None
    if bid_s <= 0 or ask_s <= 0:                  # short must be a real, tradeable quote
        return None
    cross = bid_s - ask_l
    mid = (bid_s + ask_s) / 2 - (bid_l + ask_l) / 2
    return cross, mid


def vspread_exit_debit(q, k_short, k_long, right):
    """debit to close = short ask - long bid (cross back)."""
    s = q.get((k_short, right)); l = q.get((k_long, right))
    if not s or not l:
        return None
    return s[1] - l[0]


def put_loss(close, k_short):   # points lost on a put short at expiry, capped by WIDTH
    return min(max(k_short - close, 0.0), WIDTH)


def call_loss(close, k_short):
    return min(max(close - k_short, 0.0), WIDTH)


def main():
    daily = load_daily()
    files = sorted(glob.glob(str(PARSED / "*.parquet")))
    print(f"{len(files)} parsed days")

    rows = []
    for f in files:
        date = pd.Timestamp(Path(f).stem)
        if date not in daily.index:
            continue
        row = daily.loc[date]
        pc, pv, op, cl = row["prior_close"], row["prior_vix"], row["Open"], row["Close"]
        if any(pd.isna(x) for x in (pc, pv, op, cl)):
            continue
        em = pc * (pv / 100) / SQRT252
        gap_pct = (op - pc) / pc * 100

        day = pd.read_parquet(f)
        day["ts"] = pd.to_datetime(day["ts"], utc=True)
        strikes = sorted(day["strike"].unique())
        if len(strikes) < 10:
            continue
        q_open, ts_open = quote_at(day, "09:30")
        q_1545, _ = quote_at(day, "15:45")
        if q_open is None:
            continue

        for anchor, center in (("close", pc), ("open", op)):
            em_low = snap(strikes, center - em)
            em_high = snap(strikes, center + em)
            atm = snap(strikes, center)

            defs = {
                "bps":  [("P", em_low,  em_low - WIDTH)],
                "bcs":  [("C", em_high, em_high + WIDTH)],
                "ic":   [("P", em_low,  em_low - WIDTH), ("C", em_high, em_high + WIDTH)],
                "ifly": [("P", atm,     atm - WIDTH),    ("C", atm,     atm + WIDTH)],
            }
            for strat, legs in defs.items():
                cr_cross = cr_mid = 0.0; ok = True; legcount = 0
                for right, ks, kl in legs:
                    kl = snap(strikes, kl)
                    c = vspread_credit(q_open, ks, kl, right)
                    if c is None:
                        ok = False; break
                    cr_cross += c[0]; cr_mid += c[1]; legcount += 2
                if not ok or cr_mid <= 0:
                    continue
                # expiry intrinsic loss (same regardless of fill)
                loss = 0.0
                for right, ks, kl in legs:
                    loss += put_loss(cl, ks) if right == "P" else call_loss(cl, ks)
                comm = COMMISSION * legcount / MULT
                pnl_cross = (cr_cross - loss - comm) * MULT
                pnl_mid = (cr_mid - loss - comm) * MULT
                rows.append({
                    "date": date.date().isoformat(), "anchor": anchor, "strat": strat,
                    "gap_pct": round(gap_pct, 3), "em": round(em, 1),
                    "prior_close": round(pc, 1), "open": round(op, 1), "close": round(cl, 1),
                    "vix_prior": round(pv, 1), "em_low": em_low, "em_high": em_high, "atm": atm,
                    "credit_mid": round(cr_mid, 2), "credit_cross": round(cr_cross, 2),
                    "pnl_mid": round(pnl_mid, 2), "pnl_cross": round(pnl_cross, 2),
                    "win_mid": int(pnl_mid > 0),
                })

    out = OUTDIR / "trades_all.csv"
    with open(out, "w", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=list(rows[0].keys()))
        w.writeheader(); w.writerows(rows)
    print(f"{len(rows)} trades -> {out}")
    # quick sanity
    df = pd.DataFrame(rows)
    print("MID fill:")
    print(df.groupby(["anchor", "strat"]).agg(
        n=("win_mid", "size"), wr=("win_mid", "mean"),
        mean_mid=("pnl_mid", "mean"), sum_mid=("pnl_mid", "sum"),
        mean_cross=("pnl_cross", "mean")).round(2).to_string())


if __name__ == "__main__":
    main()
