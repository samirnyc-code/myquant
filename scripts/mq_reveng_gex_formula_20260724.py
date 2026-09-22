"""Crack MQ's GEX formula by matching their published per-strike GEX values.

For each overlap day, take MQ's published (strike, gex_value) pairs
(gex_1..gex_10, cr, ps, hvl) and compute candidate per-strike quantities from
the ORATS chains under many DTE filters/weights.  Per-day cross-sectional OLS
through the origin gives beta_day and R2; a constant beta across days = pure
unit scaling.  Regressing log(beta_day) on log(spot) reveals any spot power.

Output: data/regime/mq_reveng/gex_formula_fit_20260724.csv (variant summary)
        data/regime/mq_reveng/gex_formula_beta_daily_20260724.csv (per-day betas, winner)
"""
import numpy as np
import pandas as pd

DATA = r"C:\Users\Admin\myquant\data\regime\mq_reveng"
FIT_CUT = "2023-12-31"

# ---------------------------------------------------------------- load chains
ch = pd.read_parquet(
    f"{DATA}\\chain_slices_overlap.parquet",
    columns=["tradeDate", "expirDate", "dte", "strike",
             "callOpenInterest", "putOpenInterest", "gamma", "spotPrice"],
)
ch["gamma"] = ch["gamma"].clip(lower=0)  # kill tiny negative numerical noise
gc = ch["gamma"].to_numpy("float64") * ch["callOpenInterest"].to_numpy("float64")
gp = ch["gamma"].to_numpy("float64") * ch["putOpenInterest"].to_numpy("float64")
dte = ch["dte"].to_numpy("int32")

exp_dt = pd.to_datetime(ch["expirDate"])
is_monthly = (exp_dt.dt.weekday == 4) & (exp_dt.dt.day.between(15, 21))

weights = {
    "all":      np.ones_like(dte, dtype="float64"),
    "d90":      (dte <= 90).astype("float64"),
    "d60":      (dte <= 60).astype("float64"),
    "d45":      (dte <= 45).astype("float64"),
    "d30":      (dte <= 30).astype("float64"),
    "d20":      (dte <= 20).astype("float64"),
    "d7":       (dte <= 7).astype("float64"),
    "dte1":     (dte == 1).astype("float64"),          # 0DTE only
    "ex1":      (dte > 1).astype("float64"),           # exclude 0DTE
    "monthly":  is_monthly.to_numpy("float64"),
    "isqrt":    1.0 / np.sqrt(np.maximum(dte, 1)),
    "inv":      1.0 / np.maximum(dte, 1),
    "exp10":    np.exp(-(dte - 1) / 10.0),
    "exp30":    np.exp(-(dte - 1) / 30.0),
    "exp60":    np.exp(-(dte - 1) / 60.0),
}

agg = pd.DataFrame({"tradeDate": ch["tradeDate"].astype(str),
                    "strike": ch["strike"].astype("float64")})
for name, w in weights.items():
    agg[f"gc_{name}"] = gc * w
    agg[f"gp_{name}"] = gp * w
del ch, gc, gp, dte, exp_dt, is_monthly

per_strike = agg.groupby(["tradeDate", "strike"], sort=False).sum().reset_index()
del agg
spot = per_strike[["tradeDate"]].copy()  # spot per day
sp = pd.read_parquet(f"{DATA}\\chain_slices_overlap.parquet",
                     columns=["tradeDate", "spotPrice"])
spot_day = sp.groupby(sp["tradeDate"].astype(str))["spotPrice"].first()
del sp

# ---------------------------------------------------------------- load truth
truth = pd.read_csv(f"{DATA}\\mq_truth.csv")
pairs = []
level_cols = [("cr", "cr_gex"), ("ps", "ps_gex"), ("hvl", "hvl_gex")] + \
             [(f"gex_{i}", f"gex_{i}_gex") for i in range(1, 11)]
for lc, gcol in level_cols:
    sub = truth[["eod_date", lc, gcol]].dropna()
    sub.columns = ["tradeDate", "strike", "mq_gex"]
    sub["level"] = lc
    pairs.append(sub)
pairs = pd.concat(pairs, ignore_index=True)
# dedupe identical (day, strike): cr/ps/hvl usually repeat a gex_i strike
pairs = pairs.drop_duplicates(subset=["tradeDate", "strike"])
pairs["strike"] = pairs["strike"].astype("float64")

m = pairs.merge(per_strike, on=["tradeDate", "strike"], how="left")
n_missing = m[f"gc_all"].isna().sum()
m = m.dropna(subset=["gc_all"]).copy()
m["spot"] = m["tradeDate"].map(spot_day).astype("float64")
m["is_fit"] = m["tradeDate"] <= FIT_CUT
print(f"pairs: {len(pairs)}  matched to chains: {len(m)}  missing: {n_missing}")
print(f"fit rows: {m.is_fit.sum()}  holdout rows: {(~m.is_fit).sum()}  "
      f"days: {m.tradeDate.nunique()}")

# sign convention check (on net all-expiry candidate)
net_all = m["gc_all"] - m["gp_all"]
sign_agree = np.mean(np.sign(m["mq_gex"]) == np.sign(net_all))
print(f"sign agreement mq vs (call-put) net, all expiries: {sign_agree:.4f}")

# ---------------------------------------------------------------- evaluate
def r2(y, yhat):
    ss = np.sum((y - yhat) ** 2)
    st = np.sum((y - np.mean(y)) ** 2)
    return 1.0 - ss / st

rows = []
mq = m["mq_gex"].to_numpy()
fit_mask = m["is_fit"].to_numpy()
day_idx = m["tradeDate"].to_numpy()
spot_v = m["spot"].to_numpy()

for name in weights:
    for combo in ["net", "tot", "call", "put"]:
        c = m[f"gc_{name}"].to_numpy()
        p = m[f"gp_{name}"].to_numpy()
        if combo == "net":
            x = c - p
        elif combo == "tot":
            x = c + p
        elif combo == "call":
            x = c
        else:
            x = -p
        if np.all(x == 0):
            continue
        # global beta on fit period (through origin), then R2 fit + holdout
        xf, yf = x[fit_mask], mq[fit_mask]
        denom = np.sum(xf * xf)
        if denom == 0:
            continue
        beta = np.sum(xf * yf) / denom
        r2f = r2(yf, beta * xf)
        r2h = r2(mq[~fit_mask], beta * x[~fit_mask])
        # per-day beta stability + spot power (fit period only)
        df = pd.DataFrame({"d": day_idx, "x": x, "y": mq, "s": spot_v,
                           "f": fit_mask})
        g = df[df.f].groupby("d").apply(
            lambda t: pd.Series({
                "beta": np.sum(t.x * t.y) / np.sum(t.x * t.x)
                        if np.sum(t.x * t.x) > 0 else np.nan,
                "spot": t.s.iloc[0]}), include_groups=False)
        g = g.dropna()
        g = g[g.beta > 0]
        cv = g.beta.std() / g.beta.mean() if len(g) else np.nan
        # spot power: slope of log(beta) ~ log(spot)
        if len(g) > 10:
            sl = np.polyfit(np.log(g.spot), np.log(g.beta), 1)[0]
        else:
            sl = np.nan
        rows.append(dict(weight=name, combo=combo, beta_global=beta,
                         r2_fit=r2f, r2_holdout=r2h,
                         beta_day_median=g.beta.median() if len(g) else np.nan,
                         beta_day_cv=cv, spot_power=sl, n_days=len(g)))

res = pd.DataFrame(rows).sort_values("r2_fit", ascending=False)
res.to_csv(f"{DATA}\\gex_formula_fit_20260724.csv", index=False)
print("\n=== TOP 15 by fit R2 ===")
print(res.head(15).to_string(index=False))
print("\n=== net variants ===")
print(res[res.combo == "net"].to_string(index=False))

# winner daily betas
best = res.iloc[0]
name, combo = best.weight, best.combo
c = m[f"gc_{name}"]; p = m[f"gp_{name}"]
x = {"net": c - p, "tot": c + p, "call": c, "put": -p}[combo]
df = pd.DataFrame({"d": day_idx, "x": x, "y": mq, "s": spot_v})
g = df.groupby("d").apply(lambda t: pd.Series({
    "beta": np.sum(t.x * t.y) / np.sum(t.x * t.x),
    "r2": r2(t.y.to_numpy(), (np.sum(t.x * t.y) / np.sum(t.x * t.x)) * t.x.to_numpy()),
    "spot": t.s.iloc[0]}), include_groups=False)
g.to_csv(f"{DATA}\\gex_formula_beta_daily_20260724.csv")
print(f"\nwinner {name}/{combo}: daily beta median {g.beta.median():.6g}, "
      f"IQR {g.beta.quantile(.25):.6g}..{g.beta.quantile(.75):.6g}, "
      f"daily R2 median {g.r2.median():.4f}")
# ratio interpretations
sm = g.spot.median()
print(f"median spot {sm:.1f}; beta/100 = {g.beta.median()/100:.4g}; "
      f"beta/spot = {g.beta.median()/sm:.4g}; "
      f"beta/(100*spot) = {g.beta.median()/(100*sm):.4g}; "
      f"beta/(spot^2*0.01) = {g.beta.median()/(sm*sm*0.01):.4g}; "
      f"beta/(100*spot^2*0.01) = {g.beta.median()/(100*sm*sm*0.01):.4g}")
