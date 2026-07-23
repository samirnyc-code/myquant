# Grimes live-web research — current sites, published code, regime material
Fetched 2026-07-23 (S81). VERIFIED = page actually fetched; otherwise search-snippet only.

## Current web presence
- **adamhgrimes.com** — active blog (VERIFIED). Latest visible post Oct 9, 2025 ("Trading a Powerful Trend in Gold"); mid-2025 burst then apparent stall. Nav: Home, MarketLife, First Fire, About, Subscribe. NO indicators/downloads page anymore.
- **marketlife.com** — current paid platform (VERIFIED; marketlifetrading.com serves same content). Daily Market Insight ~$97–147/mo, free Discord, courses: First Steps (free), Options Trading, Pullback Masterclass, TradeCraft. The old free "Art & Science of Trading" course no longer found standalone (not verified).
- **adamgrimes.substack.com** — "First Fire", NON-trading (philosophy/consciousness).
- LinkedIn: "Talon Advisors" (snippet only). X: @AdamHGrimes.

## Published code / specs (the "easy code")
- **Official free-indicators downloads page is DEAD**: adamhgrimes.com/free-trading-indicators/ → 404 (VERIFIED).
- **Grimes Efficiency Ratio (GER)** — his own EasyLanguage code, on-page (VERIFIED, blog 2015-03-17 "A new tool to measure trend strength"):
  ```
  inputs: lookback(20);
  vars: rng(0), crng(0), sumrng(0);
  rng  = highest(h, lookback) - lowest(l, lookback);
  crng = iff(rng > 0, ((c - lowest(l, lookback)) / rng), 0);
  sumrng = average(crng, lookback);
  plot1(sumrng);
  ```
  ~1.0 strong uptrend, ~0.0 strong downtrend, mid = range. Uses: stop tightening, cross-market ranking, breakout candidates, fading extremes.
- **SigmaSpike** exact calc (VERIFIED, blog 2015-09-25): return = c/c[1]−1; 20-day stdev of returns; spike = today's return ÷ YESTERDAY's 20-day stdev. 2.5–3.0σ significant.
- **MAC Spike** (VERIFIED, blog 2023-11-17): today's |Δclose| ÷ yesterday's 20-day average |Δclose| — non-parametric SigmaSpike replacement (no normality assumption).
- **Volatility Compression** (VERIFIED, blog 2011-10-12): 5-day ATR ÷ 60-day ATR, reference 1.0; <1.0 = compressed → switch from fading to momentum mode. (Note: the workbook test used 5/40 < 0.5.)
- **Rvol relative volume** (VERIFIED, blog 2025-08-21): time-of-day sliced average volume, current/baseline ratio; no code published.
- Community implementations (specs verified where noted):
  - TradingView "Modified MACD" by modhelius (2017) — 3/10/16 SMA, credits App.B (VERIFIED description).
  - TradingView "Adam H Grimes - Keltner Channels with Day's High & Low" by Senthaamizh (2020) — 20-EMA ± 2.25×ATR (VERIFIED).
  - TradingView "SigmaSpikes(R) per Adam H. Grimes" by irdoj75 (snippet).
  - ThinkOrSwim: useThinkScript "Grimes Modified MACD" thinkscript by Kory Gill, 3/10/16 (snippet).
  - NinjaTrader: no free code found; commercial Remek! "Classic Pack" claims SigmaSpike + Modified MACD replication (VERIFIED page, no specs).
  - No GitHub repo found for any of it.

## Regime / intraday material (new vs 2012)
- **No published fully-systematic regime engine anywhere.** Closest artifacts: GER + 5/60 ATR compression ratio + an Aug 2025 13-item discretionary "When to Trade (And When to Stay Out)" imbalance checklist (VERIFIED): elevated short-term vol/volume vs recent, trending action/repeated candle colors, extension-then-consolidation, pattern breakouts, climax volume at levels, engulfing/outside bars.
- **"How I Trade" 1–2 (2023, VERIFIED):** focus "shifting ever more toward systematic approaches"; toolset unchanged in kind (one intermediate MA, Keltner over Bollinger, momentum + overextension); downplays parameter specifics ("no magic indicators").
- **Returned to day trading 2023** (VERIFIED): trades 1- and 5-minute charts after ~20 years away; deliberately withholds methodology. Related posts: "Intraday accumulation" (2023-05-20), "Snap Pullback" (2023-10-06, VERIFIED — renamed Anti: trend exhaustion → sharp countertrend snap → reluctant weak pullback → entry on break of recent resistance; S&P futures example, timeframe-agnostic, no stats), "Beyond the News: Breakout Behavior" (2023-10-09), "S&P futures activity by time of day" (2018-11-14).
- Snippet (unverified): watches 2-minute ES bars for Keltner touches intraday (tradingwithrayner interview).
- **Quant stance 2025** ("Brute Force, Bad Math", VERIFIED): Monte-Carlo-first; √t (not linear) range scaling example.
- Podcast "MarketLife Ep 20 – Market cycles and regimes" exists (not fetched).
