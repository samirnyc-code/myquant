"""archive_chain_day.py — EOD close-out for the 0DTE chain tape.

Turns the day's loose recorder CSV into the durable dataset:
  data/options_sim/chain_YYYYMMDD.csv   (what the recorder appends all session)
      -> data/options_tape/chain_YYYYMMDD.parquet     (snappy; query-fast, ~5-10x smaller)
      -> data/options_tape/raw/chain_YYYYMMDD.csv.gz   (gzipped raw, irreplaceable backup)

VERIFIES before it trusts anything: the Parquet row count AND the gzip read-back row
count must both equal the CSV. Only with both verified will --remove-loose delete the
working CSV (keeps data/options_sim/ clean). Idempotent — re-running lands the same files.

Called at EOD by the recorder supervisor after the completeness gate; standalone for
backfill:
    python scripts/archive_chain_day.py --date 2026-08-21          # parquet + gz, keep loose
    python scripts/archive_chain_day.py --date 2026-08-21 --remove-loose
    python scripts/archive_chain_day.py --all --remove-loose        # backfill every day
"""
from __future__ import annotations
import argparse, gzip, io, shutil
from pathlib import Path
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
SIM = ROOT / "data" / "options_sim"
TAPE = ROOT / "data" / "options_tape"
RAW = TAPE / "raw"


def _csv_rows(path: Path) -> int:
    with path.open("rb") as f:
        return max(0, sum(1 for _ in f) - 1)          # minus header


def archive_one(csv: Path, remove_loose: bool = False, verbose: bool = True) -> dict:
    date = csv.stem.replace("chain_", "")
    TAPE.mkdir(parents=True, exist_ok=True)
    RAW.mkdir(parents=True, exist_ok=True)
    pq = TAPE / f"chain_{date}.parquet"
    gz = RAW / f"chain_{date}.csv.gz"

    df = pd.read_csv(csv)
    n_csv = len(df)
    for c in ("spot", "strike", "bid", "ask"):        # numeric columns; ts_et stays string
        if c in df.columns:
            df[c] = pd.to_numeric(df[c], errors="coerce")
    df.to_parquet(pq, index=False, compression="snappy")

    # gzip the raw bytes verbatim (exact backup, not a re-serialization)
    with csv.open("rb") as fi, gzip.open(gz, "wb", compresslevel=6) as fo:
        shutil.copyfileobj(fi, fo)

    # VERIFY both copies before trusting them
    n_pq = len(pd.read_parquet(pq, columns=[df.columns[0]]))
    with gzip.open(gz, "rb") as f:
        n_gz = max(0, sum(1 for _ in io.TextIOWrapper(f)) - 1)
    if n_pq != n_csv or n_gz != n_csv:
        raise SystemExit(f"VERIFY FAILED {date}: csv={n_csv} parquet={n_pq} gz={n_gz} — nothing removed")

    csv_mb, pq_mb, gz_mb = (p.stat().st_size / 1e6 for p in (csv, pq, gz))
    removed = False
    if remove_loose:
        csv.unlink()
        removed = True
    if verbose:
        msg = (f"{date}: {n_csv} rows verified | csv {csv_mb:.2f}MB -> parquet {pq_mb:.2f}MB "
               f"({csv_mb / pq_mb:.1f}x) + gz {gz_mb:.2f}MB")
        msg += "  [loose CSV removed]" if removed else "  [loose CSV kept]"
        print(msg)
    return dict(date=date, rows=n_csv, parquet=str(pq.relative_to(ROOT)),
                gz=str(gz.relative_to(ROOT)), csv_mb=round(csv_mb, 2),
                parquet_mb=round(pq_mb, 2), gz_mb=round(gz_mb, 2),
                compression_x=round(csv_mb / pq_mb, 1), loose_removed=removed)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--date", help="YYYY-MM-DD")
    ap.add_argument("--all", action="store_true", help="every chain_*.csv in options_sim")
    ap.add_argument("--remove-loose", action="store_true",
                    help="delete the working CSV after parquet+gz are BOTH verified")
    a = ap.parse_args()
    if a.all:
        files = sorted(SIM.glob("chain_20*.csv"))
    elif a.date:
        files = [SIM / f"chain_{a.date.replace('-', '')}.csv"]
    else:
        raise SystemExit("pass --date YYYY-MM-DD or --all")
    for csv in files:
        if not csv.exists():
            print(f"skip: {csv.name} not found")
            continue
        archive_one(csv, remove_loose=a.remove_loose)


if __name__ == "__main__":
    main()
