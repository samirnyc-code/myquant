"""backup_live_data.py — S134: independent (non-git) backup of the live desk's
runtime state, now that data/_catalog, data/options_log, data/options_sim,
data/gexlog, and data/vix_daily.csv are gitignored (see .gitignore S134 note).
Untracking them fixed the actual bug (a stray git op could silently revert
them); this is the second, complementary layer — cheap insurance against a
non-git failure (disk issue, a bad script overwriting a file, fat-fingered
delete) that untracking doesn't cover.

Copies the 4 live directories + vix_daily.csv into a timestamped folder under
BACKUP_ROOT, then prunes backups older than KEEP_DAYS. Read-only with
respect to the source — never deletes or modifies anything being backed up.

    python scripts/backup_live_data.py
"""
from __future__ import annotations
import datetime as dt
import shutil
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
BACKUP_ROOT = Path(r"C:\Users\Admin\myquant_backups")
KEEP_DAYS = 14

SOURCES = [
    ROOT / "data" / "_catalog",
    ROOT / "data" / "options_log",
    ROOT / "data" / "options_sim",
    ROOT / "data" / "gexlog",
    ROOT / "data" / "vix_daily.csv",
]


def main():
    stamp = dt.datetime.now().strftime("%Y%m%d_%H%M%S")
    dest = BACKUP_ROOT / stamp
    dest.mkdir(parents=True, exist_ok=True)

    for src in SOURCES:
        if not src.exists():
            print(f"  ! missing, skipped: {src}")
            continue
        target = dest / src.name
        if src.is_dir():
            shutil.copytree(src, target, dirs_exist_ok=True)
        else:
            shutil.copy2(src, target)
        print(f"  {src} -> {target}")

    cutoff = dt.datetime.now() - dt.timedelta(days=KEEP_DAYS)
    removed = 0
    if BACKUP_ROOT.exists():
        for d in BACKUP_ROOT.iterdir():
            if not d.is_dir():
                continue
            try:
                ts = dt.datetime.strptime(d.name, "%Y%m%d_%H%M%S")
            except ValueError:
                continue
            if ts < cutoff:
                shutil.rmtree(d, ignore_errors=True)
                removed += 1

    print(f"\nbackup done -> {dest}")
    if removed:
        print(f"pruned {removed} backup(s) older than {KEEP_DAYS} days")


if __name__ == "__main__":
    main()
