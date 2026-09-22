"""Sweep 4: fine-tune max(callGEX,putGEX) selection — dte windows around 2-21,
exp-dte decay, and relative strike-band caps (FPs of d2_21 sit too far out).

Output: gex10_spec_scores4_20260724.csv + per-day file for the best spec.
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
ch["cg"] = ch["callOpenInterest"] * ch["gamma"].astype("float64")
ch["pg"] = ch["putOpenInterest"] * ch["gamma"].astype("float64")

AGG = {}
WINDOWS = {"d1_10": (1, 10), "d2_10": (2, 10), "d1_14": (1, 14), "d2_14": (2, 14),
           "d3_14": (3, 14), "d1_21": (1, 21), "d2_21": (2, 21), "d2_25": (2, 25),
           "d4_21": (4, 21), "d5_21": (5, 21), "d2_18": (2, 18), "d2_28": (2, 28)}
for name, (lo, hi) in WINDOWS.items():
    m = ch["dte"].between(lo, hi)
    AGG[name] = ch.loc[m].groupby(["tradeDate", "strike"], sort=False)[["cg", "pg"]].sum()
for tau in (5, 7, 10, 14, 21):
    w = np.exp(-ch["dte"] / tau)
    tmp = ch.loc[ch["dte"] >= 2, ["tradeDate", "strike"]].copy()
    ww = w[ch["dte"] >= 2]
    tmp["cg"] = ch.loc[ch["dte"] >= 2, "cg"] * ww
    tmp["pg"] = ch.loc[ch["dte"] >= 2, "pg"] * ww
    AGG[f"wexp{tau}_d2"] = tmp.groupby(["tradeDate", "strike"], sort=False)[["cg", "pg"]].sum()
del ch

tr = pd.read_csv(f"{BASE}\\mq_truth.csv", parse_dates=["eod_date"])
gcols = [f"gex_{k}" for k in range(1, 11)]
LVL7 = ["cr", "ps", "hvl", "cr0", "ps0", "hvl0", "gw0"]
tr = tr[tr[gcols].notna().any(axis=1)]
truth = [(r["eod_date"], set(r[gcols].dropna().astype(float)),
          [float(r[c]) for c in LVL7 if pd.notna(r[c])]) for _, r in tr.iterrows()]

BANDS = (None, 0.02, 0.025, 0.03, 0.04, 0.05)
rows = []
best = (-1, None, None)
for dname, g in AGG.items():
    gg = g.reset_index()
    gg["v"] = np.maximum(g["cg"].values, g["pg"].values)
    by_day = dict(tuple(gg[["tradeDate", "strike", "v"]].groupby("tradeDate", sort=False)))
    for band in BANDS:
        pf = jf = ph = jh = 0.0
        nf = nh = 0
        daily = []
        for d, T, lv in truth:
            dv = by_day.get(d)
            if dv is None or not T or d not in spot.index:
                continue
            sp = spot[d]
            st = dv["strike"].values.astype(float)
            v = dv["v"].values
            keep = ~np.isin(st, lv)
            if band is not None:
                keep &= np.abs(st / sp - 1.0) <= band
            st2, v2 = st[keep], v[keep]
            n = len(T)
            if len(st2) < n:
                continue
            idx = np.argsort(-v2)[:n]
            C = set(st2[idx])
            inter = len(C & T)
            if d <= FIT_END:
                pf += inter / n; jf += inter / len(C | T); nf += 1
            else:
                ph += inter / n; jh += inter / len(C | T); nh += 1
            daily.append(dict(eod_date=d, precision=inter / n,
                              jaccard=inter / len(C | T)))
        if not (nf and nh):
            continue
        rec = dict(dte=dname, band=band if band else 0,
                   prec_fit=pf / nf, jacc_fit=jf / nf,
                   prec_holdout=ph / nh, jacc_holdout=jh / nh)
        rows.append(rec)
        if rec["prec_fit"] > best[0]:
            best = (rec["prec_fit"], rec, daily)

sc = pd.DataFrame(rows).sort_values("prec_fit", ascending=False)
sc.to_csv(f"{BASE}\\gex10_spec_scores4_20260724.csv", index=False)
print(sc.head(25).to_string(index=False))
print("\nbest:", best[1])
pd.DataFrame(best[2]).to_csv(f"{BASE}\\gex10_best_daily4_20260724.csv", index=False)
