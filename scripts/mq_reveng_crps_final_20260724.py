"""Final CR/PS spec sweep for MQ reverse-engineering.

Prior best (crps_crack/refine):
  CR: argmax net GEX (gamma*(cOI-pOI)), all dte, K%50==0, no band/side -> 68.9/78.3
  PS: argmin net, K%100==0, band +-20-30% -> 72.5/77.8
Misses are 60% rank-2 flips. Value-fit evidence (gex_dtecap_scan) says MQ's
per-strike value best matches net GEX with the FRONT expiry excluded and dte
capped ~90-120. Test whether that re-ranking fixes the flips, plus proximity
tie-breaking.

Sweep: dte windows lo in {1,2} x hi in {60,90,120,150,180,365,inf};
grids m25/m50/m100; bands none/20%/30%; sides none/ge (CR) and none/le (PS).
Stage 2: proximity tie-break alpha on the top specs.

Outputs (data/regime/mq_reveng/):
  crps_final_scoreboard_20260724.csv, crps_final_tiebreak_20260724.csv,
  crps_final_best_daily_20260724.csv
"""
import numpy as np
import pandas as pd
from itertools import product

BASE = r"C:\Users\Admin\myquant\data\regime\mq_reveng"
FIT_END = pd.Timestamp("2023-12-31")

ch = pd.read_parquet(f"{BASE}\\chain_slices_overlap.parquet",
                     columns=["tradeDate", "dte", "strike", "callOpenInterest",
                              "putOpenInterest", "gamma", "spotPrice"])
ch["tradeDate"] = pd.to_datetime(ch["tradeDate"])
g = ch["gamma"].clip(lower=0).astype("float64")
ch["net"] = g * (ch["callOpenInterest"] - ch["putOpenInterest"])
spot_by_day = ch.groupby("tradeDate")["spotPrice"].first()

# dte buckets: 1 | 2-60 | 61-90 | 91-120 | 121-150 | 151-180 | 181-365 | 366+
EDGES = np.array([1, 2, 61, 91, 121, 151, 181, 366])  # bucket i = [EDGES[i], EDGES[i+1])
ch["bkt"] = np.searchsorted(EDGES, ch["dte"].to_numpy(), side="right") - 1
NB = 8
agg = ch.groupby(["tradeDate", "strike", "bkt"], sort=True)["net"].sum().reset_index()
del ch

# per-day: strikes K, matrix M (nK x NB)
DAYS = {}
for d, sub in agg.groupby("tradeDate", sort=False):
    piv = sub.pivot_table(index="strike", columns="bkt", values="net",
                          aggfunc="sum", fill_value=0.0)
    M = np.zeros((len(piv), NB))
    M[:, piv.columns.to_numpy()] = piv.to_numpy()
    DAYS[d] = (piv.index.to_numpy("float64"), M)
del agg

tr = pd.read_csv(f"{BASE}\\mq_truth.csv", parse_dates=["eod_date"])
tr = tr.dropna(subset=["cr", "ps"]).reset_index(drop=True)
days = [pd.Timestamp(d) for d in tr["eod_date"]]
is_fit = (tr["eod_date"] <= FIT_END).to_numpy()
truth = {"cr": tr["cr"].to_numpy("float64"), "ps": tr["ps"].to_numpy("float64")}

# dte windows as bucket index ranges (inclusive)
HI_BKT = {60: 1, 90: 2, 120: 3, 150: 4, 180: 5, 365: 6, 9999: 7}
WINDOWS = [(lo, hi) for lo in (1, 2) for hi in (60, 90, 120, 150, 180, 365, 9999)]
GRIDS = ["m25", "m50", "m100"]
BANDS = [("none", None), ("b20", 0.20), ("b30", 0.30)]

# precompute per-day static things
prep = []
for di, d in enumerate(days):
    if d not in DAYS:
        prep.append(None)
        continue
    K, M = DAYS[d]
    spot = float(spot_by_day.get(d, np.nan))
    gm = {"m25": K % 25 == 0, "m50": K % 50 == 0, "m100": K % 100 == 0}
    bm = {}
    for bn, bv in BANDS:
        bm[bn] = np.ones(len(K), bool) if bv is None else (np.abs(K / spot - 1) <= bv)
    ge = K >= spot
    le = K <= spot
    prep.append((K, M, spot, gm, bm, ge, le))


def score(pred, tv):
    out = {}
    for tag, m in [("fit", is_fit), ("hold", ~is_fit)]:
        p, tt = pred[m], tv[m]
        ok = ~np.isnan(p)
        ae = np.abs(p[ok] - tt[ok])
        out[f"n_{tag}"] = int(ok.sum())
        out[f"exact_{tag}"] = float((ae == 0).mean())
        out[f"w25_{tag}"] = float((ae <= 25).mean())
        out[f"medae_{tag}"] = float(np.median(ae))
    return out


rows = []
pred_cache = {}
for (lo, hi), grid, (bn, _) in product(WINDOWS, GRIDS, BANDS):
    b0 = 0 if lo == 1 else 1
    b1 = HI_BKT[hi]
    preds = {("cr", "none"): np.full(len(days), np.nan),
             ("cr", "ge"): np.full(len(days), np.nan),
             ("ps", "none"): np.full(len(days), np.nan),
             ("ps", "le"): np.full(len(days), np.nan)}
    for di in range(len(days)):
        pr = prep[di]
        if pr is None:
            continue
        K, M, spot, gm, bm, ge, le = pr
        v = M[:, b0:b1 + 1].sum(1)
        base = gm[grid] & bm[bn]
        if base.any():
            idx = np.where(base)[0]
            preds[("cr", "none")][di] = K[idx[v[idx].argmax()]]
            preds[("ps", "none")][di] = K[idx[v[idx].argmin()]]
        m2 = base & ge
        if m2.any():
            idx = np.where(m2)[0]
            preds[("cr", "ge")][di] = K[idx[v[idx].argmax()]]
        m3 = base & le
        if m3.any():
            idx = np.where(m3)[0]
            preds[("ps", "le")][di] = K[idx[v[idx].argmin()]]
    for (lev, side), p in preds.items():
        r = {"level": lev, "lo": lo, "hi": hi, "grid": grid, "band": bn,
             "side": side}
        r.update(score(p, truth[lev]))
        rows.append(r)
        pred_cache[(lev, lo, hi, grid, bn, side)] = p

sb = pd.DataFrame(rows).sort_values(["level", "exact_fit"], ascending=[True, False])
sb.to_csv(f"{BASE}\\crps_final_scoreboard_20260724.csv", index=False)
for lev in ["cr", "ps"]:
    print(f"== {lev} top10 by exact_fit ==")
    print(sb[sb.level == lev].head(10).to_string(index=False))

# ---- Stage 2: proximity tie-break on top-3 specs per level ----
rows2 = []
best_specs = {}
for lev in ["cr", "ps"]:
    top = sb[sb.level == lev].head(3)
    best_specs[lev] = top.iloc[0]
    for _, r in top.iterrows():
        lo, hi, grid, bn, side = int(r.lo), int(r.hi), r.grid, r.band, r.side
        b0 = 0 if lo == 1 else 1
        b1 = HI_BKT[hi]
        for alpha in [0.85, 0.90, 0.95, 0.98]:
            p = np.full(len(days), np.nan)
            for di in range(len(days)):
                pr = prep[di]
                if pr is None:
                    continue
                K, M, spot, gm, bm, ge, le = pr
                v = M[:, b0:b1 + 1].sum(1)
                base = gm[grid] & bm[bn]
                if side == "ge":
                    base = base & ge
                elif side == "le":
                    base = base & le
                if not base.any():
                    continue
                idx = np.where(base)[0]
                vv = v[idx]
                if lev == "cr":
                    cand = idx[vv >= alpha * vv.max()] if vv.max() > 0 else idx[[vv.argmax()]]
                else:
                    cand = idx[vv <= alpha * vv.min()] if vv.min() < 0 else idx[[vv.argmin()]]
                p[di] = K[cand[np.abs(K[cand] - spot).argmin()]]
            r2 = {"level": lev, "lo": lo, "hi": hi, "grid": grid, "band": bn,
                  "side": side, "alpha": alpha}
            r2.update(score(p, truth[lev]))
            rows2.append(r2)

tb = pd.DataFrame(rows2).sort_values(["level", "exact_fit"], ascending=[True, False])
tb.to_csv(f"{BASE}\\crps_final_tiebreak_20260724.csv", index=False)
for lev in ["cr", "ps"]:
    print(f"== {lev} tiebreak top5 ==")
    print(tb[tb.level == lev].head(5).to_string(index=False))

# ---- best daily ----
out = {"eod_date": tr["eod_date"]}
for lev in ["cr", "ps"]:
    r = best_specs[lev]
    out[f"{lev}_true"] = truth[lev]
    out[f"{lev}_pred"] = pred_cache[(lev, int(r.lo), int(r.hi), r.grid, r.band, r.side)]
pd.DataFrame(out).to_csv(f"{BASE}\\crps_final_best_daily_20260724.csv", index=False)
print("saved best_daily")
