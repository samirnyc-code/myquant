"""CR/PS final grid check: all-strikes universe vs m25, under dte>=2.

truthfp: 5.3% of true CR and 0.6% of PS are NOT multiples of 25 -> m25 grid
caps exact%. Test grid 'any' (all listed strikes) vs m25 for the winning
dte>=2 specs, bands none/b15/b20, hi 365/9999. Yearly breakdown included.
Output: crps_gridany_20260724.csv (+ _yearly)
"""
import numpy as np
import pandas as pd
from itertools import product

BASE = r"C:\Users\Admin\myquant\data\regime\mq_reveng"
FIT_END = pd.Timestamp("2023-12-31")

ch = pd.read_parquet(f"{BASE}\\chain_slices_overlap.parquet",
                     columns=["tradeDate", "dte", "strike", "callOpenInterest",
                              "putOpenInterest", "gamma", "spotPrice"])
ch["tradeDate"] = pd.to_datetime(ch["tradeDate"])
g = ch["gamma"].clip(lower=0).astype("float64")
ch["net"] = g * (ch["callOpenInterest"] - ch["putOpenInterest"])
spot_by_day = ch.groupby("tradeDate")["spotPrice"].first()
ch = ch[ch["dte"] >= 2]
ch["far"] = ch["dte"] > 365
agg = ch.groupby(["tradeDate", "strike", "far"], sort=True)["net"].sum().reset_index()
del ch
DAYS = {}
for d, sub in agg.groupby("tradeDate", sort=False):
    piv = sub.pivot_table(index="strike", columns="far", values="net",
                          aggfunc="sum", fill_value=0.0)
    K = piv.index.to_numpy("float64")
    near = piv[False].to_numpy() if False in piv.columns else np.zeros(len(K))
    far = piv[True].to_numpy() if True in piv.columns else np.zeros(len(K))
    DAYS[d] = (K, near, far)
del agg

tr = pd.read_csv(f"{BASE}\\mq_truth.csv", parse_dates=["eod_date"])
tr = tr.dropna(subset=["cr", "ps"]).reset_index(drop=True)
days = [pd.Timestamp(d) for d in tr["eod_date"]]
is_fit = (tr["eod_date"] <= FIT_END).to_numpy()
years = tr["eod_date"].dt.year.to_numpy()
truth = {"cr": tr["cr"].to_numpy("float64"), "ps": tr["ps"].to_numpy("float64")}

rows, yrows = [], []
for hi, grid, bn in product((365, 9999), ("any", "m25"), ("none", "b15", "b20")):
    preds = {"cr": np.full(len(days), np.nan), "ps": np.full(len(days), np.nan)}
    for di, d in enumerate(days):
        if d not in DAYS:
            continue
        K, near, far = DAYS[d]
        v = near + (far if hi == 9999 else 0)
        spot = float(spot_by_day.get(d, np.nan))
        m = np.ones(len(K), bool)
        if grid == "m25":
            m &= K % 25 == 0
        if bn == "b15":
            m &= np.abs(K / spot - 1) <= 0.15
        elif bn == "b20":
            m &= np.abs(K / spot - 1) <= 0.20
        if not m.any():
            continue
        idx = np.where(m)[0]
        preds["cr"][di] = K[idx[v[idx].argmax()]]
        preds["ps"][di] = K[idx[v[idx].argmin()]]
    for lev, p in preds.items():
        r = {"level": lev, "hi": hi, "grid": grid, "band": bn}
        for tag, mm in [("fit", is_fit), ("hold", ~is_fit)]:
            ok = mm & ~np.isnan(p)
            ae = np.abs(p[ok] - truth[lev][ok])
            r[f"exact_{tag}"] = float((ae == 0).mean())
            r[f"w25_{tag}"] = float((ae <= 25).mean())
            r[f"medae_{tag}"] = float(np.median(ae))
        rows.append(r)
        for y in sorted(set(years)):
            ok = (years == y) & ~np.isnan(p)
            ae = np.abs(p[ok] - truth[lev][ok])
            yrows.append({"level": lev, "hi": hi, "grid": grid, "band": bn,
                          "year": y, "exact": float((ae == 0).mean())})

sb = pd.DataFrame(rows).sort_values(["level", "exact_fit"], ascending=[True, False])
sb.to_csv(f"{BASE}\\crps_gridany_20260724.csv", index=False)
pd.DataFrame(yrows).to_csv(f"{BASE}\\crps_gridany_yearly_20260724.csv", index=False)
print(sb.to_string(index=False))
yy = pd.DataFrame(yrows)
print(yy[(yy.grid == "any")].pivot_table(index=["level", "hi", "band"],
                                         columns="year", values="exact").to_string())
