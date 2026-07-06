# 0012 — The OR12 Base-Rate Card: Replicating the IB Statistics, and What They're Really Made Of — 2026-07-07

**Series:** MC Setup Research Notes · Note 0012
**Confidence:** High — 1,251 ES days (2021–2026) of our own tick-built 5M data, simple counts (no fitting), era-split stability shown per cell, and the two headline third-party claims stress-tested with controls. No trading claim; no cost model applies.
**TL;DR:** We replicated the published Initial-Balance statistics (note 0011 §4.1) on our own data — and then dissected them. Three findings: (1) the celebrated **"IB extreme formation order" skew is mostly a proximity artifact** — the real conditioner is *where price sits within the IB at 10:30* (low third → ~85% first break down AND 2.5:1 odds the day closes below the IB; mirrored at the high); (2) **"narrow IB → range extension" inverts in ADR units** — wide IBs are followed by *bigger* afternoons (post-IB range >0.5×ADR: ~60% narrow vs ~90–99% wide); IB width is a realized-volatility nowcast that predicts afternoon *range*, not direction; (3) trend days concentrate on **wide**-IB days (38–41% vs 9–12% narrow), the opposite of the folklore reading. The card (bucket × IB-width × 10:30 location) is now validated on our data and ready to be the foundation of the 9:35 context screen.

## 1. The setup (so this note stands alone)

- **Data:** 1,251 ES RTH sessions (2021-07 → 2026-07), 5-minute bars built from tick data, back-adjusted continuous.
- **IB** = first 12 bars (08:30–09:30 CT). All conditioning features are known by 09:30 CT (open bucket, gap) or at the IB close (IB width vs ADR14, formation order, bar-12 close location). Outcomes are end-of-day.
- **Why:** note 0010's verdict was to build a context *display*, whose foundation is honest conditional base rates. Note 0011 catalogued third-party ES numbers (TradingStats, 2,686 days 2015–25); nothing goes on a live screen until replicated here — this note is that replication, plus the tautology controls the third-party source never ran.
- **Definitions:** bucket = open location vs yesterday's range (above_yH / upper_half / lower_half / below_yL); IB-width tiers = full-sample terciles of IBrange/ADR14 (cuts: 0.393, 0.582); trend day = RTH range > 1.1×ADR20 AND close within 25% of the day's extreme; extension = trading >0.5 IB-widths beyond either IB extreme after 09:30.

## 2. The question

Do the documented IB conditioners (width-vs-ATR, extreme formation order) replicate on our 2021–26 data — and are they *real* information or measurement artifacts?

## 3. How we tested it

1. Main card: bucket × IB-width tier → P(trend), P(extension, IB units), P(post-IB range >0.5×ADR), median follow-through in ADR, P(both sides broken), P(day close above/inside/below IB), with a 2021–23 vs 2024–26 era split per cell.
2. Formation-order replication: which IB extreme formed first → first break side.
3. **Proximity control:** the same, *within* bands of where bar 12 closes inside the IB (low/mid/high third).
4. **Denominator control:** extension measured both in IB multiples (their convention) and in ADR units (ours).
5. Bar-12 close location → day close vs IB (position persistence vs directional prediction).

## 4. Results

### 4.1 The main card (bucket × IB-width tier), key columns

| bucket | tier | n | P_trend | P_ext (IB units) | P(postIB rng>0.5 ADR) | med follow-thru (ADR) |
| --- | --- | --- | --- | --- | --- | --- |
| above_yH | narrow | 111 | 9.9% | 90.1% | 56.8% | 0.23 |
| above_yH | mid | 94 | 16.0% | 72.3% | 83.0% | 0.29 |
| above_yH | wide | 73 | 38.4% | 56.2% | 89.0% | 0.35 |
| below_yL | narrow | 34 | 5.9% | 73.5% | 67.6% | 0.18 |
| below_yL | mid | 77 | 23.4% | 67.5% | 85.7% | 0.36 |
| below_yL | wide | 93 | 33.3% | 47.3% | 98.9% | 0.39 |
| lower_half | narrow | 101 | 11.9% | 81.2% | 68.3% | 0.28 |
| lower_half | mid | 112 | 25.0% | 75.9% | 89.3% | 0.38 |
| lower_half | wide | 116 | 41.4% | 53.4% | 95.7% | 0.38 |
| upper_half | narrow | 171 | 8.8% | 81.3% | 60.2% | 0.23 |
| upper_half | mid | 134 | 23.9% | 73.9% | 82.8% | 0.36 |
| upper_half | wide | 135 | 39.3% | 57.8% | 91.9% | 0.46 |

Unconditional: trend 23%, extension 70%, both-sides broken 27%. Era split (2021–23 vs 2024–26): trend rates stable within ~±7pp for all cells with n>90 except upper_half/narrow (15.6% → 4.7% — flag). Full card incl. close-vs-IB columns: `docs/living/or12_baserate_tables_20260707.csv`.

**Read:** the two extension columns tell opposite stories, and both are partly mechanical (§5). The robust, non-tautological gradients: **trend days concentrate on wide IBs** (9–12% narrow → 33–41% wide, stable across eras) and **afternoon range grows with IB width** in ADR units.

### 4.2 Formation order replicates… (raw)

IB high formed first → first break down 69.0% / up 28.0% (n=607); low first → up 73.4% / down 25.3% (n=644). Stronger than the documented 45/24 — suspiciously strong.

### 4.3 …and mostly dies under the proximity control

First-break-down rate, by formation order WITHIN bar-12 close-location bands:

| bar-12 closes in | hi-first: down% | lo-first: down% | formation-order residual |
| --- | --- | --- | --- |
| low third of IB | 86.2 (n=363) | 80.0 (n=45) | +6pp |
| mid third | 50.3 (n=179) | 45.9 (n=148) | +4pp |
| high third | 24.6 (n=65) | 13.1 (n=451) | +11pp |

**The real variable is where price sits at 10:30** (low third → ~85% first break down regardless of order); formation order contributes a +4…+11pp residual. The documented "2:1 skew" is mostly proximity in disguise. Corollary: the n-splits show formation order and location are heavily entangled (high-formed-first days usually *are* sitting low at 10:30).

### 4.4 Bar-12 location also predicts the day CLOSE — position persists, direction doesn't

| bar-12 closes in | day closes above IB | inside | below IB | P_trend | n |
| --- | --- | --- | --- | --- | --- |
| low third | 17.6% | 38.5% | 43.9% | 27.9% | 408 |
| mid third | 37.6% | 36.7% | 25.7% | 19.3% | 327 |
| high third | 48.8% | 32.9% | 18.2% | 22.5% | 516 |

~2.6:1 odds the day closes on the side price already occupies at 10:30. Crucial nuance: this is **position persistence, not a forward-return signal** — the sign of the move *from* the 10:30 price remains ~50/50 (note 0010 test [2]). Both can be true at once: price that is low tends to stay low without necessarily going lower.

### 4.5 The denominator dissection (why the folklore inverts)

- "Narrow IB → 90% extension" (IB units) is favored mechanically: half an IB-width is a *small* absolute move when the IB is narrow.
- In ADR units the ranking flips: post-IB range >0.5×ADR on ~60% of narrow-IB days vs ~90–99% of wide-IB days; median follow-through 0.18–0.28 ADR narrow vs 0.35–0.46 wide.
- Interpretation: **IB width vs ADR14 is a same-day realized-volatility nowcast** (ADR14 lags; a wide IB means vol has expanded *today*, and intraday vol clusters). It predicts how far the afternoon travels — in either direction — and hence trend-day odds. It says nothing about side.

## 5. Why it works / fails (the synthesis)

The third-party numbers replicate, but two of the three headline effects are partly measurement geometry: formation order proxies for 10:30 location; IB-unit extension proxies for the denominator. What survives dissection as genuinely informative at 10:30 is a clean three-factor card: **(1) open-location bucket** (auction context vs yesterday), **(2) IB width vs ADR** (vol nowcast → afternoon range & trend-day odds), **(3) bar-12 close location within IB** (position persistence → which side the day likely settles on + first-break side). All three are already features in the OR12 fingerprint — the card is the interpretable 3-axis projection of what the twin-matcher uses in 80 dimensions.

## 6. Recommendation

**Adopt the 3-factor card (bucket × IB-width tier × 10:30 location) as the foundation of the 9:35 context screen.** Display real per-cell rates with n; grey out cells with n<50; show the upper_half/narrow era instability flag. Drop formation order from the display (keep as a fingerprint feature) — it's redundant with location and would double-count. Frame the location factor as "the day tends to *settle* on this side," never as "price will go this way from here." No trade recommendation is made or implied.

## 7. Caveats & open questions

- Cell n runs 34–171; below_yL/narrow (n=34) is unusable — grey it out.
- Terciles are full-sample cuts (mild look-ahead for a *historical* card); the live screen should use trailing cuts — trivial change, queued with the screen build.
- Trend-day thresholds (1.1×ADR, 25% band) inherited from 0011's community definitions, sanity-checked but not optimized (deliberately — optimizing labels invites circularity).
- upper_half/narrow trend rate collapsed in 2024–26 (15.6% → 4.7%) — watch item.
- C-period confirmation (10:30–11:00 close outside IB) not yet replicated — natural v2 column for the card.

## 8. Reproduce

- `scripts/or12_baserate_tables.py` (one run, ~40s) → tables above + `docs/living/or12_baserate_tables_20260707.csv`
- Outcome extractor shared with 0010: `scripts/or12_outcome_agreement.py` (`day_outcome`, incl. `first_break`, `post_rng_pts`, `abs_ret_pts`)
- Fingerprint/context builder: `scripts/or12_pattern_groups.py` (`build_features`, `ib_atr`, `close_loc`, buckets)
- Companions: note 0010 (twin-matcher verdict), note 0011 (source survey), `docs/living/or12_research_daytype_20260706.md`
