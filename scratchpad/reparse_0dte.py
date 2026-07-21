"""Reparse the saved 0DTE backfill raw dumps (no new QUIN queries)."""
import csv
import glob
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))
from mq_quin_backfill_0dte import OUT, parse

rows = {}
for f in sorted(glob.glob(str(Path(__file__).resolve().parent.parent / "data" / "menthorq" / "harvest" / "backfill_0dte_raw" / "*.txt"))):
    sym = Path(f).name.split("_")[0]
    for r in parse(open(f, encoding="utf-8").read()):
        rows[(r[0], sym)] = r
with open(OUT, "w", newline="") as fh:
    w = csv.writer(fh)
    w.writerow(["date", "symbol", "cr0", "ps0", "hvl0", "gw0", "d1_min", "d1_max"])
    for (d, sym), r in sorted(rows.items()):
        w.writerow([d, sym, *r[1:]])
print(f"reparsed {len(rows)} rows -> {OUT}")
