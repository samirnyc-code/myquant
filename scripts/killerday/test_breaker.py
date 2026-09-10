"""
S115 killer-day study — DAY-LEVEL CIRCUIT BREAKER, stage-1 approximation.

Question: if the book halts entries and flattens everything once cumulative
realized day loss hits -T (T in {1000, 1500, 2000, 3000}), what is saved on
killer days vs what whipsaw costs on recovered/winning days?

STAGE-1 LIMITATION (stated up front): we have per-trade P&L and exit_kind
(stop vs settle) but NO intraday marks and NO stop timestamps. So we cannot
know the true intraday running-loss path. We therefore produce BOUNDS plus a
midpoint estimate. The stage-2 intraday sim (ThetaData minute marks) resolves
the true number tomorrow. No ThetaData requests are made here — local CSVs only.

Chronology proxy (the only time structure knowable from the rows):
  - 'stop' exits realize intraday, BEFORE any 'settle' exit (settles are all
    simultaneous at the close and are atomic — a breaker cannot act between them).
  - Within the stop group the order is unknown -> worst-loss-first is used for
    the trigger path (earliest possible trigger given the group structure).

Three scenarios per (book, threshold):
  OPT  (upper bound on breaker value): perfect marks-based trigger — the day
       P&L is floored at exactly -T: final = max(baseline, -T). Never whipsaws
       a recovered day, never overshoots. Delta >= 0 by construction.
  MID  (point estimate): stops realize worst-first, then settles. If the
       running sum hits <= -T inside the stop region the desk flattens; all
       remaining trades (later stops + every settle) contribute 0 further P&L.
       Saves remaining losses but forfeits every win that would have come
       after the trigger. Sign is non-trivial. Settle-driven losses (no stop
       printed) are NOT catchable in this scenario — the breaker only fires
       off realized stop-outs, which understates savings on pure-settle
       killer days (stage-2 marks will catch those).
  PESS (lower bound): same worst-first trigger path, but flattening saves
       NOTHING — every remaining loser still realizes its full loss (its stop
       was effectively already in the money) while every remaining winner is
       forfeited. Delta <= 0 by construction.

Books:
  ic        rows.csv, method==vix252, streams eodic_c/eodic_p/openic_c/openic_p
  fly       fly_rows.csv, streams eodfly_c/eodfly_p/openfly_c/openfly_p
  puts_band rows.csv vix252, put streams only (eodic_p, openic_p) with
            credit in [0.5, 2.5]  (verified: reproduces killer_context
            puts_band_pnl to within 0.48 rounding)
  combined  ic + fly pooled, one breaker on the pooled running loss.
            (puts_band is a SUBSET of ic, so it is not added on top —
            adding it would double-count.)

Baseline = per-day sums of the same trade rows (verified vs killer_context.csv
day columns ic_pnl / fly_pnl / puts_band_pnl, max abs diff 0.48 = rounding).

Metrics per rule (reported on MID; OPT/PESS carried alongside):
  train_delta  sum(final - baseline), dates 2022-01-01..2024-12-31
  test_delta   same, 2025-01-01..2026-12-31
  killer_days_avoided  baseline day < -1500 AND breaker fired AND MID final > baseline
  winning_days_lost    baseline day > 0 AND breaker fired (day flips to <= -T)
  verdict  ROBUST only if MID positive in BOTH periods (economic story required),
           TRAIN_ONLY if train>0 and test<=0, DEAD otherwise.
No lookahead: the breaker consumes only realized intraday P&L of the same day.

Output: data/options_sim/backtest_full/killerday/breaker_results.csv
"""
import os
import pandas as pd

ROOT = r"C:\Users\Admin\myquant"
BT = os.path.join(ROOT, "data", "options_sim", "backtest_full")
OUT = os.path.join(BT, "killerday", "breaker_results.csv")

THRESHOLDS = [1000, 1500, 2000, 3000]
KILLER_CUT = -1500.0
TRAIN_END = "2024-12-31"


def load_books():
    rows = pd.read_csv(os.path.join(BT, "rows.csv"))
    rows = rows[rows["method"] == "vix252"].dropna(subset=["pnl"]).copy()
    fly = pd.read_csv(os.path.join(BT, "fly_rows.csv")).dropna(subset=["pnl"]).copy()
    for df in (rows, fly):
        df["is_stop"] = df["exit_kind"].astype(str).str.strip() == "stop"
    puts_band = rows[
        rows["strat"].isin(["eodic_p", "openic_p"])
        & (rows["credit"] >= 0.5)
        & (rows["credit"] <= 2.5)
    ].copy()
    combined = pd.concat([rows, fly], ignore_index=True)
    return {"ic": rows, "fly": fly, "puts_band": puts_band, "combined": combined}


def day_scenarios(day_df, thr):
    """Return (baseline, opt, mid, pess, fired_mid) for one day at threshold thr."""
    baseline = day_df["pnl"].sum()
    opt = max(baseline, -thr)

    stops = sorted(day_df.loc[day_df["is_stop"], "pnl"].tolist())  # worst first
    settle_sum = day_df.loc[~day_df["is_stop"], "pnl"].sum()
    settle_neg = day_df.loc[~day_df["is_stop"] & (day_df["pnl"] < 0), "pnl"].sum()

    cum = 0.0
    fired = False
    fire_idx = len(stops)
    for i, p in enumerate(stops):
        cum += p
        if cum <= -thr:
            fired = True
            fire_idx = i + 1
            break

    if not fired:
        return baseline, opt, baseline, baseline, False

    remaining = stops[fire_idx:]
    rem_neg = sum(p for p in remaining if p < 0)
    mid = cum                      # everything after trigger flattened at 0 further P&L
    pess = cum + rem_neg + settle_neg  # losers still lose fully, winners forfeited
    return baseline, opt, mid, pess, True


def run():
    books = load_books()
    results = []
    for book, df in books.items():
        days = []
        for date, g in df.groupby("date"):
            for thr in THRESHOLDS:
                base, opt, mid, pess, fired = day_scenarios(g, thr)
                days.append(dict(date=date, thr=thr, baseline=base, opt=opt,
                                 mid=mid, pess=pess, fired=fired))
        dd = pd.DataFrame(days)
        dd["train"] = dd["date"] <= TRAIN_END
        for thr in THRESHOLDS:
            d = dd[dd["thr"] == thr]
            tr, te = d[d["train"]], d[~d["train"]]
            mid_train = (tr["mid"] - tr["baseline"]).sum()
            mid_test = (te["mid"] - te["baseline"]).sum()
            killer = d["baseline"] < KILLER_CUT
            killer_avoided = int((killer & d["fired"] & (d["mid"] > d["baseline"])).sum())
            winners_lost = int(((d["baseline"] > 0) & d["fired"]).sum())
            if mid_train > 0 and mid_test > 0:
                verdict = "ROBUST"
            elif mid_train > 0:
                verdict = "TRAIN_ONLY"
            else:
                verdict = "DEAD"
            results.append(dict(
                book=book, threshold=-thr,
                n_killer_days_baseline=int(killer.sum()),
                days_fired_mid=int(d["fired"].sum()),
                train_delta_opt=round((tr["opt"] - tr["baseline"]).sum(), 0),
                test_delta_opt=round((te["opt"] - te["baseline"]).sum(), 0),
                train_delta_mid=round(mid_train, 0),
                test_delta_mid=round(mid_test, 0),
                train_delta_pess=round((tr["pess"] - tr["baseline"]).sum(), 0),
                test_delta_pess=round((te["pess"] - te["baseline"]).sum(), 0),
                killer_days_avoided=killer_avoided,
                winning_days_lost=winners_lost,
                verdict_mid=verdict,
            ))
    res = pd.DataFrame(results)
    os.makedirs(os.path.dirname(OUT), exist_ok=True)
    res.to_csv(OUT, index=False)
    pd.set_option("display.width", 250)
    print(res.to_string(index=False))
    print(f"\nsaved -> {OUT}")


if __name__ == "__main__":
    run()
