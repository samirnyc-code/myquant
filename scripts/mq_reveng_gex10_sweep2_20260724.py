"""Sweep 2 for gex_1..10 spec: exclude ALL 7 published levels (cr,ps,hvl,cr0,ps0,
hvl0,gw0) from candidates, and probe DTE floors (drop 0DTE/short weeklies whose
ATM gamma over-weights near-spot strikes vs MQ truth).

Output: gex10_spec_scores2_20260724.csv
"""
import numpy as np
import pandas as pd

BASE = r"C:\Users\Admin\myquant\data\regime\mq_reveng"
FIT_END = pd.Timestamp("2023-12-31")

ch = pd.read_parquet(f"{BASE}\\chain_slices_overlap.parquet",
                     columns=["tradeDate", "expirDate", "dte", "strike",
                              "callOpenInterest", "putOpenInterest", "gamma",
                              "spotPrice"])
ch["tradeDate"] = pd.to_datetime(ch["tradeDate"])
spot = ch.groupby("tradeDate")["spotPrice"].first()
ch["cg"] = ch["callOpenInterest"] * ch["gamma"].astype("float64")
ch["pg"] = ch["putOpenInterest"] * ch["gamma"].astype("float64")
ed = pd.to_datetime(ch["expirDate"])
ch["is_monthly"] = ((ed.dt.weekday == 4) & ed.dt.day.between(15, 21)).values

DTE = {
    "all": ch["dte"] >= 0,
    "d1_inf": ch["dte"] >= 1,
    "d2_inf": ch["dte"] >= 2,
    "d5_inf": ch["dte"] >= 5,
    "d1_30": ch["dte"].between(1, 30),
    "d1_45": ch["dte"].between(1, 45),
    "d1_60": ch["dte"].between(1, 60),
    "d1_90": ch["dte"].between(1, 90),
    "d2_60": ch["dte"].between(2, 60),
    "d5_60": ch["dte"].between(5, 60),
    "d0_30": ch["dte"].between(0, 30),
    "d0_60": ch["dte"].between(0, 60),
    "monthly": ch["is_monthly"],
    "monthly_d1": ch["is_monthly"] & (ch["dte"] >= 1),
}
AGG = {}
for name, m in DTE.items():
    AGG[name] = ch.loc[m].groupby(["tradeDate", "strike"], sort=False)[
        ["cg", "pg", "callOpenInterest", "putOpenInterest"]].sum()
del ch

tr = pd.read_csv(f"{BASE}\\mq_truth.csv", parse_dates=["session_date", "eod_date"])
gcols = [f"gex_{k}" for k in range(1, 11)]
LVL7 = ["cr", "ps", "hvl", "cr0", "ps0", "hvl0", "gw0"]
tr = tr[tr[gcols].notna().any(axis=1)]

truth = []
for _, r in tr.iterrows():
    truth.append((r["eod_date"],
                  set(r[gcols].dropna().astype(float)),
                  {float(r[c]) for c in LVL7 if pd.notna(r[c])}))

FORMULAS = {
    "net_gob": lambda g: g["cg"] - g["pg"],
    "tot_gob": lambda g: g["cg"] + g["pg"],
    "net_oi":  lambda g: (g["callOpenInterest"] - g["putOpenInterest"]).astype(float),
    "tot_oi":  lambda g: (g["callOpenInterest"] + g["putOpenInterest"]).astype(float),
}
rows = []
for fname, ffun in FORMULAS.items():
    for dname, g in AGG.items():
        val = ffun(g).rename("v").reset_index()
        by_day = dict(tuple(val.groupby("tradeDate", sort=False)))
        pf = jf = ph = jh = 0.0
        nf = nh = 0
        for d, T, ex7 in truth:
            dv = by_day.get(d)
            if dv is None or not T:
                continue
            st = dv["strike"].values.astype(float)
            v = dv["v"].values
            keep = ~np.isin(st, list(ex7))
            st2, v2 = st[keep], v[keep]
            n = len(T)
            if len(st2) < n:
                continue
            idx = np.argsort(-np.abs(v2))[:n]
            C = set(st2[idx])
            inter = len(C & T)
            prec = inter / n
            jac = inter / len(C | T)
            if d <= FIT_END:
                pf += prec; jf += jac; nf += 1
            else:
                ph += prec; jh += jac; nh += 1
        if nf and nh:
            rows.append(dict(formula=fname, dte=dname, excl="excl7",
                             prec_fit=pf / nf, jacc_fit=jf / nf, n_fit=nf,
                             prec_holdout=ph / nh, jacc_holdout=jh / nh,
                             n_holdout=nh))

sc = pd.DataFrame(rows).sort_values("prec_fit", ascending=False)
sc.to_csv(f"{BASE}\\gex10_spec_scores2_20260724.csv", index=False)
print(sc.to_string(index=False))
