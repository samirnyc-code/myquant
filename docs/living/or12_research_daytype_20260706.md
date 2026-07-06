# Day-type / context classification research — agent findings (S60, 2026-07-06)

Two web-research agents (academic/quant + practitioner) gathered methods for
programmatically identifying day type and context in real time (first 60 min)
for ES. Full agent transcripts summarized here; this doc is the durable record.

## The consensus that matters

**Morning predicts CHARACTER, not DIRECTION.** Every serious source agrees:

- arXiv 2605.11423 (MNQ vol/volume/gap classifier, 947 days, walk-forward):
  regime classes descriptively distinct; ALL directional strategies fail costs
  + year-stability.
- Gao et al. "Market Intraday Momentum" (JFE 2018): first-30-min → last-30-min
  predictability decayed ~75% post-publication; driven by hedging flows.
- futures.io prop trader: predicting day type ahead of time is "ABSURD";
  pragmatic consensus = binary directional-vs-rotational call in first 30 min.
- Matches our own S60 result: twins predict close-vs-IB at 39-40% vs 34%
  chance (p<.001) but direction = coin flip.

**Full Brooks mechanization has a documented public failure:**
github.com/nicksung369/brooks-pa-failure — 25 setups + always-in + 8 filters
coded from the books: +60.7%/360d at zero fees → −59.1% with 0.04%+0.01%
costs; monotonically worse with more data (30d −2.3% → 2y −210.8%).
Elite Trader reached the same verdict: bars are easy to code, context isn't.

## Documented ES effect sizes (steal these as baselines — twins must BEAT them)

TradingStats IB study (2,686 ES days 2015-25, IB = 9:30-10:30 ET):

- 97.8% of days break IB at least once; 28.7% break both sides.
- **IB width vs 14d ATR**: <0.5×ATR → 98.7% break, 74.8% median extension;
  >1.5×ATR → 66.7% break, 22.3% extension. Strongest known conditioner.
- **IB extreme formation order**: IB-high-first → break down 44.8% vs up 24.0%
  (mirror for low-first). ~2:1 causal directional skew, computable at 10:30.
- C-period (10:30-11:00) close outside IB ≈ doubles 100%-extension odds
  (45.5% vs 18.8%).
- First breakouts fail (close back inside) 34%; retrace depth after breakout
  <25% → 93.8% close in breakout direction; ≥50% → 24.8%.
- HOD or LOD forms in the first 60 min ~75% of the time (TPO folklore,
  multiple sources).

ES day-type base rates (nexusfi, mechanical defs): **Normal Variation 54%,
Neutral 25%, Trend 16%** — "predict mean-reversion always" is the 80/20 prior.

## Mechanical taxonomies worth adopting

**Day types (MWG86/Brewer, futures.io):**

- Trend: RTH range > ~1.1-1.2× ADR AND close within 25% of day extreme
- Neutral: BOTH IB sides broken (center = closes mid-range; extreme = at extreme)
- Normal variation: one IB side broken, range < 2× IB
- Normal / non-trend: neither IB side broken (narrow IB variant = non-trend)

**Open types (Marketcalls / Dalton, programmatic):**

- Open Drive: opens outside prior VA+range, one-sided, never re-trades the
  open → directional day odds jump
- Open Test Drive: probes a reference opposite, reverses through open
- Open Rejection Reverse: drives, reverses back through opening range
- Open Auction In Range: rotates around open inside prior VA → rotational

**RVOL (universal practitioner convention):** cumulative volume since open ÷
avg cumulative volume at same time-of-day, 10-20 day lookback, per-slot (NOT
full-day avg — U-curve bias). Thresholds: >1.5 elevated, >2.0 conviction,
<1.0 skip breakouts / expect rotation.

**One-time-framing (15/30M):** OTF-up = every bar's low > prior bar's low;
break = state off. Real-time non-repainting always-in proxy; Raschke trend-day
signature = minimal retracement + acceleration.

**Raschke trend-day preconditions:** NR7, 2-3 narrow days, inside day, hook
day, large gap → expansion expected (NR7 alone ≈ 57% weak; conditioning
variable, not signal).

**Gap buckets (btcLeft, 2,646 ES days):** Tiny <0.3×ATR / Small 0.3-0.7 /
Medium 0.7-1.2 / Large >1.2, × direction. Small gaps: 80%+ fill by noon;
large gaps outside prior range = trend fuel, don't fade.

**Lorentzian distance** (jdehorty/LuxAlgo kNN scripts): log(1+|Δ|) per feature
instead of Euclidean — compresses CPI/FOMC outlier days in similarity space.

## Academic upgrades queued

1. **Li & Liu functional classification w/ dynamic partial-curve updating**
   (Energy 2023 + IJF 2025 mixture follow-up) — THE formalization of query
   mode: probabilistic cluster membership of the partial day-curve, updating
   bar by bar. FPCA scores of first-hour curve = compact 3-5 number fingerprint.
2. **HMM filtered P(trend-state | bars so far)** (arXiv 2006.08307, 1-min ES)
   as a continuous trendiness score.
3. ATR-normalize the path (not IB-range) so vol regimes are comparable.
4. Tajmouati k-NN: CV-select k and window — discipline against analog overfit.
5. Skip TS2Vec/CLIP-class embeddings — no demonstrated edge, wrong data scale.

## Warnings ledger

- "Narrow IB → extension" is near-tautological when extension is measured in
  IB multiples — use ADR-denominated outcomes too.
- Vendor day-type indicators (TradeDevils PATS, Price Action Pro, Indicator
  Warehouse) publish NO backtests — internals are hypotheses only.
- Cost sensitivity: 0.05% RT flipped a Brooks system by 120pp. Our $5 RT MES
  reality applies to anything tradable that comes out of this.
- kNN/Lorentzian TradingView scripts: repaint/overfit complaints, no forward
  stats. Take the distance metric, not the hype.

Key URLs: futures.io/traders-hideout/56023, futures.io/emini-emicro-index/57209,
nexusfi.com/showthread.php?t=44002, tradingstats.net/initial-balance-breakout-statistics,
github.com/nicksung369/brooks-pa-failure, arxiv.org/pdf/2605.11423,
ssrn.com/abstract=2440866, sciencedirect.com/science/article/abs/pii/S0360544223027494,
marketcalls.in/market-profile/market-profile-open-type-and-confidence.html,
traderslog.com/capturing-trend-days, edgeful.com/blog/posts/gap-fill-report,
tradingview.com/script/32pGGSWx, luxalgo.com/library/indicator/knn-market-architecture
