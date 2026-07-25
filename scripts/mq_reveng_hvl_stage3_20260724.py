"""HVL crack stage 3 — price-space smoothing + selection tweaks.

Stage-2 winner: ex1 (dte>1), rolling-5 (row-space) smoothed per-strike net GEX,
sign-flip nearest spot -> medabs 10, agree 0.93/0.96. Row-space smoothing is
grid-dependent; here we smooth in PRICE space on a 5-pt strike grid:
net aggregated to 5-pt buckets, rolling window of +-W points (W=10..100),
then sign-flip selection: nearest spot / nearest below spot / max swing,
negative-side strike. Weight fixed ex1 ('all' control). Ref = chain spot and
MQ spot_eod.

Outputs: data/regime/mq_reveng/hvl_stage3_scoreboard_20260724.csv
         data/regime/mq_reveng/hvl_final_daily_20260724.csv (top-3 overall)
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
WEIGHTS = {"ex1": (dte > 1).astype("float64"), "all": np.ones(len(ch))}

agg = pd.DataFrame({"tradeDate": ch["tradeDate"].astype(str).values,
                    "g5": (np.round(ch["strike"].to_numpy() / 5) * 5)})
for wn, w in WEIGHTS.items():
    agg[f"net_{wn}"] = net * w
day_spot = ch.assign(tradeDate=ch["tradeDate"].astype(str)).groupby("tradeDate")["spotPrice"].max()
A = agg.groupby(["tradeDate", "g5"], sort=True).sum().reset_index()

truth = pd.read_csv(f"{DATA}\\mq_truth.csv",
                    usecols=["eod_date", "spot_eod", "hvl"])
truth = truth.dropna(subset=["hvl", "spot_eod"])
truth["eod_date"] = truth["eod_date"].astype(str)
truth = truth[truth["eod_date"].isin(set(A["tradeDate"]))].reset_index(drop=True)
by_day = {d: sub for d, sub in A.groupby("tradeDate")}

WINDOWS = [0, 10, 15, 20, 25, 35, 50, 75, 100]  # +-W points; 0 = no smoothing


def flips_negside(vals, strikes):
    idx = np.where(np.sign(vals[:-1]) * np.sign(vals[1:]) < 0)[0]
    ks = np.where(vals[idx] < 0, strikes[idx], strikes[idx + 1])
    sw = np.abs(vals[idx + 1] - vals[idx])
    return ks, sw


rows = []
for _, tr in truth.iterrows():
    d = tr["eod_date"]
    sub = by_day[d]
    strikes = sub["g5"].to_numpy()
    refs = {"cspot": float(day_spot.get(d, tr["spot_eod"])),
            "mqspot": float(tr["spot_eod"])}
    rec = {"eod_date": d, "hvl": tr["hvl"], "spot_eod": tr["spot_eod"]}
    for wn in WEIGHTS:
        nv0 = sub[f"net_{wn}"].to_numpy()
        for W in WINDOWS:
            if W == 0:
                sv = nv0
            else:
                # price-space rolling: strikes on 5-grid but possibly gapped
                sv = np.array([nv0[(strikes >= k - W) & (strikes <= k + W)].sum()
                               for k in strikes])
            ks, sw = flips_negside(sv, strikes)
            for rn, ref in refs.items():
                base = f"{wn}|{rn}|W{W}"
                if len(ks):
                    rec[f"{base}|near"] = ks[np.argmin(np.abs(ks - ref))]
                    below = ks[ks <= ref]
                    rec[f"{base}|nearbelow"] = below.max() if len(below) else np.nan
                    rec[f"{base}|maxswing"] = ks[np.argmax(sw)]
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
S = pd.DataFrame(out).sort_values(["medabs_fit", "medabs_hold"])
S.to_csv(f"{DATA}\\hvl_stage3_scoreboard_20260724.csv", index=False)

top3 = S.head(3)["spec"].tolist()
P[["eod_date", "spot_eod", "hvl"] + top3].to_csv(
    f"{DATA}\\hvl_final_daily_20260724.csv", index=False)

pd.set_option("display.width", 260)
print("=== TOP 20 by medabs_fit ===")
print(S.head(20).to_string(index=False))
print("\n=== TOP 10 by exact_fit ===")
print(S.sort_values("exact_fit", ascending=False).head(10)[
    ["spec", "medabs_fit", "medabs_hold", "exact_fit", "exact_hold",
     "within5_fit", "within5_hold", "agree_fit", "agree_hold"]].to_string(index=False))
print("\n=== TOP 10 by agree_fit ===")
print(S.sort_values("agree_fit", ascending=False).head(10)[
    ["spec", "medabs_fit", "medabs_hold", "agree_fit", "agree_hold",
     "exact_fit", "exact_hold", "within25_fit", "within25_hold"]].to_string(index=False))
