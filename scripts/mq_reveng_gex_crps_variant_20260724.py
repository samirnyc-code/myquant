"""Check whether cr_gex/ps_gex use call-only/put-only GEX vs net.

Formula base: sum over expiries dte>1 of gamma*OI*100*spot_eod.
Compares at CR strikes: net vs call-only; at PS strikes: net vs -put-only;
at HVL strikes: net. Reports median ratio and R2 (fit <=2023 ex-2021, holdout 2024+).

Output: data/regime/mq_reveng/gex_crps_variant_20260724.csv
"""
import numpy as np
import pandas as pd

DATA = r"C:\Users\Admin\myquant\data\regime\mq_reveng"

ch = pd.read_parquet(
    f"{DATA}\\chain_slices_overlap.parquet",
    columns=["tradeDate", "dte", "strike",
             "callOpenInterest", "putOpenInterest", "gamma"],
)
ch.loc[(ch["gamma"] < 0) | (ch["gamma"] > 0.5), "gamma"] = 0.0
keep = ch["dte"] > 1
g = ch["gamma"].to_numpy("float64") * keep.to_numpy()
base = pd.DataFrame({"tradeDate": ch["tradeDate"].astype(str),
                     "strike": ch["strike"].astype("float64"),
                     "gcall": g * ch["callOpenInterest"].to_numpy("float64"),
                     "gput": g * ch["putOpenInterest"].to_numpy("float64")})
del ch, g
ps_agg = base.groupby(["tradeDate", "strike"], sort=False).sum().reset_index()
del base

truth = pd.read_csv(f"{DATA}\\mq_truth.csv")
rows = []
def r2(y, yh):
    return 1.0 - np.sum((y - yh) ** 2) / np.sum((y - np.mean(y)) ** 2)

for lc, gcol in [("cr", "cr_gex"), ("ps", "ps_gex"), ("hvl", "hvl_gex")]:
    sub = truth[["eod_date", lc, gcol, "spot_eod"]].dropna().copy()
    sub.columns = ["tradeDate", "strike", "mq_gex", "spot"]
    sub["strike"] = sub["strike"].astype("float64")
    sub = sub.merge(ps_agg, on=["tradeDate", "strike"], how="inner")
    sub = sub[sub["tradeDate"].str[:4] != "2021"]
    fit = sub["tradeDate"] <= "2023-12-31"
    for vname, x in [("net", sub.gcall - sub.gput),
                     ("call_only", sub.gcall),
                     ("put_only_neg", -sub.gput)]:
        yh = x.to_numpy() * 100.0 * sub["spot"].to_numpy()
        y = sub["mq_gex"].to_numpy()
        ratio = y / np.where(yh == 0, np.nan, yh)
        rows.append(dict(level=lc, variant=vname,
                         ratio_med_fit=np.nanmedian(ratio[fit]),
                         ratio_med_hold=np.nanmedian(ratio[~fit]),
                         r2_fit=r2(y[fit.to_numpy()], yh[fit.to_numpy()]),
                         r2_hold=r2(y[~fit.to_numpy()], yh[~fit.to_numpy()]),
                         n=len(sub)))
res = pd.DataFrame(rows)
res.to_csv(f"{DATA}\\gex_crps_variant_20260724.csv", index=False)
print(res.to_string(index=False))
