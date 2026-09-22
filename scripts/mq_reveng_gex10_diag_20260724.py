"""Diagnostics for the gex_1..10 universe: strike granularity, overlap with 0DTE
levels, and anatomy of false positives/negatives for the leading spec
(tot gamma*OI, dte<=30, excl CR/PS/HVL).

Output: gex10_diag_20260724.csv (false pos/neg rows) + printed stats.
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
m = ch["dte"].between(0, 30)
g = ch.loc[m].groupby(["tradeDate", "strike"])[["cg", "pg"]].sum()
g["tot"] = g["cg"] + g["pg"]
g["net"] = g["cg"] - g["pg"]
by_day = dict(tuple(g.reset_index().groupby("tradeDate", sort=False)))

tr = pd.read_csv(f"{BASE}\\mq_truth.csv", parse_dates=["session_date", "eod_date"])
gcols = [f"gex_{k}" for k in range(1, 11)]

# 1) strike granularity of truth picks
allk = tr[gcols].values.ravel()
allk = allk[~pd.isna(allk)].astype(float)
for q in (5, 10, 25, 50, 100):
    print(f"truth gex strikes divisible by {q}: {(allk % q == 0).mean():.4f}")

# n picks per day
npicks = tr[gcols].notna().sum(axis=1)
print("picks per day value counts:", npicks.value_counts().to_dict())

# 2) overlap with the 0dte/other level columns
lvlcols = ["cr", "ps", "hvl", "cr0", "ps0", "hvl0", "gw0", "d1_min", "d1_max"]
for c in lvlcols:
    hit = tr.apply(lambda r: pd.notna(r[c]) and r[c] in set(r[gcols].dropna()), axis=1)
    print(f"gex set contains {c}: {hit.mean():.4f}")

# 3) false positive / negative anatomy for leading spec
rows = []
for _, r in tr.iterrows():
    d = r["eod_date"]
    T = set(r[gcols].dropna().astype(float))
    if not T or d not in by_day:
        continue
    dv = by_day[d]
    sp = spot[d]
    ex = {r[c] for c in ("cr", "ps", "hvl") if pd.notna(r[c])}
    st, v = dv["strike"].values.astype(float), dv["tot"].values
    keep = ~np.isin(st, list(ex))
    st, v = st[keep], v[keep]
    order = np.argsort(-np.abs(v))
    n = len(T)
    cand = st[order[:n]]
    C = set(cand)
    for k in C - T:
        rows.append(dict(eod_date=d, kind="FP", strike=k, dist=(k - sp),
                         mod25=k % 25 == 0, reldist=abs(k / sp - 1)))
    for k in T - C:
        # where did it rank in our list?
        pos = np.where(st[order] == k)[0]
        rows.append(dict(eod_date=d, kind="FN", strike=k, dist=(k - sp),
                         mod25=k % 25 == 0, reldist=abs(k / sp - 1),
                         our_rank=int(pos[0]) + 1 if len(pos) else -1))
diag = pd.DataFrame(rows)
diag.to_csv(f"{BASE}\\gex10_diag_20260724.csv", index=False)
fp = diag[diag["kind"] == "FP"]
fn = diag[diag["kind"] == "FN"]
print(f"\nFP: {len(fp)}  mod25 frac: {fp['mod25'].mean():.3f}  "
      f"median reldist: {fp['reldist'].median():.4f}")
print(f"FN: {len(fn)}  mod25 frac: {fn['mod25'].mean():.3f}  "
      f"median reldist: {fn['reldist'].median():.4f}")
print("FN our_rank describe:")
print(fn["our_rank"].describe().to_string())
print("FN our_rank quantiles:", fn["our_rank"].quantile([0.5, 0.75, 0.9]).to_dict())
print("\nFP reldist quantiles:", fp["reldist"].quantile([0.25, 0.5, 0.75, 0.95]).to_dict())
print("FN reldist quantiles:", fn["reldist"].quantile([0.25, 0.5, 0.75, 0.95]).to_dict())
print("FP dist sign: above frac", (fp["dist"] > 0).mean())
print("FN dist sign: above frac", (fn["dist"] > 0).mean())
