"""
audit_continuous.py — self-contained completeness audit for each instrument's
continuous series. For every business day inside the series' own span that is
MISSING, check the source: if the daily flatfile is absent or has zero RTH ticks
for that instrument, the day is a genuine exchange closure (OK). If it has real
RTH ticks, it's a hole (BUG) that must be fixed.

No ES reference — this uses each instrument's own exchange flatfiles + calendar.
"""
from __future__ import annotations

import datetime as D
import gzip
import io
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

import pandas as pd  # noqa: E402
from instruments import INSTRUMENTS  # noqa: E402

RTH0, RTH1 = D.time(8, 30), D.time(15, 15)


def instr_rth_ticks(spec, cache_dir: Path, ds: str) -> int | None:
    p = cache_dir / f"{ds}.csv.gz"
    if not p.exists():
        return None  # no flatfile -> genuine (nothing to include)
    df = pd.read_csv(io.BytesIO(gzip.open(p, "rb").read()))
    tk = df["ticker"].astype(str)
    m = tk.str.match(rf"^{spec.massive_root}[FGHJKMNQUVXZ]\d$")
    if m.sum() == 0:
        return 0
    sub = df[m]
    dt = (pd.to_datetime(sub["timestamp"], unit="ns", utc=True)
          .dt.tz_convert("America/Chicago").dt.tz_localize(None))
    t = dt.dt.time
    return int(((t >= RTH0) & (t < RTH1)).sum())


def main() -> None:
    for key, spec in INSTRUMENTS.items():
        cont = ROOT / "data" / "bars" / f"_continuous_{key}.parquet"
        if not cont.exists():
            print(f"{key}: no continuous file"); continue
        df = pd.read_parquet(cont, columns=["DateTime"])
        days = set(df["DateTime"].dt.date)
        lo, hi = min(days), max(days)
        bdays = {d.date() for d in pd.bdate_range(lo, hi)}
        missing = sorted(bdays - days)

        cache_dir = ROOT / "data" / spec.gz_subdir
        bugs, genuine = [], 0
        for d in missing:
            n = instr_rth_ticks(spec, cache_dir, d.isoformat())
            if n and n > 100:
                bugs.append((str(d), n))
            else:
                genuine += 1
        flag = "❌ BUGS" if bugs else "✅ clean"
        print(f"{key}: span {lo}..{hi} | {len(days)} days | missing bdays {len(missing)} "
              f"(genuine closures {genuine}, holes {len(bugs)}) {flag}", flush=True)
        for ds, n in bugs:
            print(f"      HOLE {ds}: {n} RTH ticks in source but absent from continuous", flush=True)


if __name__ == "__main__":
    main()
