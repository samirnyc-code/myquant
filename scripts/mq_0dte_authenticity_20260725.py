"""mq_0dte_authenticity_20260725.py — are MQ's historical 0DTE levels REAL or placeholder?

Question (2026-07-25): the scraped SPX history shows cr0/ps0/hvl0/gw0 populated for all
1,183 sessions back to 2021-09-27, but another count said only ~530 sessions (2024-07+)
of 0DTE data. Hypothesis: MQ's API returns 0DTE fields for every date, but before some
date they are copies of the main levels / degenerate — not genuine 0DTE-chain levels.

Checks, per year:
  1. raw API audit: does the 2021/2022 JSON actually contain 'Call Resistance 0DTE'
     level objects? (grep the _raw.jsonl rows directly)
  2. distinctness: share of sessions where cr0 != cr, ps0 != ps, hvl0 != hvl,
     and where the 0DTE gex magnitudes differ from the main ones.
  3. SPX expiry reality: share of sessions that HAD a dying expiry (from ORATS chains,
     via our backfill's cr0 coverage) — 0DTE levels only MEAN anything on those days.
Saves dated CSV to data/regime/mq_reveng/.
"""
import datetime as dt
import json
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parent.parent

# ---- 1. raw JSONL: count sessions whose raw response contains explicit 0DTE levels
raw_has = {}
with open(ROOT / "data" / "menthorq" / "SPX_mq_levels_history_raw.jsonl",
          encoding="utf-8") as f:
    for line in f:
        try:
            js = json.loads(line)
        except Exception:
            continue
        txt = json.dumps(js)
        # find the session date key in the record
        m = None
        for k in ("req_date", "date", "session_date"):
            if isinstance(js, dict) and js.get(k):
                m = str(js[k])[:10]
                break
        if m is None:
            import re
            mm = re.search(r"\d{4}-\d{2}-\d{2}", txt)
            m = mm.group(0) if mm else "unknown"
        raw_has[m] = ("Call Resistance 0DTE" in txt, "Gamma Wall 0DTE" in txt)

rh = pd.DataFrame([dict(date=k, has_cr0=v[0], has_gw0=v[1]) for k, v in raw_has.items()])
rh["year"] = rh["date"].str[:4]
raw_by_year = rh.groupby("year").agg(sessions=("date", "count"),
                                     raw_cr0=("has_cr0", "sum"),
                                     raw_gw0=("has_gw0", "sum"))

# ---- 2. distinctness in the parsed history
t = pd.read_csv(ROOT / "data" / "menthorq" / "SPX_mq_levels_history.csv")
t["session_date"] = pd.to_datetime(t["session_date"]).dt.date
t = t.drop_duplicates("session_date", keep="last")
t["year"] = t["session_date"].astype(str).str[:4]
t["cr0_neq_cr"] = (t["cr0"].notna()) & (t["cr"].notna()) & (t["cr0"] != t["cr"])
t["ps0_neq_ps"] = (t["ps0"].notna()) & (t["ps"].notna()) & (t["ps0"] != t["ps"])
t["hvl0_neq_hvl"] = (t["hvl0"].notna()) & (t["hvl"].notna()) & (t["hvl0"] != t["hvl"])
t["cr0gex_neq"] = (t["cr0_gex"].notna()) & (t["cr_gex"].notna()) & (t["cr0_gex"] != t["cr_gex"])
dist = t.groupby("year").agg(
    sessions=("session_date", "count"),
    cr0_nonnull=("cr0", "count"),
    cr0_distinct=("cr0_neq_cr", "sum"),
    ps0_distinct=("ps0_neq_ps", "sum"),
    hvl0_distinct=("hvl0_neq_hvl", "sum"),
    cr0gex_distinct=("cr0gex_neq", "sum"))

# ---- 3. dying-expiry reality from our ORATS backfill
b = pd.read_csv(ROOT / "data" / "regime" / "mq_regime_daily_2007_2026_v2.csv",
                parse_dates=["date"])
b["year"] = b["date"].dt.year.astype(str)
b = b[b["year"] >= "2021"]
dying = b.groupby("year").agg(orats_days=("date", "count"),
                              dying_expiry_days=("cr0", "count"))

out = raw_by_year.join(dist, how="outer", rsuffix="_hist").join(dying, how="outer")
print(out.to_string())

# distinct-0DTE totals and first date where cr0 != cr
dd = t[t["cr0_neq_cr"]]
print(f"\nsessions with cr0 != cr: {len(dd)}  first={dd['session_date'].min()}  "
      f"last={dd['session_date'].max()}")
d2 = t[t["cr0_neq_cr"] & (t["session_date"].astype(str) >= "2024-07-01")]
print(f"  of which 2024-07-01+: {len(d2)}")
dh = t[t["hvl0_neq_hvl"]]
print(f"sessions with hvl0 != hvl: {len(dh)}  first={dh['session_date'].min()}")

out.to_csv(ROOT / "data" / "regime" / "mq_reveng"
           / f"mq_0dte_authenticity_{dt.date.today():%Y%m%d}.csv")
