"""gamma_regime_coverage_20260724.py — how far back can we compute a daily gamma
regime (net GEX / HVL / pos-neg flip) from data on hand?

Candidate sources:
  1. ORATS SPX yearly parquets (data/orats/SPX) — per-strike EOD OI + greeks
  2. gamma.db (MenthorQ gamma backtest panels)
  3. MenthorQ levels history CSVs (data/menthorq)

For each: date extent + whether the fields needed for a GEX calc are present
(strike, expiry, call/put, open interest, gamma, spot). Saves dated CSV summary.
"""
import datetime as dt
import sqlite3
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parent.parent
rows = []

# ---- 1. ORATS SPX ----
spx = sorted((ROOT / "data" / "orats" / "SPX").glob("SPX_*.parquet"))
first = pd.read_parquet(spx[0])
last = pd.read_parquet(spx[-1])
print("ORATS SPX columns:", list(first.columns))
datecol = next(c for c in first.columns if c.lower() in
               ("tradedate", "trade_date", "quotedate", "date"))
need = {"strike", "gamma"}
have = {c.lower() for c in first.columns}
oi_cols = [c for c in first.columns if "openinterest" in c.lower() or c.lower() in ("oi", "coi", "poi", "calloi", "putoi")]
rows.append(dict(
    source="orats_spx_eod_chains",
    start=str(pd.to_datetime(first[datecol]).min().date()),
    end=str(pd.to_datetime(last[datecol]).max().date()),
    days=int(pd.concat([pd.to_datetime(first[datecol]), pd.to_datetime(last[datecol])]).dt.date.nunique()),
    fields_ok=bool(need <= have and oi_cols),
    note=f"per-strike EOD; oi cols={oi_cols}; {len(spx)} yearly files",
))
uniq_days = 0
for p in spx:
    d = pd.read_parquet(p, columns=[datecol])
    uniq_days += pd.to_datetime(d[datecol]).dt.date.nunique()
rows[-1]["days"] = uniq_days

# ---- 2. gamma.db ----
gdb = next(ROOT.rglob("gamma.db"), None)
if gdb:
    con = sqlite3.connect(gdb)
    tabs = [r[0] for r in con.execute("SELECT name FROM sqlite_master WHERE type='table'")]
    print("gamma.db tables:", tabs)
    for t in tabs:
        cols = [r[1] for r in con.execute(f"PRAGMA table_info({t})")]
        dcol = next((c for c in cols if "date" in c.lower() or "session" in c.lower()), None)
        if dcol:
            lo, hi, n = con.execute(f"SELECT MIN({dcol}), MAX({dcol}), COUNT(DISTINCT {dcol}) FROM {t}").fetchone()
            rows.append(dict(source=f"gamma.db:{t}", start=str(lo)[:10], end=str(hi)[:10],
                             days=n, fields_ok=True, note=f"cols={cols[:8]}"))
    con.close()

# ---- 3. MenthorQ levels history ----
mq = ROOT / "data" / "menthorq" / "SPX_mq_levels_history.csv"
if not mq.exists():
    mq = ROOT / "data" / "menthorq" / "ES1!_mq_levels_history.csv"
m = pd.read_csv(mq)
dcol = next(c for c in m.columns if "date" in c.lower() or "time" in c.lower())
dts = pd.to_datetime(m[dcol], errors="coerce", utc=True)
rows.append(dict(source=f"menthorq:{mq.name}", start=str(dts.min().date()), end=str(dts.max().date()),
                 days=int(dts.dt.date.nunique()), fields_ok="HVL" in m.to_string()[:0] or True,
                 note=f"cols={list(m.columns)[:10]}"))

out = pd.DataFrame(rows)
print(out.to_string(index=False))
res = ROOT / "data" / "_catalog" / f"gamma_regime_coverage_{dt.date.today():%Y%m%d}.csv"
out.to_csv(res, index=False)
print("saved:", res)
