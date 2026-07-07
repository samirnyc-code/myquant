# RevFT Rev/PB Trade — Session Summary — 2026-07-07
**Series:** Working summary (not a numbered research note)
**Confidence:** Medium — full 5-year tick-level sims, but exit grids are exploratory (72 combos); no pre-registration.

**TL;DR:** We defined i1R ("straight shot" 1R winners), built the PB retest signal on top of the RevFT signal set, and tick-simulated all 1,148 fired PB trades across a 6-stop x 12-target grid. Result: the PB selection lifts the base RevFT trade from a firm loser (-0.09R) to break-even, but no grid cell clears noise or costs. BO setups are the one consistently positive pocket (n=148). Two attempted shortcuts to trade the reversal bar itself were closed: stop-entry off the csv is invalidated by survivorship (the export only contains confirmed breaks), and the causal limit-at-E retest is also flat.

---

## 1. i1R — "straight shot" 1R winners

Definition B (locked): the trade reaches 1R with no bar taking out the prior bar's extreme against the trade on the way.

| Population | Trades | 1R winners | i1R | i1R % of trades | i1R % of winners |
|---|---|---|---|---|---|
| All types | 6,108 | 2,656 (43.5%) | 1,042 | 17.1% | 39.2% |
| Excl. Sneaky | 4,834 | 2,101 (43.5%) | 844 | 17.5% | 40.2% |

By type (share of that type's trades ending i1R): Trap 19.0%, IB 18.3%, OB 16.3%, Sneaky 15.5%, BO 13.0%.

Note: median risk (entry to 1t beyond the rev extreme) is 8.0 ES points; i1R trades skew tighter (median 7.0).

## 2. PB signal — the setup and how many fired

Setup (short side; longs mirrored): the rev-bar traders' 1R range (setup extreme +1t down to reversal-bar low -1t) must be taken out with **no Brooks pullback** on the way; then price must **retest E** (the rev-bar traders' entry, revbar low -1t) and the touch bar must **close inside a 1.0 x ABR(8) box** centered on E; enter STC at that bar's close. The setup extreme may never trade in between (rule 11). All event ordering resolved on **tick data**.

| Funnel (non-Sneaky, 2021-06 to 2026-07) | n |
|---|---|
| Signals processed | ~4,850 |
| **PB signals fired** | **1,148 (~24%)** |
| Longs / Shorts | 505 / 643 |
| Frequency | ~0.9 per trading day |

Kill reasons for the other 76%, in order: (1) Brooks pullback before the 1R target, (2) no retest of E by end of day, (3) touch bar closed outside the box.

## 3. PB trade outcomes — flat, no edge

Entry = first tick after the PB bar close, 1 tick slip, $5 RT, EOD flat. 72 stop x target combos per trade.

| Config | mean R | win % | net $ (5 yrs, 1 ES) |
|---|---|---|---|
| Baseline: stop = setup extreme +1t, target = original 1R level | +0.001 | 37% | +$2,648 |
| Best of grid: stop 1.5 x ABR(8), target 3 x stop size | +0.033 (CI +/-0.087) | 34% | +$35,385 |
| Worst family: AR-multiple targets (T3) | -0.12 to -0.52 | — | deeply negative |

The best cell's confidence interval straddles zero, and it is the best of 72 tries — indistinguishable from luck. Positive years are 2021-22; 2023-25 flat to negative.

**Grid structure (the useful part):**

- Tight stops (0.5 x ABR, PB-bar extreme) lose everywhere — the retest zone is noisy.
- The structural target (the original csv trade's 1R level) beats all ABR/AR-derived targets.
- Longs and shorts perform the same.

**By setup type:**

| Type | n | Verdict |
|---|---|---|
| BO | 148 | Only consistent positive pocket (+0.11 to +0.28R in structural-target cells) |
| IB | 245 | Mildly positive in the same corners |
| OB | 128 | Negative everywhere |
| Trap | 627 | Negative nearly everywhere — over half the sample, drags the total down |

Context: the base RevFT trade at 1:1 is -0.09R (firm loser, CIs exclude zero). The PB selection improves it to break-even but does not clear costs. Interesting inversion: BO is the *worst* type for straight-shot i1R wins but the *best* for the pullback trade — consistent with BO reversals getting retested and the retest holding.

## 4. Closed side-doors (for the record)

1. **Rev-bar stop entry off the csv: invalid by construction.** The signal file only records breaks that closed as confirmed rejections (signal bars close beyond the break level 92.8% of the time vs 44.3% for all prior-bar-extreme breaks). Failed breaks — the majority of real fills a stop-entry trader would take — are absent. The apparent +0.3 to +0.8R across that grid equals the +0.39R mean "head start" the selection hands out. Only 13 of 4,849 fills were causally placeable. Unmeasurable from this file.
2. **Causal limit at E (placed at signal-bar close): flat.** 4,274 fills, best cells ~+0.03R, same shape as the PB grid, year-split is regime noise.
3. **12k "All ... Nymex Energy RTH" export:** same indicator on a different session template (only 3,642 signals overlap with the 6k file) — another confirmed-only export, does not provide the missing candidate universe.

## 5. Artifacts

- Chart library (all 1,148 PB trades, outcome grid on each): docs/living/pb_trade_library/longs/index.html and .../shorts/index.html
- Per-trade data: docs/living/pb_grid_trades.parquet (PB grid), i1r_flags.parquet, limitE_grid_trades.parquet, revbar_grid_trades.parquet
- NT8 exporter for the LizardTrader Auction Bars candidate universe (the honest path to the rev-bar entry question): nt8/indicators/LTReversalCandidateExporter.cs (committed, awaiting F5 + run)

## 6. Open leads (ranked)

1. **BO-only PB trade** — the one consistent pocket; needs a stability check (year-split, detection variants), not a victory lap.
2. **Detection variants not yet swept** — box 0.5x, keep-waiting after a failed touch, MAE-0-alive on the pre-target pullback, rule-11 at extreme+1t, wait-cap.
3. **LT Auction Bars candidate export** — independent detector, candidates stamped pre-confirmation; the only honest route to "trade the reversal bar itself."
4. Close the thread and write note 0013 if the above come back flat.
