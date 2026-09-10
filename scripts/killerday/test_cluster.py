"""
S115 killer-day study — DAY-AFTER / CLUSTER stand-down rules.

Rule family (all morning-knowable, no lookahead):
  A. loss_standdown(X, N): after a traded day with book P&L < X, stand down the
     next N sessions. X in {-1000, -1500, -2000}, N in {1, 2, 3}.
     Trigger fires only on days actually traded (a skipped day has no P&L).
  B. vix_standdown(T): skip day t if prior-day VIX close (vix_prior) > T,
     T in {25, 30, 35}. Auto re-entry when VIX recedes below T.
  C. loss_reentry(X): after a traded loss < X, stand down until the first
     morning where prior-day VIX change (vix_chg) < 0 ("VIX receded"),
     capped at 5 sessions. Early re-entry version of A.
  D. cluster2(-500): skip day t if the last two traded days BOTH lost < -500
     (consecutive-loss cluster).

Baseline = book P&L as-is from killer_context.csv (ic_pnl / fly_pnl /
puts_band_pnl; combined = sum). NaN book P&L = no trade = 0.

Metrics per rule x book:
  train_delta  = rule P&L - baseline P&L, 2022-2024
  test_delta   = same, 2025-2026
  killer_avoided = skipped days with baseline P&L < -1500 (full period)
  winners_lost   = skipped days with baseline P&L > 0 (full period)
  skipped_pnl_sum = total baseline P&L forfeited on skipped days (= -total delta)
  dayafter_killer_avg = avg baseline P&L on the session right after a killer
     day (<-1500) — the "recovery day" this family gives up (diagnostic,
     rule-independent per book).

Output: data/options_sim/backtest_full/killerday/cluster_results.csv
"""
import pandas as pd
import numpy as np
from pathlib import Path

ROOT = Path(r"C:\Users\Admin\myquant")
CTX = ROOT / "data/options_sim/backtest_full/killer_context.csv"
OUT = ROOT / "data/options_sim/backtest_full/killerday/cluster_results.csv"
OUT_SKIP = ROOT / "data/options_sim/backtest_full/killerday/cluster_skipped_days.csv"

KILLER = -1500.0
TRAIN_END = pd.Timestamp("2024-12-31")

df = pd.read_csv(CTX, parse_dates=["date"]).sort_values("date").reset_index(drop=True)
for c in ["ic_pnl", "fly_pnl", "puts_band_pnl"]:
    df[c] = df[c].fillna(0.0)
df["combined_pnl"] = df["ic_pnl"] + df["fly_pnl"] + df["puts_band_pnl"]
df["vix_chg"] = df["vix_chg"].fillna(0.0)
df["is_train"] = df["date"] <= TRAIN_END

BOOKS = {
    "ic": "ic_pnl",
    "fly": "fly_pnl",
    "puts_band": "puts_band_pnl",
    "combined": "combined_pnl",
}


def sim_loss_standdown(pnl, X, N):
    """Skip flags: after a TRADED day with pnl < X, skip next N days."""
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


def sim_vix_standdown(vix_prior, T):
    return (vix_prior > T).fillna(False).values


def sim_loss_reentry(pnl, vix_chg, X, cap=5):
    """After traded loss < X, stand down until prior-day VIX change < 0, cap sessions."""
    skip = np.zeros(len(pnl), dtype=bool)
    standing = False
    days_out = 0
    for i in range(len(pnl)):
        if standing:
            # morning of day i: re-enter if yesterday's VIX fell, or cap hit
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
    """Skip ONE day after two consecutive traded losses < X, then resume."""
    skip = np.zeros(len(pnl), dtype=bool)
    traded_hist = []  # pnl of traded days
    for i in range(len(pnl)):
        if len(traded_hist) >= 2 and traded_hist[-1] < X and traded_hist[-2] < X:
            skip[i] = True
            traded_hist.clear()  # cooldown consumed; resume next day
            continue
        traded_hist.append(pnl[i])
    return skip


def evaluate(rule_name, book, skip, sub_rows):
    pnl = df[BOOKS[book]].values
    skipped = df[skip]
    d_train = -skipped.loc[skipped["is_train"], BOOKS[book]].sum()
    d_test = -skipped.loc[~skipped["is_train"], BOOKS[book]].sum()
    killers = int((skipped[BOOKS[book]] < KILLER).sum())
    winners = int((skipped[BOOKS[book]] > 0).sum())
    n_skip = int(skip.sum())
    if d_train > 0 and d_test > 0:
        verdict = "ROBUST_CANDIDATE"  # economic story assessed in report
    elif d_train > 0:
        verdict = "TRAIN_ONLY"
    else:
        verdict = "DEAD"
    for _, r in skipped.iterrows():
        sub_rows.append({"rule": rule_name, "book": book, "date": r["date"].date(),
                         "baseline_pnl": r[BOOKS[book]], "vix_prior": r["vix_prior"],
                         "next_ret": r["next_ret"]})
    allday_avg = float(df[BOOKS[book]].mean())
    avg_skip = float(skipped[BOOKS[book]].mean()) if n_skip else np.nan
    winners_pnl = float(skipped.loc[skipped[BOOKS[book]] > 0, BOOKS[book]].sum())
    return {
        "rule": rule_name, "book": book, "n_skipped": n_skip,
        "train_delta": round(float(d_train), 1), "test_delta": round(float(d_test), 1),
        "total_delta": round(float(d_train + d_test), 1),
        "killer_days_avoided": killers, "winning_days_lost": winners,
        "winners_pnl_forfeited": round(winners_pnl, 1),
        "skipped_pnl_sum": round(float(skipped[BOOKS[book]].sum()), 1),
        "avg_skipped_pnl": round(avg_skip, 1) if n_skip else np.nan,
        "allday_avg_pnl": round(allday_avg, 1),
        "selectivity": round(avg_skip - allday_avg, 1) if n_skip else np.nan,
        "verdict": verdict,
    }


results = []
skiprows = []
for book, col in BOOKS.items():
    pnl = df[col].values
    # A. loss stand-down sweep
    for X in (-1000.0, -1500.0, -2000.0):
        for N in (1, 2, 3):
            skip = sim_loss_standdown(pnl, X, N)
            results.append(evaluate(f"loss<{int(X)}_stand{N}d", book, skip, skiprows))
    # B. VIX threshold
    for T in (25.0, 30.0, 35.0):
        skip = sim_vix_standdown(df["vix_prior"], T)
        results.append(evaluate(f"vixprior>{int(T)}_standdown", book, skip, skiprows))
    # C. loss + VIX-recede re-entry
    for X in (-1000.0, -1500.0, -2000.0):
        skip = sim_loss_reentry(pnl, df["vix_chg"].values, X)
        results.append(evaluate(f"loss<{int(X)}_until_vixdown", book, skip, skiprows))
    # D. consecutive-loss cluster
    skip = sim_cluster2(pnl)
    results.append(evaluate("cluster_2x_loss<-500", book, skip, skiprows))

res = pd.DataFrame(results)

# ---- recovery diagnostic: what does the day AFTER a killer look like? ----
diag = []
for book, col in BOOKS.items():
    killer_mask = df[col] < KILLER
    idx_after = np.flatnonzero(killer_mask.values) + 1
    idx_after = idx_after[idx_after < len(df)]
    after = df.iloc[idx_after]
    diag.append({
        "book": book,
        "n_killer_days": int(killer_mask.sum()),
        "dayafter_avg_pnl": round(float(after[col].mean()), 1) if len(after) else np.nan,
        "dayafter_win_rate": round(float((after[col] > 0).mean()), 3) if len(after) else np.nan,
        "dayafter_sum_pnl": round(float(after[col].sum()), 1) if len(after) else np.nan,
        "dayafter_avg_next_ret_abs": round(float(after["next_ret"].abs().mean()), 2) if len(after) else np.nan,
        "allday_avg_pnl": round(float(df[col].mean()), 1),
    })
diag_df = pd.DataFrame(diag)

OUT.parent.mkdir(parents=True, exist_ok=True)
res.to_csv(OUT, index=False)
pd.DataFrame(skiprows).to_csv(OUT_SKIP, index=False)
diag_path = OUT.parent / "cluster_dayafter_diag.csv"
diag_df.to_csv(diag_path, index=False)

pd.set_option("display.width", 250)
print(f"rows: {len(df)}  {df['date'].min().date()} -> {df['date'].max().date()}")
print(f"train days: {int(df['is_train'].sum())}  test days: {int((~df['is_train']).sum())}")
print("\n=== DAY-AFTER-KILLER DIAGNOSTIC (what stand-down gives up) ===")
print(diag_df.to_string(index=False))
print("\n=== FULL SWEEP ===")
print(res.to_string(index=False))
print(f"\nsaved: {OUT}\nsaved: {OUT_SKIP}\nsaved: {diag_path}")
