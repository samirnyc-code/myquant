"""S115 killer-day study — CREDIT-RICHNESS rule family.

Premise (S114): rich morning credit = the market pricing risk the EM missed.
Tests, per book (ic / fly / puts_band / combined):
  - skip day when cr_eodic_c > thr           (thr sweep 2.0/2.5/3.0/4.0)
  - skip day when cr_eodic_p > thr           (thr sweep 2.0/2.5/3.0/4.0)
  - skip day when total credit c+p > thr     (thr sweep 3.0/4.0/5.0/6.0)
  - puts band: trade only when 0.5 <= cr_p <= 2.5 (skip outside)
  - call band: trade only when 0.5 <= cr_c <= 2.5 (skip outside)
  - credit FLOORS: skip when cr_c < 0.5 / cr_p < 0.5 / total < 1.0
  - IC side-level: drop only the call side when cr_c > thr; drop only the put
    side when cr_p > thr (per-trade rows, method==vix252). Two variants:
    eodic leg only, and the full side (eodic + openic legs).

NOTE (verified): killer_context.ic_pnl == sum of ALL FOUR vix252 legs per day
(eodic_c + eodic_p + openic_c + openic_p), max abs diff 0.48 (rounding).

Method:
  - baseline = book P&L as-is from killer_context.csv day columns
    (ic_pnl / fly_pnl / puts_band_pnl); IC side legs from rows.csv vix252.
  - delta = P&L improvement vs baseline = -(sum of skipped P&L).
  - train = 2022-2024, test = 2025-2026.
  - killer days avoided = flagged days with book baseline < -1500 (full period).
  - winning days lost   = flagged days with book baseline > 0    (full period).
  - NaN credit -> rule cannot fire (no lookahead, no assumption): keep the day.
  - verdict: ROBUST if delta>0 in BOTH periods; TRAIN_ONLY if train>0 only; else DEAD.

Output: data/options_sim/backtest_full/killerday/credit_results.csv
"""
import os
import numpy as np
import pandas as pd

ROOT = r"C:\Users\Admin\myquant"
CTX = os.path.join(ROOT, "data", "options_sim", "backtest_full", "killer_context.csv")
ROWS = os.path.join(ROOT, "data", "options_sim", "backtest_full", "rows.csv")
OUTDIR = os.path.join(ROOT, "data", "options_sim", "backtest_full", "killerday")
OUT = os.path.join(OUTDIR, "credit_results.csv")

KILLER = -1500.0
SPLIT = pd.Timestamp("2025-01-01")


def main():
    os.makedirs(OUTDIR, exist_ok=True)
    df = pd.read_csv(CTX, parse_dates=["date"]).sort_values("date").reset_index(drop=True)
    df["total_cr"] = df["cr_eodic_c"] + df["cr_eodic_p"]  # NaN if either side missing
    df["combined_pnl"] = df["ic_pnl"] + df["fly_pnl"] + df["puts_band_pnl"]

    # --- IC side legs from per-trade rows (method==vix252) -------------------
    r = pd.read_csv(ROWS, parse_dates=["date"])
    rv = r[r["method"] == "vix252"]
    piv = rv.pivot_table(index="date", columns="strat", values="pnl", aggfunc="sum")
    df = df.merge(piv.rename(columns={"eodic_c": "ic_c_pnl", "eodic_p": "ic_p_pnl"}),
                  left_on="date", right_index=True, how="left")
    for c in ("ic_c_pnl", "ic_p_pnl"):
        if c not in df:
            df[c] = np.nan
        df[c] = df[c].fillna(0.0)

    # sanity: side decomposition vs day column
    side_diff = (df["ic_c_pnl"] + df["ic_p_pnl"] - df["ic_pnl"]).abs().max()
    print(f"[check] ic sides vs ic_pnl max abs diff: {side_diff:.2f}")
    print(f"[check] dates {df.date.min().date()}..{df.date.max().date()} n={len(df)} "
          f"train={(df.date < SPLIT).sum()} test={(df.date >= SPLIT).sum()}")
    print(f"[check] NaN credits: c={df.cr_eodic_c.isna().sum()} p={df.cr_eodic_p.isna().sum()} "
          f"total={df.total_cr.isna().sum()}")
    for b in ("ic_pnl", "fly_pnl", "puts_band_pnl", "combined_pnl"):
        print(f"[check] {b}: sum={df[b].sum():.0f} killers<-1500={(df[b] < KILLER).sum()}")

    train = df["date"] < SPLIT
    test = ~train

    BOOKS = {"ic": "ic_pnl", "fly": "fly_pnl", "puts_band": "puts_band_pnl",
             "combined": "combined_pnl"}

    results = []

    def add(rule, book, mask, pnl_col=None, story=""):
        """mask True = skip (drop the flagged P&L). pnl_col = P&L removed by the
        rule (defaults to the book day column). Killer/winner counts use the
        BOOK day baseline."""
        base_col = BOOKS[book]
        rm = pnl_col if pnl_col is not None else base_col
        m = mask.fillna(False)
        tr_delta = -df.loc[m & train, rm].sum()
        te_delta = -df.loc[m & test, rm].sum()
        killers = int((m & (df[base_col] < KILLER)).sum())
        winners = int((m & (df[base_col] > 0)).sum())
        if tr_delta > 0 and te_delta > 0:
            verdict = "ROBUST"
        elif tr_delta > 0:
            verdict = "TRAIN_ONLY"
        else:
            verdict = "DEAD"
        results.append(dict(rule=rule, book=book,
                            train_delta=round(float(tr_delta), 0),
                            test_delta=round(float(te_delta), 0),
                            days_flagged=int(m.sum()),
                            days_flagged_train=int((m & train).sum()),
                            days_flagged_test=int((m & test).sum()),
                            killer_days_avoided=killers,
                            winning_days_lost=winners,
                            verdict=verdict, economic_story=story))

    cr_c, cr_p, tot = df["cr_eodic_c"], df["cr_eodic_p"], df["total_cr"]

    # A/B: single-side richness thresholds, day-level, per book -------------
    for thr in (2.0, 2.5, 3.0, 4.0):
        for book in ("ic", "fly", "puts_band"):
            add(f"skip_day_if_cr_c>{thr}", book, cr_c > thr,
                story=f"Rich call credit (> {thr}) = market pricing upside risk the EM missed; stand down.")
            add(f"skip_day_if_cr_p>{thr}", book, cr_p > thr,
                story=f"Rich put credit (> {thr}) = market pricing downside risk the EM missed; stand down.")

    # C: TOTAL morning credit as danger score -------------------------------
    for thr in (3.0, 4.0, 5.0, 6.0):
        for book in ("ic", "fly", "puts_band", "combined"):
            add(f"skip_day_if_total_cr>{thr}", book, tot > thr,
                story=f"Total morning credit c+p > {thr} = both wings bid, market braced for a move the EM missed.")

    # D/E: bands (trade only inside 0.5-2.5; skip outside incl. NaN=no-fire kept) --
    band_p_out = (cr_p < 0.5) | (cr_p > 2.5)
    band_c_out = (cr_c < 0.5) | (cr_c > 2.5)
    for book in ("ic", "fly", "puts_band"):
        add("band_p_0.5-2.5", book, band_p_out,
            story="Put credit inside 0.5-2.5 = normal premium; below = no edge, above = market pricing a down move.")
        add("band_c_0.5-2.5", book, band_c_out,
            story="Call credit inside 0.5-2.5 = normal premium; below = no edge, above = market pricing an up move.")

    # F: LOW-end floors ------------------------------------------------------
    for book in ("ic", "fly", "puts_band"):
        add("skip_day_if_cr_c<0.5", book, cr_c < 0.5,
            story="Thin call credit < 0.5 = no premium to harvest; risk/reward not there.")
        add("skip_day_if_cr_p<0.5", book, cr_p < 0.5,
            story="Thin put credit < 0.5 = no premium to harvest; risk/reward not there.")
        add("skip_day_if_total_cr<1.0", book, tot < 1.0,
            story="Total credit < 1.0 = dead tape, nothing to sell; commissions eat the edge.")

    # G: IC side-level — drop only the rich leg -----------------------------
    for thr in (2.0, 2.5, 3.0, 4.0):
        add(f"ic_drop_call_leg_if_cr_c>{thr}", "ic", cr_c > thr, pnl_col="ic_c_pnl",
            story=f"Drop only the call spread when its credit > {thr}: sell the normal side, skip the side the market says is in play.")
        add(f"ic_drop_put_leg_if_cr_p>{thr}", "ic", cr_p > thr, pnl_col="ic_p_pnl",
            story=f"Drop only the put spread when its credit > {thr}: sell the normal side, skip the side the market says is in play.")

    out = pd.DataFrame(results)
    out.to_csv(OUT, index=False)
    print(f"\nsaved {len(out)} rules -> {OUT}\n")
    with pd.option_context("display.width", 250, "display.max_rows", 250):
        print(out.to_string(index=False))

    # baseline period P&L for reference
    for book, col in BOOKS.items():
        print(f"[baseline] {book}: train={df.loc[train, col].sum():.0f} "
              f"test={df.loc[test, col].sum():.0f}")


if __name__ == "__main__":
    main()
