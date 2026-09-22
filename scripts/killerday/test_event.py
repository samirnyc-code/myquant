"""S115 killer-day study — EVENT-DAY rule family.

Books: ic (day col ic_pnl), fly (fly_pnl), puts_band (puts_band_pnl),
combined (sum of the three).

Baseline = book P&L as-is from killer_context.csv day columns.
Side-level rules use per-trade rows (rows.csv method==vix252 eodic_c/eodic_p;
fly_rows.csv eodfly_c/eodfly_p).

Rules swept (morning-knowable inputs only: the econ calendar is known in advance,
morning credits cr_eodic_c/cr_eodic_p are known at entry):
  1. skip <EVENT> entirely (FOMC / CPI / NFP / any-event) x each book
  2. skip only the CALL side on event days (ic, fly, combined; per-event + any)
  3. skip only FLIES on event days (combined book: zero fly contribution)
  4. FOMC close-by-12:30CT approximation: FOMC-day pnl := max(pnl, 0)
     APPROXIMATION (stated honestly): this is an OPTIMISTIC UPPER BOUND —
     it assumes every FOMC-day loser is exited flat before the 13:00 CT
     announcement (loss fully avoided) while every winner still keeps its
     full credit. In reality early exit pays back remaining premium on
     winners, and some losses (morning moves) are already realized by 12:30.
     True value lies between this and full-skip (delta = -sum of event-day pnl).
  5. event-day x rich-credit interaction: on event days trade only if
     total morning IC credit (cr_eodic_c + cr_eodic_p) >= T, and the inverse
     (skip event days with credit >= T), T in {2,3,4,5,6}.

Metrics per rule:
  train_delta  = sum(modified - baseline) over 2022-2024
  test_delta   = sum(modified - baseline) over 2025-2026
  killer_days_avoided = # days baseline < -1500 and modified >= -1500 (full period)
  winning_days_lost   = # days baseline > 0 and modified <= 0 (full period)
  verdict: ROBUST if train>0 and test>0 (economic story required, stated in csv);
           TRAIN_ONLY if train>0 >= test; DEAD otherwise.

Output: data/options_sim/backtest_full/killerday/event_results.csv
"""
import os
import pandas as pd
import numpy as np

ROOT = r"C:\Users\Admin\myquant"
BF = os.path.join(ROOT, "data", "options_sim", "backtest_full")
OUTDIR = os.path.join(BF, "killerday")
os.makedirs(OUTDIR, exist_ok=True)
OUT = os.path.join(OUTDIR, "event_results.csv")

KILLER = -1500.0

# ---------------- load ----------------
ctx = pd.read_csv(os.path.join(BF, "killer_context.csv"))
ctx["date"] = ctx["date"].astype(str)
ctx = ctx[ctx["date"].str.match(r"\d{4}-\d{2}-\d{2}")].copy()
for c in ["ic_pnl", "fly_pnl", "puts_band_pnl", "cr_eodic_c", "cr_eodic_p"]:
    ctx[c] = pd.to_numeric(ctx[c], errors="coerce")
ctx["ic_pnl"] = ctx["ic_pnl"].fillna(0.0)
ctx["fly_pnl"] = ctx["fly_pnl"].fillna(0.0)
ctx["puts_band_pnl"] = ctx["puts_band_pnl"].fillna(0.0)
ctx["combined_pnl"] = ctx["ic_pnl"] + ctx["fly_pnl"] + ctx["puts_band_pnl"]
ctx["event"] = ctx["event"].fillna("")
ctx["year"] = ctx["date"].str[:4].astype(int)
ctx["is_fomc"] = ctx["event"].str.contains("FOMC")
ctx["is_cpi"] = ctx["event"].str.contains("CPI")
ctx["is_nfp"] = ctx["event"].str.contains("NFP")
ctx["is_event"] = ctx["event"] != ""
ctx["cr_total"] = ctx["cr_eodic_c"].fillna(0.0) + ctx["cr_eodic_p"].fillna(0.0)
ctx = ctx.set_index("date", drop=False)

# per-trade rows for side-level rules
rows = pd.read_csv(os.path.join(BF, "rows.csv"), on_bad_lines="skip")
rows = rows[rows["date"].astype(str).str.match(r"\d{4}-\d{2}-\d{2}", na=False)]
rows["pnl"] = pd.to_numeric(rows["pnl"], errors="coerce").fillna(0.0)
ic252 = rows[rows["method"] == "vix252"]
# ic_pnl day column = sum of ALL vix252 strats (eodic_c/p + openic_c/p) per
# killer_day_context.py; call side = eodic_c + openic_c
ic_c_by_day = ic252[ic252["strat"].isin(["eodic_c", "openic_c"])].groupby("date")["pnl"].sum()
ic_p_by_day = ic252[ic252["strat"].isin(["eodic_p", "openic_p"])].groupby("date")["pnl"].sum()

frows = pd.read_csv(os.path.join(BF, "fly_rows.csv"), on_bad_lines="skip")
frows = frows[frows["date"].astype(str).str.match(r"\d{4}-\d{2}-\d{2}", na=False)]
frows["pnl"] = pd.to_numeric(frows["pnl"], errors="coerce").fillna(0.0)
fly_c_by_day = frows[frows["strat"].isin(["eodfly_c", "openfly_c"])].groupby("date")["pnl"].sum()

# consistency check: day col vs trade-row sum (report only, never blocks)
chk = ctx[["date", "ic_pnl", "fly_pnl"]].copy()
chk["ic_rows"] = (ic_c_by_day.reindex(chk["date"]).fillna(0).values
                  + ic_p_by_day.reindex(chk["date"]).fillna(0).values)
fly_p_by_day = frows[frows["strat"].isin(["eodfly_p", "openfly_p"])].groupby("date")["pnl"].sum()
chk["fly_rows"] = (fly_c_by_day.reindex(chk["date"]).fillna(0).values
                   + fly_p_by_day.reindex(chk["date"]).fillna(0).values)
ic_corr = chk["ic_pnl"].corr(chk["ic_rows"])
fly_corr = chk["fly_pnl"].corr(chk["fly_rows"])
ic_mismatch = int((abs(chk["ic_pnl"] - chk["ic_rows"]) > 50).sum())
fly_mismatch = int((abs(chk["fly_pnl"] - chk["fly_rows"]) > 50).sum())
print(f"[check] ic day-col vs vix252 trade-row sum: corr={ic_corr:.4f}, "
      f"|diff|>$50 on {ic_mismatch}/{len(chk)} days")
print(f"[check] fly day-col vs trade-row sum: corr={fly_corr:.4f}, "
      f"|diff|>$50 on {fly_mismatch}/{len(chk)} days")

# call-leg pnl aligned to ctx index (for call-side-skip rules)
ctx["ic_call_pnl"] = ic_c_by_day.reindex(ctx.index).fillna(0.0)
ctx["fly_call_pnl"] = fly_c_by_day.reindex(ctx.index).fillna(0.0)

BOOKS = {"ic": "ic_pnl", "fly": "fly_pnl", "puts_band": "puts_band_pnl",
         "combined": "combined_pnl"}
TRAIN = ctx["year"] <= 2024
TEST = ctx["year"] >= 2025

results = []


def evaluate(rule, book, modified, story):
    base = ctx[BOOKS[book]]
    delta = modified - base
    tr = float(delta[TRAIN].sum())
    te = float(delta[TEST].sum())
    killers = int(((base < KILLER) & (modified >= KILLER)).sum())
    winlost = int(((base > 0) & (modified <= 0)).sum())
    if tr > 0 and te > 0:
        verdict = "ROBUST"
    elif tr > 0:
        verdict = "TRAIN_ONLY"
    else:
        verdict = "DEAD"
    results.append(dict(rule=rule, book=book,
                        train_delta=round(tr, 0), test_delta=round(te, 0),
                        killer_days_avoided=killers, winning_days_lost=winlost,
                        verdict=verdict, economic_story=story))


# ---------------- 1. skip event entirely, per book ----------------
EVENT_MASKS = {"FOMC": ctx["is_fomc"], "CPI": ctx["is_cpi"],
               "NFP": ctx["is_nfp"], "ANY_EVENT": ctx["is_event"]}
for ev, mask in EVENT_MASKS.items():
    for book, col in BOOKS.items():
        mod = ctx[col].where(~mask, 0.0)
        evaluate(f"skip_{ev}", book, mod,
                 f"{ev} announcement can gap SPX through short strikes; stand aside")

# ---------------- 2. skip only the CALL side on event days ----------------
# ic: remove eodic_c pnl; fly: remove eodfly_c pnl; combined: remove both.
for ev, mask in EVENT_MASKS.items():
    mod = ctx["ic_pnl"] - ctx["ic_call_pnl"].where(mask, 0.0)
    evaluate(f"skip_callside_{ev}", "ic", mod,
             f"relief rallies after {ev} rip through call strikes while puts survive")
    mod = ctx["fly_pnl"] - ctx["fly_call_pnl"].where(mask, 0.0)
    evaluate(f"skip_callside_{ev}", "fly", mod,
             f"relief rallies after {ev} blow out the call fly wing")
    mod = ctx["combined_pnl"] - (ctx["ic_call_pnl"] + ctx["fly_call_pnl"]).where(mask, 0.0)
    evaluate(f"skip_callside_{ev}", "combined", mod,
             f"drop all call-side premium on {ev} days, keep put side")

# ---------------- 3. skip only FLIES on event days (combined) ----------------
for ev, mask in EVENT_MASKS.items():
    mod = ctx["combined_pnl"] - ctx["fly_pnl"].where(mask, 0.0)
    evaluate(f"skip_flies_{ev}", "combined", mod,
             f"tight ATM flies need pin; {ev} days trend away from the morning pin")

# ---------------- 4. FOMC close-by-12:30 CT approximation ----------------
# APPROX: FOMC-day pnl := max(pnl, 0). Optimistic upper bound (see docstring).
mask = ctx["is_fomc"]
for book, col in BOOKS.items():
    mod = ctx[col].where(~mask, ctx[col].clip(lower=0.0))
    evaluate("fomc_close_1230_UPPERBOUND", book, mod,
             "13:00 CT announcement hits after morning entry; exit before it "
             "(approx keeps winners full, losers flat = optimistic bound)")

# ---------------- 5. event day x rich credit ----------------
# cr_total = morning IC total credit, known at entry. Two directions.
for T in [2.0, 3.0, 4.0, 5.0, 6.0]:
    thin = ctx["is_event"] & (ctx["cr_total"] < T)
    rich = ctx["is_event"] & (ctx["cr_total"] >= T)
    for book, col in BOOKS.items():
        mod = ctx[col].where(~thin, 0.0)
        evaluate(f"skip_event_if_credit_below_{T:g}", book, mod,
                 "thin credit on an event day = no compensation for announcement risk")
        mod = ctx[col].where(~rich, 0.0)
        evaluate(f"skip_event_if_credit_above_{T:g}", book, mod,
                 "rich credit on an event day = market itself pricing a big move")

# ---------------- save ----------------
res = pd.DataFrame(results)
res.to_csv(OUT, index=False)
print(f"\nsaved {len(res)} rule rows -> {OUT}")

# event-day baseline color, for the report
print("\n--- event-day baseline P&L by book (full period) ---")
for ev, mask in EVENT_MASKS.items():
    n = int(mask.sum())
    line = f"{ev:9s} n={n:3d} "
    for book, col in BOOKS.items():
        s = ctx.loc[mask, col]
        line += f" {book}={s.sum():>9.0f} (avg {s.mean():>6.0f})"
    print(line)
print("\n--- non-event baseline avg/day ---")
ne = ~ctx["is_event"]
for book, col in BOOKS.items():
    print(f"{book:9s} avg {ctx.loc[ne, col].mean():.0f}")

print("\n--- full results ---")
with pd.option_context("display.max_rows", None, "display.width", 220):
    print(res.drop(columns=["economic_story"]).to_string(index=False))
