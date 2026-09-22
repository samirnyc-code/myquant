"""MQ reverse-engineering: crack the strike universe + ranking behind gex_1..gex_10.

Approach:
  1. Precompute per-(tradeDate,strike) call/put gamma-OI sums under several DTE filters.
  2. Candidate specs = {value formula} x {DTE filter} x {strike band} x {exclude CR/PS/HVL or not}.
     Ranking-wise, constant-per-day multipliers (spot^2, contract mult) don't matter.
  3. Score top-N strike overlap vs MQ's gex_1..gex_10 set: precision@N, Jaccard.
     Fit on eod_date <= 2023-12-31, report holdout 2024+ separately.
  4. Fingerprint their VALUE: per-day ratio mq_gex / (net gammaOI) at their strikes,
     check against spot^2-type multipliers.
  5. Infer their ORDERING of gex_1..gex_10 (by |gex|? distance? raw?) and set symmetry.

Outputs (data/regime/mq_reveng/):
  gex10_spec_scores_20260724.csv     - per-spec fit/holdout precision & jaccard
  gex10_best_daily_20260724.csv      - per-day scores for the best spec
  gex10_order_symmetry_20260724.csv  - ordering/symmetry diagnostics
  gex10_value_ratio_20260724.csv     - per-day mq/candidate value ratio fingerprint
"""
import numpy as np
import pandas as pd

BASE = r"C:\Users\Admin\myquant\data\regime\mq_reveng"
FIT_END = pd.Timestamp("2023-12-31")

print("loading chains ...")
ch = pd.read_parquet(f"{BASE}\\chain_slices_overlap.parquet")
ch["tradeDate"] = pd.to_datetime(ch["tradeDate"])
ch["cg"] = ch["callOpenInterest"].astype("float64") * ch["gamma"].astype("float64")
ch["pg"] = ch["putOpenInterest"].astype("float64") * ch["gamma"].astype("float64")

# spot per day
spot = ch.groupby("tradeDate")["spotPrice"].first()

# monthly/quarterly expiries = 3rd Friday of month (standard AM-settled SPX)
ed = pd.to_datetime(ch["expirDate"])
is_friday = ed.dt.weekday == 4
third_fri = is_friday & (ed.dt.day >= 15) & (ed.dt.day <= 21)
ch["is_monthly"] = third_fri.values

DTE_FILTERS = {
    "all": ch["dte"] >= 0,
    "dte1p": ch["dte"] >= 1,
    "dte_le7": ch["dte"].between(0, 7),
    "dte_le14": ch["dte"].between(0, 14),
    "dte_le30": ch["dte"].between(0, 30),
    "dte_le45": ch["dte"].between(0, 45),
    "dte_le60": ch["dte"].between(0, 60),
    "dte_le90": ch["dte"].between(0, 90),
    "monthly": ch["is_monthly"] & (ch["dte"] >= 0),
    "monthly_le90": ch["is_monthly"] & ch["dte"].between(0, 90),
}

print("aggregating per (day,strike) per dte filter ...")
AGG = {}
for name, mask in DTE_FILTERS.items():
    sub = ch.loc[mask, ["tradeDate", "strike", "cg", "pg",
                        "callOpenInterest", "putOpenInterest"]]
    g = sub.groupby(["tradeDate", "strike"], sort=False).sum()
    AGG[name] = g
    print(f"  {name}: {len(g)} day-strike rows")

# dte-weighted variants (exponential decay, gamma already decays naturally)
for tau in (10.0, 30.0):
    w = np.exp(-ch["dte"].clip(lower=0) / tau)
    sub = ch[["tradeDate", "strike"]].copy()
    sub["cg"] = ch["cg"] * w
    sub["pg"] = ch["pg"] * w
    sub["callOpenInterest"] = ch["callOpenInterest"] * w
    sub["putOpenInterest"] = ch["putOpenInterest"] * w
    AGG[f"wexp{int(tau)}"] = sub.groupby(["tradeDate", "strike"], sort=False).sum()

del ch

# ---- truth ------------------------------------------------------------------
tr = pd.read_csv(f"{BASE}\\mq_truth.csv", parse_dates=["session_date", "eod_date"])
gcols = [f"gex_{k}" for k in range(1, 11)]
gvcols = [f"gex_{k}_gex" for k in range(1, 11)]
tr = tr.dropna(subset=gcols, how="all")
print(f"truth days: {len(tr)}")

truth = {}
for _, r in tr.iterrows():
    d = r["eod_date"]
    ks = [r[c] for c in gcols if pd.notna(r[c])]
    vs = [r[c] for c in gvcols]
    lvl = {c: r[c] for c in ("cr", "ps", "hvl", "cr0", "ps0", "hvl0", "gw0")}
    truth[d] = (ks, vs, lvl)

days = sorted(set(truth) & set(spot.index))
print(f"joinable days: {len(days)}")

# does gex set already contain cr/ps/hvl?  (diagnostic)
ov_cr = ov_ps = ov_hvl = 0
for d in days:
    ks, _, lvl = truth[d]
    s = set(ks)
    ov_cr += lvl["cr"] in s
    ov_ps += lvl["ps"] in s
    ov_hvl += lvl["hvl"] in s
print(f"gex set contains cr {ov_cr}/{len(days)}, ps {ov_ps}, hvl {ov_hvl}")

# ---- spec evaluation --------------------------------------------------------
FORMULAS = {
    "net_gob":  lambda g: g["cg"] - g["pg"],            # call-put gamma*OI (net)
    "tot_gob":  lambda g: g["cg"] + g["pg"],            # total gamma*OI
    "net_oi":   lambda g: g["callOpenInterest"] - g["putOpenInterest"],
    "tot_oi":   lambda g: g["callOpenInterest"] + g["putOpenInterest"],
}
BANDS = {"nobandcap": None, "band10": 0.10, "band15": 0.15, "band20": 0.20}
EXCL = {"exclNone": (), "exclCPH": ("cr", "ps", "hvl")}

rows = []
per_day_cache = {}
for fname, ffun in FORMULAS.items():
    for dname, g in AGG.items():
        val = ffun(g).rename("v").reset_index()
        by_day = dict(tuple(val.groupby("tradeDate", sort=False)))
        for bname, band in BANDS.items():
            for ename, excl in EXCL.items():
                p_fit, j_fit, p_ho, j_ho, nf, nh = 0.0, 0.0, 0.0, 0.0, 0, 0
                daily = []
                for d in days:
                    ks, _, lvl = truth[d]
                    if not ks:
                        continue
                    dv = by_day.get(d)
                    if dv is None:
                        continue
                    st, v = dv["strike"].values, dv["v"].values
                    if band is not None:
                        sp = spot[d]
                        m = np.abs(st / sp - 1.0) <= band
                        st, v = st[m], v[m]
                    if excl:
                        ex = {lvl[c] for c in excl if pd.notna(lvl[c])}
                        m = ~np.isin(st, list(ex))
                        st, v = st[m], v[m]
                    n = len(ks)
                    if len(st) < n:
                        continue
                    idx = np.argsort(-np.abs(v))[:n]
                    cand = set(st[idx])
                    T = set(ks)
                    inter = len(cand & T)
                    prec = inter / n
                    jac = inter / len(cand | T)
                    if d <= FIT_END:
                        p_fit += prec; j_fit += jac; nf += 1
                    else:
                        p_ho += prec; j_ho += jac; nh += 1
                    daily.append((d, prec, jac))
                if nf and nh:
                    rows.append(dict(formula=fname, dte=dname, band=bname, excl=ename,
                                     prec_fit=p_fit / nf, jacc_fit=j_fit / nf, n_fit=nf,
                                     prec_holdout=p_ho / nh, jacc_holdout=j_ho / nh, n_holdout=nh))
                    per_day_cache[(fname, dname, bname, ename)] = daily

scores = pd.DataFrame(rows).sort_values("prec_fit", ascending=False)
scores.to_csv(f"{BASE}\\gex10_spec_scores_20260724.csv", index=False)
print("\nTOP 15 SPECS (by fit precision@10):")
print(scores.head(15).to_string(index=False))

best = scores.iloc[0]
bkey = (best["formula"], best["dte"], best["band"], best["excl"])
pd.DataFrame(per_day_cache[bkey], columns=["eod_date", "precision", "jaccard"]) \
    .to_csv(f"{BASE}\\gex10_best_daily_20260724.csv", index=False)

# ---- value fingerprint: mq gex value vs candidate net gammaOI ---------------
# Use best dte filter, net gamma*OI, at THEIR strikes.  ratio per day.
gbest = AGG[best["dte"]]
netv = (gbest["cg"] - gbest["pg"]).rename("v")
fp = []
for d in days:
    ks, vs, _ = truth[d]
    sp = spot[d]
    for k, v in zip(ks, vs):
        if pd.isna(v):
            continue
        try:
            cand = netv.loc[(d, np.float32(k))]
        except KeyError:
            continue
        if cand != 0:
            fp.append(dict(eod_date=d, strike=k, mq=v, cand=cand,
                           ratio=v / cand, spot=sp,
                           sign_match=np.sign(v) == np.sign(cand)))
fp = pd.DataFrame(fp)
fp.to_csv(f"{BASE}\\gex10_value_ratio_20260724.csv", index=False)
print(f"\nvalue fingerprint rows: {len(fp)}  sign match: {fp['sign_match'].mean():.3f}")
med = fp.groupby("eod_date").agg(ratio_med=("ratio", "median"), spot=("spot", "first"))
med["ratio_over_spot2"] = med["ratio_med"] / med["spot"] ** 2
med["ratio_over_spot"] = med["ratio_med"] / med["spot"]
print("per-day median ratio stats:")
print(med[["ratio_med", "ratio_over_spot2", "ratio_over_spot"]].describe().to_string())
# correlation of mq value with candidate (per-day normalized)
fp["cand_n"] = fp.groupby("eod_date")["cand"].transform(lambda s: s / s.abs().max())
fp["mq_n"] = fp.groupby("eod_date")["mq"].transform(lambda s: s / s.abs().max())
print(f"corr(mq_n, cand_n) = {fp['mq_n'].corr(fp['cand_n']):.4f}")

# ---- ordering + symmetry ----------------------------------------------------
diag = []
for d in days:
    ks, vs, _ = truth[d]
    v = np.array([x for x in vs if pd.notna(x)], dtype=float)
    k = np.array(ks, dtype=float)
    if len(v) < 3 or len(v) != len(k):
        continue
    sp = spot[d]
    absdesc = bool(np.all(np.diff(np.abs(v)) <= 1e-9))
    rawdesc = bool(np.all(np.diff(v) <= 1e-9))
    dist = np.abs(k - sp)
    distasc = bool(np.all(np.diff(dist) >= -1e-9))
    def spear(a, b):
        ra = pd.Series(a).rank().values
        rb = pd.Series(b).rank().values
        return np.corrcoef(ra, rb)[0, 1]
    diag.append(dict(eod_date=d, n=len(v),
                     abs_desc=absdesc, raw_desc=rawdesc, dist_asc=distasc,
                     sp_absval=spear(np.arange(len(v)), -np.abs(v)),
                     sp_dist=spear(np.arange(len(v)), dist),
                     n_above=int((k > sp).sum()), n_below=int((k < sp).sum()),
                     pos_above=int(((k > sp) & (v > 0)).sum()),
                     neg_below=int(((k < sp) & (v < 0)).sum()),
                     n_pos=int((v > 0).sum()), n_neg=int((v < 0).sum())))
diag = pd.DataFrame(diag)
diag.to_csv(f"{BASE}\\gex10_order_symmetry_20260724.csv", index=False)
print("\nORDERING:")
print(f"  strictly |gex| descending: {diag['abs_desc'].mean():.3f} of days")
print(f"  strictly raw gex descending: {diag['raw_desc'].mean():.3f}")
print(f"  strictly distance-from-spot ascending: {diag['dist_asc'].mean():.3f}")
print(f"  mean spearman(rank, -|gex|): {diag['sp_absval'].mean():.3f}")
print(f"  mean spearman(rank, dist): {diag['sp_dist'].mean():.3f}")
print("SYMMETRY / SIGNS:")
print(f"  mean above spot {diag['n_above'].mean():.2f}, below {diag['n_below'].mean():.2f}")
print(f"  mean pos values {diag['n_pos'].mean():.2f}, neg {diag['n_neg'].mean():.2f}")
above = diag["n_above"].sum(); below = diag["n_below"].sum()
posab = diag["pos_above"].sum(); negbe = diag["neg_below"].sum()
print(f"  P(gex>0 | strike above spot) = {posab/above:.3f}")
print(f"  P(gex<0 | strike below spot) = {negbe/below:.3f}")
print("\ndone.")
