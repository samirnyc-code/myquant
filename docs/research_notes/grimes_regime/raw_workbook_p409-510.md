# Raw extraction — Grimes Course Workbook, PDF pages 409–510 (Ch.10 Academic Theories, Ch.11 Quant Tools, Ch.12 Test Methodology, Ch.13 start)
Extracted 2026-07-22 (S81). PDF page cites.

## Core regime framework (most load-bearing content in this range)
- p.438 — Two-state model of all market action: "all market action exists in one of two broad states: range expansion or mean reversion, or... trends and trading ranges."
  - Trending = POSITIVE autocorrelation (next change more likely same direction as previous).
  - Range = NEGATIVE autocorrelation (next change more likely reverses previous).
  - KEY: aggregated, the two counterbalance → full sample shows ~zero autocorrelation. Unconditioned autocorrelation studies find nothing — a regime engine must CONDITION FIRST, then measure.
- p.438-439 — Core task definition: "it must be possible to define a set of conditions that will have some predictive value for autocorrelations over a finite time horizon... to identify the most likely emerging volatility environment." Post-hoc trend/range splitting is circular ("dividing random numbers into those greater and less than zero..."). Regime classification must be a priori.
- p.439 — Volatility clustering (the one robust nonrandom feature): "large price changes are much more likely to be followed by more large changes." High-vol environments persist after shocks. Direction unpredictable; MAGNITUDE of next change predictable — "severe violation of random walk."
- p.439-440 — ARCH/GARCH/EGARCH capture this (Campbell/Lo/MacKinlay 1996, Tsay 2005); shocks decay "like waves from a stone thrown in a pond." Usable as regime-engine volatility-state machinery.
- p.486-487 — Definitions: "Mean reversion is the tendency for large moves to reverse themselves... Range expansion is the tendency for markets to continue in the same direction after a large move." Polar opposites; the program = quantify the conditions favoring one mode.
- p.445 — Baseline for engine design: "Markets usually trade with a high degree of randomness... The trader's job is to find those very few times when markets are something less than random." Default regime state = no-edge/random.
- p.423 — RWH: random walks describe daily-to-monthly "fairly well"; intraday violations eaten by costs; violations unstable, disappear after publication (Lo & MacKinlay 1999).

## Quantitative specifications (exact)
- p.448-449 — True Range/ATR: TR = range + gap beyond prior close. Averaging window: "values between 20 and 90 are probably most useful." Standardize each day's change as %ATR.
- p.449-450 — Historical volatility: stdev of daily returns over a window (20 cited) × √252 (√52 weekly, √12 monthly).
- p.450 — Standard Deviation Spike tool (primary standardized-move measure): (1) returns; (2) 20-day stdev of returns; (3) Spike = today's return ÷ YESTERDAY's 20-day stdev. Threshold: ">about 2.5 or 3.0 stands out as a large move." Even stable large-caps print 5–6 such "SD" moves/year (fat tails). IV tracks 20-day HV closely, so a spike surprising this also surprises the options market. Engine use: σ-spike ≥2.5–3.0 = volatility-shock / possible regime-transition trigger; shocks persist → shift engine into high-vol state with decay.
- p.447-448 — Standardization: % returns (log ≈ simple for small moves); never compare nominal changes across assets.
- p.507-508 — Objective swing definition (structural primitive): legs AB = setup, BC = retracement, CD = extension. Swings = "first level pivot highs and lows, qualified by a movement of a certain ATR away from those pivots" — pivot + ATR-filtered zigzag, zero subjectivity.
- p.506-507 — Swing ratios: Retracement = BC/AB; Extension = CD/AB, % of setup leg.

## Empirical results
- p.510 — Raw retracement stats (2000–2010): Equities N=152,863 mean 122.1%, median 98.4%; Futures N=4,832 mean 124.9%, median 98.8%; Forex median 96.6%; RANDOM WALK median 99.9%. Real markets indistinguishable from random on unfiltered swing ratios — median retracement ≈ 100% of prior leg. No Fibonacci clustering.
- p.485 — MAs "do not... function as significant support or resistance levels." p.411-412: "Trend indicators are unreliable... some of the common trend indicators put you, very reliably, on the wrong side of the market."
- p.463-467 — Day-of-week false-edge worked example: Monday effect <1/5 SD = noise; year-over-year unstable.
- p.492 — Baseline drift (2001–2010): stocks mean daily +5.6bp, stdev 248.7bp, Up% 50.07; futures +2.7bp, stdev 144.0bp, Up% 50.59; forex +1.7bp, Up% 51.00. Hurdle rates any signal must beat.
- p.495 — Currencies approximate random walks most closely.
- p.425-426 — Fat tails: DJIA 2000–2010: 8 days of <1-in-a-million-under-normality moves; 1987 = 22σ. Never assume normality for risk.

## Methodology rules (for building/validating the engine)
- p.498-500 — Pythia event-study protocol: (1) per-market baseline stats as hurdle; (2) precise zero-subjectivity signal, tested symmetrically long/short; (3) enter at signal-bar close, record returns bars +1..+20; (4) compare each post-signal bar's distribution vs baseline with significance tests. Rejects P&L-style backtests as pattern tests (joint entry+exit test, no significance).
- p.488 — Non-stationarity: test any edge across multiple volatility regimes (his window deliberately spans low-vol 2001-06, crisis 2007-08, recovery 2009-10).
- p.489 — Correlated events: 1.38M stock-days NOT independent; effective sample far smaller.
- p.489, 496 — Calibrate against random data: i.i.d. normal, bootstrapped DJIA returns, and a GARCH model as nulls (MT19937). Patterns visible in random charts are the null.
- p.480-483 — Overoptimization defense: 1–2 qualifying conditions; single-use OOS; report "X out of Y" not percentages below N≈20.
- p.466-467, 477 — p-thresholds 5%/1%; t-test assumptions violated → prefer nonparametric; rough rule mean ≥2 SD from zero. Monte Carlo: trailing stops on a random walk = exactly zero edge.
- p.411-412 — Bias discipline: daily signals AGAINST the HTF trend can mark where the trend is ending — don't hard-filter counter-trend signals. A bias must be visible in the market and falsifiable.

Note: the actionable trend/range classification tests and Keltner specs follow after p.510 (Ch.13+; see raw_workbook_p511-609.md).
