"""Fingerprint MQ's CR / PS / 0DTE levels before the spec sweep.

Questions answered (saved to crps_fingerprint_20260724.csv):
  - rounding: do cr/ps/cr0/ps0/hvl0/gw0 land on 25/50/100 multiples?
  - sign of published cr_gex / ps_gex / gw0_gex (call-gamma pos? put-gamma neg?)
  - position vs spot: frac of days cr>=spot, ps<=spot, distance distributions
  - are cr/ps ever equal to one of the gex_1..10 strikes? (is CR just the max
    call-gamma strike also present in the top-10 list?)
  - is cr_gex ~ our call-gamma-OI at MQ's cr strike (which DTE slice correlates)?
"""
import numpy as np
import pandas as pd

BASE = r"C:\Users\Admin\myquant\data\regime\mq_reveng"

tr = pd.read_csv(f"{BASE}\\mq_truth.csv", parse_dates=["session_date", "eod_date"])
rows = []

LVLS = ["cr", "ps", "hvl", "cr0", "ps0", "hvl0", "gw0"]
for c in LVLS:
    v = tr[c].dropna()
    rows.append(dict(stat=f"{c}_n", value=len(v)))
    for m in (5, 10, 25, 50, 100):
        rows.append(dict(stat=f"{c}_frac_mult{m}", value=float(((v % m) == 0).mean())))
    gx = tr[f"{c}_gex"].dropna()
    if len(gx):
        rows.append(dict(stat=f"{c}_gex_frac_pos", value=float((gx > 0).mean())))
        rows.append(dict(stat=f"{c}_gex_median", value=float(gx.median())))
        rows.append(dict(stat=f"{c}_gex_absmedian", value=float(gx.abs().median())))

# position vs spot
sp = tr["spot_eod"]
for c in LVLS:
    v = tr[c]
    m = v.notna() & sp.notna()
    d = (v - sp)[m]
    rows.append(dict(stat=f"{c}_frac_above_spot", value=float((d > 0).mean())))
    rows.append(dict(stat=f"{c}_dist_spot_med", value=float(d.median())))
    rows.append(dict(stat=f"{c}_absdist_spot_med", value=float(d.abs().median())))
    rows.append(dict(stat=f"{c}_absdist_spot_p95", value=float(d.abs().quantile(0.95))))
    rows.append(dict(stat=f"{c}_reldist_p95", value=float((d.abs() / sp[m]).quantile(0.95))))

# overlap with gex_1..10
gcols = [f"gex_{k}" for k in range(1, 11)]
for c in ["cr", "ps"]:
    hit = []
    for _, r in tr.iterrows():
        if pd.isna(r[c]):
            continue
        T = set(r[gcols].dropna().astype(float))
        hit.append(float(r[c]) in T)
    rows.append(dict(stat=f"{c}_in_gex10_frac", value=float(np.mean(hit))))
    # which rank
for c in ["cr", "ps"]:
    ranks = []
    for _, r in tr.iterrows():
        if pd.isna(r[c]):
            continue
        for k in range(1, 11):
            if pd.notna(r[f"gex_{k}"]) and float(r[f"gex_{k}"]) == float(r[c]):
                ranks.append(k)
                break
    if ranks:
        rows.append(dict(stat=f"{c}_gex10_rank_med", value=float(np.median(ranks))))
        rows.append(dict(stat=f"{c}_gex10_rank1_frac",
                         value=float(np.mean(np.array(ranks) == 1))))

# does cr_gex equal the gex_k_gex at the matching strike?
match = 0
tot = 0
for _, r in tr.iterrows():
    if pd.isna(r["cr"]) or pd.isna(r["cr_gex"]):
        continue
    for k in range(1, 11):
        if pd.notna(r[f"gex_{k}"]) and float(r[f"gex_{k}"]) == float(r["cr"]):
            tot += 1
            if pd.notna(r[f"gex_{k}_gex"]) and np.isclose(r[f"gex_{k}_gex"], r["cr_gex"], rtol=1e-6):
                match += 1
            break
rows.append(dict(stat="cr_gex_equals_gex10gex_frac", value=match / tot if tot else np.nan))
rows.append(dict(stat="cr_gex_equals_gex10gex_n", value=tot))

# correlate cr_gex with our call-gamma-OI at cr strike, per DTE slice ------------
ch = pd.read_parquet(f"{BASE}\\chain_slices_overlap.parquet",
                     columns=["tradeDate", "dte", "strike", "callOpenInterest",
                              "putOpenInterest", "gamma"])
ch["tradeDate"] = pd.to_datetime(ch["tradeDate"])
ch["cg"] = ch["gamma"].clip(lower=0) * ch["callOpenInterest"]
ch["pg"] = ch["gamma"].clip(lower=0) * ch["putOpenInterest"]
for tag, m in [("all", ch["dte"] >= 0), ("d0", ch["dte"] == 0),
               ("ex0", ch["dte"] >= 1), ("le30", ch["dte"].between(0, 30)),
               ("le45", ch["dte"].between(0, 45))]:
    A = ch.loc[m].groupby(["tradeDate", "strike"])[["cg", "pg"]].sum()
    for lvl, col in (("cr", "cg"), ("ps", "pg"), ("gw0", "cg")):
        xs, ys = [], []
        for _, r in tr.iterrows():
            if pd.isna(r[lvl]) or pd.isna(r[f"{lvl}_gex"]):
                continue
            key = (r["eod_date"], float(r[lvl]))
            if key in A.index:
                xs.append(A.loc[key, col])
                ys.append(abs(r[f"{lvl}_gex"]))
        if len(xs) > 10:
            xs, ys = np.array(xs), np.array(ys)
            rows.append(dict(stat=f"corr_abs{lvl}gex_vs_{col}_{tag}",
                             value=float(np.corrcoef(xs, ys)[0, 1])))
            rows.append(dict(stat=f"ratio_med_abs{lvl}gex_over_{col}_{tag}",
                             value=float(np.median(ys / np.maximum(xs, 1e-12)))))

out = pd.DataFrame(rows)
out.to_csv(f"{BASE}\\crps_fingerprint_20260724.csv", index=False)
pd.set_option("display.width", 200)
print(out.to_string(index=False))
