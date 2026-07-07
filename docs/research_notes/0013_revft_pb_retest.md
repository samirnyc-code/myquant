# 0013 — RevFT i1R / PB Retest Trade: Full Grid Study & Why It Fails — 2026-07-07
**Series:** MC Setup Research Notes · Note 0013
**Confidence:** High **as a negative result** — two independent signal exports (6.4k and 12.7k signals), 5 years, tick-level event ordering, 72-cell exit grids, dose-response across three arming variants. Exploratory (no pre-registration), but the conclusion is the same in every cut.

**TL;DR:** We built the "rev-bar traders' breakout test": when a RevFT reversal runs to the rev-bar traders' +1R without an Al Brooks pullback (the **i1R** condition), we fade the pullback back into their entry price E (rev-bar extreme +/-1t), confirmed by a bar that touches E and closes inside a 1xABR(8) box. It fires ~24% of the time (1,148 trades on the 6k export; 2,852 on the 12k export) and is **flat net of costs in every exit configuration tested** — 6 stop modes x 12 target modes, both files. Stricter "cleaner run" arming makes it *worse*, monotonically. The one positive pocket (BO/IB with structural targets) shrinks on the larger file. Mechanism: **the cleaner the initial reversal, the more its retest of E marks the end of the move, not a defended pullback** — the rev-bar traders are paid and gone; there is nobody left to defend E. We also close a side door for good: the rev-bar stop-entry cannot be measured from confirmed-signal exports (survivorship: signal bars close beyond the break level 92.8% vs 44.3% base rate — the failed breaks a real stop order would have filled are missing from the file).

---

## 1. The setup (so this note stands alone)

**Signals.** RevFT ("MyReversals") 5M ES swing-reversal signals. Each csv row: signal bar (close-stamped), direction, and `StopPrice` = the **setup extreme** — the exact high/low of the swing the reversal formed off (verified: matches a bar extreme exactly in 479/479 sampled signals). Two exports: the standard RTH file (6,442 signals, 2021-06 to 2026-07) and the "All / Nymex Energy RTH" file (12,707 signals, different session template, only 3,642 overlap). Sneaky excluded throughout. The base RevFT trade at 1:1 is a firm loser (-0.09R; see note 0005) — this study is another rescue attempt, via a *different entry* on the same information.

**Definitions (short side; longs mirrored).**
- **Reversal bar** = the bar before the signal bar. **E** = reversal-bar low - 1t = the price where Brooks-style rev-bar traders went short on a stop.
- **1R range** = (setup extreme + 1t) down to E. **1R target** = E - range: the rev-bar traders' +1R.
- **i1R condition (arming):** the 1R target is taken out — by the signal bar itself, or later — with **no Al Brooks pullback** on the way (no bar trading above the prior bar's high, tick-ordered inside bars).
- **PB signal:** after arming, the first bar that touches E and **closes inside a box of 1.0 x ABR(8)** centered on E (ABR(8) = mean H-L of the 8 bars before the touch bar). The setup extreme must never trade in between (rule 11). Entry: sell at the touch bar's close (fill = first tick of next bar, 1t slip, $5 RT, EOD flat).

All event ordering (target takeout vs pullback vs extreme takeout vs E-touch) is resolved on **raw ticks**, not bars — this matters: a bar-level version misclassifies ~3% of arms (a bar can make its higher high *after* the target traded).

## 2. The questions

1. Does the PB retest trade make money under any reasonable stop/target scheme?
2. Does it replicate on the second, larger signal export?
3. Does *stricter* arming (a cleaner initial run) improve the retest trade?
4. Can the rev-bar traders' own trade (stop entry at E on the break) be evaluated from these files?

## 3. How we tested it

- **Exit grid per fired trade:** stops = S1 extreme+1t · S2 fill+/-{0.5,1,1.5}xABR(8) · S3 "AR" (start S1, tighten to entry-bar extreme+1t at its close) · S4 PB-bar extreme+1t. Targets = T1 the original csv trade's 1R level (fallback 1x stop) · T2 {0.5,1,1.5}xABR(8) · T3 {1..5}xAR (armed after entry bar closes) · T4 {1,2,3}x stop size. 72 combos, all tick-simulated, R reported against each row's initial stop distance.
- **Replication:** identical pipeline on the 12k export (11,017 signals mappable onto RTH bars).
- **Dose-response:** three arming variants — (a) the i1R rule above; (b) gate additionally on the csv trade winning *its own* farther 1R cleanly; (c) zero-MAE: price never re-crosses E at all before the target.
- **Side door:** stop-entry at E during the break, plus a causality audit of the export itself.

## 4. Results

### 4.1 The PB trade is flat — both files

| | 6k file | 12k file |
|---|---|---|
| PB trades fired | 1,148 (~24% of signals) | 2,852 (~26%) |
| Baseline exit (S1 stop, T1 target) | +0.001R, 37% win, +$2,648 | +0.002R, 37% win, +$17,315 |
| Best cell of 72 | +0.033R +/-0.087 | +0.062R +/-0.059 (S2_1.5 x T4_3) |
| Cells meaningfully positive | none (best-of-72 selection) | none after selection discount |

Grid structure is identical in both files: tight stops (S2_0.5, S4) lose everywhere — the retest zone is noisy; the structural target (T1) and large multiples of wide stops do best; AR-multiple targets (T3) are the worst family (-0.1 to -0.5R); longs = shorts.

**Year-split of the 12k best cells:** S2_1.5xT1: 2021 -0.00, 2022 +0.07, 2023 +0.00, 2024 +0.02, 2025 +0.01, 2026 +0.12. Nothing stable enough to trade; the positive mean leans on 2022/2026.

### 4.2 By setup type — the BO/IB pocket shrinks on the bigger file

| Type | 6k: n / S1xT1 | 12k: n / S1xT1 | 12k best cell |
|---|---|---|---|
| BO | 148 / **+0.113** +/-0.227 | 470 / +0.025 +/-0.121 | +0.170 |
| IB | 245 / +0.086 +/-0.179 | 599 / +0.010 +/-0.115 | +0.123 |
| OB | 128 / -0.037 | 371 / -0.085 | -0.002 |
| Trap | 627 / -0.051 | 1,412 / +0.013 | +0.056 |

The 6k file's one hopeful pocket (BO +0.11, best cell +0.28) **regresses toward zero at 3x the sample**. That is the signature of noise, not of a small edge.

### 4.3 Dose-response: the cleaner the run, the worse the retest

| Arming (strictness increasing) | n | Baseline outcome |
|---|---|---|
| i1R (rules as specified) | 1,148 | ~= 0.00R |
| + csv trade must win its own 1R cleanly | 329 | -0.09R, **all 72 cells negative** |
| Zero-MAE (never re-crosses E before target) | 65 | -0.2 to -0.4R |

Monotone. This is the study's most informative pattern (discussed in section 5).

### 4.4 The side door, closed: rev-bar stop entry is unmeasurable from these files

A stop order at E during the break looks spectacular from the csv (+0.3 to +0.8R everywhere, tight stops "best") — and is entirely survivorship. The export's signal bars close beyond the break level **92.8%** of the time vs **44.3%** for all prior-bar-extreme breaks (n=90,366): a row only exists when the break *worked into the bar close*. The failed breaks — which a resting stop order fills all the same — are absent. Mean conditioned "head start" at signal-bar close: +0.39R, i.e. the entire apparent edge. Only 13 of 4,849 fills were causally placeable (order at signal-bar close). Same bias family as the ER10 bug (note 0002). A causal variant — LIMIT order at E placed at signal-bar close — fills 4,274 times and is **flat** (best cells ~+0.03R), consistent with the PB grid.

## 5. Why the i1R PB trade doesn't work as hoped

The trade's premise: rev-bar traders entered at E, they are +1R, so a pullback to E should be *defended* — by their re-entries, by breakeven stops sitting there, by late traders wanting the "second chance" entry. The data says the premise fails, and the dose-response says *why*:

1. **The defenders are gone by the time we need them.** A clean, pullback-free run to +1R is precisely the move where early shorts take profits (the 1R target *is* their exit) and trailing entries never got a pullback to join. When price finally returns to E, the cohort with an interest in defending it has largely monetized. The retest is not a test of committed inventory — it is price re-entering a vacuum.
2. **Selection cuts against us, monotonically.** If shallow-retest-then-continue were the dominant behavior, stricter cleanliness should *help* (purer momentum, stronger defense). It does the opposite at every step (0.00 -> -0.09 -> -0.3R). The cleaner the impulse, the more often the return to E is a genuine V-reversal that runs straight through the level. Brooks' own framing agrees: strong spikes get *one* pullback that holds well above the entry price; price actually coming all the way back to the breakout price after a clean 1R move is more often "failed breakout" behavior than "breakout test" behavior on this timeframe.
3. **The information is stale by construction.** Everything the setup knows (extreme, E, the clean run) is public an hour before our entry. The market has already paid out the reversal move once; our entry buys the *second* serving of an edge that note 0005 showed doesn't exist even for the first serving. Adding costs (~$17/trade at median 8-pt risk) on top of a ~0 gross means the trade needs the retest to be defended *more* often than randomly — and it is defended slightly *less* often.
4. **The exits can't rescue an entry with no edge.** 72 stop/target geometries on two files move the needle from -0.02 to +0.06R — exactly the spread you get re-slicing noise. The only structure (wide stops > tight stops, structural targets > volatility targets) says the *level* is noisy, not that it is an edge.

## 6. Verdict & what survives

- **Retire the PB retest trade** as specified, all variants, both signal files. Do not re-tune exits; the entry has no edge to manage.
- **The framework survives:** tick-ordered arming/retest/box detection, the 72-cell exit grid, and the per-trade chart library are reusable on any signal set with a real edge (e.g. the MC signals).
- **The survivorship audit (4.4) is the durable lesson:** any "trade the setup bar's break" idea backtested from a *confirmed-signal* export will look brilliant and be fake. The honest route to the rev-bar entry question is a candidate-level export (setups stamped before confirmation) — the LizardTrader Auction Bars indicator documents exactly such candidate series; exporter built (`nt8/indicators/LTReversalCandidateExporter.cs`), vendor series currently NULL on chart (pending settings/vendor resolution), or we re-implement the manual's mechanical candidate definitions directly on our bars.

**Artifacts:** `docs/living/pb_grid_trades.parquet` (+`_12k`, `_i1r`, `_defA`), `limitE_grid_trades.parquet`, `revbar_grid_trades.parquet`, `i1r_flags.parquet`, chart library `docs/living/pb_trade_library/{longs,shorts}/index.html`, verification charts `docs/living/pb_verify/`.
