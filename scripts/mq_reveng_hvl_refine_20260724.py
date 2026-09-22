"""Refine HVL crack (stage 2).

Stage-1 findings (mq_reveng_hvl_crack_20260724.py):
  - hvl_gex is 100% negative, corr 0.84 with our per-strike net GEX at the HVL
    strike under weight ex1 (dte>1); ~0 corr with cumulative sums.
  => HVL = a per-strike net-GEX sign-transition strike, reported from the
     NEGATIVE side, chains excluding dte<=1.

Stage-2 candidates (weights ex1 and all as control):
  - flip nearest spot, negative-side strike (vs stage-1's smaller-|val| side)
  - UP-crossings only (net goes neg->pos as strike rises = classic gamma flip),
    nearest spot / largest swing, negative-side strike
  - rolling-smoothed profile (centered sum over k strikes, k=3,5,7,9) then flip
  - strike-grid aggregation to 5/10/25-pt buckets then flip
  - reference point: chain spotPrice vs MQ's spot_eod
  - negnearzero within +-2.5% of the chosen flip

Scoring identical to stage 1 (medabs, exact, within5, regime agreement,
fit <= 2023-12-31 vs 2024+ holdout).

Outputs: data/regime/mq_reveng/hvl_refine_scoreboard_20260724.csv
         data/regime/mq_reveng/hvl_refine_daily_20260724.csv (top-3 specs)
"""
import numpy as np
import pandas as pd

DATA = r"C:\Users\Admin\myquant\data\regime\mq_reveng"
FIT_CUT = "2023-12-31"

ch = pd.read_parquet(
    f"{DATA}\\chain_slices_overlap.parquet",
    columns=["tradeDate", "dte", "strike",
             "callOpenInterest", "putOpenInterest", "gamma", "spotPrice"],
)
ch["gamma"] = ch["gamma"].clip(lower=0)
net = ch["gamma"].to_numpy("float64") * (
    ch["callOpenInterest"].to_numpy("float64") - ch["putOpenInterest"].to_numpy("float64"))
dte = ch["dte"].to_numpy("int32")

WEIGHTS = {"ex1": (dte > 1).astype("float64"),
           "all": np.ones(len(ch))}

agg = pd.DataFrame({"tradeDate": ch["tradeDate"].astype(str).values,
                    "strike": ch["strike"].values})
for wn, w in WEIGHTS.items():
    agg[f"net_{wn}"] = net * w
day_spot = ch.assign(tradeDate=ch["tradeDate"].astype(str)).groupby("tradeDate")["spotPrice"].max()
A = agg.groupby(["tradeDate", "strike"], sort=True).sum().reset_index()

truth = pd.read_csv(f"{DATA}\\mq_truth.csv",
                    usecols=["eod_date", "spot_eod", "hvl", "hvl_gex"])
truth = truth.dropna(subset=["hvl", "spot_eod"])
truth["eod_date"] = truth["eod_date"].astype(str)
truth = truth[truth["eod_date"].isin(set(A["tradeDate"]))].reset_index(drop=True)
by_day = {d: sub for d, sub in A.groupby("tradeDate")}


def flips(vals, strikes, up_only=False):
    """sign changes; returns (neg_side_strike, swing, is_up) arrays."""
    idx = np.where(np.sign(vals[:-1]) * np.sign(vals[1:]) < 0)[0]
    ks, sw, up = [], [], []
    for i in idx:
        is_up = vals[i] < 0  # neg -> pos as strike rises
        if up_only and not is_up:
            continue
        kneg = strikes[i] if vals[i] < 0 else strikes[i + 1]
        ks.append(kneg)
        sw.append(abs(vals[i + 1] - vals[i]))
        up.append(is_up)
    return np.array(ks), np.array(sw)


def nearest(ks, ref):
    return ks[np.argmin(np.abs(ks - ref))] if len(ks) else np.nan


def gridagg(strikes, vals, step):
    gk = np.round(strikes / step) * step
    s = pd.Series(vals).groupby(gk).sum()
    return s.index.to_numpy(), s.to_numpy()


def smooth(vals, k):
    return pd.Series(vals).rolling(k, center=True, min_periods=1).sum().to_numpy()


rows = []
for _, tr in truth.iterrows():
    d = tr["eod_date"]
    sub = by_day[d]
    strikes = sub["strike"].to_numpy()
    spot_chain = float(day_spot.get(d, np.nan))
    refs = {"cspot": spot_chain if np.isfinite(spot_chain) else tr["spot_eod"],
            "mqspot": tr["spot_eod"]}
    rec = {"eod_date": d, "hvl": tr["hvl"], "spot_eod": tr["spot_eod"]}
    for wn in WEIGHTS:
        nv = sub[f"net_{wn}"].to_numpy()
        for rn, ref in refs.items():
            # raw flips, negative side
            ks_all, sw_all = flips(nv, strikes, up_only=False)
            ks_up, sw_up = flips(nv, strikes, up_only=True)
            rec[f"{wn}|{rn}|flipneg_near"] = nearest(ks_all, ref)
            rec[f"{wn}|{rn}|upflip_near"] = nearest(ks_up, ref)
            if len(ks_up):
                rec[f"{wn}|{rn}|upflip_maxswing"] = ks_up[np.argmax(sw_up)]
            # smoothed
            for k in (3, 5, 7, 9):
                sv = smooth(nv, k)
                ku, _ = flips(sv, strikes, up_only=True)
                rec[f"{wn}|{rn}|sm{k}_upflip_near"] = nearest(ku, ref)
                ka, _ = flips(sv, strikes, up_only=False)
                rec[f"{wn}|{rn}|sm{k}_flipneg_near"] = nearest(ka, ref)
            # grid-aggregated
            for step in (5, 10, 25):
                gk, gv = gridagg(strikes, nv, step)
                ku, _ = flips(gv, gk, up_only=True)
                rec[f"{wn}|{rn}|g{step}_upflip_near"] = nearest(ku, ref)
                ka, _ = flips(gv, gk, up_only=False)
                rec[f"{wn}|{rn}|g{step}_flipneg_near"] = nearest(ka, ref)
            # negnearzero within 2.5% of the raw nearest flip
            f0 = rec[f"{wn}|{rn}|flipneg_near"]
            if np.isfinite(f0):
                m = (nv < 0) & (np.abs(strikes - f0) <= 0.025 * ref)
                if m.any():
                    rec[f"{wn}|{rn}|negnz_nearflip"] = strikes[m][np.argmin(-nv[m])]
    rows.append(rec)

P = pd.DataFrame(rows)
P["is_fit"] = P["eod_date"] <= FIT_CUT

cand = [c for c in P.columns if "|" in c]
out = []
for c in cand:
    err = P[c] - P["hvl"]
    agree = np.sign(P["spot_eod"] - P["hvl"]) == np.sign(P["spot_eod"] - P[c])
    row = {"spec": c}
    for tag, m in (("fit", P["is_fit"]), ("hold", ~P["is_fit"])):
        e = err[m].dropna()
        row[f"medabs_{tag}"] = float(e.abs().median()) if len(e) else np.nan
        row[f"medbias_{tag}"] = float(e.median()) if len(e) else np.nan
        row[f"exact_{tag}"] = float((e == 0).mean()) if len(e) else np.nan
        row[f"within5_{tag}"] = float((e.abs() <= 5).mean()) if len(e) else np.nan
        row[f"within25_{tag}"] = float((e.abs() <= 25).mean()) if len(e) else np.nan
        row[f"agree_{tag}"] = float(agree[m & P[c].notna()].mean()) if (m & P[c].notna()).any() else np.nan
        row[f"n_{tag}"] = int((m & P[c].notna()).sum())
    out.append(row)
S = pd.DataFrame(out).sort_values("medabs_fit")
S.to_csv(f"{DATA}\\hvl_refine_scoreboard_20260724.csv", index=False)

top3 = S.head(3)["spec"].tolist()
P[["eod_date", "spot_eod", "hvl"] + top3].to_csv(
    f"{DATA}\\hvl_refine_daily_20260724.csv", index=False)

pd.set_option("display.width", 260)
print("=== TOP 20 by medabs_fit ===")
print(S.head(20).to_string(index=False))
print("\n=== TOP 10 by agree_fit ===")
print(S.sort_values("agree_fit", ascending=False).head(10)[
    ["spec", "medabs_fit", "medabs_hold", "agree_fit", "agree_hold",
     "exact_fit", "exact_hold", "within25_fit", "within25_hold"]].to_string(index=False))
