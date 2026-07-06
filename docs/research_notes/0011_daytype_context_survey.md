# 0011 — Programmatic Day-Type & Context Identification: What the World Knows — 2026-07-06

**Series:** MC Setup Research Notes · Note 0011
**Confidence:** n/a (survey, not a study) — sources individually graded below; documented ES effect sizes are third-party and unaudited by us until replicated (0012 queued).
**TL;DR:** Two research agents swept academic literature and practitioner sources (arXiv/SSRN, futures.io, Elite Trader, Reddit-adjacent forums, GitHub, TradingView) for programmatic, real-time day-type and context classification methods for index futures. Consensus across both worlds: **the morning tells you day CHARACTER (trend vs rotation, extension odds), never direction**; the strongest documented conditioners are **IB width vs ATR** and **open location vs prior day**; the six-way Dalton taxonomy is only knowable in hindsight, but a binary directional-vs-rotational call in the first 30–60 min is community-endorsed; and the one public attempt to fully mechanize Brooks price action lost −59% to −211% after costs. This note is the durable catalog: methods, thresholds, effect sizes, failures, and what we adopted into the OR12 tool (note 0010).

## 1. The setup (so this note stands alone)

We are building the OR12 twin-day/context tool (note 0010): fingerprint the first 60 minutes of the ES session (12 five-minute bars = the Initial Balance, IB) plus prior-day context, and support a real-time context read. Before investing further, we sent two web-research agents out with complementary briefs:

- **Agent A (academic/quant):** arXiv, SSRN, journals, quant blogs — intraday path clustering, IB research, TPO auto-classification, analog forecasting, HMMs, embeddings.
- **Agent B (practitioner):** futures.io/nexusfi, Elite Trader, TradingView scripts, GitHub repos, trading blogs — what people actually built, with community verdicts.

Everything below is third-party; nothing is our own measurement unless marked. Full URL list at the end and in `docs/living/or12_research_daytype_20260706.md`.

## 2. The question

How do others programmatically identify day type and market context **in real time** (early in the session, causally), what effect sizes are documented for ES specifically, and what has demonstrably failed?

## 3. How we searched

1. Agent A: 7-topic academic sweep (shape clustering, IB stats, TPO rules, open types, volume/volatility regimes, k-NN analogs, HMM/embeddings) with instructions to report methods + effect sizes + negative results.
2. Agent B: 8-topic practitioner sweep (futures.io day-type threads, Brooks mechanization attempts, ORB/IB heuristics, gap systems, RVOL conventions, analog-day tools, platform indicators, Mack/PATS) with instructions to report actual rules + community verdicts.

## 4. Findings

### 4.1 The documented ES effect sizes (the numbers worth stealing)

**TradingStats IB study — 2,686 ES days, 2015–2025, IB = 9:30–10:30 ET** (tradingstats.net):

| Finding | Numbers |
| --- | --- |
| IB breaks at least once | 97.8% of days (28.7% break both sides) |
| **IB width vs 14d ATR** | <0.5×ATR → 98.7% break, 74.8% median extension; >1.5×ATR → 66.7% break, 22.3% extension |
| **IB extreme formation order** | IB-high-first → break down 44.8% vs up 24.0% (mirrored for low-first) — ~2:1 causal skew at 10:30 |
| C-period (10:30–11:00) close outside IB | ~doubles 100%-extension odds: 45.5% vs 18.8% |
| First breakout fails (closes back inside) | 34% (downside breaks fail more: 53.2% vs 45.2%) |
| Post-breakout retrace depth | <25% → 93.8% close in breakout direction; ≥50% → 24.8% |
| HOD or LOD forms in first 60 min | ~75% of days (multiple sources) |

Grade: retail-adjacent source, no significance tests — but large-n, ES-specific, and the two headline features (width, formation order) are trivially causal. **Adopted into OR12 v5** (`ib_atr`, `ib_high_first`); replication on our own 2021–26 data queued as note 0012 (`scripts/or12_baserate_tables.py`).

**ES day-type base rates** (nexusfi, mechanical definitions, 2011–13): Normal Variation 54%, Neutral 25%, Trend 16% — "~1 trend day per week; ES is a mean-reversion instrument." Our own 2021–26 labels came out 54/21/23 (note 0010 §4.4) — the taxonomy transfers across regimes.

### 4.2 Mechanical taxonomies (rules you can code today)

**Day types (MWG86, futures.io):** Trend = RTH range > ~1.1–1.2× ADR AND close within 25% of the day's extreme. Neutral = both IB sides broken (center vs extreme by close location). Normal variation = one side broken. Normal/non-trend = IB holds. **Adopted as outcome labels in 0010.**

**Open types (Dalton, programmatic sketches — Marketcalls, ParaCurve):** Open Drive = opens outside prior value+range, one-sided, never re-trades the open (highest conviction); Open Test Drive = probes a reference opposite then drives back through the open; Open Rejection Reverse = drives then reverses back through the opening range; Open Auction In Range = rotates around the open inside prior value (rotational day expected). Nobody publishes thresholds or hit rates — best encoded as *features* (open-revisit flag, drive efficiency), which we did in OR12 v6.

**RVOL (universal convention):** cumulative volume since open ÷ average cumulative volume *at the same time of day*, 10–20 day lookback, per-slot (never full-day average — U-curve bias). Thresholds in common use: >1.5 elevated, >2.0 conviction, <1.0 skip breakouts/expect rotation. First 15–30 min RVOL + one-sided price = the community's trend-day tell.

**One-time-framing (15/30M):** OTF-up = every bar's low above the prior bar's low; broken = state off. The simplest non-repainting real-time trend-state machine; matches Raschke's trend-day signature (minimal retracement, acceleration late).

**Trend-day preconditions (Raschke/Crabel):** NR7, 2–3 consecutive narrow-range days, inside day, hook day, large gap → expect range expansion. Quantified verdict on NR7 alone: ~57% next-day breakout win with symmetric payoffs — a conditioning variable, not a signal.

**Gap buckets (btcLeft indicator, 2,646 ES days 2014–24):** gap at RTH open in ATR units — Tiny <0.3× / Small 0.3–0.7× / Medium 0.7–1.2× / Large >1.2×, crossed with direction; small gaps: 80%+ fill by noon; large gaps outside prior range are trend fuel — don't fade.

### 4.3 Academic methods (the formal upgrades)

- **Functional classification with dynamic partial-curve updating** (Li & Liu, Energy 2023; mixture-model follow-up IJF 2025): treat the day's cumulative 5-min return path as a function; probabilistically classify the *partial* curve into historical clusters, refining bar-by-bar; prediction error drops as the day unfolds. **This is the OR12 tool formalized, and the strongest queued upgrade** — it also gives intra-morning updating instead of a single 9:30 snapshot.
- **HMM with side information on 1-min ES** (Christensen et al., arXiv 2006.08307): filtered P(trend-state | bars so far) as a principled continuous "trendiness" score; simulation-grade evidence only.
- **FPCA on intraday curves** (Jasiak 2026, crypto): the first-hour curve compressed to 3–5 FPCA scores — a compact fingerprint alternative.
- **Multi-scale k-means on intraday shapes** (Physica A 2020): descriptive validation that intraday curves cluster meaningfully.
- **k-NN forecasting discipline** (Tajmouati et al.): CV-select k and window length — the guard against analog-tool overfitting.
- **Embeddings (TS2Vec-class): skip** — no demonstrated intraday-futures edge; wrong data scale for 12 bars. (Mirrors our S57 CLIP dead-end.)

### 4.4 The failures ledger (as valuable as the wins)

- **Full Brooks mechanization, public postmortem** (github.com/nicksung369/brooks-pa-failure): 25 setups + always-in + 8 filter layers coded from the books. +60.7%/360d at zero fees → **−59.1% with 0.04%+0.01% costs**; monotonically worse with more data (2y: −210.8%). Author's conclusion: "mechanizing textual price action rules produces noise, not edge." Elite Trader reached the same verdict a decade earlier: **bars are easy to code, context isn't.**
- **Morning→afternoon direction is the graveyard.** arXiv 2605.11423 (MNQ, walk-forward): regime classes descriptively distinct, all directional strategies fail costs + year-stability. Gao et al. (JFE 2018) intraday momentum decayed ~75% post-publication; attributed to hedging flows. Matches 0010: our twins predict direction at exactly 50%.
- **"Day type is only knowable in hindsight"** is a live practitioner objection (futures.io prop trader: predicting it ahead of time is "ABSURD"); pragmatic consensus = collapse to binary directional-vs-rotational in the first 30 min.
- **Near-tautology warning:** "narrow IB → extension" partly restates that extension is measured in IB multiples — validate with ADR-denominated outcomes too.
- **Vendor internals ≠ tested rules:** commercial day-type/PATS indicators (TradeDevils, "Price Action Pro", Indicator Warehouse) describe plausible logic, publish zero backtests.
- **TradingView kNN scripts** (Lorentzian Classification et al.): popular, repaint/overfit complaints, no forward stats. We A/B-tested their one transferable idea — Lorentzian distance — and it *lost* to Euclidean on our 80-dim fingerprint (0010 §4.1).
- **Cost sensitivity is brutal:** a 0.05% RT cost assumption flipped a system by 120 percentage points. Directly relevant to our $5 RT MES reality.

### 4.5 Analog-day prior art (query mode's competition)

Almost nothing serious exists publicly: Intraday Seasonals (template matching, Larry Williams lineage), TradingView kNN indicators (bar-level, not day-level), and no polished "show me the 10 most similar ES days and what happened next" product. **The tool we're building is genuinely under-built in public.**

## 5. Synthesis

Both worlds — peer-reviewed and forum-battle-tested — independently converge on the same three statements: (1) opening structure encodes *auction condition* (participation, conviction, balance vs imbalance), which constrains how far the day travels and whether the IB holds; (2) the *side* that wins the afternoon is decided by flows the morning chart does not contain — every directional claim died in validation or decayed post-publication; (3) the usable real-time call is binary character (directional vs rotational), made with IB width, open location, RVOL, and open type — not the six-way Dalton taxonomy. Our own OR12 measurements (note 0010) reproduce all three statements on 2021–26 ES.

## 6. Recommendation

1. **Adopt the conditional base-rate card as the tool's foundation** — bucket × IB-width × formation order (+C-period confirm later). Replicate the TradingStats numbers on our own data before display (**note 0012, script already staged**).
2. **Queue exactly two formal upgrades** for the matcher — functional partial-curve classification (Li & Liu) and era-split weight calibration — under the 0010 stop-loss rule (freeze if walk-forward accuracy can't clear ~45%).
3. **Adopt the conventions**: per-slot RVOL (10–20d), OTF state, ATR-relative gap buckets, ADR-denominated outcomes alongside IB multiples.
4. **Never re-attempt full price-action mechanization** (Brooks or PATS) as a trading system — two independent public failures plus our own S55/0006 history close that road.
5. **Direction stays out of scope.** Any future directional claim must survive walk-forward AND beat the conditional card AND survive $5 RT + slippage.

## 7. Caveats & open questions

- Every §4.1 number is third-party and unaudited: different IB definition possible (9:30–10:30 ET vs our 08:30–09:30 CT — same hour), different eras, no significance tests. Note 0012 replicates on our data before anything is trusted on-screen.
- Agent coverage is one pass (July 2026); paywalled sources (SSRN full texts, futures.io attachments) were summarized from abstracts/threads.
- The C-period confirmation stat (extension odds doubling) conditions on 11:00 CT information — usable, but it's a *second* decision point, not part of the 9:30 fingerprint.
- Open-type taxonomies have no published thresholds anywhere — our operationalization (open-revisit, drive efficiency) is our own and unvalidated in isolation.

## 8. Reproduce

- Source digest with all URLs: `docs/living/or12_research_daytype_20260706.md`
- Companion study this survey fed: note 0010 (`0010_or12_fingerprint_daytype.md`) + `scripts/or12_pattern_groups.py`, `or12_outcome_agreement.py`, `or12_walkforward.py`
- Replication of §4.1 on our data (queued 0012): `scripts/or12_baserate_tables.py`
- Key external: tradingstats.net/initial-balance-breakout-statistics · nexusfi.com/showthread.php?t=44002 · futures.io/traders-hideout/56023 · github.com/nicksung369/brooks-pa-failure · arxiv.org/pdf/2605.11423 · ssrn.com/abstract=2440866 · sciencedirect.com/science/article/abs/pii/S0360544223027494 · marketcalls.in/market-profile/market-profile-open-type-and-confidence.html · traderslog.com/capturing-trend-days · edgeful.com/blog/posts/gap-fill-report · tradingview.com/script/32pGGSWx · luxalgo.com/library/indicator/knn-market-architecture
