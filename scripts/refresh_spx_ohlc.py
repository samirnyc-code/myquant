"""refresh_spx_ohlc.py — pull SPX cash OHLC (^GSPC) from Yahoo, full history to today.

Writes data/spx_daily_ohlc.csv with Date,Open,High,Low,Close. Fixes the two gaps the
0DTE work needs: (1) an OPEN column (none of the existing SPX files have it), and
(2) coverage through today (spx_daily_full.csv ended 2026-07-17). Free, no Databento.

Run: .venv/Scripts/python.exe scripts/refresh_spx_ohlc.py
"""
from __future__ import annotations
from pathlib import Path
import yfinance as yf

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "data" / "spx_daily_ohlc.csv"


def main():
    df = yf.download("^GSPC", start="1990-01-01", auto_adjust=False, progress=False)
    df = df[["Open", "High", "Low", "Close"]].round(2)
    df.columns = ["Open", "High", "Low", "Close"]
    df.index.name = "Date"
    df.to_csv(OUT)
    print(f"wrote {OUT}  {len(df)} rows  {df.index.min().date()} -> {df.index.max().date()}")
    print(df.tail(3).to_string())

    # VIX too (EM needs it; vix_daily_full.csv was stale at 2026-07-17)
    v = yf.download("^VIX", start="1990-01-01", auto_adjust=False, progress=False)[["Close"]].round(2)
    v.columns = ["vix"]
    v.index.name = "Date"
    vout = ROOT / "data" / "vix_daily_full.csv"
    v.to_csv(vout)
    print(f"wrote {vout}  {len(v)} rows  -> {v.index.max().date()}  last vix {v['vix'].iloc[-1]}")


if __name__ == "__main__":
    main()
