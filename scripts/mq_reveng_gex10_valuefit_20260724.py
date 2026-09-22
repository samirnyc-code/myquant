"""Fingerprint MQ's GEX value formula from their published *_gex numbers.

Per day we have their GEX value at up to 13 strikes (gex_1..10 + cr/ps/hvl).
Model: mq_val(K) = sum_over_dte_buckets w_b * NET_b(K)   (per-day lstsq, no
intercept), where NET_b(K) = sum over expiries in bucket b of
(callOI*gamma - putOI*gamma) at strike K.  Also a call/put split variant:
mq_val(K) = a*CALL(K) - b*PUT(K) over a fixed dte window.

Collect per-day coefficients -> medians = their effective dte weighting.
Then re-rank strikes with fitted weights and score top-10 overlap
(fit <=2023-12-31 vs holdout 2024+).

Outputs: gex10_valuefit_weights_20260724.csv, gex10_valuefit_scores_20260724.csv
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

BUCKETS = [(0, 0), (1, 2), (3, 5), (6, 10), (11, 21), (22, 45), (46, 90), (91, 400)]
BNAMES = [f"b{lo}_{hi}" for lo, hi in BUCKETS]
ch["bucket"] = -1
for i, (lo, hi) in enumerate(BUCKETS):
    ch.loc[ch["dte"].between(lo, hi), "bucket"] = i

g = ch.groupby(["tradeDate", "strike", "bucket"])[["cg", "pg"]].sum()
g["net"] = g["cg"] - g["pg"]
cols = list(range(len(BUCKETS)))
net_w = g["net"].unstack("bucket", fill_value=0.0).reindex(columns=cols, fill_value=0.0)
cg_w = g["cg"].unstack("bucket", fill_value=0.0).reindex(columns=cols, fill_value=0.0)
pg_w = g["pg"].unstack("bucket", fill_value=0.0).reindex(columns=cols, fill_value=0.0)
del ch, g

tr = pd.read_csv(f"{BASE}\\mq_truth.csv", parse_dates=["eod_date"])
gcols = [f"gex_{k}" for k in range(1, 11)]
gvcols = [f"gex_{k}_gex" for k in range(1, 11)]
tr = tr[tr[gcols].notna().any(axis=1)]

# --- per-day regressions -----------------------------------------------------
Wrows, cp_rows = [], []
net_by_day = dict(tuple(net_w.reset_index().groupby("tradeDate", sort=False)))
cg_by_day = dict(tuple(cg_w.reset_index().groupby("tradeDate", sort=False)))
pg_by_day = dict(tuple(pg_w.reset_index().groupby("tradeDate", sort=False)))

for _, r in tr.iterrows():
    d = r["eod_date"]
    if d not in net_by_day or d not in spot.index:
        continue
    pts = {}
    for kc, vc in zip(gcols, gvcols):
        if pd.notna(r[kc]) and pd.notna(r[vc]):
            pts[float(r[kc])] = float(r[vc])
    for kc, vc in (("cr", "cr_gex"), ("ps", "ps_gex"), ("hvl", "hvl_gex")):
        if pd.notna(r[kc]) and pd.notna(r[vc]):
            pts.setdefault(float(r[kc]), float(r[vc]))
    if len(pts) < 10:
        continue
    dv = net_by_day[d].set_index("strike")
    ks = [k for k in pts if k in dv.index]
    if len(ks) < 10:
        continue
    X = dv.loc[ks, list(range(len(BUCKETS)))].values
    y = np.array([pts[k] for k in ks])
    ok = np.isfinite(y) & np.isfinite(X).all(axis=1)
    X, y = X[ok], y[ok]
    ks = [k for k, o in zip(ks, ok) if o]
    if len(y) < 10:
        continue
    scale = np.abs(y).max()
    if not np.isfinite(scale) or scale == 0:
        continue
    w, res, _, _ = np.linalg.lstsq(X / scale, y / scale, rcond=None)
    pred = X @ w
    ss = 1 - np.sum((y - pred) ** 2) / np.sum((y - y.mean()) ** 2)
    Wrows.append(dict(eod_date=d, r2=ss, spot=spot[d],
                      **{n: wi for n, wi in zip(BNAMES, w)}))
    # call/put split over dte<=90 window (buckets 0..6)
    dc = cg_by_day[d].set_index("strike")
    dp = pg_by_day[d].set_index("strike")
    C = dc.loc[ks, list(range(7))].values.sum(axis=1)
    P = dp.loc[ks, list(range(7))].values.sum(axis=1)
    A = np.column_stack([C, -P])
    ab, _, _, _ = np.linalg.lstsq(A / scale, y / scale, rcond=None)
    predcp = A @ ab
    r2cp = 1 - np.sum((y - predcp) ** 2) / np.sum((y - y.mean()) ** 2)
    cp_rows.append(dict(eod_date=d, a_call=ab[0], b_put=ab[1], r2=r2cp,
                        ratio=ab[1] / ab[0] if ab[0] else np.nan))

W = pd.DataFrame(Wrows)
W.to_csv(f"{BASE}\\gex10_valuefit_weights_20260724.csv", index=False)
CP = pd.DataFrame(cp_rows)
print(f"days fit: {len(W)}   median R2 (bucket model): {W['r2'].median():.4f}")
print("median bucket weights (normalized to b22_45):")
med = W[BNAMES].median()
print((med / med["b22_45"]).to_string())
print("raw median bucket weights:")
print(med.to_string())
# scale vs spot^2
W["w_ref"] = W["b22_45"]
print("median w_ref:", W["w_ref"].median(), " median w_ref/spot^2:",
      (W["w_ref"] / W["spot"] ** 2).median(), " /spot:",
      (W["w_ref"] / W["spot"]).median())
print(f"\ncall/put split: median R2 {CP['r2'].median():.4f}  "
      f"median a_call {CP['a_call'].median():.1f}  b_put {CP['b_put'].median():.1f}  "
      f"median put/call ratio {CP['ratio'].median():.3f}")

# --- re-rank with fitted global weights --------------------------------------
LVL7 = ["cr", "ps", "hvl", "cr0", "ps0", "hvl0", "gw0"]
truth = []
for _, r in tr.iterrows():
    truth.append((r["eod_date"], set(r[gcols].dropna().astype(float)),
                  [float(r[c]) for c in LVL7 if pd.notna(r[c])]))

wfit_med = W[BNAMES].median().values
# fit weights only on fit period to be clean
wfit_fitper = W.loc[W["eod_date"] <= FIT_END, BNAMES].median().values
print("\nfit-period-only median weights (norm to b22_45):")
print((pd.Series(wfit_fitper, index=BNAMES) / wfit_fitper[5]).to_string())

def score(weights, table, label):
    by_day = dict(tuple(table.reset_index().groupby("tradeDate", sort=False)))
    pf = jf = ph = jh = 0.0
    nf = nh = 0
    for d, T, lv in truth:
        dv = by_day.get(d)
        if dv is None or not T:
            continue
        st = dv["strike"].values.astype(float)
        v = dv[list(range(len(BUCKETS)))].values @ weights
        keep = ~np.isin(st, lv)
        st2, v2 = st[keep], v[keep]
        if len(st2) < len(T):
            continue
        idx = np.argsort(-np.abs(v2))[:len(T)]
        C = set(st2[idx])
        inter = len(C & T)
        if d <= FIT_END:
            pf += inter / len(T); jf += inter / len(C | T); nf += 1
        else:
            ph += inter / len(T); jh += inter / len(C | T); nh += 1
    out = dict(spec=label, prec_fit=pf / nf, jacc_fit=jf / nf,
               prec_holdout=ph / nh, jacc_holdout=jh / nh)
    print(out)
    return out

res = []
res.append(score(wfit_fitper, net_w, "net_fittedW(fitper)"))
res.append(score(wfit_med, net_w, "net_fittedW(all)"))
tot_w = cg_w + pg_w
res.append(score(wfit_fitper, tot_w, "tot_fittedW(fitper)"))
res.append(score(wfit_med, tot_w, "tot_fittedW(all)"))
# reference: uniform over dte 2-60 approx = buckets 1..6 partial
uni = np.array([0, 1, 1, 1, 1, 1, 1, 0], dtype=float)
res.append(score(uni, tot_w, "tot_uniform_d1_90"))
pd.DataFrame(res).to_csv(f"{BASE}\\gex10_valuefit_scores_20260724.csv", index=False)
