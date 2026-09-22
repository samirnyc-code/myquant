"""Refine the CR/PS winning specs from mq_reveng_crps_crack_20260724.py.

Base winners (fit exact% / hold exact%):
  CR: argmax net GEX (gamma*(cOI-pOI)), all dte, strikes%50==0, no side/band
      -> 68.9 / 78.3
  PS: argmin net GEX, strikes%100==0, band +-20%, no side -> 72.5 / 77.5

Refinements tested here:
  A. chain-day shift: OI reporting lag -> use chain from eod_date-1 / +1 trading day
  B. rank-of-truth: on miss days, what rank does MQ's strike have in our net-GEX
     ordering (grid-restricted)? (rank 2 = tie-break/noise; rank>5 = formula gap)
  C. extra measures at the winning grid: net*K, net*K^2, dte caps le90/le180/le365
  D. PS grids m50 vs m100 with wider band set; CR with b20..b30 bands
  E. mixed grid: m50 grid but m25 allowed if spot<4000 (early sample low strikes?)

Outputs: crps_refine_20260724.csv (scoreboard), crps_missrank_20260724.csv
"""
import numpy as np
import pandas as pd

BASE = r"C:\Users\Admin\myquant\data\regime\mq_reveng"
FIT_END = pd.Timestamp("2023-12-31")

ch = pd.read_parquet(f"{BASE}\\chain_slices_overlap.parquet",
                     columns=["tradeDate", "dte", "strike", "callOpenInterest",
                              "putOpenInterest", "gamma", "spotPrice"])
ch["tradeDate"] = pd.to_datetime(ch["tradeDate"])
g = ch["gamma"].clip(lower=0).astype("float64")
ch["net"] = g * (ch["callOpenInterest"] - ch["putOpenInterest"])
spot_by_day = ch.groupby("tradeDate")["spotPrice"].first()

dte = ch["dte"]
DTE = {"all": dte >= 0, "le90": dte <= 90, "le180": dte <= 180, "le365": dte <= 365}
AGG = {}
for name, m in DTE.items():
    a = ch.loc[m].groupby(["tradeDate", "strike"], sort=True)["net"].sum().reset_index()
    AGG[name] = dict(tuple(a.groupby("tradeDate", sort=False)))
chain_days = sorted(AGG["all"].keys())
day_pos = {d: i for i, d in enumerate(chain_days)}
del ch

tr = pd.read_csv(f"{BASE}\\mq_truth.csv", parse_dates=["eod_date"])
tr = tr.dropna(subset=["cr", "ps"]).reset_index(drop=True)
days = tr["eod_date"].tolist()
is_fit = (tr["eod_date"] <= FIT_END).to_numpy()
truth_cr = tr["cr"].to_numpy("float64")
truth_ps = tr["ps"].to_numpy("float64")


def predict(shift, dslice, grid, band, weight, target):
    """target: 'max' (CR) or 'min' (PS). Returns pred array over truth days."""
    out = np.full(len(days), np.nan)
    for di, d in enumerate(days):
        p = day_pos.get(pd.Timestamp(d))
        if p is None:
            continue
        p2 = p + shift
        if p2 < 0 or p2 >= len(chain_days):
            continue
        d2 = chain_days[p2]
        sub = AGG[dslice].get(d2)
        if sub is None:
            continue
        K = sub["strike"].to_numpy("float64")
        v = sub["net"].to_numpy("float64").copy()
        spot = float(spot_by_day.get(d2, np.nan))
        mask = np.ones(len(K), bool)
        if grid == "m50":
            mask &= (K % 50 == 0)
        elif grid == "m100":
            mask &= (K % 100 == 0)
        elif grid == "m25":
            mask &= (K % 25 == 0)
        elif grid == "m50lo25":
            mask &= np.where(spot < 4000, K % 25 == 0, K % 50 == 0)
        if band is not None and np.isfinite(spot):
            mask &= np.abs(K / spot - 1.0) <= band
        if weight == "K":
            v = v * K
        elif weight == "K2":
            v = v * K * K
        if not mask.any():
            continue
        Km, vm = K[mask], v[mask]
        out[di] = Km[np.argmax(vm)] if target == "max" else Km[np.argmin(vm)]
    return out


def score_row(pred, truth, **meta):
    err = pred - truth
    row = dict(meta)
    for tag, m in (("fit", is_fit), ("hold", ~is_fit)):
        e = err[m]
        e = e[np.isfinite(e)]
        row[f"n_{tag}"] = len(e)
        row[f"exact_{tag}"] = float((e == 0).mean()) if len(e) else np.nan
        row[f"w25_{tag}"] = float((np.abs(e) <= 25).mean()) if len(e) else np.nan
        row[f"medae_{tag}"] = float(np.median(np.abs(e))) if len(e) else np.nan
    return row


rows = []
# A: day shifts on base winners
for shift in (-1, 0, 1):
    rows.append(score_row(predict(shift, "all", "m50", None, "1", "max"), truth_cr,
                          level="cr", shift=shift, dte="all", grid="m50",
                          band="none", w="1"))
    rows.append(score_row(predict(shift, "all", "m100", 0.20, "1", "min"), truth_ps,
                          level="ps", shift=shift, dte="all", grid="m100",
                          band="b20", w="1"))
# C/D: measure and slice variants at shift 0
for dslice in DTE:
    for grid in ("m25", "m50", "m100", "m50lo25", "any"):
        for band in (None, 0.20, 0.25, 0.30):
            bn = "none" if band is None else f"b{int(band*100)}"
            for w in ("1", "K", "K2"):
                rows.append(score_row(predict(0, dslice, grid, band, w, "max"),
                                      truth_cr, level="cr", shift=0, dte=dslice,
                                      grid=grid, band=bn, w=w))
                rows.append(score_row(predict(0, dslice, grid, band, w, "min"),
                                      truth_ps, level="ps", shift=0, dte=dslice,
                                      grid=grid, band=bn, w=w))

S = pd.DataFrame(rows).sort_values(["level", "exact_fit"], ascending=[True, False])
S.to_csv(f"{BASE}\\crps_refine_20260724.csv", index=False)
pd.set_option("display.width", 250)
for lvl in ("cr", "ps"):
    print(f"=== {lvl} top 12 ===")
    print(S[S["level"] == lvl].head(12).to_string(index=False))

# B: rank-of-truth on miss days for the base winners --------------------------
miss_rows = []
for lvl, truth, grid, band, target in (("cr", truth_cr, "m50", None, "max"),
                                       ("ps", truth_ps, "m100", 0.20, "min")):
    for di, d in enumerate(days):
        sub = AGG["all"].get(pd.Timestamp(d))
        if sub is None:
            continue
        K = sub["strike"].to_numpy("float64")
        v = sub["net"].to_numpy("float64")
        spot = float(spot_by_day.get(pd.Timestamp(d), np.nan))
        mask = (K % (50 if grid == "m50" else 100) == 0)
        if band is not None and np.isfinite(spot):
            mask &= np.abs(K / spot - 1.0) <= band
        Km, vm = K[mask], v[mask]
        if target == "min":
            vm = -vm
        order = Km[np.argsort(-vm)]
        t = truth[di]
        if len(order) == 0:
            continue
        rank = int(np.where(order == t)[0][0]) + 1 if t in order else -1
        miss_rows.append(dict(level=lvl, eod_date=d, truth=t, pred=order[0],
                              rank_of_truth=rank, is_fit=bool(is_fit[di])))
M = pd.DataFrame(miss_rows)
M.to_csv(f"{BASE}\\crps_missrank_20260724.csv", index=False)
for lvl in ("cr", "ps"):
    sub = M[M["level"] == lvl]
    misses = sub[sub["rank_of_truth"] != 1]
    print(f"\n{lvl}: miss days {len(misses)}/{len(sub)}; rank-of-truth dist on misses:")
    print(misses["rank_of_truth"].value_counts().sort_index().head(12).to_string())
