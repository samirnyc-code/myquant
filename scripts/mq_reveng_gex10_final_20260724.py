"""Final: per-year precision for leading specs + ordering/symmetry summary of
MQ gex_1..10, and the locked best spec's daily scores.

Output: gex10_final_yearly_20260724.csv, gex10_final_daily_20260724.csv
"""
import numpy as np
import pandas as pd

BASE = r"C:\Users\Admin\myquant\data\regime\mq_reveng"

ch = pd.read_parquet(f"{BASE}\\chain_slices_overlap.parquet",
                     columns=["tradeDate", "dte", "strike", "callOpenInterest",
                              "putOpenInterest", "gamma", "spotPrice"])
ch["tradeDate"] = pd.to_datetime(ch["tradeDate"])
spot = ch.groupby("tradeDate")["spotPrice"].first()
ch["cg"] = ch["callOpenInterest"] * ch["gamma"].astype("float64")
ch["pg"] = ch["putOpenInterest"] * ch["gamma"].astype("float64")

SPECS = {}
m = ch["dte"].between(2, 21)
SPECS["max_d2_21_b30"] = (ch.loc[m].groupby(["tradeDate", "strike"], sort=False)
                          [["cg", "pg"]].sum(), 0.03)
w = np.exp(-ch["dte"] / 21.0)
m2 = ch["dte"] >= 2
tmp = ch.loc[m2, ["tradeDate", "strike"]].copy()
tmp["cg"] = ch.loc[m2, "cg"] * w[m2]
tmp["pg"] = ch.loc[m2, "pg"] * w[m2]
SPECS["max_wexp21_b40"] = (tmp.groupby(["tradeDate", "strike"], sort=False)
                           [["cg", "pg"]].sum(), 0.04)
SPECS["max_wexp21_b30"] = (SPECS["max_wexp21_b40"][0], 0.03)
del ch

tr = pd.read_csv(f"{BASE}\\mq_truth.csv", parse_dates=["eod_date"])
gcols = [f"gex_{k}" for k in range(1, 11)]
gvcols = [f"gex_{k}_gex" for k in range(1, 11)]
LVL7 = ["cr", "ps", "hvl", "cr0", "ps0", "hvl0", "gw0"]
tr = tr[tr[gcols].notna().any(axis=1)]

yearly_rows, daily_rows = [], []
for sname, (g, band) in SPECS.items():
    gg = g.reset_index()
    gg["v"] = np.maximum(g["cg"].values, g["pg"].values)
    by_day = dict(tuple(gg[["tradeDate", "strike", "v"]].groupby("tradeDate", sort=False)))
    recs = []
    for _, r in tr.iterrows():
        d = r["eod_date"]
        T = set(r[gcols].dropna().astype(float))
        lv = [float(r[c]) for c in LVL7 if pd.notna(r[c])]
        dv = by_day.get(d)
        if dv is None or not T or d not in spot.index:
            continue
        sp = spot[d]
        st = dv["strike"].values.astype(float)
        v = dv["v"].values
        keep = ~np.isin(st, lv) & (np.abs(st / sp - 1.0) <= band)
        st2, v2 = st[keep], v[keep]
        if len(st2) < len(T):
            continue
        C = set(st2[np.argsort(-v2)[:len(T)]])
        inter = len(C & T)
        recs.append(dict(eod_date=d, year=d.year, spec=sname,
                         precision=inter / len(T), jaccard=inter / len(C | T)))
    df = pd.DataFrame(recs)
    daily_rows.append(df)
    yr = df.groupby("year")[["precision", "jaccard"]].mean().reset_index()
    yr["spec"] = sname
    yr["n"] = df.groupby("year").size().values
    yearly_rows.append(yr)
    print(sname)
    print(yr.to_string(index=False))

pd.concat(yearly_rows).to_csv(f"{BASE}\\gex10_final_yearly_20260724.csv", index=False)
pd.concat(daily_rows).to_csv(f"{BASE}\\gex10_final_daily_20260724.csv", index=False)

# ordering / symmetry recap on truth only
diag = []
for _, r in tr.iterrows():
    d = r["eod_date"]
    if d not in spot.index:
        continue
    sp = spot[d]
    k = r[gcols].dropna().astype(float).values
    v = r[gvcols].astype(float).values[: len(k)]
    if len(k) < 3 or np.isnan(v).any():
        continue
    dist = np.abs(k - sp)
    ra = pd.Series(np.arange(len(k))).rank().values
    diag.append(dict(
        sp_dist=np.corrcoef(ra, pd.Series(dist).rank().values)[0, 1],
        sp_absv=np.corrcoef(ra, pd.Series(-np.abs(v)).rank().values)[0, 1],
        n_above=(k > sp).sum(), n_pos=(v > 0).sum(),
        pos_above=((k > sp) & (v > 0)).sum(), above=(k > sp).sum(),
        neg_below=((k < sp) & (v < 0)).sum(), below=(k < sp).sum()))
D = pd.DataFrame(diag)
print("\nORDER: mean spearman(rank,dist)=%.3f  (rank,-|v|)=%.3f" %
      (D["sp_dist"].mean(), D["sp_absv"].mean()))
print("n_above distribution:", D["n_above"].value_counts().sort_index().to_dict())
print("n_pos distribution:", D["n_pos"].value_counts().sort_index().to_dict())
print("P(v>0|above)=%.3f  P(v<0|below)=%.3f" %
      (D["pos_above"].sum() / D["above"].sum(), D["neg_below"].sum() / D["below"].sum()))
