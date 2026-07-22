# Raw extraction — Grimes book, PDF pages 385–480 (Ch.12 stats, App.A Primer, App.B MAs & MACD, App.C, Glossary)
Extracted 2026-07-22 (S81). PDF page cites (≈ book pages here; headers matched).

## Appendix B — Exact indicator specifications (pp. 409–424)

### Modified MACD (p.417)
- Fast line = 3-period SMA minus 10-period SMA (of price).
- Signal (slow) line = 16-period SMA of the fast line.
- No histogram; zero line plotted. Built from SIMPLE moving averages ("the long memory of the EMAs does make a difference at times").
- Fast line = 0 exactly when the 3-SMA and 10-SMA cross — "a condition of relative equilibrium on the time frame being measured" (pp.416-418). Fast-line zero-cross = local equilibrium/transition marker.
- p.418: fast line responds to the SECOND derivative of price — measures changes in momentum, not momentum itself.
- p.419 idealized-series artifacts: fast line hooks on the FIRST bar of a new trend; goes flat exactly 10 bars into a steady linear trend (10-SMA fully in-trend) — everything between is indicator artifact; same 10-bar artifact at trend end.
- p.421: a single large price shock produces 12 inflections in the two lines; "the indicator is nearly always irrelevant after a large price shock" (e.g., big overnight gaps intraday).
- pp.422-424 divergence mechanics: a divergence registers only when the second trend leg either (a) moves at a lower rate of change (e.g., 75% of prior leg's per-bar rate, same bar count) or (b) same rate but fewer bars. These are the ONLY two mechanical causes of MACD divergence.

### SMA vs EMA behavior (pp. 409–416)
- SMA reacts TWICE to any single large event (window entry + left-edge exit, "dual inflection"); EMA inflects once — prefer EMA (or handle outliers) for systematic slope tools on gap-prone intraday data (p.413).
- EMA reacts faster to a shock but is SLOWER to return to equilibrium (long memory); SMA equals close exactly after N flat bars.
- MA "support" in trends is a mathematical artifact — no proof any MA is better S/R than a random number (p.411).
- SMA is a low-pass filter: completely FLAT on any cycle whose wavelength is a whole-number multiple of the SMA length (p.413-414) — SMA-slope trend measures can go dead in oscillating regimes.
- Constant-%-growth: on log scale MAs lag a constant percentage — use log/percentage analysis for anything multi-regime (pp.414-416).
- p.409 methodology: test every indicator on synthetic series (flat→linear trend→flat, sine waves, single shocks) to isolate its response.

## Glossary — precise definitions (pp. 427–442)
- Keltner channels (p.432): original Chester Keltner = bands around 10-day SMA of typical price, offset by 10-day MA of ranges. Typical price (p.441) = (H+L+C)/3. Grimes's own variant = "ATR modified Keltner channels" (book p.52; excursion stats book p.198).
- True range/ATR (pp.427,441): TR = bar range + any gap from prior close. ATR% = ATR / last price (cross-asset comparable). Average range (p.427): simple mean of ranges, ignores gaps — "may be more applicable in some intraday applications."
- Efficiency Ratio (Kaufman, p.430): 0→1; net movement vs noise; 1 = straight-line move; 0 = round trip. Directly usable as chop/trend feature.
- First-order pivot (p.431) / second-order pivot (p.439) as in book Ch.2. Market structure (p.433) = swings connecting pivots.
- Time frames related "by a factor between 3 and 5" (pp.431,441).
- Free bars (p.431): bars entirely outside a band — climax/extreme marker.
- Range expansion (p.437): directional movement, expanding ranges, rising vol; opposed to mean reversion (p.433 — which "does not necessarily mean that markets will pull back to moving averages").
- Volatility clustering (p.441): high/low-vol areas cluster; "a reflection of markets moving through different volatility regimes."
- Springs/upthrusts (pp.439,441); price rejection (p.437): S/R holding = immediate sharp move away; ABSENCE of rejection ⇒ higher probability of break.
- O%Rng (p.435): open location within session range as %. Opening skew (p.435): opens cluster near session H/L — "completely explainable by the properties of random walks."
- Standard deviation spike (p.439): z-scored bar returns for current volatility.
- Historical volatility (p.432): annualized stdev of returns. Return series (p.437): % or log return — "the first task of any market analysis."
- Indicator variable (p.432): 0/1 condition; its average = frequency baseline. Excess return (p.430): mean return of signal group minus control-group baseline — his test methodology in one line.
- Out-of-sample (p.435): OOS "can be done only once; after that, the data set is contaminated."
- Three pushes (p.441): three symmetrical (price AND time) pushes to new high/low, then reversal with change of character.
- Anti (p.427): entry on the FIRST pullback after a potential trend change. Always-in (p.427): "perhaps more useful as a research/backtesting methodology than an actual trading style."
- Others: R multiple; CoV (stdev/mean); IQR; chandelier stop; Parabolic SAR acceleration; measured move objective ("better used as a guide than a precise target"); stationarity (debated for markets).

## Ch.12 — Statistical tests on trade results (pp. 388–397)
- pp.389-392 — Edge test: per-system N, mean, stdev, AvgWin/AvgLoss, Win%, p = one-tailed t-test of mean P&L > 0. Neither R/R nor win% meaningful alone.
- pp.392-394 — %R standardization: P&L ÷ initial risk. Example: raw $ P&L insignificant; %R basis mean 0.3R, SD 0.8R, p < 0.001 — sizing inconsistency had obscured a real edge.
- p.395 — SD control chart: per-period P&L, look-back 20 (10–50), bands ±2.5σ (1.5–3.0); offset MA and stdev by one period so today's outlier doesn't understate its own deviation.
- p.396-397 — Range control chart (rolling 20-period high/low envelope of P&L); win-ratio control chart (20-period MA of win ratio) = early regime-shift warning on the SYSTEM.
- p.388 — 3–5 setup categories, tagged at entry, never re-tagged. p.384 — weekly is too short for serious reevaluation; monthly cadence.

## Appendix A (pp. 399–408)
- p.402 — Trades at offer = buyer-motivated, at bid = seller-motivated (aggressor-side logic behind footprint/delta).
- p.400-401 — Spread width as uncertainty measure; illiquid prints unreliable.
- p.408 — Range bars "make backtesting and analysis virtually impossible" (EOD reconstruction ≠ real-time formation).

## Regime-engine takeaways
1. 3/10/16-SMA MACD fast line = second-derivative sensor: zero-cross = equilibrium/transition; flat fast line ≈ steady-state trend; 10-bar artifact + post-shock 12-inflection dead zone.
2. Chop/trend features with exact specs: Kaufman ER, ATR%, range expansion vs mean reversion as the two regime poles, volatility clustering as regime persistence.
3. Structural definitions: trends = second-order pivot sequences; transition markers = failure tests, Anti, three pushes; absence of price rejection ⇒ level likely breaks.
4. Test discipline: signal vs control excess return, indicator variables, one-tailed t-test, one-shot OOS, %R standardization.
