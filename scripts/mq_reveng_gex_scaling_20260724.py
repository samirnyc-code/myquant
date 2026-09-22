"""Pin down the exact scaling of MQ GEX = f(net gamma OI).

Winner from mq_reveng_gex_formula_20260724: net = sum_{dte>1} gamma*(callOI-putOI),
per-day beta ~ 100*spot. Here:
  1. Test fixed formulas with NO fitted params: net*100*spot, net*spot^2*0.01,
     net*100*spot^2*0.01, net*100 — R2 on fit (<=2023) and holdout (2024+).
  2. Use MQ's own spot_eod from truth (not ORATS spotPrice).
  3. Ratio distribution per year; pooled spot-power regression.
  4. Outlier hunt (the 1e42 holdout R2 blowup).
  5. Compare ex1 vs all vs d90 under the fixed scaling.

Output: data/regime/mq_reveng/gex_scaling_20260724.csv (formula summary)
        data/regime/mq_reveng/gex_scaling_ratio_daily_20260724.csv
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
net_row = ch["gamma"].to_numpy("float64") * (
    ch["callOpenInterest"].to_numpy("float64")
    - ch["putOpenInterest"].to_numpy("float64"))
dte = ch["dte"].to_numpy("int32")
base = pd.DataFrame({"tradeDate": ch["tradeDate"].astype(str),
                     "strike": ch["strike"].astype("float64"),
                     "net_all": net_row,
                     "net_ex1": net_row * (dte > 1),
                     "net_d90": net_row * ((dte > 1) & (dte <= 90))})
spot_orats = ch.groupby(ch["tradeDate"].astype(str))["spotPrice"].first()
del ch, net_row, dte
ps = base.groupby(["tradeDate", "strike"], sort=False).sum().reset_index()
del base

truth = pd.read_csv(f"{DATA}\\mq_truth.csv")
pairs = []
for lc, gcol in [("cr", "cr_gex"), ("ps", "ps_gex"), ("hvl", "hvl_gex")] + \
                [(f"gex_{i}", f"gex_{i}_gex") for i in range(1, 11)]:
    sub = truth[["eod_date", lc, gcol, "spot_eod"]].dropna(
        subset=[lc, gcol])
    sub.columns = ["tradeDate", "strike", "mq_gex", "spot_eod"]
    sub["level"] = lc
    pairs.append(sub)
pairs = pd.concat(pairs, ignore_index=True).drop_duplicates(
    subset=["tradeDate", "strike"])
pairs["strike"] = pairs["strike"].astype("float64")
m = pairs.merge(ps, on=["tradeDate", "strike"], how="inner")
m["spot_orats"] = m["tradeDate"].map(spot_orats).astype("float64")
m["spot_mq"] = m["spot_eod"].fillna(m["spot_orats"])
m["is_fit"] = m["tradeDate"] <= FIT_CUT
mq = m["mq_gex"].to_numpy()
f_mask = m["is_fit"].to_numpy()

def r2(y, yhat):
    return 1.0 - np.sum((y - yhat) ** 2) / np.sum((y - np.mean(y)) ** 2)

# ---- outlier hunt first
for col in ["net_all", "net_ex1", "net_d90"]:
    x = m[col].to_numpy()
    i = np.argsort(-np.abs(x))[:5]
    print(f"top |{col}|:")
    print(m.iloc[i][["tradeDate", "strike", "mq_gex", col]].to_string(index=False))

rows = []
scalings = {
    "x100spot":      lambda x, s: x * 100.0 * s,
    "xspot2_001":    lambda x, s: x * s * s * 0.01,
    "x100spot2_001": lambda x, s: x * 100.0 * s * s * 0.01,
    "x100":          lambda x, s: x * 100.0,
}
for col in ["net_all", "net_ex1", "net_d90"]:
    for sname, fn in scalings.items():
        for spot_src in ["spot_mq", "spot_orats"]:
            s = m[spot_src].to_numpy()
            yhat = fn(m[col].to_numpy(), s)
            ratio = mq / np.where(yhat == 0, np.nan, yhat)
            rows.append(dict(
                base=col, scaling=sname, spot=spot_src,
                r2_fit=r2(mq[f_mask], yhat[f_mask]),
                r2_holdout=r2(mq[~f_mask], yhat[~f_mask]),
                ratio_med_fit=np.nanmedian(ratio[f_mask]),
                ratio_med_hold=np.nanmedian(ratio[~f_mask]),
                ratio_iqr_fit=np.nanpercentile(ratio[f_mask], 75)
                              - np.nanpercentile(ratio[f_mask], 25)))
res = pd.DataFrame(rows).sort_values("r2_fit", ascending=False)
res.to_csv(f"{DATA}\\gex_scaling_20260724.csv", index=False)
print("\n=== fixed-formula fits (no free params) ===")
print(res.to_string(index=False))

# ---- pooled spot power on winner base ex1 (fit period, positive pairs only)
x = m["net_ex1"].to_numpy()
ok = f_mask & (np.sign(x) == np.sign(mq)) & (x != 0)
lp = np.log(np.abs(mq[ok] / (100.0 * x[ok])))
ls = np.log(m["spot_mq"].to_numpy()[ok])
b, a = np.polyfit(ls, lp, 1)
print(f"\npooled fit-period: log(|mq/(100*net_ex1)|) = {a:.3f} + {b:.3f}*log(spot)"
      f"  -> spot power {b:.3f}, const exp(a)={np.exp(a):.4g}")

# ---- per-day ratio (winner formula net_ex1*100*spot_mq) over time
yhat = m["net_ex1"].to_numpy() * 100.0 * m["spot_mq"].to_numpy()
d = pd.DataFrame({"day": m["tradeDate"], "ratio": mq / np.where(yhat == 0, np.nan, yhat),
                  "mq": mq, "yhat": yhat})
daily = d.groupby("day").agg(ratio_med=("ratio", "median"),
                             r2=("mq", lambda v: np.nan))
# per-day r2 with fixed formula
r2d = d.groupby("day").apply(lambda t: r2(t.mq.to_numpy(), t.yhat.to_numpy()),
                             include_groups=False)
daily["r2"] = r2d
daily.to_csv(f"{DATA}\\gex_scaling_ratio_daily_20260724.csv")
daily["year"] = daily.index.str[:4]
print("\nper-year median daily ratio (mq / net_ex1*100*spot) and daily R2:")
print(daily.groupby("year").agg(ratio_med=("ratio_med", "median"),
                                ratio_q25=("ratio_med", lambda v: v.quantile(.25)),
                                ratio_q75=("ratio_med", lambda v: v.quantile(.75)),
                                r2_med=("r2", "median"),
                                n=("r2", "size")).to_string())
