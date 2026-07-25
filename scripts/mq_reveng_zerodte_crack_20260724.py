"""Crack MQ 0DTE levels: cr0, ps0, hvl0, gw0 (Gamma Wall 0DTE).

Fingerprints: cr0 and gw0 have IDENTICAL distributions (checked below directly);
gw0_gex 84% positive, ps0_gex 83% negative, hvl0 finest grid (5s), all within
~5% of spot. EOD chain: the next session's 0DTE expiry can be dte==0 or dte==1
depending on convention -> test slices dte==0, dte==1, dte<=1.

Candidates per level (argmax over strikes, optional side/band):
  gw0 / cr0: max tot=g*(cOI+pOI), max cg=g*cOI, max net=g*(cOI-pOI)
  ps0:       min net, max pg=g*pOI
  hvl0:      per-strike net sign-flip nearest spot (HVL winner method),
             cum-net zero-cross (low->high) nearest spot, min |net|, max tot
Bands: none, 2%, 5% around spot. Sides for cr0 (none/ge) and ps0 (none/le).

Outputs: zerodte_scoreboard_20260724.csv, zerodte_best_daily_20260724.csv
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
ch["cg"] = g * ch["callOpenInterest"]
ch["pg"] = g * ch["putOpenInterest"]
spot_by_day = ch.groupby("tradeDate")["spotPrice"].first()

SLICES = {"d0": ch["dte"] == 0, "d1": ch["dte"] == 1, "d01": ch["dte"] <= 1}
AGG = {}
for name, m in SLICES.items():
    a = ch.loc[m].groupby(["tradeDate", "strike"], sort=True)[
        ["cg", "pg"]].sum().reset_index()
    AGG[name] = dict(tuple(a.groupby("tradeDate", sort=False)))
del ch

tr = pd.read_csv(f"{BASE}\\mq_truth.csv", parse_dates=["eod_date"])
tr = tr.dropna(subset=["cr0", "ps0", "gw0"]).reset_index(drop=True)
days = tr["eod_date"].tolist()
is_fit = (tr["eod_date"] <= FIT_END).to_numpy()
T = {lvl: tr[lvl].to_numpy("float64") for lvl in ("cr0", "ps0", "hvl0", "gw0")}
print("frac cr0==gw0 in truth:",
      float(np.nanmean(tr["cr0"].values == tr["gw0"].values)))
print("frac cr0_gex==gw0_gex:",
      float(np.nanmean(np.isclose(tr["cr0_gex"].values, tr["gw0_gex"].values))))

BANDS = [("none", np.inf), ("b02", 0.02), ("b05", 0.05)]


def flip_nearspot(K, v, spot):
    s = np.sign(v)
    idx = np.where(s[:-1] * s[1:] < 0)[0]
    if len(idx) == 0:
        return np.nan
    ks = np.array([K[i] if abs(v[i]) < abs(v[i + 1]) else K[i + 1] for i in idx])
    return ks[np.argmin(np.abs(ks - spot))]


def cumcross_nearspot(K, v, spot):
    c = np.cumsum(v)
    s = np.sign(c)
    idx = np.where(s[:-1] * s[1:] < 0)[0]
    if len(idx) == 0:
        return np.nan
    ks = np.array([K[i] if abs(c[i]) < abs(c[i + 1]) else K[i + 1] for i in idx])
    return ks[np.argmin(np.abs(ks - spot))]


preds = {}   # (level, slice, method, band, side) -> array
for sname in SLICES:
    for di, d in enumerate(days):
        sub = AGG[sname].get(pd.Timestamp(d))
        spot = float(spot_by_day.get(pd.Timestamp(d), np.nan))
        if not np.isfinite(spot):
            spot = float(tr.loc[di, "spot_eod"])
        if sub is None or len(sub) < 3:
            continue
        K = sub["strike"].to_numpy("float64")
        cg = sub["cg"].to_numpy()
        pg = sub["pg"].to_numpy()
        net = cg - pg
        tot = cg + pg
        for bname, bw in BANDS:
            bm = np.ones(len(K), bool) if not np.isfinite(bw) else \
                np.abs(K / spot - 1.0) <= bw
            if not bm.any():
                continue
            Kb = K[bm]
            mm = {"maxtot": Kb[np.argmax(tot[bm])],
                  "maxcg": Kb[np.argmax(cg[bm])],
                  "maxnet": Kb[np.argmax(net[bm])],
                  "minnet": Kb[np.argmin(net[bm])],
                  "maxpg": Kb[np.argmax(pg[bm])],
                  "minabsnet": Kb[np.argmin(np.abs(net[bm]))],
                  "flip": flip_nearspot(Kb, net[bm], spot),
                  "cumcross": cumcross_nearspot(Kb, net[bm], spot)}
            side_ge = bm & (K >= spot)
            side_le = bm & (K <= spot)
            if side_ge.any():
                mm["maxnet_ge"] = K[side_ge][np.argmax(net[side_ge])]
                mm["maxcg_ge"] = K[side_ge][np.argmax(cg[side_ge])]
                mm["maxtot_ge"] = K[side_ge][np.argmax(tot[side_ge])]
            if side_le.any():
                mm["minnet_le"] = K[side_le][np.argmin(net[side_le])]
                mm["maxpg_le"] = K[side_le][np.argmax(pg[side_le])]
            for meth, val in mm.items():
                key = (sname, meth, bname)
                if key not in preds:
                    preds[key] = np.full(len(days), np.nan)
                preds[key][di] = val

LEVEL_METHODS = {
    "gw0": ["maxtot", "maxcg", "maxnet", "maxtot_ge", "maxcg_ge", "maxnet_ge"],
    "cr0": ["maxnet", "maxcg", "maxtot", "maxnet_ge", "maxcg_ge", "maxtot_ge"],
    "ps0": ["minnet", "maxpg", "minnet_le", "maxpg_le"],
    "hvl0": ["flip", "cumcross", "minabsnet", "maxtot"],
}
rows = []
for lvl, meths in LEVEL_METHODS.items():
    truth = T[lvl]
    for (sname, meth, bname), pred in preds.items():
        if meth not in meths:
            continue
        err = pred - truth
        row = dict(level=lvl, slice=sname, method=meth, band=bname)
        for tag, m in (("fit", is_fit), ("hold", ~is_fit)):
            e = err[m]
            e = e[np.isfinite(e)]
            row[f"n_{tag}"] = len(e)
            row[f"exact_{tag}"] = float((e == 0).mean()) if len(e) else np.nan
            row[f"w25_{tag}"] = float((np.abs(e) <= 25).mean()) if len(e) else np.nan
            row[f"medae_{tag}"] = float(np.median(np.abs(e))) if len(e) else np.nan
        rows.append(row)

S = pd.DataFrame(rows).sort_values(["level", "exact_fit"], ascending=[True, False])
S.to_csv(f"{BASE}\\zerodte_scoreboard_20260724.csv", index=False)
pd.set_option("display.width", 250)
for lvl in LEVEL_METHODS:
    print(f"\n=== {lvl} top 8 ===")
    print(S[S["level"] == lvl].head(8).to_string(index=False))

best = {}
for lvl in LEVEL_METHODS:
    b = S[S["level"] == lvl].iloc[0]
    best[lvl] = preds[(b["slice"], b["method"], b["band"])]
out = pd.DataFrame({"eod_date": days})
for lvl in LEVEL_METHODS:
    out[f"{lvl}_true"] = T[lvl]
    out[f"{lvl}_pred"] = best[lvl]
out.to_csv(f"{BASE}\\zerodte_best_daily_20260724.csv", index=False)
