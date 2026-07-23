"""databento_build_continuous.py — ES continuous hourly + session-daily from the ohlcv-1h batch.

Input:  data/databento/GLBX-20260723-QSMLGGLMWB/*.ohlcv-1h.dbn.zst  (ES.FUT parent, 2010->2026)
Output: data/bars/_db_es_1h_continuous.parquet   (back-adjusted continuous hourly)
        data/bars/_db_es_daily_24h.parquet       (session dailies, 17:00->16:00 CT grouping)
        data/regime/db_roll_audit_<tag>.csv      (per-roll audit: date, from, to, offset)

Method:
  * outrights only (raw_symbol like 'ESM4'; spreads contain '-').
  * front month per CME session = contract with max session volume; roll confirmed only
    after the challenger out-volumes the incumbent 2 consecutive sessions (avoids one-day
    flickers), effective next session.
  * panama back-adjust: at each roll, older history shifted by (new - old) close gap so
    the stitched series has no roll jumps (matches data/bars/_continuous convention).
    Regime studies are level-free, so back-adjusted is correct here.
  * validation: overlap vs our NT-derived data/bars/_continuous_1m_24h daily closes
    (2021-06->2026-07) — report daily-return correlation + max abs diff (returns, not
    levels: different roll conventions shift levels, returns must agree).

Run: .venv/Scripts/python.exe scripts/databento_build_continuous.py
"""
from __future__ import annotations
import sys
from pathlib import Path
import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parent.parent
JOB_DIR = ROOT / "data" / "databento" / "GLBX-20260723-QSMLGGLMWB"
BARS = ROOT / "data" / "bars"
OUT_1H = BARS / "_db_es_1h_continuous.parquet"
OUT_1D = BARS / "_db_es_daily_24h.parquet"
REGIME = ROOT / "data" / "regime"
CT = "America/Chicago"


def load_hourly() -> pd.DataFrame:
    import databento as db
    files = sorted(JOB_DIR.glob("*.dbn.zst")) or sorted(JOB_DIR.glob("*.dbn"))
    if not files:
        print(f"no dbn files in {JOB_DIR}"); sys.exit(1)
    parts = []
    for fp in files:
        st = db.DBNStore.from_file(fp)
        df = st.to_df()
        parts.append(df)
    df = pd.concat(parts)
    df = df.reset_index()
    # normalize expected columns: ts_event, open/high/low/close (already scaled by to_df), volume, symbol
    tscol = "ts_event" if "ts_event" in df.columns else df.columns[0]
    df = df.rename(columns={tscol: "ts", "symbol": "raw_symbol"} if "symbol" in df.columns else {tscol: "ts"})
    sym = "raw_symbol" if "raw_symbol" in df.columns else "symbol"
    df = df[~df[sym].astype(str).str.contains("-")]          # outrights only
    df["ts"] = pd.to_datetime(df["ts"], utc=True).dt.tz_convert(CT).dt.tz_localize(None)
    df = df[["ts", sym, "open", "high", "low", "close", "volume"]].rename(
        columns={sym: "contract", "open": "Open", "high": "High", "low": "Low",
                 "close": "Close", "volume": "Volume"})
    return df.sort_values(["ts", "contract"]).reset_index(drop=True)


def session_day(ts: pd.Series) -> pd.Series:
    # CME trading day: 17:00 CT belongs to next calendar day
    return (ts + pd.Timedelta(hours=7)).dt.normalize()


def pick_front(df: pd.DataFrame) -> pd.DataFrame:
    """Per-session front-month selection with 2-session confirmation."""
    df = df.copy()
    df["sday"] = session_day(df["ts"])
    vol = df.groupby(["sday", "contract"])["Volume"].sum().reset_index()
    days = sorted(vol["sday"].unique())
    front, cur, challenger_days = {}, None, 0
    challenger = None
    for d in days:
        v = vol[vol["sday"] == d].set_index("contract")["Volume"]
        top = v.idxmax()
        if cur is None:
            cur = top
        elif top != cur:
            if top == challenger:
                challenger_days += 1
            else:
                challenger, challenger_days = top, 1
            if challenger_days >= 2:
                cur = challenger
                challenger, challenger_days = None, 0
        else:
            challenger, challenger_days = None, 0
        front[d] = cur
    fmap = pd.Series(front, name="front")
    df["front"] = df["sday"].map(fmap)
    return df[df["contract"] == df["front"]].drop(columns=["front"])


def panama(df: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Back-adjust across contract switches; returns (adjusted df, roll audit)."""
    df = df.sort_values("ts").reset_index(drop=True)
    switches = df.index[df["contract"] != df["contract"].shift(1)].tolist()[1:]
    audit = []
    offset_total = 0.0
    adj = df.copy()
    # walk switches from OLDEST to newest, but offsets apply to everything before the switch:
    # easiest = compute per-switch gap, then cumulative from the end backwards.
    gaps = []
    for i in switches:
        prev_close = df.loc[i - 1, "Close"]
        # first bar of new contract vs last of old — gap measured at the seam
        new_open = df.loc[i, "Open"]
        gaps.append((i, new_open - prev_close, df.loc[i - 1, "contract"], df.loc[i, "contract"],
                     df.loc[i, "ts"]))
    cum = 0.0
    for i, gap, c_old, c_new, ts in reversed(gaps):
        cum += gap
        adj.loc[: i - 1, ["Open", "High", "Low", "Close"]] += gap
        audit.append({"ts": ts, "from": c_old, "to": c_new, "gap": round(gap, 2)})
    audit_df = pd.DataFrame(audit).sort_values("ts") if audit else pd.DataFrame()
    return adj, audit_df


def validate_overlap(daily: pd.DataFrame):
    p = BARS / "_continuous_1m_24h.parquet"
    if not p.exists():
        print("no 24h NT series to validate against"); return
    m1 = pd.read_parquet(p)
    m1["DateTime"] = pd.to_datetime(m1["DateTime"])
    sd = session_day(m1["DateTime"])
    nt = m1.groupby(sd).agg(Close=("Close", "last"))
    nt_ret = nt["Close"].pct_change().rename("nt")
    db_ret = daily.set_index("DateTime")["Close"].pct_change().rename("db")
    j = pd.concat([nt_ret, db_ret], axis=1).dropna()
    corr = j["nt"].corr(j["db"])
    mad = (j["nt"] - j["db"]).abs().max()
    print(f"overlap validation: {len(j)} sessions, daily-return corr={corr:.5f}, max|diff|={mad:.5f}")
    if corr < 0.999:
        print("WARN: correlation below 0.999 — inspect roll differences before trusting")


def main():
    tag = pd.Timestamp.now().strftime("%Y%m%d")
    REGIME.mkdir(exist_ok=True)
    raw = load_hourly()
    print(f"hourly rows (outrights): {len(raw):,}  {raw['ts'].min()} -> {raw['ts'].max()}  "
          f"contracts: {raw['contract'].nunique()}")
    fr = pick_front(raw)
    adj, audit = panama(fr)
    if len(audit):
        audit.to_csv(REGIME / f"db_roll_audit_{tag}.csv", index=False)
        print(f"rolls: {len(audit)} (audit -> db_roll_audit_{tag}.csv)")
    cont = adj[["ts", "Open", "High", "Low", "Close", "Volume", "contract"]].rename(
        columns={"ts": "DateTime"})
    cont.to_parquet(OUT_1H, index=False)

    d = cont.copy()
    d["sday"] = session_day(d["DateTime"])
    daily = d.groupby("sday").agg(Open=("Open", "first"), High=("High", "max"),
                                  Low=("Low", "min"), Close=("Close", "last"),
                                  Volume=("Volume", "sum")).reset_index()
    daily = daily.rename(columns={"sday": "DateTime"})
    daily = daily[daily["Volume"] > 0]
    daily.to_parquet(OUT_1D, index=False)
    print(f"continuous 1h: {len(cont):,} -> {OUT_1H.name}")
    print(f"session daily: {len(daily):,} bars {daily['DateTime'].min().date()} -> "
          f"{daily['DateTime'].max().date()} -> {OUT_1D.name}")
    validate_overlap(daily)


if __name__ == "__main__":
    main()
