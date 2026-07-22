# Raw extraction — Grimes Course Workbook, PDF pages 1–102
Source: `the-art-and-science-of-trading-course-workbook-2082206344-1948101017.pdf` (609 pp)
Extracted 2026-07-22 (session S81) for the regime-engine build. Page numbers = PDF page index.
Note: pages 17–35 and 79–102 are chart-image exercise pages with no text layer (nothing extractable).

## Quantifiable chart/indicator specifications

- **p.14 — Grimes's canonical chart setup:**
  - Modified Keltner Channels: **2.25 Average True Ranges around a 20-period exponential moving average**.
  - Modified MACD: uses **simple** (not exponential) moving averages, settings **3-10-16**, **no histogram**.
  - Same setup used across all markets and all timeframes (monthly to 5-min) — deliberately timeframe-invariant.

- **p.36 — Swing/reversal flip criteria (candidate regime-state-change triggers, listed as equivalent options):**
  - Fixed price movement (point-and-figure style; must scale to instrument price).
  - Crossing a short-term moving average.
  - Parabolic Stop-and-Reverse.
  - **Reversal of a certain number of ATRs off a high or low** ("effectively the same as the Parabolic").
  - Market makes an **N-bar high or low**.
  - Guidance: choice of flip criterion is not critical; keep it simple.

- **p.64 — Grimes's own hand-kept intraday swing chart definition:** swing flip = price moves **a distance equal to 3 average bar ranges (percentage of intraday ATR) off a swing high/low**. Directly codable ZigZag definition: 3x average-bar-range reversal.

## Statistical/empirical claims

- **pp.68-69 — Pullback retracement statistics:** test over "hundreds of thousands of swings across all major asset classes," retracement as % of previous swing:
  - Distribution peak ~**60%**; **mean ≈ 63% retracement, standard deviation ≈ 21%**.
  - Retracements "can kinda stop anywhere," but on average retrace "about half, maybe a little more."
  - **p.70:** anywhere between **~40% and ~80%** retracement is roughly equally likely — Fibonacci levels (61.8%) have no special power. Regime relevance: in a healthy trend, pullbacks retracing ~40–80% of the prior swing are normal, not trend failure.

- **p.67-68 — Measured move objective:** projecting the prior swing size forward is a volatility-anchored estimate of "reasonable" move size (basis for swing-symmetry expectations in trend legs).

- **p.40 — Edge magnitude:** real patterns give roughly **55/45**, not 80/20; "those types of edges simply do not exist on timeframes that human traders can trade."

- **p.7 — Whitepapers framing:** his tests found traditional TA tools "do not show an edge" — the course is built on tools that survived his testing.

## Market structure taxonomy / structural definitions

- **p.71 — Pivot definitions (foundation, directly codable):**
  - **First-order (simple) pivot high** = a bar with a higher high than both the preceding and following bar (mirror for lows).
  - **Second-order pivot high** = a first-order pivot high **preceded and followed by lower first-order pivot highs** (mirror for lows).
  - Hierarchy: pivots → swings → trends. Swings connect second-order pivots.

- **p.71 — Module 2 conceptual chain:** pivots → swings → trends → ends of trends → trading ranges → support/resistance → randomness/EMH. Trading ranges = "areas that seem to be controlled by support and resistance."

- **p.78 — Caveat:** buying every marked uptrend / shorting every marked downtrend is **not a stand-alone methodology** — swing analysis (HH/HL vs LH/LL) is a classification foundation, noisy on real data, not a signal.

- **p.8-10 — Course map:** Module III "Market Structure & Price Action" = Trend and Range / Trend to Range and Back Again / Tools for Trends / Ends of Trends / The Two Forces / Market Cycles. Reading plan points to first-book pages: 49–64 trends, 97–120 ranges, 121–148 trend↔range interfaces, 31–48 market cycles + four trades, 189–212 indicators, 409–424 MACD/MA deep dive.

## Bar-level classification heuristics (p.16)

Per-bar features (usable as a bar-feature vector):
- Position of open and close within the bar's range.
- Open vs close relative to each other.
- Bar range relative to previous bars (range expansion/contraction).
- Bar vs prior bars; "surprises" (deviations from expectation); action around obvious S/R.
- Caveat (p.13): chart-story thinking "does not respect the random variation in the market" — training tool only.

## Randomness / classification caveats

- p.40-41: humans manufacture patterns in random data; large-sample statistical evaluation required before trusting any classification.
- p.71: EMH treated as approximately-true baseline; exploitable structure lives in its failures.

## Densest usable specs from this range
Keltner 20EMA ± 2.25 ATR; MACD SMA 3-10-16; pivot order-1/order-2 definitions; ATR-multiple swing flip (3x avg bar range); retracement distribution mean 63% / SD 21% (normal-pullback band ~40–80%).
