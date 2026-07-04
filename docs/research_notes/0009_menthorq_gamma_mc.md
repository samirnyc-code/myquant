> ## ⚠️ CORRECTION PENDING — DO NOT SHARE (2026-07-04, same session, later)
> After this note was written, the MQ **dating convention was corrected**: rows are EOD
> levels that apply to the NEXT trading day; this note's joins were same-day (lookahead).
> All studies were re-run with the causal d→d+1 join. **Retracted from this note's
> conclusions:** the ≥3-level cluster watch item (flipped sign), the Call-Res containment
> excess, and D1 significance (direction survives, n.s.). **New post-correction finding
> not in this note:** the ⭐ MAGNET — stacked trades toward a main level ≤1R: +0.52 ExpR
> PF 2.75 n=43, survived a full deep-dive battery (see `docs/living/menthorq_magnet_deepdive_20260704.md`,
> `menthorq_magnet_continuation_20260704.md`, corrected tables in `menthorq_edge_study_20260704_tables.md`).
> A full rewrite of this note is pending; until then treat the living docs as authoritative.
# 0009 — MenthorQ Gamma Data × MC Edge — 2026-07-04

**Series:** MC Setup Research Notes · Note 0009
**Confidence:** Medium — 81 trading days of MenthorQ data (Mar 6 – Jul 2, 2026), 374 filled trades / 208 Stack-v2; full-cost sims on tick data; every hypothesis pre-registered before outcomes were seen; but the sample is one 4-month regime and the archive scalars have a timestamp caveat (§7).
**TL;DR:** We bought 3 months of MenthorQ dealer-gamma data (Call Resistance, Put Support, HVL, gamma walls, GEX strikes, blind spots, net GEX, QScores) and threw four rounds of pre-registered tests at it. **The levels are not intraday support/resistance** — they bounce no more often than random prices, and neither do prior-day H/L/C, VWAP, value areas, or the IB (nothing does, at the 5M scale, in this window). **"Don't trade into a level" is refuted** — those trades did *better*. The two things that survived: **negative-gamma days realize ~1.18× the implied expected move vs 0.96× on positive days** (gamma is a *volatility amplitude* dial, not a directional or level tool), and **trading into a ≥3-level cluster within 1R was flat-to-negative while everything else earned +0.19R** (top watch item). **No change to the frozen Stack v2 spec.** The data's future value is sizing/vol-conditioning, re-testable at 6–12 months.

## 1. The setup (so this note stands alone)

**The book being filtered.** MC ("MyMicroChannel") 5-minute breakout signals on ES, filtered by the S53 frozen "Stack v2" spec: skip counter-IB-break signals, skip days after a prior trend day (>1.6×ADR14), skip signals at/after 14:00 CT. Exits: 3R target, ratchet to break-even at +1R, flat by end of session. Costs everywhere in this note: 1-tick entry slip, 1-tick exit slip, 1-tick stop offset, $4.36 round-turn commission, ES $50/pt. R = |entry − stop|. Over 2021–2026 this book backtests ≈ +0.16R/trade; in this study's 4-month window it runs +0.157R ±0.166 (n=204–208 filled stacked trades, consistent with the long-run number).

**The data being tested.** MenthorQ publishes, per trading day, option-positioning levels for ES derived from dealer gamma exposure: **Call Resistance** (largest call-gamma strike, "dealers sell into strength there"), **Put Support** (largest put-gamma strike, "dealers buy dips there"), **HVL** (the gamma-flip level: above = positive dealer gamma = vol-dampening, below = negative = vol-amplifying), 0DTE variants, **Gamma Wall 0DTE**, ten **GEX strikes** (25-pt option strikes with big exposure), ten **Blind Spots (BL)** (proprietary levels), plus daily scalars: net/total/expiring GEX, P/C ratios, IV30, 1-day expected move %, a Positive/Negative **gamma condition** flag, and four 0–5 **QScores** (option, momentum, volatility, seasonality). We back-filled **82 daily snapshots (2026-03-06 → 2026-07-02)** via their API into `data/menthorq/menthorq_levels.csv` (81 usable after joining to bar data).

**Price-space alignment (matters!).** Our bars/signals/ticks are back-adjusted continuous; MenthorQ levels are front-contract prices. Measured per-contract offsets from actual contract bars: **ESH6 +111.00, ESM6 +61.25, ESU6 +0.00** (each constant within its period, matching NT rollover records). All levels were shifted into continuous space before any distance was computed. Skipping this step would mis-place every level by 50–110 points.

## 2. The question

Does dealer-gamma positioning data improve the MC entry edge — as level S/R, as an entry filter (don't trade into levels / trade break-and-retests / avoid clusters), or as a day-regime dial? And a method question underneath: *at what unit (touch, trade, day) does this data even have a chance of showing value?*

## 3. How we tested it

All hypotheses were **pre-registered** (direction declared before looking at outcomes), coarse bins only, all cuts reported. Across the study we ran ~50 cuts — expect ~4–5 spuriously "significant" rows by chance; single-cut stars are treated accordingly.

1. **Stage 0 — data hygiene:** roll-offset alignment; are the fields causal (pre-market) or EOD-stamped?
2. **Stage 1 — level S/R touch test:** 5M touch → bounce/break within 6 bars (3-pt threshold), ~2,000 real touches vs matched random controls.
3. **Stage 2 — trade-level pre-registered tests (T1–T5):** headwind/tailwind, gamma regime, QScores, IV/expected-move, the high-vol∧neg-gamma combo — on the stacked book with frozen exec.
4. **Follow-up A (user challenge: "main levels must have merit"):** day-range **containment** vs a distance-matched benchmark; first-touch-to-EOD outcomes (T-A/T-B/T-C).
5. **Follow-up B (user rules):** U1 "never trade into a main level" (≤1R), U2 break-and-retest, U3 clusters, U4 expanded universe (prior-day H/L/C, VA, IB, VWAP) as the interpretive anchor.
6. **Follow-up C (day as the unit, n=81):** D1 gamma vs realized/implied range, D2 gamma vs trendiness, D3 corridor geometry, D4 expiring-GEX pinning, D5 book day-P&L by regime.

## 4. Results

### 4.1 Stage 0 — hygiene findings that gate everything else

- `1d_max`/`1d_min` are an **expected-move band** (width ≡ 2× expected move, ratio 1.00; realized range fully inside 78% of days) — a *forecast*, causal, usable.
- **⚠️ The archive rows are EOD-stamped**: `distance_to_hvl_%` matches the SAME-day close (median error 0.05pp) not the prior close (0.46pp). The OI-derived *levels* are computed from prior-day close data and static intraday (causal), but the archived `gamma_condition` and QScores may embed same-day information. Every regime/score test therefore has a **causal prev-day variant**, and live use requires **pre-market capture** (the app's Refresh button) — do not trust backfilled same-day scalars.

### 4.2 Stage 1 — are the levels intraday S/R? **No.**

Touch = 5M bar crosses the level; bounce = ≥3-pt rejection without a 3-pt penetration within 6 bars; controls = random in-range prices (or other 25-pt strikes for GEX), ≥5 pts from any real level, seeded.

| level group | touches | bounce% | break% | ctrl bounce% | bounce diff 95% CI |
|---|---|---|---|---|---|
| KEY (CallRes/PutSup/HVL/GW) | 611 | 21.8% | 78.1% | 23.9% | [−5.4pp, +1.4pp] |
| GEX strikes | 747 | 24.1% | 75.5% | 20.4% (n=103) | [−3.5pp, +12.1pp] |
| BL blind spots | 647 | 22.3% | 77.1% | 24.2% | [−5.6pp, +1.8pp] |

### 4.3 Stage 2 — trade-level pre-registered tests (stacked book, n=208)

Baseline in window: **+0.150R ±0.163, PF 1.29, WR 37%** (all-signals +0.061R ±0.109, n=374). Registered hypotheses and outcomes:

| hypothesis (registered direction) | stacked result | verdict |
|---|---|---|
| T1 headwind: opposing major level inside the 3R path → worse | +0.149 (headwind, n=115) vs +0.151 (clear air, n=93) | **null** |
| T1 distance-to-opposing tertiles | near +0.108 / mid +0.386✅ / far +0.036 — non-monotone | noise shape |
| T2 negative gamma → better (momentum book) | +0.148 vs +0.151 (as-published); causal prev-day −0.027 vs +0.244✅ — *wrong sign* | **null / refuted** |
| T2b above vs below HVL | +0.147 vs +0.156 | null |
| T3 vol_score low ≤1 / mid / high ≥4 | +0.182 / +0.063 / +0.183 | **null** |
| T3 momentum, option scores (coarse) | all CIs span 0 | null |
| T3 seasonality_score ≥2 | **−0.419 ±0.232 (n=32, PF 0.21, WR 19%)**; all-signals scope −0.313 ±0.204 (n=49) | **only consistent negative pocket — but 12 calendar days, 1 of ~35 cuts → watch item** |
| T4 net GEX sign | ≡ gamma condition split — null | null |
| T4 IV30 / exp-move tertiles | low −0.04 / mid +0.33✅ / high +0.21 — non-monotone | suggestive "edge needs some vol", nothing more |
| T5 user combo: high-vol(≥3) AND negative gamma → better | **+0.053 (n=50) vs rest +0.181**; causal +0.087 vs +0.171 | **refuted** (slightly *under*performed) |

### 4.4 Follow-up A — "the main levels must have merit" (containment & first touch)

**The observation is real; the explanation isn't gamma.** Containment = the day's extreme stays inside the level. Benchmark = empirical CDF of the day's (high−open)/expected-move evaluated at each level's distance — i.e., "how often would ANY price that far away contain the day?"

| level | days usable | contained | benchmark | excess | boot 95% CI |
|---|---|---|---|---|---|
| Call Resistance | 80 | 95% | 86% | +9.4pp | [+4.6, +13.9] ✅ |
| Call Res 0DTE | 74 | 82% | 72% | +10.1pp | [+2.6, +17.0] ✅ |
| **1d_max (pure IV band, ref)** | 79 | 94% | 78% | **+15.5pp** | [+9.9, +21.5] ✅ |
| Put Support | 77 | 94% | 90% | +3.4pp | [−2.5, +9.2] |
| Put Sup 0DTE | 71 | 79% | 77% | +2.3pp | [−7.7, +11.2] |
| **1d_min (pure IV band, ref)** | 75 | 92% | 78% | **+14.0pp** | [+7.6, +19.6] ✅ |

Call Resistance does cap the day 95% of the time — *but a strike-free IV band caps it better*. The containment is **distance + implied vol**, not gamma placement. First-touch-to-EOD stats are untestable at the main levels' event rate (Call Res touched 4 days of 81, Put Support 5); when Put Support *was* touched at the 6-bar scale it broke 89% of the time. Gamma Wall / HVL first-touch rejection depths beat matched controls in point estimate (48.0 vs 18.5 pts median) but every CI spans zero.

### 4.5 Follow-up B — user rules + the expanded level universe

**U4 anchor (read this first):** the same touch machinery applied to the levels "everyone knows work":

| family | touches | bounce% | break% | bounce diff vs 3,263 random-control touches |
|---|---|---|---|---|
| MQ main | 407 | 20.1% | 79.6% | [−5.0pp, +3.5pp] |
| MQ other (BL+GEX) | 1,394 | 23.2% | 76.3% | [−0.4pp, +5.0pp] |
| Prior day H/L/C | 426 | 24.4% | 75.6% | [−0.8pp, +7.6pp] |
| Prior day VA (POC/VAH/VAL) | 374 | 21.7% | 78.3% | [−3.8pp, +5.0pp] |
| IB high/low (post-IB) | 315 | 21.3% | 78.1% | [−4.4pp, +4.9pp] |
| VWAP (developing) | 448 | 22.5% | 77.2% | [−2.5pp, +5.5pp] |
| random control | 3,263 | 21.0% | 78.5% | — |

**Nothing** — not prior-day high/low, not VWAP, not value areas — bounces more than random at the 5M/30-min scale in this window. The MenthorQ null is not special; visual level-respect at this scale is mostly base rate + confirmation bias (or an effect smaller than 81 days can detect).

**U1 "never trade into a main level" (registered: worse): REFUTED.**

| cut (stacked) | n | ExpR ±CI | PF | net$ |
|---|---|---|---|---|
| INTO MQ main level (≤1R) | 48 | +0.262 ±0.362 | 1.32 | $7,591 |
| not into MQ main | 156 | +0.124 ±0.186 | 1.29 | $18,245 |
| INTO any level (MQ or structural) | 139 | +0.209 ±0.211 | 1.43 | $28,494 |
| **clear of ALL levels (≥1R air)** | 65 | **+0.044 ±0.260** | **0.88** | **−$2,658** |

Trading into levels did *fine*; clear air was the worst bucket. Skipping into-level trades would have cost money.

**U2 break-and-retest: untestable** — 16 qualifying trades all-scope, **0** in the stacked subset (main levels rarely break + retest + align with a signal). No conclusion.

**U3 clusters (registered: worse): the only registered-direction hit of the study.** Cluster = ≥3 levels (MQ + structural) chained within 4 pts; 175 zones over 81 days.

| cut | stacked | all signals |
|---|---|---|
| INTO cluster zone (≤1R) | +0.005 ±0.386, PF 0.76 (n=33) | −0.100 ±0.237, PF 0.64 (n=63) |
| not into cluster | **+0.186 ±0.183 ✅, PF 1.43** (n=171) | +0.097 ±0.123, PF 1.34 (n=307) |
| cluster touch test | bounce 26.5% vs isolated 22.0%, CI [−2.2, +10.7] | leans right, n.s. |

Registered direction, consistent across both scopes, coherent mechanism (confluence). Small n → **top watch item, not a rule**.

### 4.6 Follow-up C — the day as the unit (n=81): where gamma finally shows up

| test (registered direction) | groups | diff | 95% CI |
|---|---|---|---|
| **D1 realized range / expected move: NEG vs pos gamma (reg: NEG higher)** | **1.177 (n=33) vs 0.960 (n=48)** | **+0.217** | **[+0.032, +0.412] ✅** |
| D1 causal (prev-day label) | 1.131 vs 0.999 | +0.132 | [−0.062, +0.342] |
| D2 trend efficiency \|C−O\|/(H−L): NEG vs pos (reg: NEG higher) | 0.472 vs 0.458 | +0.014 | [−0.105, +0.131] |
| D3 corridor width vs range/EM (Spearman) | r = −0.044 | | null |
| D3 open position in corridor vs drift | r = −0.122 | | null |
| D4 expiring-GEX share vs afternoon compression | r = +0.040 | | null |
| D5 book day-P&L: NEG vs pos gamma | +$381 vs +$276/day | | [−1349, +1723] null |
| **D5 book day-P&L: days realizing > vs < implied move** | **+$1,006 vs −$386/day** | **+$1,392** | **[+46, +2806] ✅ (diagnostic)** |

**D1 is the first MenthorQ claim to pass a test on our data** — negative-gamma days overshoot the implied expected move, positive-gamma days undershoot it. Caveat: the as-published label is EOD-stamped and partly derived from where spot ended vs HVL (a big day can label *itself* negative); the causal prev-day version points the same way but isn't significant. **D2 shows the amplification is amplitude, not direction.** D5's significant row is diagnostic, not causal (you don't know the day's range in advance): it proves the stacked book is **long realized volatility** — the exact quantity a clean morning gamma/vol signal would forecast.

## 5. Why it works / fails (the synthesis)

Gamma has been used profitably for decades — but look at *how*: market-makers' gamma scalping (harvesting realized vol), vol-risk-premium selling in pinned regimes, OPEX pin trades, and modern funds using dealer-positioning as a **risk dial** (widen stops / cut size in negative gamma). Every proven use is a **volatility or sizing use**. "Buy the bounce off the gamma level intraday" — the retail rendering — is the one use this data consistently fails to support. Our results reproduce that division precisely: the amplitude effect is real (D1), the direction effect absent (D2), the level-bounce effect absent for *every* level family including classical ones (U4), the containment "merit" of the main levels is explained by implied vol alone (T-A), and our book's P&L is literally a bet on realized vol (D5). The data's value to us, if any, is as a **morning vol/sizing input** — which the current archive can't deliver cleanly (EOD stamps) but our own pre-market capture will.

## 6. Recommendation

**Change nothing in the frozen Stack v2 spec.** Specifically:

- **Do NOT** filter entries by gamma levels, level proximity, headwind, gamma condition, or QScores — every such cut was null or refuted on 81 days.
- **Do NOT** adopt "never trade into a level" — it was the *wrong-direction* rule in this window; clear-air trades were the worst bucket.
- **Keep capturing MenthorQ pre-market daily** (the app's Refresh button). The backfilled archive is EOD-stamped; only same-morning captures make the regime scalars trustworthy.
- **Three pre-registered re-tests at ~6–12 months of clean data** (one test each, no threshold tuning):
  1. **Cluster skip/downsize** — stacked trades with a ≥3-level cluster within 1R underperform (this study: +0.005 vs +0.186).
  2. **D1-causal sizing** — mornings labeled negative-gamma realize more than implied → a *sizing* rule, not an entry rule.
  3. **Seasonality_score ≥2 skip** — the −0.42R pocket (thinnest evidence of the three).

## 7. Caveats & open questions

- **One regime:** Mar–Jul 2026 (a vol spike into a long positive-gamma grind). 81 days cannot rule out effects smaller than ~±0.2R per subgroup; nulls here are "not detectable at this n", not proofs of absence.
- **EOD-stamp contamination:** as-published gamma_condition/QScores may embed same-day info; D1's headline number is partially circular. The causal variants are the honest ones and are all n.s. — direction-consistent but unproven.
- **Multiplicity:** ~50 cuts total across four rounds; isolated ✅ marks are expected by chance. Only pre-registered-direction + cross-scope-consistent findings (clusters, D1) were promoted to watch items.
- **Stage-1 scale:** the touch test used one fixed scale (6 bars / 3 pts). A different horizon might behave differently — but the containment test (day horizon) and first-touch test (EOD horizon) covered the coarser scales and agreed.
- Break-and-retest remains **untested** (event rate too low), not refuted.

## 8. Reproduce

- Data: `data/menthorq/menthorq_levels.csv` (+ raw JSON per day in `data/menthorq/raw/`), backfill: `scripts/menthorq_backfill.py`
- Round 1 (stages 0–2): `scripts/menthorq_edge_study.py` → full tables in `docs/living/menthorq_edge_study_20260704_tables.md`; sim cache `data/menthorq/_study_sim_results.parquet`
- Round 2 (containment/first-touch): `scripts/menthorq_sr_followup.py` → `docs/living/menthorq_sr_followup_20260704.md`
- Round 3 (user rules + universe): `scripts/menthorq_userrules.py` → `docs/living/menthorq_userrules_20260704.md`
- Round 4 (day regime): `scripts/menthorq_dayregime.py` → `docs/living/menthorq_dayregime_20260704.md`
- Signals: MyMicroChannel export ES SEP26 5M (Desktop, 1850 days); bars `data/bars/_continuous.parquet`; ticks `data/ticks_continuous/`; exec = S53 frozen spec via `simulation_engine.simulate_trades` + `stack_filter.py`.
