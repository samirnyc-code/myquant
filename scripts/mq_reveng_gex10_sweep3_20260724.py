"""Sweep 3: refine the SELECTION metric for MQ's gex_1..10 (their displayed
value is net all-dte>=3 gammaOI, but selection is not top-|value|).

Variants: tot/net/max(call,put) gammaOI, gamma^p*OI blends, strike^2/K
multipliers, dte windows, exp-dte weights, and per-side (5 above / 5 below)
selection.  Always exclude the 7 published levels.  Fit <=2023-12-31 vs
holdout 2024+.

Output: gex10_spec_scores3_20260724.csv, gex10_diag3_20260724.csv (FP/FN of best)
"""
import numpy as np
import pandas as pd

BASE = r"C:\Users\Admin\myquant\data\regime\mq_reveng"
FIT_END = pd.Timestamp("2023-12-31")

ch = pd.read_parquet(f"{BASE}\\chain_slices_overlap.parquet",
                     columns=["tradeDate", "dte", "strike", "callOpenInterest",
                              "putOpenInterest", "gamma", "spotPrice"])
ch["tradeDate"] = pd.to_datetime(ch["tradeDate"])
spot = ch.groupby("tradeDate")["spotPrice"].first()
gam = ch["gamma"].astype("float64")
cOI = ch["callOpenInterest"].astype("float64")
pOI = ch["putOpenInterest"].astype("float64")
ch["cg"] = cOI * gam
ch["pg"] = pOI * gam
ch["cg_h"] = cOI * np.sqrt(gam)          # gamma^0.5 blend
ch["pg_h"] = pOI * np.sqrt(gam)
K2 = ch["strike"].astype("float64") ** 2
ch["cgK2"] = ch["cg"] * K2
ch["pgK2"] = ch["pg"] * K2

WINDOWS = {
    "d1_21": (1, 21), "d2_21": (2, 21), "d3_21": (3, 21),
    "d2_30": (2, 30), "d3_30": (3, 30),
    "d2_45": (2, 45), "d3_45": (3, 45),
    "d2_60": (2, 60), "d3_60": (3, 60),
    "d3_90": (3, 90), "d3_inf": (3, 10000),
}
VALCOLS = ["cg", "pg", "cg_h", "pg_h", "cgK2", "pgK2"]
AGG = {}
for name, (lo, hi) in WINDOWS.items():
    m = ch["dte"].between(lo, hi)
    AGG[name] = ch.loc[m].groupby(["tradeDate", "strike"], sort=False)[VALCOLS].sum()
# exp decay weights on tot
for tau in (10, 20, 30):
    w = np.exp(-ch["dte"].clip(lower=0) / tau)
    tmp = ch[["tradeDate", "strike"]].copy()
    tmp["cg"] = ch["cg"] * w
    tmp["pg"] = ch["pg"] * w
    for c in ("cg_h", "pg_h", "cgK2", "pgK2"):
        tmp[c] = 0.0
    AGG[f"wexp{tau}_d1"] = tmp[ch["dte"] >= 1].groupby(
        ["tradeDate", "strike"], sort=False)[VALCOLS].sum()
del ch

tr = pd.read_csv(f"{BASE}\\mq_truth.csv", parse_dates=["eod_date"])
gcols = [f"gex_{k}" for k in range(1, 11)]
LVL7 = ["cr", "ps", "hvl", "cr0", "ps0", "hvl0", "gw0"]
tr = tr[tr[gcols].notna().any(axis=1)]
truth = [(r["eod_date"], set(r[gcols].dropna().astype(float)),
          [float(r[c]) for c in LVL7 if pd.notna(r[c])]) for _, r in tr.iterrows()]

FORMULAS = {
    "tot_gob": lambda g: (g["cg"] + g["pg"]).values,
    "net_gob": lambda g: (g["cg"] - g["pg"]).values,
    "max_gob": lambda g: np.maximum(g["cg"].values, g["pg"].values),
    "tot_gob_h": lambda g: (g["cg_h"] + g["pg_h"]).values,
    "tot_gobK2": lambda g: (g["cgK2"] + g["pgK2"]).values,
}
MODES = ("top10", "5up5dn")

rows = []
diag_best = None
best_score = -1
for fname, ffun in FORMULAS.items():
    for dname, g in AGG.items():
        if "wexp" in dname and fname not in ("tot_gob", "net_gob", "max_gob"):
            continue
        gg = g.reset_index()
        gg["v"] = ffun(g)
        by_day = dict(tuple(gg[["tradeDate", "strike", "v"]]
                            .groupby("tradeDate", sort=False)))
        for mode in MODES:
            pf = jf = ph = jh = 0.0
            nf = nh = 0
            fpfn = []
            for d, T, lv in truth:
                dv = by_day.get(d)
                if dv is None or not T or d not in spot.index:
                    continue
                sp = spot[d]
                st = dv["strike"].values.astype(float)
                v = dv["v"].values
                keep = ~np.isin(st, lv)
                st2, v2 = st[keep], np.abs(v[keep])
                n = len(T)
                if len(st2) < n:
                    continue
                if mode == "top10":
                    idx = np.argsort(-v2)[:n]
                    C = set(st2[idx])
                else:
                    up = st2 > sp
                    iu = np.argsort(-v2[up])[: n // 2]
                    idn = np.argsort(-v2[~up])[: n - n // 2]
                    C = set(st2[up][iu]) | set(st2[~up][idn])
                inter = len(C & T)
                if d <= FIT_END:
                    pf += inter / n; jf += inter / len(C | T); nf += 1
                else:
                    ph += inter / n; jh += inter / len(C | T); nh += 1
                fpfn.append((d, sp, C, T))
            if not (nf and nh):
                continue
            rec = dict(formula=fname, dte=dname, mode=mode,
                       prec_fit=pf / nf, jacc_fit=jf / nf,
                       prec_holdout=ph / nh, jacc_holdout=jh / nh)
            rows.append(rec)
            if rec["prec_fit"] > best_score:
                best_score = rec["prec_fit"]
                diag_best = (rec, fpfn)

sc = pd.DataFrame(rows).sort_values("prec_fit", ascending=False)
sc.to_csv(f"{BASE}\\gex10_spec_scores3_20260724.csv", index=False)
print(sc.head(30).to_string(index=False))

rec, fpfn = diag_best
print("\nbest:", rec)
dr = []
for d, sp, C, T in fpfn:
    for k in C - T:
        dr.append(dict(eod_date=d, kind="FP", strike=k, reldist=abs(k / sp - 1),
                       above=k > sp))
    for k in T - C:
        dr.append(dict(eod_date=d, kind="FN", strike=k, reldist=abs(k / sp - 1),
                       above=k > sp))
dr = pd.DataFrame(dr)
dr.to_csv(f"{BASE}\\gex10_diag3_20260724.csv", index=False)
for kind in ("FP", "FN"):
    s = dr[dr["kind"] == kind]
    print(f"{kind}: n={len(s)} median reldist {s['reldist'].median():.4f} "
          f"above-frac {s['above'].mean():.3f} "
          f"reldist q75 {s['reldist'].quantile(.75):.4f}")
