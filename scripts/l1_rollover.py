"""l1_rollover.py — convert finished L1 tape CSVs to parquet in the daily halt.

Sibling of depth_rollover.py, for the L1 tape+best-bid/ask recorder (L1TapeRecorderAddOn.cs).
Runs in the CME maintenance break (16:00-17:00 CT) when nothing is streaming and the day's
file is closed. Raw CSV is the right LIVE format (appendable, crash-safe); parquet is the
right ARCHIVE format (columnar, ~10x smaller, column-selective reads).

SAFETY: the CSV is deleted ONLY after the parquet is written, re-read, and its row count
matches. A conversion that cannot be verified leaves the CSV alone — losing tape data is
unrecoverable (L1 gaps have no local backfill), wasting disk is not.

    python scripts/l1_rollover.py                # convert every finished day
    python scripts/l1_rollover.py --keep-csv     # convert but keep the CSV
    python scripts/l1_rollover.py --dry-run
"""
from __future__ import annotations

import argparse
import datetime as dt
import sys
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parent.parent
L1 = ROOT / "data" / "l1_tape"
#   (base dir under data/, backup subdir in the archive repo)
SOURCES = [(L1, "l1_tape")]
# dedicated PRIVATE archive repo (off-machine backup of irreplaceable market data).
ARCHIVE = Path.home() / "myquant-data"
# Ev: T tape / B best-bid / A best-ask / C connection marker. Side is a spare (blank on L1).
DTYPES = {"Ev": "category", "Side": "category", "Aggr": "category",
          "Price": "float32", "Size": "int32"}


def chicago_now() -> dt.datetime:
    try:
        from zoneinfo import ZoneInfo
        return dt.datetime.now(ZoneInfo("America/Chicago"))
    except Exception:
        return dt.datetime.utcnow() - dt.timedelta(hours=5)


def finished_csvs(base: Path, now: dt.datetime):
    """Every L1 CSV under `base` whose session is over.

    Files carry the TRADE DATE (session template: 17:00 CT belongs to the next day), so in
    the 16:00-17:00 halt TODAY's file is already closed (session ended 16:00; the recorder
    reopens a NEW tomorrow-dated file at 17:00). The open-for-append guard in convert() is
    the final backstop for the actively-written current file."""
    today = now.date()
    halted = now.time() >= dt.time(16, 1)
    out = []
    if not base.exists():
        return out
    for p in sorted(base.glob("*_l1_*.csv")):
        try:
            # "ES_09-26_l1_2026-09-16" -> the part after the LAST "_l1_"
            d = dt.date.fromisoformat(p.stem.rsplit("_l1_", 1)[1])
        except Exception:
            continue
        if d < today or (d == today and halted):
            out.append((d, p))
    return out


def convert(csv: Path, keep_csv: bool, dry: bool) -> dict:
    pq = csv.with_suffix(".parquet")
    mb_in = csv.stat().st_size / 1e6
    if pq.exists():
        return {"file": csv.name, "status": "skip", "note": "parquet already exists"}
    # HARD GUARD: NT8's StreamWriter denies other writers. If we can't open for append, the
    # recorder still holds this file — converting now would freeze a PARTIAL parquet while
    # rows keep arriving. Skip; the recorder's halt-timer releases the file at 16:00.
    try:
        open(csv, "ab").close()
    except PermissionError:
        return {"file": csv.name, "status": "skip", "note": "still open by recorder - not touching"}
    if dry:
        return {"file": csv.name, "status": "dry", "note": f"{mb_in:,.1f}MB -> parquet"}

    try:
        df = pd.read_csv(csv, dtype=DTYPES, on_bad_lines="skip")
        df["Time"] = pd.to_datetime(df["Time"], errors="coerce")
        n_in = len(df)
        df.to_parquet(pq, engine="pyarrow", compression="zstd", index=False)
        n_out = len(pd.read_parquet(pq, columns=["Ev"]))   # verify by RE-READING
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


def archive(pq: Path, sub: str = "l1_tape") -> str:
    """Copy a verified parquet into the private data repo under `sub/` and commit (push if a
    remote exists). Never fatal — a failed backup must not lose the parquet."""
    import shutil
    import subprocess
    if not (ARCHIVE / ".git").exists():
        return "no archive repo"
    try:
        dest_dir = ARCHIVE / sub
        dest_dir.mkdir(parents=True, exist_ok=True)
        dest = dest_dir / pq.name
        if dest.exists():
            return "already archived"
        shutil.copy2(pq, dest)

        def g(*a):
            return subprocess.run(["git", "-C", str(ARCHIVE), *a], capture_output=True,
                                  text=True, timeout=120, creationflags=0x08000000)
        g("add", f"{sub}/{pq.name}")
        g("commit", "-m", f"{sub}: {pq.stem}")
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

    now = chicago_now()
    todo = [(base, sub, d, csv) for base, sub in SOURCES
            for d, csv in finished_csvs(base, now)]
    print(f"l1 rollover — {now:%Y-%m-%d %H:%M} CT — {len(todo)} finished file(s)")
    if not todo:
        print("  nothing to convert (no closed-session files yet)")
        return 0

    bad = 0
    for base, sub, d, csv in todo:
        r = convert(csv, a.keep_csv, a.dry_run)
        if r["status"] == "FAIL":
            bad += 1
        note = r["note"]
        if r["status"] == "ok" and not a.dry_run:
            note += "  ·  archive: " + archive(csv.with_suffix(".parquet"), sub)
        print(f"  [{r['status']:>4}] {sub:<8} {r['file']:<32} {note}")
    print(f"\n{len(todo)-bad}/{len(todo)} converted")
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())
