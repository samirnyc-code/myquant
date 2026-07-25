"""0DTE levels round 3: apply main-level insights + value fingerprint.

Mapping (established in zerodte2): truth session S 0DTE levels come from the
expiry DYING ON S, present in the prior trading day's chain as expirDate==S.
Prior best: cr0/gw0 = maxcg_ge (max call gamma*OI at/above spot_eod) 22/28%.

New here:
  1. more measures: pure OI (no gamma), net OI, tot; proximity tie-break.
  2. expiry slices: E0 (expir==S) and E01 (expir <= S+3cal, i.e. incl next).
  3. VALUE fingerprint: MQ's published cr0_gex/ps0_gex vs our cg/net/pg value
     AT MQ's own strike -> identifies their measure independent of OI staleness.
  4. hvl0: sign-flip of smoothed net (main-HVL winner style, W=10) on the slice.
  5. fallback check: when no expiry dies on S, does cr0==cr? (truthfp: cr0==cr
     ~60% pre-2022-05 Tue/Thu -> quantify vs existence of the expiry).
Outputs: zerodte3_scoreboard_20260724.csv, zerodte3_valuefit_20260724.csv,
         zerodte3_best_daily_20260724.csv
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
ch = ch[ch["dte"] <= 5].copy()
g = ch["gamma"].clip(lower=0).astype("float64")
ch["cg"] = g * ch["callOpenInterest"]
ch["pg"] = g * ch["putOpenInterest"]
ch["co"] = ch["callOpenInterest"].astype("float64")
ch["po"] = ch["putOpenInterest"].astype("float64")
a = ch.groupby(["tradeDate", "expirDate", "strike"], sort=True)[
    ["cg", "pg", "co", "po"]].sum().reset_index()
BY = dict(tuple(a.groupby("tradeDate", sort=False)))
chain_days = sorted(BY.keys())
day_pos = {d: i for i, d in enumerate(chain_days)}
del ch, a

tr = pd.read_csv(f"{BASE}\\mq_truth.csv", parse_dates=["session_date", "eod_date"])
tr = tr.reset_index(drop=True)
is_fit = (tr["eod_date"] <= FIT_END).to_numpy()
T = {c: tr[c].to_numpy("float64") for c in
     ("cr0", "ps0", "hvl0", "gw0", "cr", "ps", "spot_eod",
      "cr0_gex", "ps0_gex", "gw0_gex", "hvl0_gex")}
N = len(tr)

# build per-session slices
SLICES = {"E0": [None] * N, "E01": [None] * N}
spot_prev = np.full(N, np.nan)
for i, S in enumerate(tr["session_date"]):
    S = pd.Timestamp(S)
    p = day_pos.get(S)
    if p is None or p == 0:
        continue
    P = chain_days[p - 1]
    spot_prev[i] = float(spot_by_day.get(P, np.nan))
    sub = BY[P]
    e0 = sub[sub["expirDate"] == S]
    if len(e0):
        SLICES["E0"][i] = e0
    e01 = sub[sub["expirDate"] <= S + pd.Timedelta(days=3)]
    if len(e01):
        SLICES["E01"][i] = e01

spot_eod = T["spot_eod"]
have_e0 = np.array([s is not None for s in SLICES["E0"]])
# fallback check
eqcr = (T["cr0"] == T["cr"])
print(f"days with E0 expiry: {have_e0.sum()}/{N}")
print(f"cr0==cr | no E0 expiry: {eqcr[~have_e0].mean():.3f} (n={int((~have_e0).sum())})")
print(f"cr0==cr | E0 exists:    {eqcr[have_e0].mean():.3f} (n={int(have_e0.sum())})")


def score_rows(pred, tv, mask_extra=None):
    out = {}
    base = ~np.isnan(pred) & ~np.isnan(tv)
    if mask_extra is not None:
        base &= mask_extra
    for tag, m in [("fit", is_fit), ("hold", ~is_fit)]:
        mm = base & m
        ae = np.abs(pred[mm] - tv[mm])
        out[f"n_{tag}"] = int(mm.sum())
        out[f"exact_{tag}"] = float((ae == 0).mean()) if mm.any() else np.nan
        out[f"w25_{tag}"] = float((ae <= 25).mean()) if mm.any() else np.nan
        out[f"medae_{tag}"] = float(np.median(ae)) if mm.any() else np.nan
    return out


MEASURES = ["cg", "pg", "co", "po", "netg", "neto", "totg"]


def get_vec(sl, meas):
    if meas == "netg":
        return (sl["cg"] - sl["pg"]).to_numpy()
    if meas == "neto":
        return (sl["co"] - sl["po"]).to_numpy()
    if meas == "totg":
        return (sl["cg"] + sl["pg"]).to_numpy()
    return sl[meas].to_numpy()


rows = []
cache = {}
for slc in ("E0", "E01"):
    for meas in MEASURES:
        for side in ("none", "ge", "le"):
            for target in ("max", "min"):
                if meas in ("cg", "co", "totg") and target == "min":
                    continue
                if meas in ("pg", "po") and target == "min":
                    continue
                p = np.full(N, np.nan)
                for i in range(N):
                    sl = SLICES[slc][i]
                    if sl is None:
                        continue
                    K = sl["strike"].to_numpy("float64")
                    v = get_vec(sl, meas)
                    sp = spot_eod[i] if np.isfinite(spot_eod[i]) else spot_prev[i]
                    m = np.ones(len(K), bool)
                    if side == "ge":
                        m &= K >= sp
                    elif side == "le":
                        m &= K <= sp
                    if not m.any():
                        continue
                    idx = np.where(m)[0]
                    vv = v[idx]
                    p[i] = K[idx[vv.argmax() if target == "max" else vv.argmin()]]
                key = (slc, meas, side, target)
                cache[key] = p
                for lev in ("cr0", "ps0", "gw0"):
                    r = {"level": lev, "slice": slc, "meas": meas, "side": side,
                         "target": target}
                    r.update(score_rows(p, T[lev]))
                    rows.append(r)

# hvl0: smoothed net sign-flip nearest spot (main-HVL winner style)
for slc in ("E0", "E01"):
    for W in (0, 10, 25):
        p = np.full(N, np.nan)
        for i in range(N):
            sl = SLICES[slc][i]
            if sl is None:
                continue
            K = sl["strike"].to_numpy("float64")
            v = (sl["cg"] - sl["pg"]).to_numpy()
            # aggregate to 5pt grid & smooth +-W pts
            if W > 0:
                sm = np.array([v[(K >= k - W) & (K <= k + W)].sum() for k in K])
            else:
                sm = v
            sp = spot_eod[i] if np.isfinite(spot_eod[i]) else spot_prev[i]
            s = np.sign(sm)
            flips = np.where(s[:-1] * s[1:] < 0)[0]
            if len(flips) == 0:
                continue
            ks = np.array([K[j] if abs(sm[j]) < abs(sm[j + 1]) else K[j + 1]
                           for j in flips])
            p[i] = ks[np.argmin(np.abs(ks - sp))]
        key = (slc, f"flipW{W}", "near", "flip")
        cache[key] = p
        r = {"level": "hvl0", "slice": slc, "meas": f"flipW{W}", "side": "near",
             "target": "flip"}
        r.update(score_rows(p, T["hvl0"]))
        rows.append(r)

sb = pd.DataFrame(rows).sort_values(["level", "exact_hold"], ascending=[True, False])
sb.to_csv(f"{BASE}\\zerodte3_scoreboard_20260724.csv", index=False)
for lev in ("cr0", "ps0", "hvl0"):
    print(f"== {lev} top8 by exact_hold ==")
    print(sb[sb.level == lev].head(8).to_string(index=False))

# ---- value fingerprint at MQ's own strikes ----
vrows = []
for lev, meases in [("cr0", ["cg", "netg", "totg"]), ("ps0", ["pg", "netg"]),
                    ("gw0", ["cg", "netg", "totg"])]:
    for slc in ("E0", "E01"):
        for meas in meases:
            ours = np.full(N, np.nan)
            for i in range(N):
                sl = SLICES[slc][i]
                if sl is None or np.isnan(T[lev][i]):
                    continue
                K = sl["strike"].to_numpy("float64")
                j = np.where(K == T[lev][i])[0]
                if len(j):
                    ours[i] = get_vec(sl, meas)[j[0]]
            mq = T[f"{lev}_gex"]
            for tag, m in [("fit", is_fit), ("hold", ~is_fit)]:
                ok = m & ~np.isnan(ours) & ~np.isnan(mq) & (ours != 0)
                # exclude days where 0DTE level == main level (fallback rows)
                ok &= ~(T[lev] == (T["cr"] if lev in ("cr0", "gw0") else T["ps"]))
                if ok.sum() < 20:
                    continue
                ratio = mq[ok] / ours[ok]
                r = np.corrcoef(mq[ok], ours[ok])[0, 1]
                sign_agree = (np.sign(mq[ok]) == np.sign(ours[ok])).mean()
                vrows.append({"level": lev, "slice": slc, "meas": meas, "era": tag,
                              "n": int(ok.sum()), "ratio_med": float(np.median(ratio)),
                              "ratio_iqr": float(np.subtract(*np.percentile(ratio, [75, 25]))),
                              "pearson": float(r), "sign_agree": float(sign_agree)})
vf = pd.DataFrame(vrows)
vf.to_csv(f"{BASE}\\zerodte3_valuefit_20260724.csv", index=False)
print(vf.to_string(index=False))

# best daily for the top cr0/ps0 specs
best = {}
for lev in ("cr0", "ps0", "hvl0"):
    r = sb[sb.level == lev].iloc[0]
    best[lev] = cache[(r["slice"], r["meas"], r["side"], r["target"])]
out = pd.DataFrame({"session_date": tr["session_date"],
                    "cr0_true": T["cr0"], "cr0_pred": best["cr0"],
                    "ps0_true": T["ps0"], "ps0_pred": best["ps0"],
                    "hvl0_true": T["hvl0"], "hvl0_pred": best["hvl0"]})
out.to_csv(f"{BASE}\\zerodte3_best_daily_20260724.csv", index=False)
print("saved")
