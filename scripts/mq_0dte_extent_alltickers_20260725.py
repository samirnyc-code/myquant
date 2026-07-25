"""mq_0dte_extent_alltickers_20260725.py — per-ticker extent of MQ 0DTE history
(cr0 non-null + cr0!=cr distinct counts, first/last dates) across every
*_mq_levels_history.csv, to locate the source of a '530 sessions from 2024-07' claim.
Saves dated CSV to data/regime/mq_reveng/.
"""
import datetime as dt
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parent.parent
rows = []
for p in sorted((ROOT / "data" / "menthorq").glob("*_mq_levels_history.csv")):
    tkr = p.name.replace("_mq_levels_history.csv", "")
    t = pd.read_csv(p)
    if "session_date" not in t.columns:
        continue
    t["session_date"] = pd.to_datetime(t["session_date"]).dt.date
    t = t.drop_duplicates("session_date", keep="last")
    has0 = "cr0" in t.columns
    nn = t["cr0"].notna() if has0 else pd.Series(False, index=t.index)
    dist = nn & t["cr"].notna() & (t["cr0"] != t["cr"]) if has0 else nn
    sub = t[nn]
    rows.append(dict(
        ticker=tkr, sessions=len(t),
        first=str(t["session_date"].min()), last=str(t["session_date"].max()),
        cr0_nonnull=int(nn.sum()),
        cr0_first=str(sub["session_date"].min()) if len(sub) else "-",
        cr0_last=str(sub["session_date"].max()) if len(sub) else "-",
        cr0_distinct=int(dist.sum()),
        cr0_distinct_first=str(t.loc[dist, "session_date"].min()) if dist.any() else "-"))
out = pd.DataFrame(rows)
print(out.to_string(index=False))
out.to_csv(ROOT / "data" / "regime" / "mq_reveng"
           / f"mq_0dte_extent_alltickers_{dt.date.today():%Y%m%d}.csv", index=False)
