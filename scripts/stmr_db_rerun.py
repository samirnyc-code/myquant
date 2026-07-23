"""stmr_db_rerun.py — STMR-on-MES re-run on the CLEAN Databento series (S82 tearsheet audit).

Why: the S82 tearsheet (docs/artifacts/stmr_mes_tearsheet.html) was computed on the NT-derived
_continuous_1m_24h.parquet, which has ~20 bad daily closes in 2021-23 (SPX referee 17-2, see
db_overlap_audit). The S82 engine itself was never persisted (only stmr_final.json + trade
CSVs), so this reconstructs the two engines from their recorded specs and re-runs them on
data/bars/_db_es_daily_24h.parquet + _db_es_1h_continuous.parquet.

Engines (specs from S82 handoff + trade CSVs; MES $5/pt, $5 RT fee, 0.25pt slip on exit):
  DAILY: entry at session close when %K(8)<15 and Close>SMA100; exit first of:
         intrabar stop entry-35pt, intrabar target entry+75pt (checked on the HOURLY path,
         stop-first when both hit within the same hour — conservative), else close>SMA5.
  4H:    session-aligned 4h bars; same signal; exit close>SMA5; NO stop (the S82 finding was
         that 4h stops die overnight).
  Long only, one position at a time, no adds (S82's "+1" add rule not reconstructed — noted).

Windows:
  A) S82 window 2021-06-17 -> 2026-07-02  = apples-to-apples vs stmr_final.json
     (daily n=37/$5,722/PF 2.15/win 57 · 4h n=74/$6,121/PF 2.38/win 77).
  B) 2010-06 -> 2021-06 = honest OOS (params were chosen on 2021+ data).

Run: .venv/Scripts/python.exe scripts/stmr_db_rerun.py
Out: data/regime/stmr_db_rerun_<tag>.csv (trades) + console summary.
"""
from __future__ import annotations
from pathlib import Path
import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parent.parent
BARS = ROOT / "data" / "bars"
OUT = ROOT / "data" / "regime"
PT, FEE, SLIP = 5.0, 5.0, 0.25
STOP, TGT = 35.0, 75.0


def session_day(ts: pd.Series) -> pd.Series:
    return (ts + pd.Timedelta(hours=7)).dt.normalize()


def k8(df: pd.DataFrame) -> pd.Series:
    lo = df["Low"].rolling(8).min(); hi = df["High"].rolling(8).max()
    return 100 * (df["Close"] - lo) / (hi - lo).replace(0, np.nan)


def run_daily(daily: pd.DataFrame, hourly: pd.DataFrame) -> pd.DataFrame:
    d = daily.reset_index(drop=True)
    C = d["Close"]
    ent = (k8(d) < 15) & (C > C.rolling(100).mean())
    exi = C > C.rolling(5).mean()
    h = hourly.sort_values("DateTime").reset_index(drop=True)
    h["sday"] = session_day(h["DateTime"])
    rows, inp = [], False
    for i in range(len(d)):
        if not inp and bool(ent.iloc[i]) and i >= 100:
            e_px, e_day, inp = float(C.iloc[i]), d["DateTime"].iloc[i], True
        elif inp:
            day = d["DateTime"].iloc[i]
            hp = h[h["sday"] == day]
            hit = None
            for _, hb in hp.iterrows():
                if hb["Low"] <= e_px - STOP:
                    hit = ("stop", e_px - STOP); break
                if hb["High"] >= e_px + TGT:
                    hit = ("target", e_px + TGT); break
            if hit:
                x_px, why = hit[1], hit[0]
            elif bool(exi.iloc[i]):
                x_px, why = float(C.iloc[i]), "sma5"
            else:
                continue
            pts = (x_px - e_px) - SLIP
            rows.append({"engine": "daily", "entry_dt": e_day, "exit_dt": day, "why": why,
                         "entry": e_px, "exit": x_px, "pts": round(pts, 2),
                         "pnl": round(pts * PT - FEE, 2)})
            inp = False
    return pd.DataFrame(rows)


def run_4h(hourly: pd.DataFrame) -> pd.DataFrame:
    h = hourly.set_index("DateTime").sort_index()
    b = h.resample("4h", origin=pd.Timestamp("2010-06-06 17:00:00")).agg(
        {"Open": "first", "High": "max", "Low": "min", "Close": "last"}).dropna()
    b = b.reset_index()
    C = b["Close"]
    ent = ((k8(b) < 15) & (C > C.rolling(100).mean())).to_numpy()
    exi = (C > C.rolling(5).mean()).to_numpy()
    rows, inp = [], False
    for i in range(100, len(b)):
        if not inp and ent[i]:
            e_px, e_dt, inp = float(C.iloc[i]), b["DateTime"].iloc[i], True
        elif inp and exi[i]:
            pts = (float(C.iloc[i]) - e_px) - SLIP
            rows.append({"engine": "4h", "entry_dt": e_dt, "exit_dt": b["DateTime"].iloc[i],
                         "why": "sma5", "entry": e_px, "exit": float(C.iloc[i]),
                         "pts": round(pts, 2), "pnl": round(pts * PT - FEE, 2)})
            inp = False
    return pd.DataFrame(rows)


def summarize(tr: pd.DataFrame, label: str):
    if not len(tr):
        print(f"{label:26s}  n=0"); return
    gp = tr.pnl[tr.pnl > 0].sum(); gl = -tr.pnl[tr.pnl < 0].sum()
    pf = gp / gl if gl > 0 else float("inf")
    print(f"{label:26s}  n={len(tr):3d}  total=${tr.pnl.sum():8,.0f}  PF={pf:5.2f}  "
          f"win={100*(tr.pnl>0).mean():3.0f}%  worst=${tr.pnl.min():7,.0f}")


def main():
    tag = pd.Timestamp.now().strftime("%Y%m%d")
    daily = pd.read_parquet(BARS / "_db_es_daily_24h.parquet")
    hourly = pd.read_parquet(BARS / "_db_es_1h_continuous.parquet")
    daily["DateTime"] = pd.to_datetime(daily["DateTime"])
    hourly["DateTime"] = pd.to_datetime(hourly["DateTime"])

    all_tr = []
    print("S82 reference (NT data): daily n=37 $5,722 PF 2.15 win 57 | 4h n=74 $6,121 PF 2.38 win 77\n")
    for label, lo, hi in [("A: 2021-06-17..2026-07-02", "2021-06-17", "2026-07-02"),
                          ("B: 2010-06..2021-06 (OOS)", "2010-06-06", "2021-06-16"),
                          ("FULL 2010..2026", "2010-06-06", "2026-07-23")]:
        dsl = daily[(daily["DateTime"] >= lo) & (daily["DateTime"] <= hi)].reset_index(drop=True)
        hsl = hourly[(hourly["DateTime"] >= lo) & (hourly["DateTime"] <= pd.Timestamp(hi) + pd.Timedelta(days=1))]
        td = run_daily(dsl, hsl)
        t4 = run_4h(hsl)
        for t in (td, t4):
            t["window"] = label
        all_tr += [td, t4]
        summarize(td, f"{label} DAILY")
        summarize(t4, f"{label} 4H")
        print()
    pd.concat(all_tr, ignore_index=True).to_csv(OUT / f"stmr_db_rerun_{tag}.csv", index=False)
    print(f"trades -> data/regime/stmr_db_rerun_{tag}.csv")


if __name__ == "__main__":
    main()
