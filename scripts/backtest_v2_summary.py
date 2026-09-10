"""Headline summary of the FULL-HISTORY v2 backtest (rows_v2.csv) — the
desk-faithful engine (gate, WAIT band, 14:45 quotable-close) — and comparison
vs the S114 v1 engine (rows.csv vix252 + fly_rows.csv).

Books reported: eod streams (policy 'eod'), open streams under nowait and
calwait, and the combined book under each open policy. Plus yearly, per-stream,
skip stats, and the WAIT-band delta. Output: dated CSVs + stdout.
"""
import datetime as dt
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
BT = ROOT / "data" / "options_sim" / "backtest_full"
STAMP = dt.date.today().strftime("%Y%m%d")

v2 = pd.read_csv(BT / "rows_v2.csv", parse_dates=["date"])
v2["year"] = v2["date"].dt.year
tr = v2[v2["exit_kind"].isin(["stop", "settle", "time"])].copy()
sk = v2[v2["exit_kind"] == "SKIP"]

def stats(df, label):
    daily = df.groupby("date")["pnl"].sum()
    cum = daily.cumsum()
    dd = (cum - cum.cummax()).min()
    gw = df.loc[df["pnl"] > 0, "pnl"].sum()
    gl = df.loc[df["pnl"] < 0, "pnl"].sum()
    return {"book": label, "total": round(df["pnl"].sum()), "n": len(df),
            "win_pct": round(100 * (df["pnl"] > 0).mean(), 1),
            "exp": round(df["pnl"].mean(), 1),
            "pf": round(gw / abs(gl), 2) if gl else None,
            "maxdd": round(dd)}

eod = tr[tr["policy"] == "eod"]
nw = tr[tr["policy"] == "nowait"]
cw = tr[tr["policy"] == "calwait"]

rows = [
    stats(eod, "eod streams (4)"),
    stats(eod[eod["strat"].str.contains("ic")], "eod condors"),
    stats(eod[eod["strat"].str.contains("fly")], "eod flies"),
    stats(nw, "open streams nowait"),
    stats(cw, "open streams calwait"),
    stats(pd.concat([eod, nw]), "COMBINED (nowait)"),
    stats(pd.concat([eod, cw]), "COMBINED (calwait)"),
]
summary = pd.DataFrame(rows)
summary.to_csv(BT / f"v2_summary_{STAMP}.csv", index=False)
print("===== v2 books =====")
print(summary.to_string(index=False))

print("\n===== per-stream (eod + calwait) =====")
per = (pd.concat([eod, cw]).groupby("strat")
       .agg(pnl=("pnl", "sum"), n=("pnl", "size"),
            stops=("exit_kind", lambda s: (s == "stop").sum()),
            times=("exit_kind", lambda s: (s == "time").sum()))
       .round(0))
print(per.to_string())

print("\n===== yearly (COMBINED calwait) =====")
yr = (pd.concat([eod, cw]).groupby("year")["pnl"].sum().round(0))
print(yr.to_string())

print(f"\nWAIT band: calwait {cw['pnl'].sum():.0f} vs nowait {nw['pnl'].sum():.0f} "
      f"(delta {cw['pnl'].sum() - nw['pnl'].sum():+.0f})")
print(f"skips: {len(sk)} rows ({sk['note'].value_counts().to_dict()})")

# v1 comparison (same-stream basis: v1 IC vix252 + v1 fly)
v1ic = pd.read_csv(BT / "rows.csv")
v1ic = v1ic[v1ic["method"] == "vix252"]
v1fly = pd.read_csv(BT / "fly_rows.csv")
v1_eod = pd.concat([v1ic[v1ic["strat"].str.startswith("eod")],
                    v1fly[v1fly["strat"].str.startswith("eod")]])
v1_open = pd.concat([v1ic[v1ic["strat"].str.startswith("open")],
                     v1fly[v1fly["strat"].str.startswith("open")]])
print("\n===== v1 vs v2 (same buckets) =====")
print(f"eod : v1 {v1_eod['pnl'].sum():9.0f}   v2 {eod['pnl'].sum():9.0f}")
print(f"open: v1 {v1_open['pnl'].sum():9.0f}   v2 nowait {nw['pnl'].sum():9.0f}"
      f"  calwait {cw['pnl'].sum():9.0f}")
print(f"ALL : v1 {v1_eod['pnl'].sum() + v1_open['pnl'].sum():9.0f}   "
      f"v2 {eod['pnl'].sum() + cw['pnl'].sum():9.0f} (calwait)")
