# GEX / Dealer-Positioning Strategy Ideas from the Public Web

**Compiled:** 2026-07-15 (web research session). Purpose: candidate mechanisms for backtesting
against our owned data. **Not** validated — every item below is a hypothesis to test.

## Our data inventory (referenced as data-fit flags below)

| Tag | Dataset |
|---|---|
| `MQ` | 1 yr daily MenthorQ levels: Call Resistance / Put Support / HVL, ES + SPX |
| `NGEX` | 365 days aggregate NetGEX + 1-yr GEX percentile |
| `SKEW` | 0DTE / 1M / 3M skew series |
| `QS` | QScore metrics |
| `ES5` | ES 5-minute bars 2021–2026 |
| `ODX` | SPX options EOD chains 2010–2023 (OptionsDX) — lets us **compute our own GEX, gamma flip, walls, DEX/vanna/charm** for a 13-yr backtest |
| `IB` | live paper trading (ES futures, SPX options) |

Key leverage point: `ODX` means most GEX-based ideas are backtestable over 2010–2023 with
self-computed exposures, then validated live over the last year with `MQ`/`NGEX`.

---

## TIER 1 — Immediately backtestable, strongest mechanism + evidence

### 1. Gamma-regime-conditioned last-30-min intraday momentum (Baltussen et al., JFE 2021)
- **Mechanism:** Dealers/leveraged-ETF hedgers short gamma must trade *with* the market into
  the close; rest-of-day return positively predicts last-30-min return, and the effect
  concentrates when aggregate gamma imbalance is negative. Reverts over next days.
- **Rule:** If NetGEX (or price < HVL) is negative and rest-of-day return (prior close →
  15:30 ET) is up (down), go long (short) ES 15:30–16:00 ET. Skip or fade on positive-gamma days.
- **Data:** `ES5` + `NGEX`/`MQ` (live year) + `ODX`-computed GEX (2010–2023 extension). **Fully owned.**
- **Sources:** [SSRN 3760365](https://papers.ssrn.com/sol3/papers.cfm?abstract_id=3760365), [PDF](https://academicweb.nd.edu/~zda/intramom.pdf), [Harbourfront summary](https://harbourfrontquant.substack.com/p/market-intraday-momentum-and-hedging)

### 2. HVL / gamma-flip regime switch: mean-revert above, momentum below
- **Mechanism:** Above the flip dealers are long gamma (sell strength / buy weakness →
  dampened, mean-reverting tape); below it they hedge with the move (amplified, trending tape).
  The most-cited GEX trading rule on the web.
- **Rule:** Run an intraday mean-reversion system (fade extensions toward VWAP/levels) only when
  ES > HVL; run breakout/trend-following only when ES < HVL. Test both legs separately against
  unconditional baselines.
- **Data:** `MQ` (HVL daily) + `ES5`; extend with `ODX`-computed zero-gamma level. **Fully owned.**
- **Sources:** [SpotGamma gamma flip](https://support.spotgamma.com/hc/en-us/articles/15413261162387-Gamma-Flip), [MenthorQ HVL guide](https://menthorq.com/guide/high-vol-level/), [gexboard](https://gexboard.com/learn/zero-gamma-gamma-flip), [BSIC](https://bsic.it/how-dealers-gamma-impacts-underlying-stocks/)

### 3. Gamma-flip crossing → volatility-expansion breakout
- **Mechanism:** Crossing below zero-gamma is a non-linear event: stabilizing dealer flows
  become destabilizing, hedge sizes accelerate near the flip; "price can drift near the flip
  for hours, then cross and move 1% in minutes." Known failure mode: "fake flips" on low volume.
- **Rule:** When ES crosses below HVL/flip intraday and holds N bars (e.g. 3×5-min closes)
  below, enter short (or long ATR-scaled breakout in break direction); stop back above the level.
  Symmetric long on upward reclaim. Filter: distance-to-flip and volume confirmation.
- **Data:** `MQ` + `ES5` + `ODX`. **Fully owned.**
- **Sources:** [FlashAlpha flip methodology](https://flashalpha.com/articles/gamma-flip-methodology-stable-zero-gamma-level), [Unusual Whales primer](https://unusualwhales.com/news/gamma-flip-a-primer), [Perfiliev GEX/zero-gamma calc](https://perfiliev.com/blog/how-to-calculate-gamma-exposure-and-zero-gamma-level/)

### 4. Call Resistance / Put Support fade (wall-to-wall range trade)
- **Mechanism:** Largest net call (put) gamma strike = dealers sell into rallies toward it
  (buy into declines toward it) → mechanical resistance/support. SpotGamma claims price closes
  within its 1-day estimated range ~78% of the time. Effect strongest in positive gamma / low VIX.
- **Rule:** In positive-gamma regime (ES > HVL, NetGEX percentile high): short first touch of
  Call Resistance, long first touch of Put Support, stop just beyond level, target mid-range/HVL.
  Condition on wall "density" (OI concentration) if computable from `ODX`.
- **Data:** `MQ` + `ES5`; wall recomputation from `ODX`. **Fully owned.**
- **Sources:** [SpotGamma Call Wall](https://support.spotgamma.com/hc/en-us/articles/15297391724179-Call-Wall-What-It-Is-and-How-SpotGamma-Uses-It), [Put Wall theory](https://spotgamma.com/the-theory-behind-put-walls/), [MenthorQ Call Resistance](https://menthorq.com/guide/call-resistance/), [FlashAlpha 3 levels](https://flashalpha.com/articles/call-wall-put-wall-gamma-flip-options-levels-explained)

### 5. Put Support breakdown continuation (level polarity flip)
- **Mechanism:** When Put Support breaks, dealer buying below it is exhausted/reverses; the
  broken level becomes resistance ("market makers begin selling futures to collect inventory")
  and price runs to the next level down — usually now in negative gamma, so moves amplify.
- **Rule:** If ES closes (5-min) below Put Support, short retest of the level from below;
  target next MenthorQ level / measured move; regime filter: NetGEX negative or price < HVL.
- **Data:** `MQ` + `ES5`. **Fully owned.**
- **Sources:** [MenthorQ trading levels lesson](https://menthorq.com/academy/trading-with-menthorq/lessons/futures-trading-and-key-levels/), [SpotGamma Put Wall](https://support.spotgamma.com/hc/en-us/articles/15297856056979-Put-Wall-What-It-Is-and-How-SpotGamma-Uses-It)

### 6. Gamma-regime-conditioned opening-range breakout / gap trade
- **Mechanism:** Same dealer-flow asymmetry applied to the open: in negative gamma the ORB and
  overnight gaps extend (hedging chases); in positive gamma gaps fade and breakouts fail
  (dealers fade moves; SPY +1% gaps fill ~60% of the time in aggregate).
- **Rule:** Negative-gamma day → trade ORB continuation / gap-and-go. Positive-gamma day →
  fade the gap toward prior close / sell opening-range extremes. Morning vol fades after ~11:00 ET.
- **Data:** `ES5` + `NGEX`/`MQ` + `ODX`. **Fully owned.**
- **Sources:** [SpotGamma GEX playbook](https://spotgamma.com/gex/), [SharePlanner gap study](https://www.shareplanner.com/blog/strategies-for-trading/fading-the-gap-how-large-overnight-moves-in-spy-and-qqq-play-out-during-the-trading-day.html), [OAS negative gamma](https://www.optionsanalysissuite.com/documentation/negative-gamma)

### 7. GEX percentile → next-day realized vol forecast (0DTE premium selling filter)
- **Mechanism:** High dealer gamma suppresses next-day realized vol. FlashAlpha's pre-registered
  8-yr SPY backtest: raw quintile spread Q5–Q1 = **−10.63 vol pts** (t = −13.0, Spearman −0.36,
  n = 1,971). **Caveat:** shrinks to −3.15 after VIX control and −0.99 (p = 0.25) after VIX+ATM IV —
  GEX is largely a vol-level proxy. Edge, if any, is in *calm* regimes; vanishes in top-VIX quintile.
- **Rule:** Sell 0DTE/1DTE SPX expected-move iron condors / strangles only when GEX percentile
  is high AND price > HVL; benchmark vs unconditional selling and vs a pure-VIX filter (the
  decisive test: does our NetGEX add anything after VIX/ATM-IV?).
- **Data:** `NGEX` percentile + `ODX` (13 yrs of chains → both signal and option P&L) + `IB`. **Fully owned.**
- **Sources:** [FlashAlpha 8-yr backtest](https://flashalpha.com/articles/gex-dex-vex-chex-8-year-backtest-spy-vix-control), [dev.to writeup](https://dev.to/tomasz_dobrowolski_35d32c/i-backtested-my-own-gex-product-across-8-years-of-spy-most-of-it-is-just-vix-a53), [Option Alpha 4 GEX profiles](https://optionalpha.com/videos/gamma-exposure-strategy-4-gex-profiles-for-spx-0dte-day-trading)

---

## TIER 2 — Backtestable with owned data, mechanism solid, evidence thinner

### 8. OPEX / 0DTE pin trade at the magnet strike
- **Mechanism:** ATM gamma is largest near expiry; dealers hedge toward the dominant-OI strike;
  max-pain convergence adds pull. Academic anchor: Ni–Pearson–Poteshman (JFE 2005) — optionable
  stocks cluster at strikes on expiration; returns altered ≥16.5 bps on average. Requires
  positive gamma + low realized vol; max-pain predictiveness concentrates in 0–3 DTE.
- **Rule:** After 14:00 ET on expiry days, if price is within ~0.3% of the max-gamma strike and
  regime is positive gamma: 0DTE butterfly centered at the magnet (or fade ES away-moves toward
  the strike into the close). Skip in negative gamma.
- **Data:** `ODX` (strike-level OI/gamma, 13 yrs of expirations) + `ES5` + `MQ`. **Fully owned.**
- **Sources:** [Ni-Pearson-Poteshman JFE](https://www.sciencedirect.com/science/article/abs/pii/S0304405X05000577), [SpotGamma pinning](https://support.spotgamma.com/hc/en-us/articles/15249421888787-Pin-Pinning-Effect-from-Gamma), [FlashAlpha 0DTE pin risk](https://flashalpha.com/articles/0dte-gamma-exposure-pin-risk-intraday-options-analytics), [StrikeWatch max pain](https://www.strike-watch.com/lab/max-pain-theory-options-expiration)

### 9. Post-OPEX "window of weakness" (Karsan/Kai Volatility, SpotGamma)
- **Mechanism:** Monthly OPEX removes large long-gamma/charm-supported positions → stabilizing
  dealer flows vanish for ~1 week (esp. between monthly OPEX and month-end / next VIX expiry).
  Call-heavy expirations were historically followed by trend reversals; Mon/Tue after triple
  witching show statistically elevated realized vol.
- **Rule:** From monthly OPEX close through +5 sessions: stand down on premium selling / range
  fading; favor long-vol or breakout systems; optionally short bias if the expiring board was
  call-heavy (measurable from `ODX` OI).
- **Data:** `ES5` + `ODX` (expiry calendar + OI mix). **Fully owned.**
- **Sources:** [SpotGamma window of weakness](https://spotgamma.com/july-opex-opens-the-window-of-weakness/), [Mutiny Fund Karsan interview](https://mutinyfund.com/cem-karsan/), [StrikeWatch OPEX cycle](https://www.strike-watch.com/lab/options-expiration-cycle-opex-gamma-dynamics)

### 10. Pre-OPEX vanna/charm drift (long into expiration week)
- **Mechanism (Karsan):** In the 1–2 weeks before monthly OPEX/VIX expiry, charm decays OTM put
  deltas and falling IV triggers vanna flows — dealers continuously buy back short futures
  hedges → persistent supportive bid ("vanna/charm rally"). Empirically the window is said to
  start the Monday of the week before OPEX week.
- **Rule:** Long ES from ~8 trading days before monthly OPEX to OPEX Wednesday, conditional on
  IV falling (our 1M skew/IV proxy) and positive/neutral gamma; exit before the window of weakness.
- **Data:** `ES5` + `ODX` (13 yrs of OPEX cycles; can compute vanna/charm exposures) + `SKEW`. **Fully owned.**
- **Sources:** [systematicindividualinvestor How To VANNA](https://systematicindividualinvestor.com/2020/11/05/how-to-vanna/), [MenthorQ vanna/charm guide](https://menthorq.com/guide/why-markets-can-go-wild-after-options-expiration-vanna-and-charm-and-the-volatility-effect/), [RCM/Derivative podcast](https://www.rcmalternatives.com/2020/10/vol-curves-and-vanna-charm-with-cem-karsan-the-derivative/), [TradingView OPEX window indicator](https://www.tradingview.com/script/mvEJiFm7-eksOr-Charm-Vanna-Window-Monthly-OPEX/)

### 11. Negative-GEX capitulation trough buying
- **Mechanism (SqueezeMetrics):** Capitulation lows occur in deeply negative gamma; once selling
  exhausts, short-gamma dealer buying accelerates the rebound. Deep sell-offs with negative/
  near-zero GEX flagged as strong buy alerts in DIX/GEX studies.
- **Rule:** When 1-yr GEX percentile < ~5% AND ES is X% below its N-day high (oversold), scale
  into long ES with multi-day hold; exit on GEX percentile mean-reverting above median.
- **Data:** `NGEX` percentile (1 yr live) + `ODX`-computed GEX percentile for 2010–2023. **Fully owned.**
- **Sources:** [SqueezeMetrics guide](https://squeezemetrics.com/monitor/static/guide.pdf), [financetldr DIX/GEX research](https://www.financetldr.com/p/research-dark-index-and-gamma-exposure), [Confirm Signal test](https://confirmsignal.substack.com/p/testing-squeezemetrics-gex-and-dix/comments)

### 12. Dealer-gamma overnight-hold filter (gap risk, low-VIX regimes)
- **Mechanism (Maurer, SSRN 2026):** Dealer gamma forecasts overnight gap magnitude *only in
  low-VIX regimes* (calm days, where HAR baselines are miscalibrated); pooling regimes washes
  the effect out — a concrete regime-split lesson.
- **Rule:** Only hold ES overnight (or sell overnight premium) when VIX is low AND NetGEX is
  high; avoid overnight exposure when NetGEX is negative even if VIX is calm.
- **Data:** `NGEX` + `ES5` (overnight bars!) + `ODX`. **Fully owned.**
- **Source:** [SSRN 6650858](https://papers.ssrn.com/sol3/papers.cfm?abstract_id=6650858)

### 13. MM inventory gamma as intraday vol forecast for position sizing (Dim–Eraker–Vilkov)
- **Mechanism:** 0DTE-inclusive market-maker net gamma is on average positive and *negatively*
  related to future intraday volatility; positive (negative) inventory gamma strengthens
  intraday reversal (momentum). Cboe: median 0DTE net gamma at 15:30 is small (+$173mm,
  range −$1.1bn to +$2.4bn) — so day-to-day sign flips matter more than levels.
- **Rule:** Not a directional signal — a vol forecaster: size any intraday ES system inversely
  to forecast vol = f(NetGEX); widen stops / shrink size on negative-gamma days.
- **Data:** `NGEX` + `ES5` + `ODX`. **Fully owned.**
- **Sources:** [SSRN 4692190](https://papers.ssrn.com/sol3/Delivery.cfm?abstractid=4692190), [Cboe 0DTE impact](https://www.cboe.com/insights/posts/volatility-insights-evaluating-the-market-impact-of-spx-0-dte-options/), [Cboe gamma squeezes PDF](https://cdn.cboe.com/resources/education/research_publications/gammasqueezes.pdf)

### 14. Gamma fragility: end-of-session return prediction from dealer delta changes (Barbon–Buraschi)
- **Mechanism:** Changes in options-market-maker delta positions significantly predict SPX
  returns at end of session; intraday momentum (reversal) is explained by negative (positive)
  ex-ante gamma imbalance *interacted with illiquidity*. Suggests conditioning idea #1 on a
  liquidity proxy (e.g. ES volume/range) improves it.
- **Rule:** Idea #1 with an added illiquidity interaction: only take the last-30-min momentum
  trade when negative gamma AND thin liquidity (low relative volume / wide range-per-volume).
- **Data:** `ES5` + `ODX`-computed gamma imbalance. **Fully owned.**
- **Sources:** [SSRN 3725454 Gamma Fragility](https://papers.ssrn.com/sol3/Delivery.cfm/SSRN_ID3807430_code2622157.pdf?abstractid=3725454&mirid=1), [BSIC explainer](https://bsic.it/how-dealers-gamma-impacts-underlying-stocks/)

### 15. 0DTE skew-steepening as intraday downside warning
- **Mechanism:** Skew steepens when put demand surges (spot-vol correlation); a sharp intraday/
  day-over-day steepening in 0DTE skew while in negative gamma implies hedging flows will chase
  a down-move (vanna: rising IV on OTM puts pushes dealer deltas shorter → they sell futures).
- **Rule:** If 0DTE 25Δ skew steepens > k std devs day-over-day AND price < HVL → short-bias
  day / no long mean-reversion entries; optionally short breakdowns of MenthorQ levels.
- **Data:** `SKEW` (0DTE/1M/3M) + `MQ` + `ES5`. **Fully owned** (live year); `ODX` for history.
- **Sources:** [GreeksLab 0DTE skew](https://greekslab.com/blog/what-is-volatility-skew-and-how-to-use-it-in-0dte-spx-trading), [Navnoor Bawa vanna/skew](https://medium.com/@navnoorbawa/vanna-and-volatility-skew-how-hedge-funds-extract-structural-alpha-from-the-greek-that-forces-14b69dcd0294), [OAS vanna/charm/vomma](https://www.optionsanalysissuite.com/documentation/vanna-charm-vomma-exposure)

### 16. Expected-move iron condor with gamma-regime gate
- **Mechanism:** Straddle-implied expected move overprices realized range on stable days (VRP);
  positive gamma mechanically compresses realized range, so the gate should raise win rate.
  Unconditional EM condors reported ~72.6% win rate; regime gate is the testable increment.
- **Rule:** Sell 0DTE SPX iron condor at ±expected move at open only when price > HVL and GEX
  percentile > 50; hard exit if price crosses HVL intraday (regime flipped against short gamma).
- **Data:** `ODX` (13 yrs option P&L) + `MQ`/`NGEX` + `IB`. **Fully owned.**
- **Sources:** [Income Options Trading 0DTE IC backtest](https://www.incomeoptionstrading.com/blog/zero-dte-ic-spx-backtest-returns-and-risk), [OptionsTradingIQ](https://optionstradingiq.com/option-omega/), [MenthorQ expected move](https://menthorq.com/guide/from-straddle-price-to-expected-move/)

### 17. HVL "fake flip" filter research
- **Mechanism:** Documented failure mode of idea #3: brief low-volume crossings of the flip
  reverse and trap traders; the level itself also shifts intraday. A confirmation layer
  (time-below, volume, distance) should separate real regime changes from noise.
- **Rule:** Study, not a standalone strategy: measure forward vol/drift after flip crossings
  bucketed by (a) minutes sustained, (b) relative volume, (c) gap between HVL and NetGEX sign.
- **Data:** `MQ` + `NGEX` + `ES5`. **Fully owned.**
- **Source:** [TradeEdgePro gamma flip guide](https://tradeedgepro.net/gamma-flip-level-2026/), [FlashAlpha methodology](https://flashalpha.com/articles/gamma-flip-methodology-stable-zero-gamma-level)

### 18. Friday-afternoon strike-magnetism scalps (weekly pinning)
- **Mechanism:** Same as #8 but on all Fridays/weeklies, not just monthly OPEX: gamma
  concentration at round strikes attracts price in the final 1–2 hours; strongest with high OI
  concentration and positive gamma. Weekly-options pinning is documented in follow-up academic work.
- **Rule:** Last 90 min on expiry days: fade moves away from the nearest high-gamma strike when
  within 0.25%, target the strike; skip if negative gamma or |distance| too large.
- **Data:** `ODX` + `ES5` + `MQ`. **Fully owned.**
- **Sources:** [Weekly options pinning paper (WPUNJ)](https://www.wpunj.edu/Weekly%20Options%20on%20Stock%20Pinning%20upto%20page%208.pdf), [Avellaneda–Lipkin pinning model](https://www.academia.edu/57931357/Mathematical_Models_for_Stock_Pinning_near_Option_Expiration_Dates)

---

## TIER 3 — Partially fits our data / weaker or contested evidence / infrastructure ideas

### 19. DIX + GEX combined multi-day swing signal
- **Mechanism:** High dark-pool buying (DIX) + negative GEX marks institutional accumulation
  into forced-selling lows; reported ~+9.7% annualized after high-DIX readings vs −3.5% after low.
- **Rule:** Long ES multi-day when DIX > 45% and GEX percentile low.
- **Data:** **Gap — we do not own DIX.** SqueezeMetrics publishes it free daily (downloadable
  history) → could be added cheaply.
- **Sources:** [SqueezeMetrics DIX](https://squeezemetrics.com/monitor/dix), [financetldr research](https://www.financetldr.com/p/research-dark-index-and-gamma-exposure), [joapen ML test](https://joapen.com/blog/2021/05/25/using-machine-learning-to-predict-the-sp-500-price-change-using-the-dark-pool-indicators-dix-and-gex/)

### 20. VIX-expiration-Wednesday cycle effects
- **Mechanism:** VIX expiry (Wednesday 30 days before next SPX monthly) unclamps vol-linked
  hedges; near-OPEX ATM gamma is 5–10× its level two weeks prior; the OPEX→VIX-expiry sequencing
  defines Karsan's flow calendar.
- **Rule:** Calendar dummy study on ES: returns/vol by position in the OPEX↔VIXpiration cycle;
  overlay on ideas #9/#10.
- **Data:** `ES5` + expiry calendar (public). **Owned.**
- **Sources:** [SpotGamma OPEX calendar](https://spotgamma.com/options-expiration-dates-vix-expirations-dates-download/), [StrikeWatch](https://www.strike-watch.com/lab/options-expiration-cycle-opex-gamma-dynamics)

### 21. GEX-vs-VIX residualization (research hygiene, applies to ALL ideas above)
- **Mechanism/lesson:** FlashAlpha's pre-registered backtest shows raw GEX→vol signals mostly
  collapse after controlling for VIX + ATM IV (residual ρ = −0.03, p = 0.18), and vanish entirely
  in the top VIX quintile. DEX/VEX/CHEX added nothing (VEX–VIX corr +0.72; VIX–ATM IV +0.91).
- **Rule:** Every backtest we run must report the signal's edge *after* a VIX/ATM-IV control
  (double sort or residual), else we're likely re-buying VIX.
- **Data:** need VIX daily (public/free) alongside owned sets.
- **Source:** [FlashAlpha 8-yr backtest](https://flashalpha.com/articles/gex-dex-vex-chex-8-year-backtest-spy-vix-control)

### 22. Where does gamma hedging bite intraday? (timing-of-day study)
- **Mechanism:** AFA working paper asks *where* in the day gamma hedging moves the market —
  hedging pressure is not uniform; concentration near open/close. Useful to localize ideas
  #1/#6 to the right windows.
- **Rule:** Bucket ES 5-min returns by time-of-day × gamma regime; find the windows where
  regime spread is largest before committing capital.
- **Data:** `ES5` + `NGEX`/`ODX`. **Fully owned.**
- **Source:** [AFA paper](https://afajof.org/management/viewp.php?n=129472)

### 23. QScore × GEX interaction (vendor-specific composite)
- **Mechanism:** MenthorQ pitches combining volatility QScore with GEX regime to pick strategy
  type (their "GEX meets Q-Score" framework). Vendor logic, unaudited — but we own both inputs,
  so it's a free interaction term in any regime model.
- **Rule:** Add QScore as a second sort variable on ideas #2/#7/#16; keep only if it adds after
  VIX controls (#21).
- **Data:** `QS` + `NGEX` + `MQ`. **Fully owned.**
- **Source:** [MenthorQ GEX meets Q-Score](https://menthorq.com/guide/gex-meets-volatility-q-score/)

### 24. MenthorQ 1D-move level backtest replication
- **Mechanism:** MenthorQ publishes its own backtest of 1-day expected-move levels on SPX
  (bounce/rejection rates at their levels). Replicating it on our year of stored levels
  validates the vendor's claims out-of-sample and calibrates ideas #4/#5.
- **Rule:** For each stored level type: P(touch), P(reverse ≥ X pts | touch), P(close beyond),
  by gamma regime.
- **Data:** `MQ` + `ES5`. **Fully owned.**
- **Source:** [MenthorQ 1D move backtesting](https://menthorq.com/guide/backtesting-results-1d-move/)

### 25. Compute-our-own-GEX historical library (enabler, not a strategy)
- **Mechanism:** Perfiliev publishes the standard open methodology (naive dealer assumption:
  long calls/short puts customers → GEX = Σ gamma·OI·spot²·0.01 with put sign flip; zero-gamma
  via root-finding). Applying it to `ODX` 2010–2023 gives 13 years of NetGEX, flip, walls,
  vanna/charm — the backbone for backtesting every idea above beyond our 1 live year.
- **Rule:** Build `gex_history.parquet` from `ODX`; validate the overlap year against MenthorQ/
  our NetGEX feed before trusting the history.
- **Data:** `ODX`. **Fully owned.**
- **Sources:** [Perfiliev how-to](https://perfiliev.com/blog/how-to-calculate-gamma-exposure-and-zero-gamma-level/), [SqueezeMetrics guide](https://squeezemetrics.com/monitor/static/guide.pdf)

### 26. LLM/ML composite dealer-positioning models
- **Mechanism:** Recent arXiv work (obfuscation-tested LLM detection of GEX patterns; ML market-
  trough prediction with causal interpretation using GEX among features) suggests GEX matters
  most as one feature in a conditional model, not standalone.
- **Rule:** Long-horizon idea: gradient-boosted regime classifier on {NetGEX pct, skew slope,
  QScore, VIX, distance-to-HVL} predicting next-day |return| and sign of last-30-min drift.
- **Data:** all owned sets + VIX. **Mostly owned.**
- **Sources:** [arXiv 2512.17923](https://arxiv.org/pdf/2512.17923), [arXiv 2509.05922](https://arxiv.org/pdf/2509.05922)

---

## Published empirical benchmarks to verify against our own data

1. **Baltussen et al. (JFE 2021):** rest-of-day return predicts last-30-min return across 60+
   futures 1974–2020; significant, reverts over following days; strongest when gamma imbalance
   negative. → Reproduce on ES 2021–2026 with our NetGEX split.
2. **FlashAlpha (2026, pre-registered, n=1,971 SPY days):** GEX vs next-day RV: raw Spearman
   −0.36 / Q5−Q1 = −10.63 vol pts; after VIX+ATM IV: ρ −0.03 (dead); no edge in top VIX quintile.
   → Run the identical residualization on our NetGEX; if ours survives, that's real product edge.
3. **Ni–Pearson–Poteshman (JFE 2005):** expiration-date strike clustering; avg return distortion
   ≥16.5 bps. → Test SPX distance-to-max-gamma-strike convergence on expiry afternoons in `ODX`.
4. **Dim–Eraker–Vilkov (0DTE):** MM net gamma on average positive, negatively related to future
   intraday vol; positive gamma → stronger reversal, negative → momentum.
5. **Cboe (2023-24):** 0DTE median net gamma at 15:30 ≈ +$173mm (−$1.1bn to +$2.4bn), ~1.3–1.9%
   of ES daily notional → 0DTE flow usually balanced; tail days are what matter.
6. **Maurer (SSRN 2026):** dealer gamma forecasts overnight gaps only in low-VIX regimes —
   always split backtests by vol regime before concluding "no effect."
7. **SpotGamma claim:** market closes within their 1-day est. range 78% of the time → measure
   the equivalent stat for MenthorQ Call Resistance/Put Support on our year.
8. **Gap stats:** SPY +1% gap-ups fill ~60% of the time unconditionally → measure conditional on
   gamma regime.
