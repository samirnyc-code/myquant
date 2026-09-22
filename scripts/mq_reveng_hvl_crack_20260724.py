"""Crack MQ's HVL definition.

Hypotheses searched (per DTE-weight variant):
  A. zero-cross of cumulative net GEX, cumulated low->high and high->low,
     crossing selected by: nearest-spot / largest-swing / lowest / highest
  B. per-strike net-GEX sign flip nearest spot
  C. strike of max TOTAL gamma exposure (gamma*(cOI+pOI)) within spot window
  D. strike of max combined OI within spot window
  E. strike with negative net GEX closest to zero (global and near-spot) —
     motivated by fingerprint: MQ's hvl_gex is ALWAYS negative and small
  F. peak of net / most-negative net (controls)

Weights: all, ex1 (dte>1), d90/d60/d45/d30/d7, monthly, 1/sqrt(dte).
(Pure per-day scalings — spot^2, contract multiplier — cannot change an argmax
or zero-cross location, so they are not separate variants.)

Scoring vs mq_truth.hvl: median abs error, median signed error (bias),
regime agreement = sign(spot_eod - pred) == sign(spot_eod - hvl).
Fit = eod_date <= 2023-12-31, holdout = 2024+.

Outputs (data/regime/mq_reveng/):
  hvl_scoreboard_20260724.csv     — every variant x candidate, fit/holdout metrics
  hvl_fingerprint_20260724.csv    — hvl_gex sign/magnitude analysis + correlation
                                    of hvl_gex with our net/cum at MQ's hvl strike
  hvl_best_daily_20260724.csv     — per-day predictions of the top-3 specs
"""
import numpy as np
import pandas as pd

DATA = r"C:\Users\Admin\myquant\data\regime\mq_reveng"
FIT_CUT = "2023-12-31"

# ---------------------------------------------------------------- load
ch = pd.read_parquet(
    f"{DATA}\\chain_slices_overlap.parquet",
    columns=["tradeDate", "expirDate", "dte", "strike",
             "callOpenInterest", "putOpenInterest", "gamma", "spotPrice"],
)
ch["gamma"] = ch["gamma"].clip(lower=0)
g = ch["gamma"].to_numpy("float64")
cOI = ch["callOpenInterest"].to_numpy("float64")
pOI = ch["putOpenInterest"].to_numpy("float64")
dte = ch["dte"].to_numpy("int32")
exp_dt = pd.to_datetime(ch["expirDate"])
is_monthly = ((exp_dt.dt.weekday == 4) & (exp_dt.dt.day.between(15, 21))).to_numpy()

net = g * (cOI - pOI)
tot = g * (cOI + pOI)
oi = cOI + pOI

WEIGHTS = {
    "all":     np.ones(len(ch)),
    "ex1":     (dte > 1).astype("float64"),
    "d90":     (dte <= 90).astype("float64"),
    "d60":     (dte <= 60).astype("float64"),
    "d45":     (dte <= 45).astype("float64"),
    "d30":     (dte <= 30).astype("float64"),
    "d7":      (dte <= 7).astype("float64"),
    "monthly": is_monthly.astype("float64"),
    "isqrt":   1.0 / np.sqrt(np.maximum(dte, 1)),
}

# per (day,strike) aggregates for every weight -----------------------------
agg = pd.DataFrame({"tradeDate": ch["tradeDate"].values, "strike": ch["strike"].values})
for wname, w in WEIGHTS.items():
    agg[f"net_{wname}"] = (net * w).astype("float64")
    agg[f"tot_{wname}"] = (tot * w).astype("float64")
    agg[f"oi_{wname}"] = (oi * w).astype("float64")
day_spot = ch.groupby("tradeDate")["spotPrice"].max()
A = agg.groupby(["tradeDate", "strike"], sort=True).sum()
A = A.reset_index()

truth = pd.read_csv(f"{DATA}\\mq_truth.csv",
                    usecols=["eod_date", "spot_eod", "hvl", "hvl_gex", "gex_1_gex"])
truth = truth.dropna(subset=["hvl", "spot_eod"])
truth["eod_date"] = truth["eod_date"].astype(str)

chain_days = set(A["tradeDate"].astype(str).unique())
truth = truth[truth["eod_date"].isin(chain_days)].reset_index(drop=True)
print(f"overlap days scored: {len(truth)}")

# group chains by day once
A["tradeDate"] = A["tradeDate"].astype(str)
by_day = {d: sub for d, sub in A.groupby("tradeDate")}


def crossings(vals, strikes):
    """indices of sign changes in vals; returns (cross_strike, swing) arrays.
    cross strike = the strike of the smaller-|val| side of the flip."""
    s = np.sign(vals)
    nz = s != 0
    idx = np.where(s[:-1] * s[1:] < 0)[0]
    out_k, out_sw = [], []
    for i in idx:
        k = strikes[i] if abs(vals[i]) < abs(vals[i + 1]) else strikes[i + 1]
        out_k.append(k)
        out_sw.append(abs(vals[i + 1] - vals[i]))
    return np.array(out_k), np.array(out_sw)


def pick(cks, swings, spot, rule):
    if len(cks) == 0:
        return np.nan
    if rule == "nearspot":
        return cks[np.argmin(np.abs(cks - spot))]
    if rule == "maxswing":
        return cks[np.argmax(swings)]
    if rule == "lowest":
        return cks.min()
    if rule == "highest":
        return cks.max()
    raise ValueError(rule)


rows_pred = []
for _, tr in truth.iterrows():
    d = tr["eod_date"]
    sub = by_day[d]
    strikes = sub["strike"].to_numpy()
    spot = float(day_spot.get(d, np.nan))
    if not np.isfinite(spot):
        spot = tr["spot_eod"]
    win = np.abs(strikes / spot - 1.0) <= 0.15   # peak window
    win5 = np.abs(strikes / spot - 1.0) <= 0.05  # tight window
    rec = {"eod_date": d, "spot": spot, "hvl": tr["hvl"],
           "spot_eod": tr["spot_eod"], "hvl_gex": tr["hvl_gex"]}
    for wname in WEIGHTS:
        nv = sub[f"net_{wname}"].to_numpy()
        tv = sub[f"tot_{wname}"].to_numpy()
        ov = sub[f"oi_{wname}"].to_numpy()
        # cumulative low->high and high->low
        cum_lo = np.cumsum(nv)
        cum_hi = np.cumsum(nv[::-1])[::-1]
        for cname, cv in (("cumlo", cum_lo), ("cumhi", cum_hi)):
            cks, sw = crossings(cv, strikes)
            for rule in ("nearspot", "maxswing", "lowest", "highest"):
                rec[f"{wname}|{cname}_{rule}"] = pick(cks, sw, spot, rule)
        # per-strike net sign flip nearest spot
        cks, sw = crossings(nv, strikes)
        rec[f"{wname}|flipstrike_nearspot"] = pick(cks, sw, spot, "nearspot")
        # peaks (within 15% window)
        if win.any():
            rec[f"{wname}|peak_totgamma"] = strikes[win][np.argmax(tv[win])]
            rec[f"{wname}|peak_oi"] = strikes[win][np.argmax(ov[win])]
            rec[f"{wname}|peak_net"] = strikes[win][np.argmax(nv[win])]
            rec[f"{wname}|trough_net"] = strikes[win][np.argmin(nv[win])]
        # negative-net closest to zero
        negm = nv < 0
        if negm.any():
            kk = strikes[negm]
            rec[f"{wname}|negnearzero"] = kk[np.argmin(-nv[negm])]
        nm5 = negm & win5
        if nm5.any():
            kk = strikes[nm5]
            rec[f"{wname}|negnearzero_w5"] = kk[np.argmin(-nv[nm5])]
        # store net & cum at MQ's hvl strike for fingerprint (once per weight)
        hit = strikes == tr["hvl"]
        rec[f"_netAThvl_{wname}"] = nv[hit][0] if hit.any() else np.nan
        rec[f"_cumloAThvl_{wname}"] = cum_lo[hit][0] if hit.any() else np.nan
        rec[f"_cumhiAThvl_{wname}"] = cum_hi[hit][0] if hit.any() else np.nan
        if hit.any():
            order = np.argsort(np.abs(nv))          # rank of |net| at hvl strike
            rec[f"_absnetrankAThvl_{wname}"] = int(np.where(order == np.where(hit)[0][0])[0][0])
    rows_pred.append(rec)

P = pd.DataFrame(rows_pred)
P["is_fit"] = P["eod_date"] <= FIT_CUT

# ---------------------------------------------------------------- scoring
cand_cols = [c for c in P.columns if "|" in c]
score_rows = []
for c in cand_cols:
    pred = P[c]
    err = pred - P["hvl"]
    reg_true = np.sign(P["spot_eod"] - P["hvl"])
    reg_pred = np.sign(P["spot_eod"] - pred)
    agree = (reg_true == reg_pred)
    row = {"spec": c}
    for tag, m in (("fit", P["is_fit"]), ("hold", ~P["is_fit"])):
        e = err[m].dropna()
        row[f"n_{tag}"] = int(m.sum())
        row[f"nvalid_{tag}"] = len(e)
        row[f"medabs_{tag}"] = float(e.abs().median()) if len(e) else np.nan
        row[f"medbias_{tag}"] = float(e.median()) if len(e) else np.nan
        row[f"exact_{tag}"] = float((e == 0).mean()) if len(e) else np.nan
        row[f"within5_{tag}"] = float((e.abs() <= 5).mean()) if len(e) else np.nan
        row[f"agree_{tag}"] = float(agree[m & pred.notna()].mean()) if (m & pred.notna()).any() else np.nan
    score_rows.append(row)
S = pd.DataFrame(score_rows).sort_values("medabs_fit")
S.to_csv(f"{DATA}\\hvl_scoreboard_20260724.csv", index=False)

# ---------------------------------------------------------------- fingerprint
fp_rows = []
hg = P["hvl_gex"]
fp_rows.append({"stat": "hvl_gex_frac_negative", "value": float((hg < 0).mean())})
tr_full = pd.read_csv(f"{DATA}\\mq_truth.csv", usecols=["hvl_gex", "gex_1_gex"]).dropna()
ratio = (tr_full["hvl_gex"].abs() / tr_full["gex_1_gex"].abs())
fp_rows.append({"stat": "abs(hvl_gex)/abs(gex1_gex)_median", "value": float(ratio.median())})
fp_rows.append({"stat": "abs(hvl_gex)/abs(gex1_gex)_p90", "value": float(ratio.quantile(0.9))})
for wname in WEIGHTS:
    x = P[f"_netAThvl_{wname}"]
    m = x.notna() & hg.notna()
    fp_rows.append({"stat": f"corr(hvl_gex, netAThvl_{wname})",
                    "value": float(np.corrcoef(hg[m], x[m])[0, 1]) if m.sum() > 2 else np.nan})
    fp_rows.append({"stat": f"frac_netAThvl_negative_{wname}", "value": float((x[m] < 0).mean())})
    fp_rows.append({"stat": f"median_absnet_rank_at_hvl_{wname}",
                    "value": float(P[f"_absnetrankAThvl_{wname}"].median())})
    for cn in ("cumlo", "cumhi"):
        y = P[f"_{cn}AThvl_{wname}"]
        m2 = y.notna() & hg.notna()
        fp_rows.append({"stat": f"corr(hvl_gex, {cn}AThvl_{wname})",
                        "value": float(np.corrcoef(hg[m2], y[m2])[0, 1]) if m2.sum() > 2 else np.nan})
FP = pd.DataFrame(fp_rows)
FP.to_csv(f"{DATA}\\hvl_fingerprint_20260724.csv", index=False)

top3 = S.head(3)["spec"].tolist()
P[["eod_date", "spot", "spot_eod", "hvl", "hvl_gex"] + top3].to_csv(
    f"{DATA}\\hvl_best_daily_20260724.csv", index=False)

pd.set_option("display.width", 250)
print("\n=== TOP 15 by medabs_fit ===")
print(S.head(15)[["spec", "medabs_fit", "medabs_hold", "medbias_fit", "medbias_hold",
                  "exact_fit", "exact_hold", "within5_fit", "within5_hold",
                  "agree_fit", "agree_hold"]].to_string(index=False))
print("\n=== TOP 15 by agree_fit ===")
print(S.sort_values("agree_fit", ascending=False).head(15)[
    ["spec", "medabs_fit", "medabs_hold", "agree_fit", "agree_hold",
     "exact_fit", "exact_hold"]].to_string(index=False))
print("\n=== FINGERPRINT ===")
print(FP.to_string(index=False))
