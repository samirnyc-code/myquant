"""S115 killer-day rule sweep — VIX family.

Rule family: VIX absolute-level skips, vix_chg spike skips, two-day VIX
acceleration, VIX vs its own 5/10-day mean (derived from data/vix_daily.csv,
prior closes only — no lookahead), and interactions with event days.

Baseline = book P&L as-is per data/options_sim/backtest_full/killer_context.csv
(ic_pnl / fly_pnl / puts_band_pnl, plus combined = sum). A rule "skips" the
whole book on flagged days; delta = -(P&L of skipped days), i.e. improvement
vs baseline. Train = 2022-2024, Test = 2025-2026. Killer day = baseline day
P&L < -1500 for that book. Verdict ROBUST only if delta > 0 in BOTH periods.

Output: data/options_sim/backtest_full/killerday/vix_results.csv
"""
import os
import pandas as pd
import numpy as np

ROOT = r"C:\Users\Admin\myquant"
CTX = os.path.join(ROOT, "data", "options_sim", "backtest_full", "killer_context.csv")
VIX = os.path.join(ROOT, "data", "vix_daily.csv")
OUTDIR = os.path.join(ROOT, "data", "options_sim", "backtest_full", "killerday")
OUT = os.path.join(OUTDIR, "vix_results.csv")

os.makedirs(OUTDIR, exist_ok=True)

ctx = pd.read_csv(CTX, parse_dates=["date"])
vix = pd.read_csv(VIX, parse_dates=["date"]).sort_values("date").reset_index(drop=True)

# ---- derive morning-knowable VIX features from vix_daily closes ----
# For trade date d, only closes strictly before d are knowable.
vix["chg"] = vix["close"].diff()
vix["mean5"] = vix["close"].rolling(5).mean()
vix["mean10"] = vix["close"].rolling(10).mean()
vix["chg_prev"] = vix["chg"].shift(1)          # change of the day before
vix["accel2"] = vix["chg"] + vix["chg_prev"]   # two-day cumulative change

# map: for each context date, use the LAST vix row with vix.date < d
feat = vix[["date", "close", "chg", "chg_prev", "accel2", "mean5", "mean10"]].copy()
feat = feat.rename(columns={c: "v_" + c for c in feat.columns if c != "date"})
ctx = pd.merge_asof(
    ctx.sort_values("date"), feat, on="date",
    direction="backward", allow_exact_matches=False,
)

# sanity: derived prior close should match the table's vix_prior
chk = ctx.dropna(subset=["vix_prior", "v_close"])
mismatch = (chk["vix_prior"] - chk["v_close"]).abs().max()
print(f"sanity: max |vix_prior - derived prior close| = {mismatch:.3f} over {len(chk)} days")

ctx["combined_pnl"] = ctx[["ic_pnl", "fly_pnl", "puts_band_pnl"]].fillna(0).sum(axis=1)
ctx["is_event"] = ctx["event"].fillna("").astype(str).str.strip().ne("")
ctx["ratio5"] = ctx["v_close"] / ctx["v_mean5"]
ctx["ratio10"] = ctx["v_close"] / ctx["v_mean10"]

TRAIN = (ctx["date"] >= "2022-01-01") & (ctx["date"] <= "2024-12-31")
TEST = (ctx["date"] >= "2025-01-01") & (ctx["date"] <= "2026-12-31")

BOOKS = {
    "ic": "ic_pnl",
    "fly": "fly_pnl",
    "puts_band": "puts_band_pnl",
    "combined": "combined_pnl",
}

# ---- rule definitions (mask True = SKIP the day) ----
c = ctx  # shorthand
RULES = [
    # absolute level buckets
    ("skip_vix>25", "Very high implied vol regime: skip when prior VIX close > 25",
     c["v_close"] > 25),
    ("skip_vix>30", "Extreme vol regime: skip when prior VIX close > 30",
     c["v_close"] > 30),
    ("skip_vix>35", "Crisis vol regime: skip when prior VIX close > 35",
     c["v_close"] > 35),
    # one-day spike
    ("skip_vixchg>2", "Fresh vol shock: skip the day after VIX rose > 2 pts",
     c["v_chg"] > 2),
    ("skip_vixchg>3", "Fresh vol shock: skip the day after VIX rose > 3 pts",
     c["v_chg"] > 3),
    ("skip_vixchg>5", "Severe vol shock: skip the day after VIX rose > 5 pts",
     c["v_chg"] > 5),
    # two-day acceleration
    ("skip_accel2d>3", "Building vol trend: skip when VIX rose > 3 pts over prior 2 days",
     c["v_accel2"] > 3),
    ("skip_accel2d>5", "Building vol trend: skip when VIX rose > 5 pts over prior 2 days",
     c["v_accel2"] > 5),
    ("skip_2day_both_up1", "Accelerating vol: skip when VIX rose > 1 pt on BOTH prior days",
     (c["v_chg"] > 1) & (c["v_chg_prev"] > 1)),
    # VIX vs own mean
    ("skip_vix/5dma>1.10", "Vol above its recent norm: skip when prior VIX > 1.10x its 5-day mean",
     c["ratio5"] > 1.10),
    ("skip_vix/5dma>1.20", "Vol sharply above norm: skip when prior VIX > 1.20x its 5-day mean",
     c["ratio5"] > 1.20),
    ("skip_vix/10dma>1.15", "Vol above its 2-week norm: skip when prior VIX > 1.15x its 10-day mean",
     c["ratio10"] > 1.15),
    ("skip_vix/10dma>1.25", "Vol sharply above 2-week norm: skip when prior VIX > 1.25x its 10-day mean",
     c["ratio10"] > 1.25),
    # interaction with event days
    ("skip_event&vixchg>2", "Macro event landing on a fresh vol shock: skip event days after VIX rose > 2 pts",
     c["is_event"] & (c["v_chg"] > 2)),
    ("skip_event&vix>25", "Macro event in a high-vol regime: skip event days when prior VIX > 25",
     c["is_event"] & (c["v_close"] > 25)),
    ("skip_event&vix/5dma>1.10", "Macro event with vol above norm: skip event days when VIX > 1.10x 5-day mean",
     c["is_event"] & (c["ratio5"] > 1.10)),
]

# random-skip benchmark: a losing book rewards ANY skip; excess = delta minus
# the expected delta of skipping the same number of days at random.
avg_daily = {}
for book, col in BOOKS.items():
    pnl = ctx[col].fillna(0)
    avg_daily[book] = (pnl[TRAIN].mean(), pnl[TEST].mean())

rows = []
for rule_name, story, mask in RULES:
    mask = mask.fillna(False)
    for book, col in BOOKS.items():
        pnl = ctx[col].fillna(0)
        killer = pnl < -1500
        train_delta = -pnl[mask & TRAIN].sum()
        test_delta = -pnl[mask & TEST].sum()
        n_train = int((mask & TRAIN).sum())
        n_test = int((mask & TEST).sum())
        train_excess = train_delta - (-avg_daily[book][0] * n_train)
        test_excess = test_delta - (-avg_daily[book][1] * n_test)
        avoided = int((mask & killer).sum())
        lost = int((mask & (pnl > 0)).sum())
        if train_delta > 0 and test_delta > 0:
            verdict = "ROBUST"
        elif train_delta > 0:
            verdict = "TRAIN_ONLY"
        else:
            verdict = "DEAD"
        rows.append({
            "rule": rule_name,
            "book": book,
            "economic_story": story,
            "n_skipped_train": n_train,
            "n_skipped_test": n_test,
            "train_delta": round(train_delta, 0),
            "test_delta": round(test_delta, 0),
            "train_excess_vs_random": round(train_excess, 0),
            "test_excess_vs_random": round(test_excess, 0),
            "killer_days_avoided": avoided,
            "winning_days_lost": lost,
            "verdict": verdict,
        })

res = pd.DataFrame(rows)
res.to_csv(OUT, index=False)
print(f"wrote {OUT} ({len(res)} rows)")

# baseline reference
for book, col in BOOKS.items():
    pnl = ctx[col].fillna(0)
    print(f"baseline {book:10s} train {pnl[TRAIN].sum():>10.0f}  test {pnl[TEST].sum():>10.0f}  "
          f"killers train {int(((pnl < -1500) & TRAIN).sum())} test {int(((pnl < -1500) & TEST).sum())}")

print()
print(res.to_string(index=False))
