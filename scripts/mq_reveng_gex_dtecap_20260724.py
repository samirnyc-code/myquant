"""Scan the DTE cap for MQ GEX = sum gamma*(callOI-putOI)*100*spot.

Cleans corrupt ORATS gamma rows first (a handful of rows have gamma up to 1e21).
Scans caps 30..all, with and without dte==1 (0DTE), fixed scaling 100*spot_mq
(no fitted constant). Fit = eod_date <= 2023-12-31, holdout = 2024+.
Also reports metrics excluding 2021 (known mismatch year) and level-type
diagnostics (cr/ps/hvl sign + ratio).

Output: data/regime/mq_reveng/gex_dtecap_scan_20260724.csv
        data/regime/mq_reveng/gex_winner_pairs_20260724.csv (per-pair winner detail)
"""
import numpy as np
import pandas as pd

DATA = r"C:\Users\Admin\myquant\data\regime\mq_reveng"
FIT_CUT = "2023-12-31"

ch = pd.read_parquet(
    f"{DATA}\\chain_slices_overlap.parquet",
    columns=["tradeDate", "dte", "strike",
             "callOpenInterest", "putOpenInterest", "gamma"],
)
n0 = len(ch)
bad = (ch["gamma"] < 0) | (ch["gamma"] > 0.5)
print(f"rows: {n0}, corrupt/negative gamma rows zeroed: {(ch['gamma']>0.5).sum()} "
      f"(gamma>0.5), {(ch['gamma']<0).sum()} (gamma<0)")
ch.loc[bad, "gamma"] = 0.0
net_row = ch["gamma"].to_numpy("float64") * (
    ch["callOpenInterest"].to_numpy("float64")
    - ch["putOpenInterest"].to_numpy("float64"))
dte = ch["dte"].to_numpy("int32")
base = pd.DataFrame({"tradeDate": ch["tradeDate"].astype(str),
                     "strike": ch["strike"].astype("float64")})
caps = [30, 45, 60, 75, 90, 120, 150, 180, 252, 365, 500, 9999]
for cap in caps:
    base[f"c{cap}_ex1"] = net_row * ((dte > 1) & (dte <= cap))
    base[f"c{cap}_in1"] = net_row * (dte <= cap)
del ch, net_row, dte
ps = base.groupby(["tradeDate", "strike"], sort=False).sum().reset_index()
del base

truth = pd.read_csv(f"{DATA}\\mq_truth.csv")
pairs = []
for lc, gcol in [("cr", "cr_gex"), ("ps", "ps_gex"), ("hvl", "hvl_gex")] + \
                [(f"gex_{i}", f"gex_{i}_gex") for i in range(1, 11)]:
    sub = truth[["eod_date", lc, gcol, "spot_eod"]].dropna(subset=[lc, gcol])
    sub.columns = ["tradeDate", "strike", "mq_gex", "spot_eod"]
    sub["level"] = lc
    pairs.append(sub)
pairs = pd.concat(pairs, ignore_index=True)
pairs_lvl = pairs.copy()                     # keep level labels for diagnostics
pairs = pairs.drop_duplicates(subset=["tradeDate", "strike"])
pairs["strike"] = pairs["strike"].astype("float64")
# spot: MQ's own, fallback to ORATS median per day is unnecessary (only 1 NaN day)
spot_day = pairs.groupby("tradeDate")["spot_eod"].first()
pairs["spot"] = pairs["tradeDate"].map(spot_day)
m = pairs.merge(ps, on=["tradeDate", "strike"], how="inner").dropna(subset=["spot"])
m["is_fit"] = m["tradeDate"] <= FIT_CUT
m["year"] = m["tradeDate"].str[:4]
mq = m["mq_gex"].to_numpy()
f_mask = m["is_fit"].to_numpy()
no21 = (m["year"] != "2021").to_numpy()

def r2(y, yhat):
    return 1.0 - np.sum((y - yhat) ** 2) / np.sum((y - np.mean(y)) ** 2)

rows = []
for cap in caps:
    for inc in ["ex1", "in1"]:
        col = f"c{cap}_{inc}"
        yhat = m[col].to_numpy() * 100.0 * m["spot"].to_numpy()
        ratio = mq / np.where(yhat == 0, np.nan, yhat)
        fm, hm = f_mask, ~f_mask
        fm2 = f_mask & no21
        rows.append(dict(
            cap=cap, dte1="incl" if inc == "in1" else "excl",
            r2_fit=r2(mq[fm], yhat[fm]),
            r2_fit_ex2021=r2(mq[fm2], yhat[fm2]),
            r2_holdout=r2(mq[hm], yhat[hm]),
            ratio_med_fit=np.nanmedian(ratio[fm]),
            ratio_med_fit_ex21=np.nanmedian(ratio[fm2]),
            ratio_med_hold=np.nanmedian(ratio[hm]),
            ratio_iqr_hold=np.nanpercentile(ratio[hm], 75)
                           - np.nanpercentile(ratio[hm], 25)))
res = pd.DataFrame(rows)
res.to_csv(f"{DATA}\\gex_dtecap_scan_20260724.csv", index=False)
print("\n=== DTE-cap scan, fixed formula net*100*spot_mq ===")
print(res.sort_values("r2_fit_ex2021", ascending=False).to_string(index=False))

# ---- winner detail
best = res.sort_values("r2_fit_ex2021", ascending=False).iloc[0]
col = f"c{int(best.cap)}_{'in1' if best.dte1=='incl' else 'ex1'}"
m["yhat"] = m[col] * 100.0 * m["spot"]
m["ratio"] = m["mq_gex"] / m["yhat"].replace(0, np.nan)
out = m[["tradeDate", "strike", "mq_gex", "yhat", "ratio", "is_fit"]]
out.to_csv(f"{DATA}\\gex_winner_pairs_20260724.csv", index=False)

# per-day R2 with winner
g = m.groupby("tradeDate").apply(
    lambda t: r2(t.mq_gex.to_numpy(), t.yhat.to_numpy()), include_groups=False)
yy = g.index.str[:4]
print(f"\nwinner {col}: per-day R2 median overall {g.median():.4f}")
print(pd.DataFrame({"r2_med": g.groupby(yy).median(),
                    "r2_q10": g.groupby(yy).quantile(.10)}).to_string())

# ---- level-type diagnostics on winner
lv = pairs_lvl.copy()
lv["strike"] = lv["strike"].astype("float64")
lv = lv.merge(m[["tradeDate", "strike", "yhat"]].drop_duplicates(),
              on=["tradeDate", "strike"], how="inner")
lv["ratio"] = lv["mq_gex"] / lv["yhat"].replace(0, np.nan)
lv["sign_ok"] = np.sign(lv["mq_gex"]) == np.sign(lv["yhat"])
diag = lv.groupby("level").agg(n=("ratio", "size"),
                               ratio_med=("ratio", "median"),
                               sign_agree=("sign_ok", "mean"),
                               mq_med=("mq_gex", "median"))
print("\nper-level diagnostics (winner formula):")
print(diag.to_string())
