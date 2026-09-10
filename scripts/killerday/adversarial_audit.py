"""S115 killer-day study — ADVERSARIAL AUDIT of claimed-ROBUST rules.

For every day-level rule claimed ROBUST in the S115 sweep, recompute the skip
mask and attack it:

  1. Random-skip null (the correct null for a losing book): Monte-Carlo
     p-value = P(skipping the same NUMBER of random days in that period gives
     a delta >= observed). Computed for train and test separately.
     A bleeding book (fly) makes ANY skip positive — this null removes that.
  2. Bonferroni: the sweep ran ~395 rule x book comparisons (credit 63,
     vix 64, gap-prior 112, event 76, cluster 64, breaker 16). Adjusted
     p = min(1, p * N_COMPARISONS).
  3. Concentration: top-1 skipped test day's share of test_delta; test_delta
     excluding the 2025-04-03..2025-04-11 tariff window; excluding top-1 day.
  4. Common-factor overlap: Jaccard of skipped test days vs the vix>25 mask
     and vs the tariff window.

Output: data/options_sim/backtest_full/killerday/adversarial_audit_20260910.csv
"""
import os
import numpy as np
import pandas as pd

ROOT = r"C:\Users\Admin\myquant"
BF = os.path.join(ROOT, "data", "options_sim", "backtest_full")
CTX = os.path.join(BF, "killer_context.csv")
VIXF = os.path.join(ROOT, "data", "vix_daily.csv")
OUT = os.path.join(BF, "killerday", "adversarial_audit_20260910.csv")

N_COMPARISONS = 395
N_MC = 5000
KILLER = -1500.0
rng = np.random.default_rng(20260910)

# ---------------------------------------------------------------- load
df = pd.read_csv(CTX, parse_dates=["date"]).sort_values("date").reset_index(drop=True)
for c in ["ic_pnl", "fly_pnl", "puts_band_pnl"]:
    df[c] = df[c].fillna(0.0)
df["combined_pnl"] = df["ic_pnl"] + df["fly_pnl"] + df["puts_band_pnl"]
df["total_cr"] = df["cr_eodic_c"] + df["cr_eodic_p"]
df["cum2"] = df["prior_ret"] + df["prior2_ret"]
df["is_event"] = df["event"].fillna("").astype(str).str.strip().ne("")
df["year"] = df["date"].dt.year

# vix features exactly as test_vix.py
vix = pd.read_csv(VIXF, parse_dates=["date"]).sort_values("date").reset_index(drop=True)
vix["chg"] = vix["close"].diff()
vix["mean5"] = vix["close"].rolling(5).mean()
vix["mean10"] = vix["close"].rolling(10).mean()
vix["chg_prev"] = vix["chg"].shift(1)
vix["accel2"] = vix["chg"] + vix["chg_prev"]
feat = vix[["date", "close", "chg", "chg_prev", "accel2", "mean5", "mean10"]].copy()
feat = feat.rename(columns={c: "v_" + c for c in feat.columns if c != "date"})
df = pd.merge_asof(df, feat, on="date", direction="backward", allow_exact_matches=False)
df["ratio5"] = df["v_close"] / df["v_mean5"]
df["ratio10"] = df["v_close"] / df["v_mean10"]

# ic / fly side legs
r = pd.read_csv(os.path.join(BF, "rows.csv"), parse_dates=["date"])
rv = r[r["method"] == "vix252"]
eodic_c = rv[rv["strat"] == "eodic_c"].groupby("date")["pnl"].sum()
ic_call_side = rv[rv["strat"].isin(["eodic_c", "openic_c"])].groupby("date")["pnl"].sum()
fr = pd.read_csv(os.path.join(BF, "fly_rows.csv"), parse_dates=["date"], on_bad_lines="skip")
fly_call_side = fr[fr["strat"].isin(["eodfly_c", "openfly_c"])].groupby("date")["pnl"].sum()
df["eodic_c_pnl"] = eodic_c.reindex(df["date"]).fillna(0.0).values
df["ic_call_pnl"] = ic_call_side.reindex(df["date"]).fillna(0.0).values
df["fly_call_pnl"] = fly_call_side.reindex(df["date"]).fillna(0.0).values

TRAIN = df["year"].between(2022, 2024).values
TEST = df["year"].between(2025, 2026).values
APRIL = df["date"].between("2025-04-03", "2025-04-11").values
VIX25 = (df["v_close"] > 25).fillna(False).values

BOOKS = {"ic": "ic_pnl", "fly": "fly_pnl", "puts_band": "puts_band_pnl",
         "combined": "combined_pnl"}


def nn(s):
    return s.fillna(False).values if hasattr(s, "fillna") else s


# ---------------------------------------------------------------- cluster sims
def sim_loss_standdown(pnl, X, N):
    skip = np.zeros(len(pnl), dtype=bool)
    cooldown = 0
    for i in range(len(pnl)):
        if cooldown > 0:
            skip[i] = True
            cooldown -= 1
            continue
        if pnl[i] < X:
            cooldown = N
    return skip


def sim_loss_reentry(pnl, vix_chg, X, cap=5):
    skip = np.zeros(len(pnl), dtype=bool)
    standing = False
    days_out = 0
    for i in range(len(pnl)):
        if standing:
            if vix_chg[i - 1] < 0 or days_out >= cap:
                standing = False
            else:
                skip[i] = True
                days_out += 1
                continue
        if not standing:
            if pnl[i] < X:
                standing = True
                days_out = 0
    return skip


def sim_cluster2(pnl, X=-500.0):
    skip = np.zeros(len(pnl), dtype=bool)
    hist = []
    for i in range(len(pnl)):
        if len(hist) >= 2 and hist[-1] < X and hist[-2] < X:
            skip[i] = True
            hist.clear()
            continue
        hist.append(pnl[i])
    return skip


vchg_ctx = df["vix_chg"].fillna(0.0).values

# ---------------------------------------------------------------- rule table
# (rule, book, mask, removed_pnl_col)  removed_pnl_col=None -> whole book day
R = []


def add(rule, books, mask, removed=None):
    for b in books:
        R.append((rule, b, nn(mask), removed))


# --- CREDIT family
for t in (2.0, 2.5, 3.0):
    add(f"skip_day_if_cr_c>{t}", ["ic", "fly"], df["cr_eodic_c"] > t)
    add(f"ic_drop_call_leg_if_cr_c>{t}", ["ic"], df["cr_eodic_c"] > t, "eodic_c_pnl")
add("skip_day_if_cr_c>4.0", ["fly", "puts_band"], df["cr_eodic_c"] > 4.0)
for t in (2.0, 2.5, 3.0, 4.0):
    add(f"skip_day_if_cr_p>{t}", ["fly"], df["cr_eodic_p"] > t)
add("skip_day_if_total_cr>3.0", ["ic", "fly", "combined"], df["total_cr"] > 3.0)
for t in (4.0, 5.0, 6.0):
    add(f"skip_day_if_total_cr>{t}", ["fly", "combined"], df["total_cr"] > t)
add("band_p_0.5-2.5", ["ic", "fly"], (df["cr_eodic_p"] < 0.5) | (df["cr_eodic_p"] > 2.5))
add("band_c_0.5-2.5", ["fly"], (df["cr_eodic_c"] < 0.5) | (df["cr_eodic_c"] > 2.5))
add("skip_day_if_cr_p<0.5", ["ic", "fly", "puts_band"], df["cr_eodic_p"] < 0.5)
add("skip_day_if_cr_c<0.5", ["fly"], df["cr_eodic_c"] < 0.5)
add("skip_day_if_total_cr<1.0", ["ic", "fly", "puts_band"], df["total_cr"] < 1.0)

# --- GAP-PRIOR family
g = df["gap_pct"]
add("|gap|>=1.0", ["ic", "combined"], g.abs() >= 1.0)
add("|gap|>=0.75", ["ic", "combined"], g.abs() >= 0.75)
add("|gap|>=0.5", ["combined"], g.abs() >= 0.5)
add("|gap|>=0.3", ["fly"], g.abs() >= 0.3)
add("gap<=-1.0", ["ic"], g <= -1.0)
add("gap<=-0.5", ["combined"], g <= -0.5)
add("|prior_ret|>=1.0", ["fly"], df["prior_ret"].abs() >= 1.0)
add("|prior_ret|>=1.5", ["combined"], df["prior_ret"].abs() >= 1.5)
add("prior_ret<=-1.0", ["fly"], df["prior_ret"] <= -1.0)
add("prior_ret<=-1.5", ["combined"], df["prior_ret"] <= -1.5)
add("prior_range>=2.0", ["combined"], df["prior_range"] >= 2.0)
add("prior_range>=4.0", ["puts_band", "combined"], df["prior_range"] >= 4.0)
add("|cum2day|>=2.0", ["combined"], df["cum2"].abs() >= 2.0)
add("|cum2day|>=3.0", ["combined"], df["cum2"].abs() >= 3.0)
add("|gap|>=0.5&vixchg>=2", ["combined"], (g.abs() >= 0.5) & (df["vix_chg"] >= 2))
add("gap<=-0.5&vixchg>=2", ["combined"], (g <= -0.5) & (df["vix_chg"] >= 2))
add("prior_range>=3&|gap|>=0.3", ["combined"], (df["prior_range"] >= 3) & (g.abs() >= 0.3))

# --- VIX family
add("skip_vix>25", ["ic", "fly", "combined"], df["v_close"] > 25)
add("skip_vix>30", ["ic", "fly", "combined"], df["v_close"] > 30)
add("skip_vixchg>2", ["ic", "fly", "combined"], df["v_chg"] > 2)
add("skip_vixchg>3", ["fly", "combined"], df["v_chg"] > 3)
add("skip_accel2d>3", ["ic", "fly", "combined"], df["v_accel2"] > 3)
add("skip_accel2d>5", ["ic", "fly", "combined"], df["v_accel2"] > 5)
add("skip_2day_both_up1", ["fly", "combined"], (df["v_chg"] > 1) & (df["v_chg_prev"] > 1))
add("skip_vix/5dma>1.10", ["ic", "fly", "combined"], df["ratio5"] > 1.10)
add("skip_vix/5dma>1.20", ["ic", "fly", "combined"], df["ratio5"] > 1.20)
add("skip_vix/10dma>1.15", ["ic", "fly", "combined"], df["ratio10"] > 1.15)
add("skip_vix/10dma>1.25", ["ic", "fly", "combined"], df["ratio10"] > 1.25)
add("skip_event&vixchg>2", ["fly", "combined"], df["is_event"] & (df["v_chg"] > 2))
add("skip_event&vix>25", ["ic", "fly", "combined"], df["is_event"] & (df["v_close"] > 25))
add("skip_event&vix/5dma>1.10", ["fly", "combined"], df["is_event"] & (df["ratio5"] > 1.10))

# --- EVENT family
ev = df["event"].fillna("").astype(str)
add("skip_FOMC", ["ic", "fly", "combined"], ev.str.contains("FOMC"))
add("skip_CPI", ["fly"], ev.str.contains("CPI"))
add("skip_NFP", ["ic", "fly", "combined"], ev.str.contains("NFP"))
add("skip_ANY_EVENT", ["ic", "fly", "combined"], df["is_event"])
add("skip_callside_CPI", ["fly"], ev.str.contains("CPI"), "fly_call_pnl")
df["allcall_pnl"] = df["ic_call_pnl"] + df["fly_call_pnl"]
add("skip_callside_CPI", ["combined"], ev.str.contains("CPI"), "allcall_pnl")
for e in ("FOMC", "CPI", "NFP"):
    add(f"skip_flies_{e}", ["combined"], ev.str.contains(e), "fly_pnl")
add("skip_flies_ANY_EVENT", ["combined"], df["is_event"], "fly_pnl")
for T in (2, 3, 4, 5, 6):
    add(f"skip_event_if_credit_above_{T}", ["ic", "fly", "combined"],
        df["is_event"] & (df["total_cr"] > T))
    add(f"skip_event_if_credit_below_{T}", ["ic", "fly", "combined"],
        df["is_event"] & (df["total_cr"] < T))

# --- CLUSTER family
for b in ("ic", "fly", "combined"):
    p = df[BOOKS[b]].values
    for X in (-1000, -1500, -2000):
        for N in (1, 2):
            add(f"loss<{X}_stand{N}d", [b], sim_loss_standdown(p, X, N))
        add(f"loss<{X}_until_vixdown", [b], sim_loss_reentry(p, vchg_ctx, X))
    add("cluster_2x_loss<-500", [b], sim_cluster2(p))
add("vixprior>25_standdown", ["ic", "fly", "combined"], df["vix_prior"] > 25)
add("vixprior>30_standdown", ["ic", "fly", "combined"], df["vix_prior"] > 30)

# ---------------------------------------------------------------- evaluate
rows = []
for rule, book, mask, removed in R:
    col = removed if removed else BOOKS[book]
    pnl = df[col].values
    d_train = -pnl[mask & TRAIN].sum()
    d_test = -pnl[mask & TEST].sum()
    n_tr = int((mask & TRAIN).sum())
    n_te = int((mask & TEST).sum())

    # MC null: skip same number of random days in each period
    def mc_p(period, n, obs):
        if n == 0:
            return np.nan
        pool = pnl[period]
        n = min(n, len(pool))
        # per-draw sampling WITHOUT replacement, vectorized
        idx = np.random.default_rng(hash((rule, book, n)) % 2**32).random(
            (N_MC, len(pool))).argpartition(n - 1, axis=1)[:, :n]
        draws = pool[idx].sum(axis=1)
        return float(np.mean(-draws >= obs))

    p_tr = mc_p(TRAIN, n_tr, d_train)
    p_te = mc_p(TEST, n_te, d_test)
    # joint (Fisher approx) then Bonferroni over all comparisons in sweep
    if np.isnan(p_tr) or np.isnan(p_te):
        p_joint = p_te if not np.isnan(p_te) else p_tr
    else:
        from scipy import stats as _st
        chi = -2 * (np.log(max(p_tr, 1e-6)) + np.log(max(p_te, 1e-6)))
        p_joint = float(_st.chi2.sf(chi, 4))
    p_bonf = min(1.0, p_joint * N_COMPARISONS) if not np.isnan(p_joint) else np.nan

    # concentration in TEST
    sk_te = pnl[mask & TEST]
    if len(sk_te) and d_test > 0:
        top1 = -sk_te.min() if sk_te.min() < 0 else 0.0
        top1_share = top1 / d_test
    else:
        top1, top1_share = 0.0, np.nan
    d_test_ex_april = -pnl[mask & TEST & ~APRIL].sum()
    if len(sk_te):
        ex1 = sk_te[sk_te != sk_te.min()] if len(sk_te) > 1 else np.array([])
        d_test_ex_top1 = -ex1.sum()
    else:
        d_test_ex_top1 = np.nan
    n_april = int((mask & TEST & APRIL).sum())

    # overlap with vix>25 in test
    both = int((mask & TEST & VIX25).sum())
    either = int(((mask | VIX25) & TEST).sum())
    jac_vix = both / either if either else np.nan

    rows.append(dict(rule=rule, book=book, removed=removed or "day",
                     n_train=n_tr, n_test=n_te,
                     train_delta=round(d_train), test_delta=round(d_test),
                     p_train=p_tr, p_test=p_te, p_joint=p_joint, p_bonf=p_bonf,
                     top1_share_test=None if np.isnan(top1_share) else round(top1_share, 3),
                     test_ex_april=round(d_test_ex_april),
                     test_ex_top1=None if np.isnan(d_test_ex_top1) else round(d_test_ex_top1),
                     n_april_skips=n_april, jaccard_vix25_test=round(jac_vix, 3) if either else "",
                     ))

res = pd.DataFrame(rows)
res.to_csv(OUT, index=False)
print(f"wrote {OUT} ({len(res)} rules)")
print(f"baselines: " + ", ".join(f"{b} train={df.loc[TRAIN, c].sum():.0f} test={df.loc[TEST, c].sum():.0f}"
                                  for b, c in BOOKS.items()))
print(f"test days={TEST.sum()} train days={TRAIN.sum()} april days={APRIL.sum()}")
kd = {b: int((df[c] < KILLER).sum()) for b, c in BOOKS.items()}
print("killer<-1500 days per book:", kd)
# summary buckets
res["surv"] = (res["p_bonf"] < 0.05).map({True: "SURVIVES_BONF", False: "FAILS_BONF"})
print(res.groupby("surv").size())
with pd.option_context("display.width", 250, "display.max_rows", 300):
    print(res.sort_values("p_joint").to_string(index=False))
