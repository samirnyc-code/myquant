"""Crack MQ Call Resistance (CR) and Put Support (PS) exact spec.

Fingerprint facts driving the design (crps_fingerprint_20260724.csv):
  - cr on 50-multiples 94.7% / 100s 84.7%; ps on 100s 95.4%  -> test candidate
    strike grids: any / mult25 / mult50 / mult100
  - cr_gex always > 0 (call gamma), ps_gex always < 0 (put gamma)
  - corr(|cr_gex|, call gamma*OI) ~0.63 only for dte<=30/45 slices -> DTE cap
  - cr above spot 97% (med +109), ps below spot 96% (med -199)

Sweep: DTE slice x measure x strike-grid x spot-side restriction x band.
  CR measures: cg=gamma*callOI, cgK2=cg*strike^2, callOI, net=cg-pg (argmax)
  PS measures: pg=gamma*putOI, pgK2, putOI, net (argmin = most negative)
Scoring vs mq_truth cr/ps: exact %, within25 %, medAE; fit <=2023-12-31 vs 2024+.

Outputs: crps_scoreboard_20260724.csv, crps_best_daily_20260724.csv
"""
import numpy as np
import pandas as pd

BASE = r"C:\Users\Admin\myquant\data\regime\mq_reveng"
FIT_END = pd.Timestamp("2023-12-31")

ch = pd.read_parquet(f"{BASE}\\chain_slices_overlap.parquet",
                     columns=["tradeDate", "expirDate", "dte", "strike",
                              "callOpenInterest", "putOpenInterest", "gamma",
                              "spotPrice"])
ch["tradeDate"] = pd.to_datetime(ch["tradeDate"])
g = ch["gamma"].clip(lower=0).astype("float64")
ch["cg"] = g * ch["callOpenInterest"]
ch["pg"] = g * ch["putOpenInterest"]
ed = pd.to_datetime(ch["expirDate"])
ch["is_monthly"] = ((ed.dt.weekday == 4) & ed.dt.day.between(15, 21)).values
spot_by_day = ch.groupby("tradeDate")["spotPrice"].first()

dte = ch["dte"]
DTE = {
    "all":    dte >= 0,
    "le20":   dte <= 20,
    "le30":   dte <= 30,
    "le45":   dte <= 45,
    "le60":   dte <= 60,
    "le90":   dte <= 90,
    "d1_30":  dte.between(1, 30),
    "d1_45":  dte.between(1, 45),
    "d1_60":  dte.between(1, 60),
    "ex0":    dte >= 1,
    "monthly": ch["is_monthly"],
}
AGG = {}
for name, m in DTE.items():
    a = ch.loc[m].groupby(["tradeDate", "strike"], sort=True)[
        ["cg", "pg", "callOpenInterest", "putOpenInterest"]].sum().reset_index()
    AGG[name] = dict(tuple(a.groupby("tradeDate", sort=False)))
del ch, a

tr = pd.read_csv(f"{BASE}\\mq_truth.csv", parse_dates=["eod_date"])
tr = tr.dropna(subset=["cr", "ps"]).reset_index(drop=True)
days = tr["eod_date"].tolist()
is_fit = (tr["eod_date"] <= FIT_END).to_numpy()
truth_cr = tr["cr"].to_numpy("float64")
truth_ps = tr["ps"].to_numpy("float64")

GRIDS = [("any", 1), ("m25", 25), ("m50", 50), ("m100", 100)]
BANDS = [("bNone", np.inf), ("b05", 0.05), ("b10", 0.10), ("b15", 0.15), ("b20", 0.20)]
SIDES_CR = ["none", "ge", "gt"]
SIDES_PS = ["none", "le", "lt"]
MEAS_CR = ["cg", "cgK2", "coi", "net"]
MEAS_PS = ["pg", "pgK2", "poi", "netmin"]

# spec index maps
specs_cr, specs_ps = [], []
for dname in DTE:
    for gname, _ in GRIDS:
        for sname in SIDES_CR:
            for bname, _ in BANDS:
                for mname in MEAS_CR:
                    specs_cr.append((dname, gname, sname, bname, mname))
for dname in DTE:
    for gname, _ in GRIDS:
        for sname in SIDES_PS:
            for bname, _ in BANDS:
                for mname in MEAS_PS:
                    specs_ps.append((dname, gname, sname, bname, mname))
idx_cr = {s: i for i, s in enumerate(specs_cr)}
idx_ps = {s: i for i, s in enumerate(specs_ps)}
P_cr = np.full((len(specs_cr), len(days)), np.nan)
P_ps = np.full((len(specs_ps), len(days)), np.nan)

for di, d in enumerate(days):
    spot = float(spot_by_day.get(d, np.nan))
    if not np.isfinite(spot):
        spot = float(tr.loc[di, "spot_eod"])
    for dname in DTE:
        sub = AGG[dname].get(d)
        if sub is None or len(sub) == 0:
            continue
        K = sub["strike"].to_numpy("float64")
        cg = sub["cg"].to_numpy()
        pg = sub["pg"].to_numpy()
        coi = sub["callOpenInterest"].to_numpy("float64")
        poi = sub["putOpenInterest"].to_numpy("float64")
        K2 = K * K
        meas_cr = {"cg": cg, "cgK2": cg * K2, "coi": coi, "net": cg - pg}
        meas_ps = {"pg": pg, "pgK2": pg * K2, "poi": poi, "netmin": -(cg - pg)}
        grid_masks = {gname: (np.ones(len(K), bool) if gm == 1 else (K % gm == 0))
                      for gname, gm in GRIDS}
        band_masks = {bname: (np.ones(len(K), bool) if not np.isfinite(bw)
                              else (np.abs(K / spot - 1.0) <= bw))
                      for bname, bw in BANDS}
        side_cr = {"none": np.ones(len(K), bool), "ge": K >= spot, "gt": K > spot}
        side_ps = {"none": np.ones(len(K), bool), "le": K <= spot, "lt": K < spot}
        for gname, _ in GRIDS:
            gmask = grid_masks[gname]
            for bname, _ in BANDS:
                bmask = gmask & band_masks[bname]
                for sname in SIDES_CR:
                    mask = bmask & side_cr[sname]
                    if mask.any():
                        Km = K[mask]
                        for mname in MEAS_CR:
                            v = meas_cr[mname][mask]
                            P_cr[idx_cr[(dname, gname, sname, bname, mname)], di] = \
                                Km[np.argmax(v)]
                for sname in SIDES_PS:
                    mask = bmask & side_ps[sname]
                    if mask.any():
                        Km = K[mask]
                        for mname in MEAS_PS:
                            v = meas_ps[mname][mask]
                            P_ps[idx_ps[(dname, gname, sname, bname, mname)], di] = \
                                Km[np.argmax(v)]


def score(P, specs, truth):
    rows = []
    for i, s in enumerate(specs):
        err = P[i] - truth
        row = dict(dte=s[0], grid=s[1], side=s[2], band=s[3], meas=s[4])
        for tag, m in (("fit", is_fit), ("hold", ~is_fit)):
            e = err[m]
            e = e[np.isfinite(e)]
            row[f"n_{tag}"] = len(e)
            row[f"exact_{tag}"] = float((e == 0).mean()) if len(e) else np.nan
            row[f"w25_{tag}"] = float((np.abs(e) <= 25).mean()) if len(e) else np.nan
            row[f"medae_{tag}"] = float(np.median(np.abs(e))) if len(e) else np.nan
            row[f"bias_{tag}"] = float(np.median(e)) if len(e) else np.nan
        rows.append(row)
    return pd.DataFrame(rows)


S_cr = score(P_cr, specs_cr, truth_cr)
S_cr["level"] = "cr"
S_ps = score(P_ps, specs_ps, truth_ps)
S_ps["level"] = "ps"
S = pd.concat([S_cr, S_ps]).sort_values(["level", "exact_fit"],
                                        ascending=[True, False])
S.to_csv(f"{BASE}\\crps_scoreboard_20260724.csv", index=False)

pd.set_option("display.width", 250)
cols = ["level", "dte", "grid", "side", "band", "meas", "exact_fit", "exact_hold",
        "w25_fit", "w25_hold", "medae_fit", "medae_hold", "bias_fit", "bias_hold"]
print("=== CR top 20 by exact_fit ===")
print(S_cr.sort_values("exact_fit", ascending=False).head(20)
      .assign(level="cr")[cols].to_string(index=False))
print("\n=== CR top 10 by w25_fit ===")
print(S_cr.sort_values("w25_fit", ascending=False).head(10)
      .assign(level="cr")[cols].to_string(index=False))
print("\n=== PS top 20 by exact_fit ===")
print(S_ps.sort_values("exact_fit", ascending=False).head(20)
      .assign(level="ps")[cols].to_string(index=False))
print("\n=== PS top 10 by w25_fit ===")
print(S_ps.sort_values("w25_fit", ascending=False).head(10)
      .assign(level="ps")[cols].to_string(index=False))

# save best-daily for top spec each
best_cr = S_cr.sort_values(["exact_fit", "w25_fit"], ascending=False).iloc[0]
best_ps = S_ps.sort_values(["exact_fit", "w25_fit"], ascending=False).iloc[0]
bc = (best_cr["dte"], best_cr["grid"], best_cr["side"], best_cr["band"], best_cr["meas"])
bp = (best_ps["dte"], best_ps["grid"], best_ps["side"], best_ps["band"], best_ps["meas"])
out = pd.DataFrame({"eod_date": days, "cr_true": truth_cr,
                    "cr_pred": P_cr[idx_cr[bc]], "ps_true": truth_ps,
                    "ps_pred": P_ps[idx_ps[bp]]})
out.to_csv(f"{BASE}\\crps_best_daily_20260724.csv", index=False)
print("\nbest cr spec:", bc, " best ps spec:", bp)
