"""Test for a minimum-spacing / dedup rule in MQ's gex_1..10 picks.

1. Distribution of nearest-neighbor spacing within {gex strikes} and between
   gex strikes and the 7 published levels (abs pts and % of spot).
2. Greedy top-|GEX| selection with a min-spacing constraint (vs levels and vs
   already-picked strikes), grid over spacing, using tot gamma*OI d2_60 / d1_30.

Output: gex10_spacing_scores_20260724.csv + printed spacing distribution.
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
for name, m in {"d2_60": ch["dte"].between(2, 60),
                "d1_30": ch["dte"].between(1, 30)}.items():
    g = ch.loc[m].groupby(["tradeDate", "strike"], sort=False)[["cg", "pg"]].sum()
    g["tot"] = g["cg"] + g["pg"]
    AGG[name] = dict(tuple(g.reset_index().groupby("tradeDate", sort=False)))
del ch

tr = pd.read_csv(f"{BASE}\\mq_truth.csv", parse_dates=["eod_date"])
gcols = [f"gex_{k}" for k in range(1, 11)]
LVL7 = ["cr", "ps", "hvl", "cr0", "ps0", "hvl0", "gw0"]
tr = tr[tr[gcols].notna().any(axis=1)]

# --- 1) spacing stats --------------------------------------------------------
nn_within, nn_tolvl = [], []
for _, r in tr.iterrows():
    d = r["eod_date"]
    if d not in spot.index:
        continue
    sp = spot[d]
    ks = np.sort(r[gcols].dropna().astype(float).values)
    lv = np.array([r[c] for c in LVL7 if pd.notna(r[c])], dtype=float)
    if len(ks) >= 2:
        nn_within.extend((np.diff(ks) / sp * 100).tolist())
    for k in ks:
        if len(lv):
            nn_tolvl.append(np.abs(lv - k).min() / sp * 100)
nn_within = pd.Series(nn_within)
nn_tolvl = pd.Series(nn_tolvl)
print("gap between adjacent gex strikes (% of spot):")
print(nn_within.quantile([0, .01, .05, .1, .25, .5]).to_string())
print("min gap gex-strike -> nearest level (% of spot):")
print(nn_tolvl.quantile([0, .01, .05, .1, .25, .5]).to_string())
print("abs pts adjacent gap min/1%/5%:",
      (nn_within * 0).min())  # placeholder replaced below
w_abs, l_abs = [], []
for _, r in tr.iterrows():
    ks = np.sort(r[gcols].dropna().astype(float).values)
    lv = np.array([r[c] for c in LVL7 if pd.notna(r[c])], dtype=float)
    if len(ks) >= 2:
        w_abs.extend(np.diff(ks).tolist())
    for k in ks:
        if len(lv):
            l_abs.append(np.abs(lv - k).min())
print("adjacent gap abs pts quantiles:",
      pd.Series(w_abs).quantile([0, .01, .05, .25, .5]).to_dict())
print("gap-to-level abs pts quantiles:",
      pd.Series(l_abs).quantile([0, .01, .05, .25, .5]).to_dict())

# --- 2) greedy selection with min spacing ------------------------------------
truth = []
for _, r in tr.iterrows():
    truth.append((r["eod_date"],
                  set(r[gcols].dropna().astype(float)),
                  np.array([r[c] for c in LVL7 if pd.notna(r[c])], dtype=float)))

rows = []
for dname, by_day in AGG.items():
    for spacing_pts in (0, 5, 10, 15, 20, 25):
        for rel in (False, True):
            pf = jf = ph = jh = 0.0
            nf = nh = 0
            for d, T, lv in truth:
                dv = by_day.get(d)
                if dv is None or not T or d not in spot.index:
                    continue
                sp = spot[d]
                gap = sp * spacing_pts / 10000.0 if rel else float(spacing_pts)
                st = dv["strike"].values.astype(float)
                v = np.abs(dv["tot"].values)
                order = np.argsort(-v)
                picked = []
                for i in order:
                    k = st[i]
                    if len(lv) and np.abs(lv - k).min() < max(gap, 1e-9):
                        continue
                    if len(lv) and np.any(lv == k):
                        continue
                    if picked and np.abs(np.array(picked) - k).min() < gap:
                        continue
                    picked.append(k)
                    if len(picked) == len(T):
                        break
                C = set(picked)
                inter = len(C & T)
                prec = inter / len(T)
                jac = inter / len(C | T)
                if d <= FIT_END:
                    pf += prec; jf += jac; nf += 1
                else:
                    ph += prec; jh += jac; nh += 1
            rows.append(dict(dte=dname, spacing=spacing_pts,
                             unit="bp_of_spot" if rel else "pts",
                             prec_fit=pf / nf, jacc_fit=jf / nf,
                             prec_holdout=ph / nh, jacc_holdout=jh / nh))
sc = pd.DataFrame(rows).sort_values("prec_fit", ascending=False)
sc.to_csv(f"{BASE}\\gex10_spacing_scores_20260724.csv", index=False)
print(sc.to_string(index=False))
