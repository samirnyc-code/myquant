"""
S115 killer-day rule sweep — OVERNIGHT GAP + PRIOR-DAY family.

Baseline: book P&L as-is from data/options_sim/backtest_full/killer_context.csv
(day columns ic_pnl / fly_pnl / puts_band_pnl; combined = sum of the three).

Rules tested (all morning-knowable, no lookahead):
  - |gap_pct| >= T           for T in 0.3 / 0.5 / 0.75 / 1.0
  - gap_pct <= -T            (down-gap only) same thresholds
  - |prior_ret| >= T         for T in 1.0 / 1.5 / 2.0 / 3.0
  - prior_ret <= -T          (prior-day crash only) same thresholds
  - prior_range >= T         for T in 2.0 / 3.0 / 4.0 / 5.0
  - |prior_ret + prior2_ret| >= T   for T in 2.0 / 3.0 / 4.0
  - combos: |gap|>=0.5 & vix_chg>0 ; |gap|>=0.5 & vix_chg>=2 ;
            gap<=-0.5 & vix_chg>=2 ; prior_range>=3 & |gap|>=0.3 ;
            prior_range>=4 & vix_chg>=0

Metrics per rule x book:
  train delta (2022-2024), test delta (2025-2026)  [delta = -sum(pnl on skipped days)]
  killer days avoided (skipped days with baseline pnl < -1500)
  winning days lost (skipped days with baseline pnl > 0)
  avoids 2025-04-09 flag
Verdict: ROBUST if train>0 AND test>0; TRAIN_ONLY if train>0>=test; DEAD otherwise.

Output: data/options_sim/backtest_full/killerday/gap-prior_results.csv
"""
import os
import pandas as pd
import numpy as np

ROOT = r"C:\Users\Admin\myquant"
CTX = os.path.join(ROOT, "data", "options_sim", "backtest_full", "killer_context.csv")
OUTDIR = os.path.join(ROOT, "data", "options_sim", "backtest_full", "killerday")
OUT = os.path.join(OUTDIR, "gap-prior_results.csv")
os.makedirs(OUTDIR, exist_ok=True)

df = pd.read_csv(CTX, parse_dates=["date"])
df["combined_pnl"] = df[["ic_pnl", "fly_pnl", "puts_band_pnl"]].sum(axis=1, min_count=1)
df["cum2"] = df["prior_ret"] + df["prior2_ret"]
df["year"] = df["date"].dt.year
train_mask = df["year"].between(2022, 2024)
test_mask = df["year"].between(2025, 2026)

BOOKS = {"ic": "ic_pnl", "fly": "fly_pnl", "puts_band": "puts_band_pnl",
         "combined": "combined_pnl"}

TARGET = pd.Timestamp("2025-04-09")


def cond_notna(series_cond):
    """Missing inputs -> no skip (trade as normal)."""
    return series_cond.fillna(False)


rules = []
for t in [0.3, 0.5, 0.75, 1.0]:
    rules.append((f"|gap|>={t}", cond_notna(df["gap_pct"].abs() >= t),
                  "large overnight gap = strikes set on stale info + elevated open vol"))
    rules.append((f"gap<=-{t}", cond_notna(df["gap_pct"] <= -t),
                  "down-gaps carry follow-through/vol risk that short-premium eats"))
for t in [1.0, 1.5, 2.0, 3.0]:
    rules.append((f"|prior_ret|>={t}", cond_notna(df["prior_ret"].abs() >= t),
                  "big prior-day move = elevated realized vol regime next day"))
    rules.append((f"prior_ret<=-{t}", cond_notna(df["prior_ret"] <= -t),
                  "prior-day crash = next-day vol-of-vol and gap risk"))
for t in [2.0, 3.0, 4.0, 5.0]:
    rules.append((f"prior_range>={t}", cond_notna(df["prior_range"] >= t),
                  "wide prior-day range = realized vol already exceeding EM pricing"))
for t in [2.0, 3.0, 4.0]:
    rules.append((f"|cum2day|>={t}", cond_notna(df["cum2"].abs() >= t),
                  "2-day trend move = market in motion, mean-reversion premium bets lose"))
rules.append(("|gap|>=0.5&vixchg>0",
              cond_notna((df["gap_pct"].abs() >= 0.5) & (df["vix_chg"] > 0)),
              "gap with rising VIX = fear-confirmed gap, not a fade"))
rules.append(("|gap|>=0.5&vixchg>=2",
              cond_notna((df["gap_pct"].abs() >= 0.5) & (df["vix_chg"] >= 2)),
              "gap with VIX spike = vol regime shift overnight"))
rules.append(("gap<=-0.5&vixchg>=2",
              cond_notna((df["gap_pct"] <= -0.5) & (df["vix_chg"] >= 2)),
              "down-gap with VIX spike = crash continuation risk"))
rules.append(("prior_range>=3&|gap|>=0.3",
              cond_notna((df["prior_range"] >= 3) & (df["gap_pct"].abs() >= 0.3)),
              "wide prior range AND gapping again = vol not settling"))
rules.append(("prior_range>=4&vixchg>=0",
              cond_notna((df["prior_range"] >= 4) & (df["vix_chg"] >= 0)),
              "huge prior range with VIX not falling = still in the storm"))

recs = []
for rule_name, skip, story in rules:
    avoids_target = bool(skip[df["date"] == TARGET].any())
    for book, col in BOOKS.items():
        pnl = df[col]
        traded = pnl.notna()
        sk = skip & traded
        train_delta = -pnl[sk & train_mask].sum()
        test_delta = -pnl[sk & test_mask].sum()
        killers = int(((pnl < -1500) & sk).sum())
        winners_lost = int(((pnl > 0) & sk).sum())
        days_skipped = int(sk.sum())
        base_train = pnl[train_mask].sum()
        base_test = pnl[test_mask].sum()
        if train_delta > 0 and test_delta > 0:
            verdict = "ROBUST"
        elif train_delta > 0:
            verdict = "TRAIN_ONLY"
        else:
            verdict = "DEAD"
        recs.append({
            "rule": rule_name, "book": book, "story": story,
            "days_skipped": days_skipped,
            "train_delta": round(train_delta, 0),
            "test_delta": round(test_delta, 0),
            "total_delta": round(train_delta + test_delta, 0),
            "killer_days_avoided": killers,
            "winning_days_lost": winners_lost,
            "avoids_2025_04_09": avoids_target,
            "baseline_train": round(base_train, 0),
            "baseline_test": round(base_test, 0),
            "verdict": verdict,
        })

res = pd.DataFrame(recs)
res.to_csv(OUT, index=False)

# console report
pd.set_option("display.width", 250)
pd.set_option("display.max_rows", 300)
print(f"days total={len(df)} train={train_mask.sum()} test={test_mask.sum()}")
print("baselines (train/test):")
for book, col in BOOKS.items():
    print(f"  {book:10s} {df[col][train_mask].sum():>10.0f} {df[col][test_mask].sum():>10.0f}")
print()
print(res[["rule", "book", "days_skipped", "train_delta", "test_delta",
           "killer_days_avoided", "winning_days_lost", "avoids_2025_04_09",
           "verdict"]].to_string(index=False))
print()
print("ROBUST rules:")
rob = res[res["verdict"] == "ROBUST"].sort_values("total_delta", ascending=False)
print(rob[["rule", "book", "train_delta", "test_delta", "killer_days_avoided",
           "winning_days_lost", "avoids_2025_04_09"]].to_string(index=False))
print(f"\nsaved -> {OUT}")
