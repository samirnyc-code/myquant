"""databento_overlap_audit.py — where do the DB-continuous vs NT-24h daily returns disagree?

Hypotheses: (a) diffs cluster on ROLL dates (different roll calendars between the two
panama series -> the roll-day return contains a basis gap in one series but not the other);
(b) my seam gap (new_open - prev_close) conflates real market movement with roll basis.

Run: .venv/Scripts/python.exe scripts/databento_overlap_audit.py
Out: data/regime/db_overlap_audit_<tag>.csv + console top-20 table.
"""
from __future__ import annotations
from pathlib import Path
import pandas as pd

ROOT = Path(__file__).resolve().parent.parent
BARS = ROOT / "data" / "bars"
REGIME = ROOT / "data" / "regime"


def session_day(ts: pd.Series) -> pd.Series:
    return (ts + pd.Timedelta(hours=7)).dt.normalize()


def main():
    tag = pd.Timestamp.now().strftime("%Y%m%d")
    dbd = pd.read_parquet(BARS / "_db_es_daily_24h.parquet")
    m1 = pd.read_parquet(BARS / "_continuous_1m_24h.parquet")
    m1["DateTime"] = pd.to_datetime(m1["DateTime"])
    nt = m1.groupby(session_day(m1["DateTime"])).agg(Close=("Close", "last"))
    j = pd.concat([nt["Close"].pct_change().rename("nt"),
                   dbd.set_index("DateTime")["Close"].pct_change().rename("db")], axis=1).dropna()
    j["diff"] = (j["nt"] - j["db"]).abs()

    audits = sorted(REGIME.glob("db_roll_audit_*.csv"))
    rolls = pd.read_csv(audits[-1], parse_dates=["ts"]) if audits else pd.DataFrame()
    roll_days = set(session_day(rolls["ts"]).dt.date) if len(rolls) else set()

    j = j.sort_values("diff", ascending=False)
    j["is_roll_day"] = [d.date() in roll_days for d in j.index]
    top = j.head(20)
    print(top.to_string())
    n_big = (j["diff"] > 0.002).sum()
    n_big_roll = ((j["diff"] > 0.002) & j["is_roll_day"]).sum()
    print(f"\nsessions with |ret diff| > 20bp: {n_big}  (on my roll days: {n_big_roll})")
    corr_ex = j[~j["is_roll_day"]]["nt"].corr(j[~j["is_roll_day"]]["db"])
    print(f"return corr EXCLUDING my roll days: {corr_ex:.5f}")

    # referee: SPX cash daily returns (independent source) — which series is closer
    # on the disagreement days? ES vs SPX differ by basis drift (small), so the loser
    # on a 1%+ disagreement is unambiguous.
    spx = pd.read_csv(ROOT / "data" / "spx_daily.csv")
    dcol = [c for c in spx.columns if c.lower() in ("date", "datetime")][0]
    ccol = [c for c in spx.columns if c.lower() in ("close", "adj close", "spx", "spx_close")][0]
    spx[dcol] = pd.to_datetime(spx[dcol])
    sr = spx.set_index(dcol)[ccol].pct_change().rename("spx")
    top = j[j["diff"] > 0.002].join(sr, how="left").dropna(subset=["spx"])
    top["nt_err"] = (top["nt"] - top["spx"]).abs()
    top["db_err"] = (top["db"] - top["spx"]).abs()
    top["closer"] = top[["nt_err", "db_err"]].idxmin(axis=1).str[:2]
    print("\nreferee vs SPX cash on the >20bp disagreement days:")
    print(top[["nt", "db", "spx", "closer"]].to_string())
    print(f"\nverdict counts: {top['closer'].value_counts().to_dict()}")
    j.to_csv(REGIME / f"db_overlap_audit_{tag}.csv")


if __name__ == "__main__":
    main()
