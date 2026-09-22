"""databento_build_continuous_1m.py — ES continuous 1-min (+ RTH 1m/5m frames) from the
ohlcv-1m batch, for the pre-2021 backfill / 2010-2020 OOS run of the 2E book.

Input:  data/databento/GLBX-20260725-X98V5EDDHH/*.ohlcv-1m.dbn.zst  (ES.FUT parent 2010->2026)
Output: data/bars/_db_es_1m_continuous_24h.parquet   (back-adjusted continuous, 24h)
        data/bars/_db_es_1m_rth.parquet              (RTH 08:30-15:14 CT, matches _continuous_1m)
        data/bars/_db_es_5m_rth.parquet              (RTH 08:30-15:10 CT, matches _continuous)
        data/regime/db_roll_audit_1m_<tag>.csv       (per-roll audit)

Method = SAME as databento_build_continuous.py (validated on the 1h data):
  * outrights only; front month per CME session = max session volume, 2-session confirmation;
    panama back-adjust across switches (vectorized). Additive shift => strategy-invariant intraday.
  * RTH frames: CT, [08:30, 15:15); 5m via resample label/closed='left' (engine convention).
  * validation: 1-min RTH daily-return corr + max|diff| vs data/bars/_continuous_1m.parquet on the
    2021-06->2026 overlap (returns, not levels — different roll conventions shift levels).

Run: python scripts/databento_build_continuous_1m.py
"""
from __future__ import annotations
import sys
from pathlib import Path
import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parent.parent
JOB_DIR = ROOT / "data" / "databento" / "GLBX-20260725-X98V5EDDHH"
BARS = ROOT / "data" / "bars"
OUT_24H = BARS / "_db_es_1m_continuous_24h.parquet"
OUT_1M = BARS / "_db_es_1m_rth.parquet"
OUT_5M = BARS / "_db_es_5m_rth.parquet"
REGIME = ROOT / "data" / "regime"
CT = "America/Chicago"
RTH_START, RTH_END = "08:30", "15:15"   # [start, end) CT


def load_minute() -> pd.DataFrame:
    import databento as db
    files = sorted(JOB_DIR.glob("*.dbn.zst")) or sorted(JOB_DIR.glob("*.dbn"))
    if not files:
        print(f"no dbn files in {JOB_DIR}"); sys.exit(1)
    parts = [db.DBNStore.from_file(fp).to_df() for fp in files]
    df = pd.concat(parts).reset_index()
    tscol = "ts_event" if "ts_event" in df.columns else df.columns[0]
    sym = "symbol" if "symbol" in df.columns else "raw_symbol"
    df = df[~df[sym].astype(str).str.contains("-")]                 # outrights only
    df["ts"] = pd.to_datetime(df[tscol], utc=True).dt.tz_convert(CT).dt.tz_localize(None)
    df = df[["ts", sym, "open", "high", "low", "close", "volume"]].rename(
        columns={sym: "contract", "open": "Open", "high": "High", "low": "Low",
                 "close": "Close", "volume": "Volume"})
    return df.sort_values(["ts", "contract"]).reset_index(drop=True)


def session_day(ts: pd.Series) -> pd.Series:
    return (ts + pd.Timedelta(hours=7)).dt.normalize()             # 17:00 CT -> next day


def pick_front(df: pd.DataFrame) -> pd.DataFrame:
    df = df.copy(); df["sday"] = session_day(df["ts"])
    vol = df.groupby(["sday", "contract"])["Volume"].sum().reset_index()
    days = sorted(vol["sday"].unique())
    front, cur, challenger, challenger_days = {}, None, None, 0
    for d in days:
        v = vol[vol["sday"] == d].set_index("contract")["Volume"]; top = v.idxmax()
        if cur is None:
            cur = top
        elif top != cur:
            if top == challenger:
                challenger_days += 1
            else:
                challenger, challenger_days = top, 1
            if challenger_days >= 2:
                cur = challenger; challenger, challenger_days = None, 0
        else:
            challenger, challenger_days = None, 0
        front[d] = cur
    df["front"] = df["sday"].map(pd.Series(front))
    return df[df["contract"] == df["front"]].drop(columns=["front"])


def panama(df: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Vectorized back-adjust: offset[row] = sum of seam gaps at/after that row's era."""
    df = df.sort_values("ts").reset_index(drop=True)
    switches = df.index[df["contract"] != df["contract"].shift(1)].tolist()[1:]
    offset = np.zeros(len(df))
    audit = []
    for i in switches:
        gap = float(df.loc[i, "Open"] - df.loc[i - 1, "Close"])    # seam gap
        offset[:i] += gap                                          # shift all older history
        audit.append({"ts": df.loc[i, "ts"], "from": df.loc[i - 1, "contract"],
                      "to": df.loc[i, "contract"], "gap": round(gap, 2)})
    adj = df.copy()
    for c in ["Open", "High", "Low", "Close"]:
        adj[c] = adj[c].values + offset
    return adj, (pd.DataFrame(audit).sort_values("ts") if audit else pd.DataFrame())


def rth_frames(cont: pd.DataFrame):
    t = cont["DateTime"].dt.strftime("%H:%M")
    rth = cont[(t >= RTH_START) & (t < RTH_END)].copy()
    m1 = rth[["DateTime", "Open", "High", "Low", "Close", "Volume", "contract"]].rename(
        columns={"contract": "Contract"}).reset_index(drop=True)
    # 5m: resample per session day, label/closed left (engine convention)
    r = rth.set_index("DateTime")
    o = r["Open"].resample("5min", label="left", closed="left").first()
    h = r["High"].resample("5min", label="left", closed="left").max()
    lo = r["Low"].resample("5min", label="left", closed="left").min()
    c = r["Close"].resample("5min", label="left", closed="left").last()
    v = r["Volume"].resample("5min", label="left", closed="left").sum()
    m5 = pd.concat([o, h, lo, c, v], axis=1).dropna(subset=["Open"]).reset_index()
    m5.columns = ["DateTime", "Open", "High", "Low", "Close", "Volume"]
    tt = m5["DateTime"].dt.strftime("%H:%M")
    m5 = m5[(tt >= RTH_START) & (tt < RTH_END)].reset_index(drop=True)
    return m1, m5


def validate(m1: pd.DataFrame):
    p = BARS / "_continuous_1m.parquet"
    if not p.exists():
        print("no NT 1-min series to validate against"); return
    nt = pd.read_parquet(p); nt["DateTime"] = pd.to_datetime(nt["DateTime"])
    a = m1.set_index("DateTime")["Close"]; bnt = nt.set_index("DateTime")["Close"]
    j = pd.concat([a.rename("db"), bnt.rename("nt")], axis=1).dropna()
    if not len(j):
        print("no overlapping timestamps to validate"); return
    ret = j.pct_change().dropna()
    corr = ret["db"].corr(ret["nt"]); mad = (ret["db"] - ret["nt"]).abs().max()
    print(f"\nOVERLAP seam-check (1-min RTH closes, {j.index.min().date()}->{j.index.max().date()}): "
          f"{len(j):,} bars, per-bar-return corr={corr:.5f}, max|diff|={mad:.5f}")
    print("  " + ("OK (corr>=0.999)" if corr >= 0.999 else "WARN corr<0.999 — inspect roll differences"))


def main():
    tag = pd.Timestamp.now().strftime("%Y%m%d")
    REGIME.mkdir(exist_ok=True)
    raw = load_minute()
    print(f"minute rows (outrights): {len(raw):,}  {raw['ts'].min()} -> {raw['ts'].max()}  "
          f"contracts: {raw['contract'].nunique()}")
    fr = pick_front(raw)
    adj, audit = panama(fr)
    if len(audit):
        audit.to_csv(REGIME / f"db_roll_audit_1m_{tag}.csv", index=False)
        print(f"rolls: {len(audit)} (audit -> db_roll_audit_1m_{tag}.csv)")
    cont = adj[["ts", "Open", "High", "Low", "Close", "Volume", "contract"]].rename(columns={"ts": "DateTime"})
    cont.to_parquet(OUT_24H, index=False)
    print(f"continuous 1m 24h: {len(cont):,} -> {OUT_24H.name}")
    m1, m5 = rth_frames(cont)
    m1.to_parquet(OUT_1M, index=False); m5.to_parquet(OUT_5M, index=False)
    print(f"RTH 1m: {len(m1):,} bars {m1['DateTime'].min().date()} -> {m1['DateTime'].max().date()} -> {OUT_1M.name}")
    print(f"RTH 5m: {len(m5):,} bars {m5['DateTime'].min().date()} -> {m5['DateTime'].max().date()} -> {OUT_5M.name}")
    validate(m1)


if __name__ == "__main__":
    main()
