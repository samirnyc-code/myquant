"""data_audit.py — Stage 0a of the tempo/market-state study (S116).

Audits data/ticks_continuous/ (Panama-adjusted ES trade ticks, CT-naive,
RTH [08:30,15:15)) before the 2000t feature build:

  - per day: tick count, volume, first/last tick time, non-monotonic timestamp count
  - session-boundary violations (ticks outside [08:30,15:15))
  - missing weekdays inside the covered range (holidays expected)
  - short sessions (early closes / partial days) by tick-count and last-tick time

Saves tempo/outputs/data_audit_<today>.csv (per-day) + _summary.txt.

    python tempo/scripts/data_audit.py
"""
from __future__ import annotations
import datetime as dt
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
TROVE = ROOT / "data" / "ticks_continuous"
OUT = ROOT / "tempo" / "outputs"


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    files = sorted(TROVE.glob("*.parquet"))
    rows = []
    for f in files:
        df = pd.read_parquet(f)
        t = df["DateTime"]
        rows.append({
            "date": f.stem,
            "n_ticks": len(df),
            "volume": int(df["Volume"].sum()),
            "first": t.iloc[0].time().isoformat(timespec="seconds"),
            "last": t.iloc[-1].time().isoformat(timespec="seconds"),
            "non_monotonic": int((t.diff() < pd.Timedelta(0)).sum()),
            "out_of_session": int(((t.dt.time < dt.time(8, 30)) | (t.dt.time >= dt.time(15, 15))).sum()),
            "price_min": float(df["Price"].min()),
            "price_max": float(df["Price"].max()),
        })
    per_day = pd.DataFrame(rows)
    today = dt.date.today().isoformat()
    csv = OUT / f"data_audit_{today}.csv"
    per_day.to_csv(csv, index=False)

    d0, d1 = per_day["date"].iloc[0], per_day["date"].iloc[-1]
    have = set(per_day["date"])
    all_wd = pd.bdate_range(d0, d1).strftime("%Y-%m-%d")
    missing = [d for d in all_wd if d not in have]
    short = per_day[per_day["last"] < "14:00:00"]
    tiny = per_day[per_day["n_ticks"] < 20000]

    lines = [
        f"tick trove audit — {today}",
        f"days: {len(per_day)}  range: {d0} .. {d1}",
        f"ticks/day: median {per_day['n_ticks'].median():,.0f}  min {per_day['n_ticks'].min():,}  max {per_day['n_ticks'].max():,}",
        f"non-monotonic timestamps: {per_day['non_monotonic'].sum()} total across {int((per_day['non_monotonic']>0).sum())} days",
        f"out-of-session ticks: {per_day['out_of_session'].sum()} total",
        f"missing weekdays in range: {len(missing)} (holidays expected ~9/yr => ~{round(len(all_wd)*0.035)})",
        f"  first 15: {missing[:15]}",
        f"short sessions (last tick <14:00): {len(short)} days: {short['date'].tolist()[:20]}",
        f"tiny days (<20k ticks): {len(tiny)}: {tiny['date'].tolist()[:20]}",
    ]
    txt = "\n".join(lines)
    (OUT / f"data_audit_{today}_summary.txt").write_text(txt, encoding="utf-8")
    print(txt)
    print(f"\nsaved -> {csv.relative_to(ROOT)}")


if __name__ == "__main__":
    main()
