"""CR/PS refine round 2: finer front-expiry exclusion + band widths + yearly split.

crps_final result: excluding dte==1 (lo=2) jumps CR to 74.7/89.7 and PS to
74.3/84.8 (m25, b20). Here:
  - lo in {1..6} (exclude first k-1 days of dte), hi in {180,365,9999}
  - CR grids m25/m50, bands none/b20/b30
  - PS grids m25/m50/m100, bands b10/b15/b20/b30/none
  - yearly exact% breakdown for the winners (is the fit-era gap 2021-specific?)
Outputs: crps_refine2_scoreboard_20260724.csv, crps_refine2_yearly_20260724.csv,
         crps_refine2_best_daily_20260724.csv
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

# buckets: dte 1 | 2 | 3 | 4 | 5 | 6-180 | 181-365 | 366+
EDGES = np.array([1, 2, 3, 4, 5, 6, 181, 366])
ch["bkt"] = np.searchsorted(EDGES, ch["dte"].to_numpy(), side="right") - 1
NB = 8
agg = ch.groupby(["tradeDate", "strike", "bkt"], sort=True)["net"].sum().reset_index()
del ch

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
years = tr["eod_date"].dt.year.to_numpy()
truth = {"cr": tr["cr"].to_numpy("float64"), "ps": tr["ps"].to_numpy("float64")}

BANDS = [("none", None), ("b10", .10), ("b15", .15), ("b20", .20), ("b30", .30)]
prep = []
for d in days:
    if d not in DAYS:
        prep.append(None)
        continue
    K, M = DAYS[d]
    spot = float(spot_by_day.get(d, np.nan))
    gm = {"m25": K % 25 == 0, "m50": K % 50 == 0, "m100": K % 100 == 0}
    bm = {bn: (np.ones(len(K), bool) if bv is None else np.abs(K / spot - 1) <= bv)
          for bn, bv in BANDS}
    prep.append((K, M, spot, gm, bm))

HI_BKT = {180: 5, 365: 6, 9999: 7}


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
cache = {}
SPECS = {"cr": [("m25", b) for b in ("none", "b20", "b30")] +
               [("m50", b) for b in ("none", "b20", "b30")],
         "ps": [(gr, b) for gr in ("m25", "m50", "m100")
                for b in ("b10", "b15", "b20", "b30", "none")]}
for lo, hi in product(range(1, 7), (180, 365, 9999)):
    b0, b1 = lo - 1, HI_BKT[hi]
    # per-day value vector
    VC = []
    for pr in prep:
        VC.append(None if pr is None else pr[1][:, b0:b1 + 1].sum(1))
    for lev in ("cr", "ps"):
        for grid, bn in SPECS[lev]:
            p = np.full(len(days), np.nan)
            for di, pr in enumerate(prep):
                if pr is None:
                    continue
                K, M, spot, gm, bm = pr
                mask = gm[grid] & bm[bn]
                if not mask.any():
                    continue
                idx = np.where(mask)[0]
                v = VC[di][idx]
                p[di] = K[idx[v.argmax() if lev == "cr" else v.argmin()]]
            r = {"level": lev, "lo": lo, "hi": hi, "grid": grid, "band": bn}
            r.update(score(p, truth[lev]))
            rows.append(r)
            cache[(lev, lo, hi, grid, bn)] = p

sb = pd.DataFrame(rows).sort_values(["level", "exact_fit"], ascending=[True, False])
sb.to_csv(f"{BASE}\\crps_refine2_scoreboard_20260724.csv", index=False)
for lev in ("cr", "ps"):
    print(f"== {lev} top12 by exact_fit ==")
    print(sb[sb.level == lev].head(12).to_string(index=False))

# yearly breakdown of winners (top by exact_fit and top by exact_hold)
yr_rows = []
best = {}
for lev in ("cr", "ps"):
    sub = sb[sb.level == lev]
    for tag, r in [("byfit", sub.iloc[0]),
                   ("byhold", sub.sort_values("exact_hold", ascending=False).iloc[0])]:
        key = (lev, int(r.lo), int(r.hi), r.grid, r.band)
        p = cache[key]
        if tag == "byfit":
            best[lev] = key
        for y in sorted(set(years)):
            m = years == y
            ok = m & ~np.isnan(p)
            ae = np.abs(p[ok] - truth[lev][ok])
            yr_rows.append({"level": lev, "pick": tag, "spec": str(key), "year": y,
                            "n": int(ok.sum()), "exact": float((ae == 0).mean()),
                            "w25": float((ae <= 25).mean()),
                            "medae": float(np.median(ae))})
yr = pd.DataFrame(yr_rows)
yr.to_csv(f"{BASE}\\crps_refine2_yearly_20260724.csv", index=False)
print(yr.to_string(index=False))

out = {"eod_date": tr["eod_date"]}
for lev in ("cr", "ps"):
    out[f"{lev}_true"] = truth[lev]
    out[f"{lev}_pred"] = cache[best[lev]]
pd.DataFrame(out).to_csv(f"{BASE}\\crps_refine2_best_daily_20260724.csv", index=False)
print("saved")
