"""
mq_reveng_final_20260724.py -- SYNTHESIS: one coherent MenthorQ SPX level-replication spec.

Combines the winning specs from the four reverse-engineering agents (GEX formula,
CR/PS/0DTE, HVL, GEX-10 universe) into a single pipeline, computes ALL levels for
every overlap day from ORATS EOD chains, and scores against mq_truth.csv with
fit (eod_date <= 2023-12-31) vs holdout (2024+) separated.

Adversarial head-to-heads included where agent specs conflicted:
  - HVL: per-strike sign-flip w/ +-25pt smoothing (HVL agent)  VS  cumulative
    net-GEX zero-crossing (web/Perfiliev hypothesis).
  - GEX 1-10 selection: max(callOI*g, putOI*g), 2<=dte<=21, +-3% band, excl levels
    (ranking agent)  VS  top-10 |net GEX| inside published 1D band (web hypothesis).

THE SPEC (all from same-day ORATS EOD chain, tradeDate == eod_date, gamma zeroed
outside [0, 0.5] to kill 63 corrupt rows + ~961k tiny negative deep-ITM gammas):
  net(K)     = sum over expiries dte>=2 of gamma * (callOI - putOI)      [ORATS dte: same-day = 1]
  value(K)   = net(K) * 100 * spot            (dollar gamma per 1-pt SPX move)
  CR         = argmax_K net(K), all strikes
  PS         = argmin_K net(K), strikes within +-20% of spot
  HVL        = negative-side strike of the net-GEX sign flip nearest spot, after
               aggregating net(K) to a 5-pt grid and smoothing with a +-25pt
               price-window rolling sum
  GEX 1..10  = top-10 strikes by max(sum_{2<=dte<=21} gamma*callOI,
               sum_{2<=dte<=21} gamma*putOI), universe |K/spot - 1| <= 3%,
               excluding the 7 primary levels; ordered by |K - spot| (gex_1 nearest)
  0DTE set (from PRIOR day's chain, expiry dying on session S; degenerate same-day
  rows in the S chain are unusable):
    CR0 = GW0 = argmax_K gamma*callOI, K >= spot         (fallback: CR when no expiry dies)
    PS0        = argmin_K gamma*(callOI-putOI), K <= spot, expiries <= S+3 calendar days
    HVL0       = smaller-|net| side of net sign flip nearest spot on the dying expiry

Outputs:
  data/regime/mq_reveng/final_replication.csv                (per-day levels, ours vs truth)
  data/regime/mq_reveng/final_replication_summary_20260724.csv (all metrics, fit vs holdout)
  data/regime/mq_reveng/final_headtohead_20260724.csv        (conflicting-spec duels)
"""
import numpy as np
import pandas as pd
from pathlib import Path

BASE = Path(__file__).resolve().parents[1]
D = BASE / "data" / "regime" / "mq_reveng"
FIT_END = "2023-12-31"

# ---------------------------------------------------------------- load
print("loading...")
chain = pd.read_parquet(
    D / "chain_slices_overlap.parquet",
    columns=["tradeDate", "expirDate", "dte", "strike",
             "callOpenInterest", "putOpenInterest", "gamma", "spotPrice"],
)
chain["tradeDate"] = chain["tradeDate"].astype(str)
chain["expirDate"] = chain["expirDate"].astype(str)
# gamma hygiene: zero anything outside [0, 0.5] (corrupt 1e21 rows, negative deep-ITM)
g = chain["gamma"].to_numpy(copy=True)
bad = (g < 0) | (g > 0.5) | ~np.isfinite(g)
g[bad] = 0.0
chain["gamma"] = g
print(f"  chain rows {len(chain):,}; zeroed gamma rows {bad.sum():,}")

truth = pd.read_csv(D / "mq_truth.csv")
truth = truth.sort_values("eod_date").reset_index(drop=True)

spot_by_day = chain.groupby("tradeDate")["spotPrice"].first()

# ---------------------------------------------------------------- per-day/strike aggregates
print("aggregating...")
m = chain[chain["dte"] >= 2].copy()
m["net"] = m["gamma"] * (m["callOpenInterest"] - m["putOpenInterest"])
net_main = m.groupby(["tradeDate", "strike"])["net"].sum()

m21 = m[m["dte"] <= 21]
c21 = (m21["gamma"] * m21["callOpenInterest"]).groupby(
    [m21["tradeDate"], m21["strike"]]).sum()
p21 = (m21["gamma"] * m21["putOpenInterest"]).groupby(
    [m21["tradeDate"], m21["strike"]]).sum()

# short-dated slice (per-expiry granularity) for the 0DTE levels
short = chain[chain["dte"] <= 10][
    ["tradeDate", "expirDate", "strike", "callOpenInterest", "putOpenInterest", "gamma"]
].copy()
short_by_day = dict(tuple(short.groupby("tradeDate")))

net_by_day = dict(tuple(net_main.reset_index().groupby("tradeDate")))
c21_d = dict(tuple(c21.rename("v").reset_index().groupby("tradeDate")))
p21_d = dict(tuple(p21.rename("v").reset_index().groupby("tradeDate")))

trade_dates = sorted(spot_by_day.index)
prev_date = {d: (trade_dates[i - 1] if i > 0 else None)
             for i, d in enumerate(trade_dates)}

# ---------------------------------------------------------------- level functions
def smooth_window_sum(strikes, vals, half):
    """price-window rolling sum: for each strike, sum vals within +-half points."""
    cs = np.concatenate([[0.0], np.cumsum(vals)])
    lo = np.searchsorted(strikes, strikes - half, side="left")
    hi = np.searchsorted(strikes, strikes + half, side="right")
    return cs[hi] - cs[lo]

def hvl_flip(strikes, net, spot, half=25.0):
    """5-pt grid, +-half smoothing, sign flip nearest spot, negative-side strike.
    Returns (strike, fallback_used)."""
    gridk = np.round(strikes / 5.0) * 5.0
    dfg = pd.DataFrame({"k": gridk, "v": net}).groupby("k")["v"].sum()
    k = dfg.index.to_numpy(float)
    s = smooth_window_sum(k, dfg.to_numpy(float), half)
    sgn = np.sign(s)
    flips = np.where(sgn[:-1] * sgn[1:] < 0)[0]
    if len(flips) == 0:
        return float(k[np.argmin(np.abs(s))]), True
    dist = np.minimum(np.abs(k[flips] - spot), np.abs(k[flips + 1] - spot))
    i = flips[np.argmin(dist)]
    neg = k[i] if s[i] < 0 else k[i + 1]
    return float(neg), False

def hvl_cumulative(strikes, net, spot):
    """head-to-head variant B: zero-crossing of cumulative net-GEX (low->high),
    crossing nearest spot; returns the strike where cumsum crosses zero."""
    cs = np.cumsum(net)
    sgn = np.sign(cs)
    flips = np.where(sgn[:-1] * sgn[1:] < 0)[0]
    if len(flips) == 0:
        return np.nan
    cand = strikes[flips + 1]
    return float(cand[np.argmin(np.abs(cand - spot))])

def zerodte_levels(prior_short, session_date, spot):
    """CR0/GW0, PS0, HVL0 from prior day's chain. Returns dict (may be empty)."""
    out = {}
    if prior_short is None:
        return out
    dying = prior_short[prior_short["expirDate"] == session_date]
    if len(dying):
        agg = dying.groupby("strike").agg(
            c=("callOpenInterest", "sum"), p=("putOpenInterest", "sum"),
            gsum=("gamma", "sum"))
        # per-strike gamma*OI must be summed per row then per strike:
        gc = (dying["gamma"] * dying["callOpenInterest"]).groupby(dying["strike"]).sum()
        gn = (dying["gamma"] * (dying["callOpenInterest"] - dying["putOpenInterest"])
              ).groupby(dying["strike"]).sum()
        ks = gc.index.to_numpy(float)
        # CR0/GW0: max call gamma*OI at/above spot
        above = ks >= spot
        if above.any():
            sel = gc[above]
            out["cr0"] = float(sel.idxmax())
            out["cr0_gex"] = float(sel.max() * 100 * spot)
        # HVL0: sign flip nearest spot, smaller-|net| side
        v = gn.to_numpy(float)
        sgn = np.sign(v)
        flips = np.where(sgn[:-1] * sgn[1:] < 0)[0]
        if len(flips):
            side = np.where(np.abs(v[flips]) <= np.abs(v[flips + 1]), ks[flips], ks[flips + 1])
            out["hvl0"] = float(side[np.argmin(np.abs(side - spot))])
    # PS0: expiries <= session+3 calendar days
    lim = (pd.Timestamp(session_date) + pd.Timedelta(days=3)).strftime("%Y-%m-%d")
    near = prior_short[(prior_short["expirDate"] >= session_date)
                       & (prior_short["expirDate"] <= lim)]
    if len(near):
        gnn = (near["gamma"] * (near["callOpenInterest"] - near["putOpenInterest"])
               ).groupby(near["strike"]).sum()
        below = gnn[gnn.index.to_numpy(float) <= spot]
        if len(below):
            out["ps0"] = float(below.idxmin())
            out["ps0_gex"] = float(below.min() * 100 * spot)
    return out

# ---------------------------------------------------------------- main loop
print("computing levels...")
rows = []
for _, tr in truth.iterrows():
    d = tr["eod_date"]                      # == session_date on every row (verified)
    nb = net_by_day.get(d)
    if nb is None:
        continue
    spot_chain = float(spot_by_day[d])
    spot = float(tr["spot_eod"]) if np.isfinite(tr["spot_eod"]) else spot_chain
    ks = nb["strike"].to_numpy(float)
    nv = nb["net"].to_numpy(float)
    order = np.argsort(ks)
    ks, nv = ks[order], nv[order]

    r = {"eod_date": d, "spot": spot}

    # CR / PS
    i_cr = int(np.argmax(nv))
    r["cr_pred"] = ks[i_cr]
    r["cr_gex_pred"] = nv[i_cr] * 100 * spot
    band = np.abs(ks / spot - 1.0) <= 0.20
    i_ps = int(np.argmin(np.where(band, nv, np.inf)))
    r["ps_pred"] = ks[i_ps]
    r["ps_gex_pred"] = nv[i_ps] * 100 * spot

    # HVL (winner) + cumulative variant (duel)
    hvl, fb = hvl_flip(ks, nv, spot, half=25.0)
    r["hvl_pred"], r["hvl_fallback"] = hvl, int(fb)
    j = np.searchsorted(ks, hvl)
    r["hvl_gex_pred"] = (nv[j] * 100 * spot) if (j < len(ks) and ks[j] == hvl) else np.nan
    r["hvl_cum_pred"] = hvl_cumulative(ks, nv, spot)

    # GEX 1-10 winner: max(call21, put21), +-3% band, excl 7 levels
    cd, pdd = c21_d.get(d), p21_d.get(d)
    score = {}
    if cd is not None:
        for kk, vv in zip(cd["strike"].to_numpy(float), cd["v"].to_numpy(float)):
            score[kk] = max(score.get(kk, 0.0), vv)
    if pdd is not None:
        for kk, vv in zip(pdd["strike"].to_numpy(float), pdd["v"].to_numpy(float)):
            score[kk] = max(score.get(kk, 0.0), vv)

    # 0DTE set first (needed for the exclusion list)
    zd = zerodte_levels(short_by_day.get(prev_date.get(d)), d, spot)
    r["cr0_pred"] = zd.get("cr0", r["cr_pred"])          # fallback: cr0 = cr
    r["cr0_gex_pred"] = zd.get("cr0_gex", np.nan)
    r["ps0_pred"] = zd.get("ps0", r["ps_pred"])
    r["ps0_gex_pred"] = zd.get("ps0_gex", np.nan)
    r["hvl0_pred"] = zd.get("hvl0", r["hvl_pred"])
    r["gw0_pred"] = r["cr0_pred"]
    r["zerodte_from_chain"] = int("cr0" in zd)

    excl_pred = {r["cr_pred"], r["ps_pred"], r["hvl_pred"],
                 r["cr0_pred"], r["ps0_pred"], r["hvl0_pred"], r["gw0_pred"]}
    excl_truth = {tr[c] for c in ("cr", "ps", "hvl", "cr0", "ps0", "hvl0", "gw0")
                  if np.isfinite(tr[c])}

    cand = [(kk, vv) for kk, vv in score.items() if abs(kk / spot - 1.0) <= 0.03]
    for tag, excl in (("pred", excl_pred), ("truth", excl_truth)):
        cc = [(kk, vv) for kk, vv in cand if kk not in excl]
        cc.sort(key=lambda x: -x[1])
        top = [kk for kk, _ in cc[:10]]
        top.sort(key=lambda kk: abs(kk - spot))          # gex_1 = nearest spot
        for i in range(10):
            r[f"gex_{i+1}_pred_x{tag}"] = top[i] if i < len(top) else np.nan
    # published-value prediction at our (pred-excl) strikes
    for i in range(10):
        kk = r[f"gex_{i+1}_pred_xpred"]
        if np.isfinite(kk):
            j = np.searchsorted(ks, kk)
            r[f"gex_{i+1}_gex_pred"] = (nv[j] * 100 * spot
                                        if j < len(ks) and ks[j] == kk else np.nan)

    # GEX-10 web variant B: top-10 |net| inside published 1D band
    if np.isfinite(tr["d1_min"]) and np.isfinite(tr["d1_max"]):
        inb = (ks >= tr["d1_min"]) & (ks <= tr["d1_max"])
        kb, vb = ks[inb], np.abs(nv[inb])
        o2 = np.argsort(-vb)
        r["gexB_all"] = ",".join(str(kb[i]) for i in o2[:10])
        keep = [i for i in o2 if kb[i] not in excl_truth][:10]
        r["gexB_excl"] = ",".join(str(kb[i]) for i in keep)

    # value-formula check at TRUTH strikes (13 levels)
    for c in ["cr", "ps", "hvl"] + [f"gex_{i}" for i in range(1, 11)]:
        kk = tr[c]
        if np.isfinite(kk):
            j = np.searchsorted(ks, kk)
            r[f"val_at_{c}"] = (nv[j] * 100 * spot
                                if j < len(ks) and ks[j] == kk else np.nan)
    rows.append(r)

pred = pd.DataFrame(rows)
out = truth.merge(pred, on="eod_date", how="inner")
print(f"  merged days: {len(out)}")

# ---------------------------------------------------------------- scoring
out["period"] = np.where(out["eod_date"] <= FIT_END, "fit", "holdout")
out["year"] = out["eod_date"].str[:4]

def level_metrics(df, t, p):
    ok = df[[t, p]].dropna()
    if not len(ok):
        return dict(n=0)
    err = (ok[p] - ok[t]).abs()
    return dict(n=len(ok), exact=float((err == 0).mean()),
                within5=float((err <= 5).mean()), within25=float((err <= 25).mean()),
                medAE=float(err.median()), meanAE=float(err.mean()))

def gex10_metrics(df, tag):
    precs, jacs = [], []
    for _, rr in df.iterrows():
        tset = {rr[f"gex_{i}"] for i in range(1, 11) if np.isfinite(rr[f"gex_{i}"])}
        pset = {rr[f"gex_{i}_pred_x{tag}"] for i in range(1, 11)
                if np.isfinite(rr[f"gex_{i}_pred_x{tag}"])}
        if not tset or not pset:
            continue
        inter = len(tset & pset)
        precs.append(inter / 10.0)
        jacs.append(inter / len(tset | pset))
    return dict(n=len(precs), precision10=float(np.mean(precs)) if precs else np.nan,
                jaccard=float(np.mean(jacs)) if jacs else np.nan)

def gex10_str_metrics(df, col):
    precs = []
    for _, rr in df.iterrows():
        tset = {rr[f"gex_{i}"] for i in range(1, 11) if np.isfinite(rr[f"gex_{i}"])}
        if not isinstance(rr.get(col), str) or not tset:
            continue
        pset = {float(x) for x in rr[col].split(",") if x}
        precs.append(len(tset & pset) / 10.0)
    return dict(n=len(precs), precision10=float(np.mean(precs)) if precs else np.nan)

def value_metrics(df):
    ys, ps_ = [], []
    for c in ["cr", "ps", "hvl"] + [f"gex_{i}" for i in range(1, 11)]:
        sub = df[[f"{c}_gex", f"val_at_{c}"]].dropna()
        ys.append(sub[f"{c}_gex"].to_numpy())
        ps_.append(sub[f"val_at_{c}"].to_numpy())
    y = np.concatenate(ys); p = np.concatenate(ps_)
    ok = np.isfinite(y) & np.isfinite(p)
    y, p = y[ok], p[ok]
    r2 = 1 - np.sum((y - p) ** 2) / np.sum((y - y.mean()) ** 2)
    ratio = y[p != 0] / p[p != 0]
    q75, q25 = np.percentile(ratio, [75, 25])
    return dict(n=len(y), pooled_r2=float(r2), med_ratio=float(np.median(ratio)),
                ratio_iqr=float(q75 - q25))

# regime label: positive-gamma if spot > hvl
sp = out["spot"]
out["regime_truth"] = np.sign(sp - out["hvl"])
out["regime_pred"] = np.sign(sp - out["hvl_pred"])
out["regime_pred_cum"] = np.sign(sp - out["hvl_cum_pred"])

summary = []
for per in ("fit", "holdout"):
    df = out[out["period"] == per]
    for lvl, t, p in [("cr", "cr", "cr_pred"), ("ps", "ps", "ps_pred"),
                      ("hvl", "hvl", "hvl_pred"), ("hvl_cumB", "hvl", "hvl_cum_pred"),
                      ("cr0", "cr0", "cr0_pred"), ("ps0", "ps0", "ps0_pred"),
                      ("hvl0", "hvl0", "hvl0_pred"), ("gw0", "gw0", "gw0_pred")]:
        summary.append(dict(level=lvl, period=per, **level_metrics(df, t, p)))
    summary.append(dict(level="gex10_winner_xpred", period=per, **gex10_metrics(df, "pred")))
    summary.append(dict(level="gex10_winner_xtruth", period=per, **gex10_metrics(df, "truth")))
    summary.append(dict(level="gex10_webB_1dband", period=per, **gex10_str_metrics(df, "gexB_all")))
    summary.append(dict(level="gex10_webB_1dband_excl", period=per, **gex10_str_metrics(df, "gexB_excl")))
    summary.append(dict(level="gex_value_formula", period=per, **value_metrics(df)))
    vm = value_metrics(df[df["year"] != "2021"])
    summary.append(dict(level="gex_value_formula_ex2021", period=per, **vm))
    ok = df.dropna(subset=["regime_truth", "regime_pred"])
    summary.append(dict(level="regime_agreement", period=per, n=len(ok),
                        exact=float((ok.regime_truth == ok.regime_pred).mean())))
    okc = df.dropna(subset=["regime_truth", "regime_pred_cum"])
    summary.append(dict(level="regime_agreement_cumB", period=per, n=len(okc),
                        exact=float((okc.regime_truth == okc.regime_pred_cum).mean())))

# overall regime agreement (the headline number)
okall = out.dropna(subset=["regime_truth", "regime_pred"])
overall_regime = float((okall.regime_truth == okall.regime_pred).mean())
summary.append(dict(level="regime_agreement", period="all", n=len(okall), exact=overall_regime))

# per-year CR/PS/HVL exact + regime for the note
peryear = []
for y, df in out.groupby("year"):
    row = dict(year=y, n=len(df))
    for lvl, t, p in [("cr", "cr", "cr_pred"), ("ps", "ps", "ps_pred")]:
        row[f"{lvl}_exact"] = level_metrics(df, t, p).get("exact")
    row["hvl_medAE"] = level_metrics(df, "hvl", "hvl_pred").get("medAE")
    okd = df.dropna(subset=["regime_truth", "regime_pred"])
    row["regime_agree"] = float((okd.regime_truth == okd.regime_pred).mean())
    row["gex10_prec_xpred"] = gex10_metrics(df, "pred")["precision10"]
    peryear.append(row)

sm = pd.DataFrame(summary)
py = pd.DataFrame(peryear)
out.to_csv(D / "final_replication.csv", index=False)
sm.to_csv(D / "final_replication_summary_20260724.csv", index=False)
py.to_csv(D / "final_replication_peryear_20260724.csv", index=False)

# head-to-head file
duel = sm[sm.level.isin(["hvl", "hvl_cumB", "regime_agreement", "regime_agreement_cumB",
                         "gex10_winner_xtruth", "gex10_webB_1dband", "gex10_webB_1dband_excl"])]
duel.to_csv(D / "final_headtohead_20260724.csv", index=False)

pd.set_option("display.width", 250)
print("\n=== SUMMARY (fit = <=2023-12-31, holdout = 2024+) ===")
print(sm.to_string(index=False))
print("\n=== PER YEAR ===")
print(py.to_string(index=False))
print(f"\nOVERALL REGIME AGREEMENT: {overall_regime:.4f}  (n={len(okall)})")
print("saved:", D / "final_replication.csv")
