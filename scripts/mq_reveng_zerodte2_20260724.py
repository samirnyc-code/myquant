"""0DTE levels round 2: correct expiry join.

Facts (verified): chain parquet has NO dte==0 rows (min dte 1) and truth has
session_date == eod_date. MQ's 0DTE levels for session S refer to the expiry
DYING ON S. That expiry is absent from the chain dated S (expired/dropped) —
it lives in the PRIOR trading day's chain as expirDate == S. Round 1 wrongly
used dte==1 of the same-day chain (= next session's expiry).

Here: for each truth session S, take chain(prev trading day), rows with
expirDate == S. Methods as round 1. Spot: prev-day spotPrice (pre-market view)
AND truth spot_eod (intraday view) as band anchors.

Output: zerodte2_scoreboard_20260724.csv, zerodte2_best_daily_20260724.csv
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
ch["expirDate"] = pd.to_datetime(ch["expirDate"])
spot_by_day = ch.groupby("tradeDate")["spotPrice"].first()
ch = ch[ch["dte"] <= 5]  # only near expiries needed
g = ch["gamma"].clip(lower=0).astype("float64")
ch["cg"] = g * ch["callOpenInterest"]
ch["pg"] = g * ch["putOpenInterest"]
a = ch.groupby(["tradeDate", "expirDate", "strike"], sort=True)[
    ["cg", "pg"]].sum().reset_index()
BY = dict(tuple(a.groupby("tradeDate", sort=False)))
chain_days = sorted(BY.keys())
day_pos = {d: i for i, d in enumerate(chain_days)}
del ch, a

tr = pd.read_csv(f"{BASE}\\mq_truth.csv", parse_dates=["session_date", "eod_date"])
tr = tr.dropna(subset=["cr0", "ps0", "gw0"]).reset_index(drop=True)
days = tr["session_date"].tolist()
is_fit = (tr["eod_date"] <= FIT_END).to_numpy()
T = {lvl: tr[lvl].to_numpy("float64") for lvl in ("cr0", "ps0", "hvl0", "gw0")}

BANDS = [("none", np.inf), ("b02", 0.02), ("b05", 0.05)]


def flip_nearspot(K, v, spot):
    s = np.sign(v)
    idx = np.where(s[:-1] * s[1:] < 0)[0]
    if len(idx) == 0:
        return np.nan
    ks = np.array([K[i] if abs(v[i]) < abs(v[i + 1]) else K[i + 1] for i in idx])
    return ks[np.argmin(np.abs(ks - spot))]


preds = {}
nmatch = 0
for di, d in enumerate(days):
    S_ts = pd.Timestamp(d)
    p = day_pos.get(S_ts)
    if p is None or p == 0:
        continue
    prev = chain_days[p - 1]
    sub = BY[prev]
    sub = sub[sub["expirDate"] == S_ts]
    if len(sub) < 3:
        continue
    nmatch += 1
    for stag, spot in (("spotprev", float(spot_by_day.get(prev, np.nan))),
                       ("spoteod", float(tr.loc[di, "spot_eod"]))):
        if not np.isfinite(spot):
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
                  "flip": flip_nearspot(Kb, net[bm], spot)}
            ge = bm & (K >= spot)
            le = bm & (K <= spot)
            if ge.any():
                mm["maxnet_ge"] = K[ge][np.argmax(net[ge])]
                mm["maxcg_ge"] = K[ge][np.argmax(cg[ge])]
                mm["maxtot_ge"] = K[ge][np.argmax(tot[ge])]
            if le.any():
                mm["minnet_le"] = K[le][np.argmin(net[le])]
                mm["maxpg_le"] = K[le][np.argmax(pg[le])]
            for meth, val in mm.items():
                key = (meth, bname, stag)
                if key not in preds:
                    preds[key] = np.full(len(days), np.nan)
                preds[key][di] = val
print("prev-day expiry matches:", nmatch, "of", len(days))

LEVEL_METHODS = {
    "gw0": ["maxtot", "maxcg", "maxnet", "maxtot_ge", "maxcg_ge", "maxnet_ge"],
    "cr0": ["maxnet", "maxcg", "maxtot", "maxnet_ge", "maxcg_ge", "maxtot_ge"],
    "ps0": ["minnet", "maxpg", "minnet_le", "maxpg_le"],
    "hvl0": ["flip", "minabsnet", "maxtot"],
}
rows = []
for lvl, meths in LEVEL_METHODS.items():
    truth = T[lvl]
    for (meth, bname, stag), pred in preds.items():
        if meth not in meths:
            continue
        err = pred - truth
        row = dict(level=lvl, method=meth, band=bname, spot=stag)
        for tag, m in (("fit", is_fit), ("hold", ~is_fit)):
            e = err[m]
            e = e[np.isfinite(e)]
            row[f"n_{tag}"] = len(e)
            row[f"exact_{tag}"] = float((e == 0).mean()) if len(e) else np.nan
            row[f"w25_{tag}"] = float((np.abs(e) <= 25).mean()) if len(e) else np.nan
            row[f"medae_{tag}"] = float(np.median(np.abs(e))) if len(e) else np.nan
        rows.append(row)

S = pd.DataFrame(rows).sort_values(["level", "exact_fit"], ascending=[True, False])
S.to_csv(f"{BASE}\\zerodte2_scoreboard_20260724.csv", index=False)
pd.set_option("display.width", 250)
for lvl in LEVEL_METHODS:
    print(f"\n=== {lvl} top 6 ===")
    print(S[S["level"] == lvl].head(6).to_string(index=False))

out = pd.DataFrame({"session_date": days})
for lvl in LEVEL_METHODS:
    b = S[S["level"] == lvl].iloc[0]
    out[f"{lvl}_true"] = T[lvl]
    out[f"{lvl}_pred"] = preds[(b["method"], b["band"], b["spot"])]
out.to_csv(f"{BASE}\\zerodte2_best_daily_20260724.csv", index=False)
