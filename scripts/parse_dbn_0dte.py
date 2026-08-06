"""parse_dbn_0dte.py — DBN cbbo-1m -> lean per-day 0DTE parquet.

Each downloaded file opra-pillar-YYYYMMDD.cbbo-1m.dbn.zst holds ALL symbols that
traded that day (0DTE for that date + the pre-expiry superset). We keep only the
0DTE contracts (OSI expiry == file date), extract strike/right, and write
data/databento/0dte_parsed/<date>.parquet with [ts, strike, right, bid, ask, bsz, asz].

Resumable (skips dates already parsed). Safe to run while the download is still going;
re-run to pick up newly downloaded files.

Run: .venv/Scripts/python.exe scripts/parse_dbn_0dte.py
"""
from __future__ import annotations
import glob
from pathlib import Path
import re

import databento as db
import pandas as pd

ROOT = Path(__file__).resolve().parent.parent
SRC = ROOT / "data" / "databento" / "0dte_spxw_cbbo1m"
OUT = ROOT / "data" / "databento" / "0dte_parsed"
OUT.mkdir(parents=True, exist_ok=True)

FILE_RE = re.compile(r"opra-pillar-(\d{8})\.cbbo-1m\.dbn\.zst$")


def parse_symbol(sym: str):
    """'SPXW  230818C04170000' -> (yymmdd, right, strike_float)."""
    core = sym.replace("SPXW", "").strip()          # '230818C04170000'
    yymmdd, right, strike = core[:6], core[6], core[7:]
    return yymmdd, right, int(strike) / 1000.0


def main():
    files = sorted(glob.glob(str(SRC / "*" / "*.cbbo-1m.dbn.zst")))
    done = {p.stem for p in OUT.glob("*.parquet")}
    print(f"{len(files)} dbn files found, {len(done)} dates already parsed")

    n = 0
    for f in files:
        m = FILE_RE.search(f)
        if not m:
            continue
        ymd = m.group(1)                            # '20230818'
        date_iso = f"{ymd[:4]}-{ymd[4:6]}-{ymd[6:]}"
        if date_iso in done:
            continue
        yy = ymd[2:]                                # '230818'
        try:
            df = db.DBNStore.from_file(f).to_df(map_symbols=True)
        except Exception as e:
            print(f"  {date_iso} READ ERR {str(e)[:60]}"); continue
        if df.empty:
            continue
        parsed = df["symbol"].map(parse_symbol)
        df = df.assign(_ymd=[p[0] for p in parsed],
                       right=[p[1] for p in parsed],
                       strike=[p[2] for p in parsed])
        z = df[df["_ymd"] == yy]                     # 0DTE only
        if z.empty:
            print(f"  {date_iso} no 0DTE rows (n={len(df)})"); continue
        out = pd.DataFrame({
            "ts": z.index,                          # ts_recv, UTC
            "strike": z["strike"].values,
            "right": z["right"].values,
            "bid": z["bid_px_00"].values,
            "ask": z["ask_px_00"].values,
            "bsz": z["bid_sz_00"].values,
            "asz": z["ask_sz_00"].values,
        })
        out.to_parquet(OUT / f"{date_iso}.parquet", compression="zstd")
        n += 1
        if n % 25 == 0:
            print(f"  parsed {n} new dates (latest {date_iso}, {len(out)} rows, "
                  f"{out['strike'].nunique()} strikes)")
    print(f"done: {n} new dates -> {OUT}")


if __name__ == "__main__":
    main()
