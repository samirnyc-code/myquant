# 0010 — OR12: Can the First Hour Find Its Twins, and Do Twins Share a Fate? — 2026-07-06

**Series:** MC Setup Research Notes · Note 0010
**Confidence:** Medium-High for the verdict — 1,251 ES days (2021–2026), permutation-controlled AND walk-forward-validated (1,001 OOS days, neighbours strictly in the past); no trading claim is made, so no cost model applies.
**TL;DR:** We built a "twin day" engine: fingerprint each ES session's first 12 five-minute bars (the Initial Balance) plus the prior-day open context, and find the most similar historical openings. Twin days **do** share a fate — but only in *character*, not *direction*, and the character edge over simple conditional base-rate tables is real but **thin** (walk-forward log-loss edge +0.025, 95% CI barely above zero). Direction is a coin flip in every version. **Verdict: keep the road, change the destination** — stop chasing prediction accuracy (the ceiling is structural, and the literature agrees); build the tool as an honest *context display*: conditional base rates + the twins themselves as charts + the twin vote only where it's confident (13% of days it hits ~50% vs a 37% prior).

## 1. The setup (so this note stands alone)

This is a **context study**, not a trade study — there is no entry, stop, or cost model. The object under test is the ES day itself.

- **Data:** 1,251 full RTH sessions of back-adjusted continuous ES 5-minute bars built from tick data (2021-06 → 2026-07). RTH = 08:30–15:15 CT, 81 bars/day.
- **IB (Initial Balance):** the first 12 bars = first 60 minutes (08:30–09:30 CT).
- **The tool:** each day gets a ~80-dimension "fingerprint" computed **strictly from bars 1–12 plus information already known at the open** (prior day, ADR). Nothing after bar 12 leaks in. Days are matched to their nearest neighbours ("twins") in fingerprint space, and we ask whether the twins' afternoons resemble today's afternoon.
- **Why anyone cares:** the user's trading inconsistency traces to real-time *context identification* (Brooks/Dalton day-type reads), not signal knowledge (see handoff S56). A tool that reliably says "today's opening looks like these 5 historical days" externalizes that read.

## 2. The question

If two days start the same way — same opening-hour structure, same relationship to yesterday — do they end the same way? Concretely: do a day's k nearest fingerprint-neighbours predict (a) where it closes relative to the IB, (b) rest-of-day direction, (c) range extension vs rotation, (d) its mechanical Dalton-style day type — better than chance?

## 3. How we tested it

1. **Fingerprint v1 (shape only):** normalized 12-bar close path, per-bar IBS / body-fraction / direction sign, direction flips, bar-to-bar overlap, breakout (BO) and failed-breakout (fBO) counts vs the developing IB extreme, double-top/bottom flags, high/low timing, close location in IB.
2. **v2 (+context, hard gate):** open-location **bucket** vs yesterday's range (above yHigh 280d / upper half 440d / lower half 330d / below yLow 204d) as a *hard* match gate — twins never cross buckets; plus gap size, prior-day range vs ADR14, prior close location as soft features.
3. **v3 (+Brooks trend/range diagnostics, user-specified):** inside the IB, P&L of *stop-entry* traders (buy above prior high / sell below prior low) vs *BB/SA limit* traders (buy below / sell above — BLSH) for bulls and bears separately; EMA20 location (fraction of bars above, distance, slope — EMA computed on the continuous series so it's causal at the open); Always-In proxy at bar 12.
4. **v4 (+swing structure & volume):** strength-2 swing pivots → push counts (wedge = 3 pushes), two-legged pullback flag; relative IB volume (IB volume ÷ 20-day median).
5. **v5 (+literature features):** IB width ÷ ADR14 (strongest documented ES character conditioner) and IB-extreme formation order (high-before-low → ~2:1 documented skew toward later downside break).
6. **v6 (+open-type & OTF):** open never-revisited flag (Open Drive proxy), drive efficiency (net move ÷ path length), one-time-framing up/down on 15-minute aggregates of the IB. Also A/B-tested **Lorentzian vs Euclidean** distance.
7. **Evaluation:** for each day, 5 nearest same-bucket neighbours vote on the outcome. Controls: (a) 500-draw permutation — 5 *random* same-bucket days (this is the honest control: it inherits all bucket base-rate information), (b) "bucket mode" — always predict the bucket's most common outcome. Also K=15 variant.

## 4. Results

### 4.1 Day close vs IB (above / inside / below) — the character test

| Fingerprint | kNN accuracy | Random-5 same bucket | Bucket-mode | p (perm) |
|---|---|---|---|---|
| v1 shape only | 39.0% | 33.9% ± 1.2% | 38.0% | <0.001 |
| v3 +Brooks diagnostics | 39.8% | 33.9% | 38.0% | <0.001 |
| v4 +swing/volume | 39.2% | 33.9% | 37.9% | <0.001 |
| **v6 (Euclidean)** | **40.5%** | 33.9% | 37.9% | **<0.001** |
| v6 (Lorentzian) | 38.4% | 33.9% | 37.9% | <0.001 |

Read: real and stable across every version — twins carry ~6–7 points of character information over random same-context days, ~2.5 over the bucket's base rate. Euclidean beats Lorentzian (log-compression flattens ~80 z-scored dimensions; the outlier-taming trick that works for 6-feature TradingView kNNs hurts here).

### 4.2 Rest-of-day direction — the null result (important)

| Test | kNN | Random control | p |
|---|---|---|---|
| sign(mean twin return) vs sign(day return), best version | 50.8% | 49.9% ± 1.3% | 0.24 |
| corr(day rest-of-day return, mean twin return) | −0.01 to −0.06 | ~0 | n.s. |

Read: **no version, no K, no metric ever beat a coin flip on direction.** This is the note's most trustworthy finding.

### 4.3 Extension vs rotation (>0.5 IB beyond either extreme, post-IB)

kNN 65.7% vs random 63.7% ± 1.0% (p=0.03) — but **"always predict extension" scores 69.9%** because extension is the base case in ES. At a naive 0.5 vote threshold the twins add discrimination over random picks yet lose to the unconditional prior. Verdict: no added value as tested; needs calibrated probabilities, not majority votes.

### 4.4 Mechanical day type (MWG86/futures.io taxonomy, ADR-calibrated)

Our 5 years label as: **normal-variation 54%, trend 23%, neutral 21%, normal 2%** — nearly identical to the community's published 2011–13 ES base rates (54/16/25), which validates the taxonomy across regimes. But kNN majority vote hits 45.2% vs **54.0%** for "always say normal-variation": with one dominant class, majority voting is the wrong decoder. Same fix as 4.3: neighbour *distributions*, not votes.

### 4.5 Per-bucket base rates (context alone, no matching)

| bucket | close above IB | below | inside |
|---|---|---|---|
| above_yH | 32.9% | 31.4% | 35.7% |
| below_yL | 32.8% | 25.0% | 42.2% |
| lower_half | 37.6% | 27.3% | 35.2% |
| upper_half | 37.7% | 29.1% | 33.2% |

Notable: gap-down-below-range days end *inside* their IB most often (42%) — big down-opens rotate more than they run, on this sample.

### 4.6 Walk-forward — the decision test (neighbours strictly in the past)

The live-tool simulation: for each of 1,001 days after a 250-day burn-in, take the K=20 nearest *past* same-bucket days and read their outcome **distribution** (no majority vote), scored against two priors computable from the same past data.

| Predictor of day close vs IB | Accuracy | Log-loss |
|---|---|---|
| **Twin distribution (K=20, past only)** | **40.1%** | **1.0862** |
| Bucket base rates (past) | 37.3% | 1.0968 |
| Bucket × IB-width-tercile base rates (past) | 36.7% | 1.1110 |

Log-loss edge of twins over the conditional prior: **+0.0249, 95% CI [+0.0004, +0.0483]** — statistically real, practically thin. The useful structure is in **confidence stratification**: when the twin vote is ≥55% concentrated (13% of days), OOS accuracy is **49.6%** vs a ~37% prior — those are the days the tool has something to say.

**Trend-day early warning** (base rate 22.5% OOS): twin-trend-fraction quintiles produce a monotone gradient — bottom quintile 18.8%, top 32.0%. **But** the simple bucket × IB-width conditional prior reproduces nearly the same gradient (18.1% → 37.3%) — for trend-day warning, the kNN machinery adds almost nothing beyond the free conditional table.

## 5. Why it works / fails (the synthesis)

The result reproduces the literature almost embarrassingly well (two research agents surveyed academic + practitioner sources; full digest in `docs/living/or12_research_daytype_20260706.md`):

- An arXiv study doing nearly this exact project on MNQ found regime classes that are *descriptively* distinct while **all directional strategies failed costs and year-stability**.
- The canonical "first half-hour predicts last half-hour" result (JFE 2018) decayed ~75% after publication and is attributed to hedging flows, not chart structure.
- A public repo (`brooks-pa-failure`) that faithfully mechanized 25 Brooks setups went from +61% (zero fees) to −59%…−211% with realistic costs — "bars are easy to code, context isn't."
- Practitioner consensus (futures.io): day-type prediction collapses to a **binary directional-vs-rotational call in the first 30–60 min**; the 6-way Dalton taxonomy is only knowable in hindsight.

Mechanically: opening structure encodes *auction condition* (initiative vs responsive participation), which constrains how far the day travels and whether the IB holds — but the *side* that wins the afternoon is decided by flows the morning chart doesn't contain. Our fingerprint is a condition detector, not a direction detector, and the data says exactly that.

## 6. Verdict & recommendation

**The question asked: does it make sense to keep going down this road — a tool that predicts current context? Answer: yes for CONTEXT, no for PREDICTION-accuracy chasing.** Three findings force this split:

1. **The predictive ceiling is real and low.** Six fingerprint versions, two distance metrics, two K values, and every documented feature from a two-agent literature sweep moved OOS character accuracy from ~39% to ~40% (vs 34% chance, 37% context prior). Direction never left 50%. The MNQ paper, the decayed JFE intraday-momentum result, and the futures.io practitioner consensus all hit the same wall. More features will not break it — the afternoon's *side* is decided by flows the morning chart does not contain.
2. **Most of the usable signal is free.** Simple conditional base-rate tables — open-location bucket × IB-width-vs-ADR (× formation order) — reproduce nearly the whole trend-day-warning gradient (18% → 37%) without any kNN machinery. These tables should be built, trusted, and displayed regardless of what happens to the matcher.
3. **The matcher's surviving edge is small but real, and concentrated.** Walk-forward, the twin distribution beats the conditional prior (log-loss CI just above zero), and on the 13% of days when the twins agree strongly it hits ~50% vs a 37% prior. Plus the un-quantifiable part: the twins are *charts a Brooks-trained eye can read* — the tool externalizes the context read, which was the original S56 goal.

**So: continue, with the destination changed from "predict the day" to "display the honest context."** The v1 product is a 9:35–10:35 screen showing: (a) today's bucket / IB-width tier / formation order with their historical base-rate table, (b) today's 5 twins as full-day charts (IB marked, yH/yL/yC), (c) the twin outcome distribution **only when confidence ≥55%**, greyed out otherwise, (d) the standing reminder that direction is unknowable from this. Do **not** bolt a directional trade onto it — the 50% is not a bug to fix; it is the finding.

Stop-loss for the research thread: if walk-forward character accuracy can't be pushed past ~45% overall (or the confident-subset fraction past ~25% of days) with the two remaining serious upgrades — functional partial-curve classification (Li & Liu) and calibrated feature weights on a train/validation era split — freeze the matcher and keep only the base-rate tables + twin display.

## 7. Caveats & open questions

- **§4.1–4.5 use full-sample kNN** (neighbours include future days); §4.6 is the walk-forward confirmation — quote §4.6 numbers, not §4.1, for anything load-bearing.
- **Majority-vote decoder** understates skill on imbalanced outcomes (§4.3, §4.4); §4.6 uses distributions and log-loss instead.
- **Feature weights are hand-set** (path 2.0, diagnostics 1.5, context 1.8…); tuning them on the same diagnostic would overfit — needs a train/validation split by era (2021–23 / 2024–26).
- "Narrow IB → extension" is near-tautological when extension is measured in IB multiples; ADR-denominated outcomes should be added.
- Day-type thresholds (1.1×ADR, 25% close band) taken from community folklore and only sanity-checked, not optimized.
- Bars are open-time-stamped on this machine (close-time migration scoped in handoff S60, not yet executed); all OR12 code reads bars by position, so results are convention-immune.

## 8. Reproduce

- `scripts/or12_pattern_groups.py` — fingerprint builder + bucket-gated kNN + clusters → `docs/living/or12_pattern_groups_<date>.csv` (per day: bucket, cluster, nn1–nn5). Env: `OR12_METRIC=euclidean|lorentzian`.
- `scripts/or12_render_pairs.py` / `or12_render_pairs_fullday.py` — tightest-pair galleries (12-bar and full-day w/ IB + prior-day levels) → `docs/living/or12_pairs*/index.html` (gitignored, regenerate at will).
- `scripts/or12_outcome_agreement.py` — all five outcome tests with permutation controls. Env: `OR12_K` (neighbours), `OR12_METRIC`.
- `scripts/or12_walkforward.py` — §4.6 decision test: past-only neighbours, distribution scoring vs bucket and bucket×IB-width priors, trend-day lift table.
- Research digest: `docs/living/or12_research_daytype_20260706.md` (agent survey: methods, effect sizes, URLs).
- Data: `data/bars/_continuous.parquet` (5M ES continuous, tick-built).
