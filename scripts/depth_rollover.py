"""depth_rollover.py — convert finished depth CSVs to parquet in the daily halt.

Runs in the CME maintenance break (16:00-17:00 CT) when nothing is streaming and the
files are closed. Raw CSV is the right LIVE format — appendable, crash-safe, trivially
recoverable — but it is the wrong ARCHIVE format: ES book events run to hundreds of MB a
day, and at that rate the disk is the binding constraint on how long we can record.

Parquet is columnar and compresses the repetitive numeric columns hard (typically ~10x),
and reads far faster because a query touches only the columns it needs.

SAFETY: the CSV is deleted ONLY after the parquet is written, re-read, and its row count
matches. A conversion that cannot be verified leaves the CSV alone — losing depth data is
unrecoverable, wasting disk is not.

    python scripts/depth_rollover.py                # convert every finished day
    python scripts/depth_rollover.py --keep-csv     # convert but keep the CSV
    python scripts/depth_rollover.py --dry-run
"""
from __future__ import annotations

import argparse
import datetime as dt
import sys
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parent.parent
DEPTH = ROOT / "data" / "depth"
# dedicated PRIVATE archive repo (off-machine backup of irreplaceable, un-repurchasable
# market data). Immutable daily parquet -> git stays lean. Pushed if a remote exists.
ARCHIVE = Path.home() / "myquant-data"
DTYPES = {"Ev": "category", "Side": "category", "Pos": "int16",
          "Price": "float32", "Size": "int32"}


def chicago_today() -> dt.date:
    try:
        from zoneinfo import ZoneInfo
        return dt.datetime.now(ZoneInfo("America/Chicago")).date()
    except Exception:
        return (dt.datetime.utcnow() - dt.timedelta(hours=5)).date()


def finished_csvs(today: dt.date):
    """Every depth CSV whose session is over. Today's file is still being written -
    the recorder holds it open and rows are still arriving, so it is never touched."""
    out = []
    for p in sorted(DEPTH.glob("*_depth_*.csv")):
        try:
            # "ES_09-26_depth_2026-07-19" -> the part after the LAST "_depth_"
            d = dt.date.fromisoformat(p.stem.rsplit("_depth_", 1)[1])
        except Exception:
            continue
        if d < today:
            out.append((d, p))
    return out


def convert(csv: Path, keep_csv: bool, dry: bool) -> dict:
    pq = csv.with_suffix(".parquet")
    mb_in = csv.stat().st_size / 1e6
    if pq.exists():
        return {"file": csv.name, "status": "skip", "note": "parquet already exists"}
    if dry:
        return {"file": csv.name, "status": "dry", "note": f"{mb_in:,.1f}MB -> parquet"}

    try:
        df = pd.read_csv(csv, dtype=DTYPES, on_bad_lines="skip")
        df["Time"] = pd.to_datetime(df["Time"], errors="coerce")
        n_in = len(df)
        df.to_parquet(pq, engine="pyarrow", compression="zstd", index=False)
        # verify by RE-READING: a written file is not a correct file
        n_out = len(pd.read_parquet(pq, columns=["Ev"]))
    except Exception as e:
        if pq.exists():
            pq.unlink()
        return {"file": csv.name, "status": "FAIL", "note": f"{type(e).__name__}: {e}"}

    if n_out != n_in:
        pq.unlink()
        return {"file": csv.name, "status": "FAIL",
                "note": f"row mismatch {n_in:,} -> {n_out:,}; CSV kept"}

    mb_out = pq.stat().st_size / 1e6
    ratio = mb_in / mb_out if mb_out else 0
    if not keep_csv:
        csv.unlink()
    return {"file": csv.name, "status": "ok", "rows": n_in,
            "note": f"{mb_in:,.1f}MB -> {mb_out:,.1f}MB ({ratio:.1f}x)"
                    f"{'' if keep_csv else ', CSV removed'}"}


def archive(pq: Path) -> str:
    """Copy a verified parquet into the private data repo and commit (push if a remote
    exists). Runs in the halt right after rollover, so the off-machine backup happens the
    same hour the parquet is made. Never fatal - a failed backup must not lose the parquet."""
    import shutil
    import subprocess
    if not (ARCHIVE / ".git").exists():
        return "no archive repo"
    try:
        dest_dir = ARCHIVE / "depth"
        dest_dir.mkdir(parents=True, exist_ok=True)
        dest = dest_dir / pq.name
        if dest.exists():
            return "already archived"
        shutil.copy2(pq, dest)

        def g(*a):
            return subprocess.run(["git", "-C", str(ARCHIVE), *a], capture_output=True,
                                  text=True, timeout=120, creationflags=0x08000000)
        g("add", f"depth/{pq.name}")
        g("commit", "-m", f"depth: {pq.stem}")
        if g("remote").stdout.strip():
            return "committed + pushed" if g("push", "-q").returncode == 0 \
                else "committed (push failed)"
        return "committed (no remote yet)"
    except Exception as e:
        return f"archive failed: {type(e).__name__}"


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--keep-csv", action="store_true")
    ap.add_argument("--dry-run", action="store_true")
    a = ap.parse_args()

    today = chicago_today()
    todo = finished_csvs(today)
    print(f"depth rollover — {today} CT — {len(todo)} finished file(s)")
    if not todo:
        print("  nothing to convert (today's file is still being written)")
        return 0

    bad = 0
    for d, csv in todo:
        r = convert(csv, a.keep_csv, a.dry_run)
        if r["status"] == "FAIL":
            bad += 1
        note = r["note"]
        if r["status"] == "ok" and not a.dry_run:
            note += "  ·  archive: " + archive(csv.with_suffix(".parquet"))
        print(f"  [{r['status']:>4}] {r['file']:<34} {note}")
    print(f"\n{len(todo)-bad}/{len(todo)} converted")
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())
