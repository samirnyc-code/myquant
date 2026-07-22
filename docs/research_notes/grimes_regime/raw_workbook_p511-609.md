# Raw extraction — Grimes Course Workbook, PDF pages 511–609 (Ch.13 retracement stats, Ch.14 MAs, Ch.15 Opening Range, Ch.16 Two Forces tests)
Extracted 2026-07-22 (S81). PDF page cites. THE most quantitative section for futures — Ch.16 especially.

## Ch.13 remnant — Retracement/extension statistics (pp. 511–518)
- p.511 — Structural trend definition: "a retracement less than 100% will hold a higher low in an uptrend or a lower high in a downtrend, which is a key structure in most market structure–oriented definitions of a trend." Retracement >100% = failed pullback / extension the other way.
- p.511, Table 13.6 — Retracements ≤100% (Futures): N=2,459, mean 64.4%, StDev 21.0%, median 64.9%, IQR 35.4%.
- p.513-514 — "Qualified retracement" criteria: extension >25% of setup leg; retracement held higher low (≤100%); extension makes new high vs B. Futures N=1,566: mean 61.9%, median 62.1% — essentially unchanged from unfiltered.
- p.515-518, Tables 13.8/13.10 — Extension size by retracement depth r (mean extension % of setup leg): r≤25% → 36.7; 25–50% → 63.5; 50–75% → 92.0; 75–100% → 119.6; >100% → 157.1. DEEPER retracements set up proportionally LARGER extensions — opposite of "shallow pullback = strong trend" folklore. Monotone with or without vol filter.
- p.518 — No Fibonacci significance; retracement terminations plateau ~40–75%; "look for retracements to terminate at about 50% of the setup leg, with a very large margin of error." Mean extension ≈120% of setup leg.

## Ch.14 — Moving averages (pp. 519–555)
- p.523 — Pythia framework: composite excess return at days 1-5, 10, 15, 20 vs asset-class baseline drift (bp); * = 0.05, ** = 0.01. Baselines %Up: Equities 50.07, Futures 50.59, Forex 51.0.
- p.527-532 — Touch-and-hold of 50/45/200/random-period SMA: statistically indistinguishable; no MA acts as S/R; no period special (pp.536, 554).
- p.532-538 — Penetration fade: equity edge exists but is identical WITHOUT the MA ("fade close outside previous day's range": equities buy +9.1bp** d1, +20.7bp** d5). Futures: buy 52.6% vs 50.6% base — significant but only ~2–4bp, "too small to be economically significant on its own." Futures/forex ≈ random walk; equities strongly reject RW.
- p.548-551, Table 14.10 — Trend-indicator test methodology (KEY): categorize all days by indicator state (up/down/neutral), assign current bar's return to the PREVIOUS bar's condition (no look-ahead), compare mean excess return, StDev, HV, %Up per state. Indicator: slope of 50-SMA = slope of linear regression through last 5 points of the average; neutral = flat.
- p.549-551 — Futures results (relevant for ES): Down state N=18,818: excess −94.1bp (annualized-composite basis), %Up 50.1. Up N=21,827: +81.1bp, %Up 51.1. In FUTURES the MA-slope state IS directionally informative (equities INVERT: down +177.2, up −129.6). Caveats: lag (~1/3 of a move retraced before flip); whipsaw in flat markets.
- p.552, Table 14.11 — Triple MA (10/20/50 SMA correctly ordered = trend; undefined when interleaved): Futures Down −203.0bp excess, %Up 49.8; Up +80.7bp, %Up 51.5 — "possibly an edge in futures, particularly on the short side." Equities inverted again.
- p.553-555, Table 14.12 — 200-day MA long-only filter, DJIA 1960–2010: ROI 1,408% vs B&H 1,504% while in market only 8,450/12,842 days; mean daily 3.3bp vs 2.2, StDev 79.8 vs 101.5, CoV 24.3 vs 46.0. Works with nearly ANY period — captures "declining markets are more volatile," not the 200-day itself.
- p.541-547 — Brock/Lakonishok/LeBaron 1/50 crossover: in-sample 1920-86 28.0% win, 84bp/trade; OOS 1987-2010 20.9% win, 7bp; KS p=0.007 → the regime broke. Guards: few conditions, big samples, distrust incredible results.

## Ch.15 — Opening range (pp. 556–567)
- p.557 — O%Rng = (Open − Low)/(High − Low) × 100.
- p.558-567 — Opening skew (O%Rng ≤5 or ≥95): active markets daily 14.7%; pure random walk 15.6%; AR(2) (β=0.25, γ=0.1) 18.1%. Opening skew fully consistent with random walk + slight positive autocorrelation (arcsine law) — NOT exploitable structure. Null-model discipline example for intraday features.

## Ch.16 — The Two Forces: mean reversion vs range expansion (pp. 568–603) — CORE
- p.570 — Volatility Spike: daily return z-scored by past-20-day stdev; ±4–5σ common (non-normal).
- p.572-573, Table 16.1 — Fade ±3σ closes: Equities significant (buy +11.3bp** d1); FUTURES NOT significant — pattern suggests CONTINUATION after big single days in futures. For ES-adjacent work: large single days in futures lean continuation, not fade.
- p.575 — Strengthened equity fade (close top 75% of range, open bottom 50%): +25.7bp** d1. Futures/forex fail.
- p.576-577 — Signal quality rules: suspect effects <10bp; suspect mean/median sign disagreement; suspect single-day-only effects.
- p.580-581, Table 16.5 — S&P 500 CASH runs test 1980–2011 (N=7,918), P(Up)=52.99%: P(next same direction | exact run N): N=2 51.4%, N=3 45.9%, N=4 46.5%, N=5 47.5%, N=6 39.0%, N=7 51.2%, N=8 47.6%. The S&P INDEX mean-reverts after runs (rejects weak EMH). Use EXACT N-length runs.
- p.582-583 — Fading 3/5-day runs: equities strongly mean-reverting (5-day-run buy +18.4bp** d1 → +76.5bp** d5). Futures 5-day-run buy d1 +13.5bp* then fades.
- p.584-589 — Donchian breakouts (entry on close, ≥5 days between same-direction entries): 20-day: equities FADE the breakout (buy −12.3**), futures WITH it (buy +7.2*). 100-day: futures buy +10.1* d1 → +73.3** d20; sell −115.6** d20 — clear momentum in futures at longer channels; forex similar; equities still mean-revert. 260-day: futures buy +101.7** d20; equity 52-week-high buys DOWN ~1% after 20 days.
- p.589 — Modified Keltner spec (THE band definition): bands 2.25 × ATR above/below a 20-period EXPONENTIAL moving average; contains ~85% of market activity across asset classes and timeframes. Close outside = potentially overextended.
- p.590-591, Table 16.11 — Fade close outside Keltner (prev bar inside): Futures buy d1 %Up 60.3% vs 50.6% base (one-day reversion edge, then erodes); equities revert strongly; forex shows continuation (fade fails).
- p.594-596 — REGIME CYCLE (central claim): "Markets tend to work in mean reversion mode after a period of expanded volatility, and in range expansion mode after a period of contracted volatility. This is a price-pattern expression of an underlying cycle in volatility" (p.602). Volatility cycles are NOT arbitraged away (price cycles are).
- p.595 — Compression measures: (a) HV percentile — flag compressed when in bottom 20th percentile of its history; (b) ratio of short HV (5–20d) to long HV (50–260d); example chart 10d/60d.
- p.596-598, Table 16.13 — Volatility Compression Breakout test (exact spec): setup = 5-day/40-day ATR ratio < 0.5 on previous day; trigger = current day's true range ≥ 5-day ATR; filter = close in top 50% of range and above yesterday's close (reversed for shorts). ~1 in 500 trading days. FUTURES BUY: +53.8 d1, +91.8* d3, +128.2** d4, +89.5* d5 (%Up 73.0% d5) — strongest futures continuation signal in the book. Edge decays/reverses by d15–20. Criteria must be re-adapted per asset class.
- p.599-601, Table 16.14 — Keltner pullback entry (trend-continuation spec): shorts armed after close below lower Keltner channel; entry = touch of the 20-EMA (executed at PREVIOUS bar's EMA to avoid the average being pulled into the bar); one entry per channel excursion (must re-close outside to re-arm); symmetric buys. ~1% of trading days. Futures sell: −59.0bp** d1 (%Up 40.4), −45.5** d3, −86.4* d20; buys positive but weaker. Robust to wide parameter bands and even RANDOMIZED averages — the pattern is impulse → retrace → continuation, not the MA itself. "This is the very essence of trend trading."
- p.602-603 — Two verified forces only: mean reversion (post-expanded-vol, strongest equities) and range expansion (post-compressed-vol, or after pullback within impulse structure). Tests ≤3 conditions, uncustomized. "Most trading losses come from incorrectly identifying the emerging volatility environment" (p.594).

## Futures/ES-specific summary
- Futures ≈ near-random on most single-condition tests. Exceptions WITH signal:
  1. Longer Donchian breakouts (100/260-day) → momentum.
  2. Vol-compression breakout (5/40 ATR < 0.5 + TR ≥ 5d-ATR trigger) → strong 1–5 day continuation (73% up d5).
  3. Keltner pullback-to-EMA → trend continuation, especially short side.
  4. MA-slope / triple-MA state: correct-sign categorical returns in futures (unlike equities).
  5. S&P cash INDEX mean-reverts after multi-day runs (Table 16.5).
- Classifier skeleton per Grimes: vol-ratio (short/long ATR or HV) → compressed = expect expansion/trend regime (no fading); expanded = expect mean-reversion regime (no breakout chasing); trend state via market structure (higher lows / retracement ≤100% of setup leg), NOT MA crosses; overextension boundary = 2.25×ATR Keltner around 20-EMA (~85% containment).
- Testing discipline: excess return vs baseline in bp at d1–20, assign returns to prior bar's state, exact-run definitions, RW/AR(2)/GARCH nulls, exclude effects <10bp or mean/median disagreement, per-asset-class breakdowns.
