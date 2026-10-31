# 3-month setup review — preliminary (2026-10-31)

**Status: OBSERVATIONAL ONLY. No rule/menu changes from this.** Per user
instruction: decisions wait until 3 more months of data, or end of year,
whichever is later. This is the first pass of ongoing monitoring.

**Window:** 2026-08-06 → 2026-10-30 (2026-08-04/05 excluded as known error
days, same as the dashboard). 499 deduped, real auto-executed paper trades
across 59 trading days, 10 setups. Script: `scripts/setup_review_3mo_20261031.py`
(re-runnable). Full data: `data/options_log/_analysis/setup_review_3mo_*.csv`.

## Per-strategy summary (sorted worst expectancy first)

| strategy | anchor | width | side | n | total P&L | expectancy | win% | structural BE% | PF | worst day | ex-worst-day total |
|---|---|---|---|---|---|---|---|---|---|---|---|
| eodic_p | eod | ic | put | 50 | -$945 | -$18.90 | 92.0% | 95.8% | 0.79 | 10/30 (-$1,703) | +$758 |
| eodfly_p | eod | fly | put | 58 | -$833 | -$14.36 | 50.0% | 63.7% | 0.91 | 10/23 (-$813) | -$20 |
| gx_bps | gexlog | wall | put | 45 | -$145 | -$3.22 | 66.7% | 80.7% | 0.97 | 9/28 (-$937) | +$791 |
| openic_p | open | ic | put | 55 | +$509 | +$9.25 | 96.4% | 98.4% | 1.37 | 10/16 (-$1,272) | +$1,780 |
| openic_c | open | ic | call | 32 | +$524 | +$16.37 | 93.8% | 99.2% | ~102* | 8/19 (-$3) | +$526 |
| openfly_p | open | fly | put | 59 | +$1,237 | +$20.97 | 32.2% | 68.1% | 1.13 | 10/30 (-$1,443) | +$2,680 |
| gx_bcs | gexlog | wall | call | 46 | +$1,136 | +$24.69 | 71.7% | 84.6% | 1.19 | 10/20 (-$1,037) | +$2,172 |
| eodfly_c | eod | fly | call | 58 | +$1,646 | +$28.38 | 51.7% | 62.2% | 1.20 | 10/15 (-$2,074) | +$3,720 |
| eodic_c | eod | ic | call | 37 | +$1,059 | +$28.62 | 83.8% | 95.1% | 1.75 | 9/3 (-$801) | +$1,860 |
| openfly_c | open | fly | call | 59 | +$5,589 | +$94.73 | 45.8% | 65.0% | 1.51 | 10/15 (-$1,493) | +$7,083 |

*openic_c's PF is a near-zero-risk artifact (tiny, consistently small wins, one -$3 loss) — not a meaningful "best" signal, flagged so it isn't over-read.

**"Structural BE%"** = breakeven win rate implied by the structure's own max-gain/max-loss (binary-outcome approximation, not the real P&L distribution) — a comparable bar across setups. **eodic_p, eodfly_p, and gx_bps all show realized win rate BELOW their own structural breakeven** — the three worst-expectancy setups are worst by this measure too, consistent (not contradictory) findings.

## Monthly consistency (the actual bar for "consistently bad")

| strategy | Aug | Sep | Oct | months negative |
|---|---|---|---|---|
| eodfly_p | -$328 | -$741 | +$236 | **2 of 3** |
| gx_bps | +$1,954 | -$602 | -$1,497 | **2 of 3** |
| eodfly_c | -$115 | +$2,250 | -$490 | 2 of 3 (net still +$1,646 — not a real concern) |
| eodic_p | +$786 | +$1,715 | -$3,446 | 1 of 3 |
| openfly_p | +$1,394 | -$2,338 | +$2,180 | 1 of 3 |
| gx_bcs | +$325 | +$2,632 | -$1,821 | 1 of 3 |
| openic_p | +$593 | +$351 | -$435 | 1 of 3 |
| eodic_c / openic_c / openfly_c | all positive | all positive | all positive | 0 of 3 |

**This is the key honest finding: `eodic_p` has the worst overall expectancy, but it is NOT consistently bad month-to-month** — Aug and Sep were both solidly positive; October alone (one bad month, concentrated further in specific days) drags the total negative. That's a different, less alarming finding than "this setup doesn't work," and the ex-worst-day column above confirms it: pull the single worst day and `eodic_p` is net positive for the whole 3 months.

**`eodfly_p` and `gx_bps` are the only two that clear my pre-registered "≥2 of 3 months negative" bar** without being single-day-driven (removing their worst day barely moves the sign). These are the only two genuine watch-list candidates from the raw P&L lens.

## Symmetric pair comparison (put side vs. call side of the same condor/fly)

| pair | put total | call total | gap |
|---|---|---|---|
| eodic_p vs eodic_c | -$945 | +$1,059 | **-$2,004** |
| eodfly_p vs eodfly_c | -$833 | +$1,646 | **-$2,479** |
| openic_p vs openic_c | +$509 | +$524 | -$15 (even) |
| openfly_p vs openfly_c | +$1,237 | +$5,589 | **-$4,352** |
| gx_bps vs gx_bcs | -$145 | +$1,136 | **-$1,281** |

**Every single pair favors the call side, 5 for 5.** This is the single most consistent pattern in the whole dataset — more consistent than any individual setup's own track record. It reads as a market-direction/skew effect over this specific 3-month window (net downward pressure, sharp selloffs like 10/30 hurting puts more than calls gained on the way up), not a flaw in put-selling as a structure. Worth remembering when October's `eodic_p` result above gets re-examined — the put-side weakness is NOT unique to `eodic_p`, it's present in all five pairs, which argues against "retire eodic_p specifically" and for "this was a tough window for selling puts generally."

## Worst-day co-movement (does one bad day explain everything?)

- **Put-side family** (eodic_p, openic_p, eodfly_p, openfly_p, gx_bps): worst-5-day lists overlap moderately — 10/16 appears in 3 of 5 strategies' worst days; 10/30, 10/14, 9/15, 9/8, 10/1 each appear in 2. No single day explains it all, but there's real clustering, consistent with a few shared macro/vol days hitting the whole put side at once rather than five independent bad strategies.
- **Call-side family:** 10/20 appears in 4 of 5 strategies' worst days — the most concentrated single-day effect found in this analysis. 10/15 and 8/28 each appear in 2.

## GEX-briefing context (joined from `data/gexlog/gexlog_daily.csv`)

**Caveat up front: cells here are thin (n=4-31). These are hypothesis-generating, not confirmed — explicitly flagging per the "don't overfit on 3 months" standing order.**

- **By gamma regime (POSITIVE/NEGATIVE):** no clean story. 4 of 5 put-sellers did *better* in NEGATIVE regime and worse in POSITIVE (counter to the naive "negative gamma = dangerous for premium sellers" intuition) — `openfly_p` is the exception. Call side is roughly mirror-image but not uniformly. Not presenting this as a usable signal; it doesn't hold together cleanly enough.
- **By session type — the cleanest cut found:** `TREND (strong)` days are the worst bucket for **every single put-selling setup**, often by a wide margin (`eodic_p`: -$1,149/trade in TREND-strong vs -$19/trade overall). Call-side setups show no such uniform pattern in TREND-strong (some best, some worst). **But n=4-6 per strategy in this bucket** — this could just mean "the handful of strong-trend days in 3 months happened to be down days," which is a restatement of the pair-comparison finding above through a thinner lens, not new independent evidence. Worth re-checking with more data, not actionable yet.
- **By risk_level / signal:** messier, no cut as clean as session-type. Full tables in the CSVs if useful.

## Classification (evidence only — no action taken)

- **Watch list (clears the consistency bar, not single-day-driven):** `eodfly_p`, `gx_bps`.
- **Tail-risk flag, not a consistency flag:** `eodic_p` — fine most months, but win rate sits below its own structural breakeven and it has the account's worst recorded trade day (-$1,703 baseline, before the duplicate-fire bug tripled it). Worth watching for position-sizing/tail-hedge discussion later, not menu removal now.
- **Market-wide pattern, not a setup flaw:** the put-vs-call gap is present in all 5 pairs — argues against singling out any one put-side setup over the others; if anything changes, it should be considered together, not piecemeal.
- **No concern:** `eodic_c`, `openic_c`, `openfly_c` (clean across all 3 months); `openfly_p`, `gx_bcs`, `openic_p` (one bad month each, not a pattern).

**Next check-in: whenever the user revisits (3 more months of data, or EOY, whichever is later).** Re-run `scripts/setup_review_3mo_20261031.py` against the then-current book before any menu decision.
