"""mq_truth_0dte_extent_20260725.py — verify the extent of MenthorQ's OWN 0DTE level
history (cr0/ps0/hvl0/gw0) in the scraped SPX history, per-column non-null counts and
date ranges. Saves dated output to data/regime/mq_reveng/.
"""
import datetime as dt
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parent.parent
t = pd.read_csv(ROOT / "data" / "menthorq" / "SPX_mq_levels_history.csv")
t["session_date"] = pd.to_datetime(t["session_date"]).dt.date
t = t.drop_duplicates("session_date", keep="last")

rows = []
for c in ["cr0", "ps0", "hvl0", "gw0", "cr", "ps", "hvl", "gex_1", "d1_min"]:
    ok = t[t[c].notna()]
    rows.append(dict(col=c, n=len(ok),
                     first=str(ok["session_date"].min()) if len(ok) else "-",
                     last=str(ok["session_date"].max()) if len(ok) else "-"))
out = pd.DataFrame(rows)
print(f"total sessions in history: {len(t)} "
      f"({t['session_date'].min()}..{t['session_date'].max()})")
print(out.to_string(index=False))
out.to_csv(ROOT / "data" / "regime" / "mq_reveng"
           / f"mq_truth_0dte_extent_{dt.date.today():%Y%m%d}.csv", index=False)
