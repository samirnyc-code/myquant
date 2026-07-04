# MenthorQ × MC edge study — S54 (July 4, 2026)

**Question:** does 3 months of MenthorQ data (gamma levels, GEX, BL, HVL, gamma regime,
QScores) improve the MC / Stack v2 entry edge?

**Verdict up front: NO actionable edge found, and the spec stays frozen.** The
high-powered test (level S/R validity on raw price, ~2,000 touch events) is **null**.
The trade-level pre-registered tests (208 stacked trades) are null on every registered
hypothesis; the one consistent negative pocket (seasonality_score ≥2) rests on 12
calendar days and is logged as a **watch item only**. Keep ingesting daily; re-test at
6–12 months of data.

**Method discipline:** hypotheses pre-registered before outcomes were seen (T1–T5
below); frozen exec everywhere (3R target, BE ratchet @+1R, slips 1/1/1, stop offset 1,
comm $4.36, EOD flat); coarse bins only; ALL cuts reported (~35 cuts × 2 scopes → expect
3–4 spurious "significant" rows by chance — read the table with that in mind).

Script: session scratchpad `menthorq_study.py` (S54). Data: `data/menthorq/menthorq_levels.csv`
(82 trading days, 2026-03-06 → 2026-07-02), MC signal export ES SEP26 5M (380 window
signals, 374 filled; 208 Stack-v2), continuous bars/ticks (S53 verified pipeline).

---

## Stage 0 — data hygiene (all downstream work depends on these)

- **Price space**: bars/signals are back-adjusted continuous; MenthorQ levels are actual
  front contract. Offsets measured from per-contract bar files: **ESH6 +111.00,
  ESM6 +61.25, ESU6 +0.00** (constant within period, matches `nt_rollovers_export.csv`
  cumulative offsets). All levels shifted into continuous space before use.
- **`1d_max`/`1d_min` are an expected-move band, NOT realized H/L** (band ≡ 2× expected
  move, ratio 1.00; realized range fully inside the band 78% of days; median gap to
  realized H/L ~40–46 pts). Causal — usable.
- **⚠️ The archive row is EOD-stamped**: `distance_to_hvl_%` matches the SAME-day close
  (err 0.05pp) not the prior close (0.46pp). The OI-derived levels (CallRes/PutSup/
  HVL/BL/GEX) are computed from prior-day close option data and are static intraday, so
  they remain causal — but `gamma_condition` and the QScores **may embed same-day
  information** as archived. Every regime/score test below therefore has a CAUSAL
  variant using the PRIOR day's value. **For live use, capture the values pre-market**
  (the app's "Refresh Today's Data" pulled pre-market is fine); do not trust the
  backfilled archive stamps for same-day scalars.

## Stage 1 — do MenthorQ levels act as intraday S/R? **NO.**

Touch test on 5M bars, 82 days: bounce = ≥3 pts reject without 3-pt penetration within
6 bars; controls = other 25-pt strikes (for GEX) / random in-range prices (3×, seed 42),
excluding ±5 pts of real levels.

| level group | touches | bounce% | break% | ctrl bounce% | bounce diff 95% CI |
|---|---|---|---|---|---|
| KEY (CallRes/PutSup/HVL/GW) | 611 | 21.8% | 78.1% | 23.9% | [−5.4pp, +1.4pp] |
| GEX strikes | 747 | 24.1% | 75.5% | 20.4% (n=103) | [−3.5pp, +12.1pp] |
| BL blind spots | 647 | 22.3% | 77.1% | 24.2% | [−5.6pp, +1.8pp] |

MenthorQ levels bounce **no more often than random prices** at the 5M/30-min scale.
(GEX control is under-powered — few free 25-pt strikes per day — but the point estimate
is +3.7pp with CI spanning 0.) There is nothing here for a trade filter to inherit.

## Stage 2 — pre-registered trade tests (Stack v2, n=208, Mar 6 – Jul 2)

Window baseline: stacked +0.150R ±0.163 (PF 1.29, WR 37%, $25.2K one-ES-lot) — consistent
with the frozen book. All-signal baseline +0.061R ±0.109 (n=374).

| registered hypothesis | result |
|---|---|
| **T1 headwind/tailwind** (major level inside 3R target path hurts) | **REFUTED/null** — headwind +0.149 vs clear-air +0.151. Distance tertiles non-monotone (near +0.11, mid +0.39✅, far +0.04) = noise shape, no gradient. |
| **T2 gamma regime** (negative gamma should help a momentum book) | **null / wrong sign** — as-published: no diff (+0.148 vs +0.151). Causal prev-day: neg −0.03 vs pos +0.24✅ — *opposite* of the registered direction, inconsistent with the as-published cut → treated as noise. |
| **T2b HVL side** | null (+0.147 above vs +0.156 below). |
| **T3 vol_score** | null — low(≤1) +0.182 vs high(≥4) +0.183. Momentum, option scores: null. |
| **T3 seasonality_score ≥2** | **only consistent hit — NEGATIVE pocket**: stacked −0.419 ±0.232 (n=32, PF 0.21, WR 19%); all-signals −0.313 ±0.204 (n=49). But: 12 calendar days carry it, scopes overlap (not independent), one of ~35 cuts. **Watch item, NOT a rule.** |
| **T4 net GEX sign** | null (≡ gamma condition split). |
| **T4 IV30 / exp-move tertiles** | low tertile negative (−0.04), mid +0.33✅, high +0.21 — mid>high>low is not a clean gradient; IV and exp-move are the same variable. Suggestive "edge needs some vol" texture at most. |
| **T5 user combo: high-vol(≥3) ∧ negative gamma** | **REFUTED** — +0.053 vs rest +0.181 (causal variant +0.087 vs +0.171). The hypothesized favorable regime slightly *under*performed. |

Full tables (every cut, both scopes) preserved in the session scratchpad output and
reproduced by re-running the script.

## Decisions / follow-ups

1. **No change to the frozen spec.** Nothing here clears the bar (pre-registered
   direction + significance + structural story). This is the agreed S53 discipline
   working as intended.
2. **Keep the daily MenthorQ ingestion running** (app Refresh button — pre-market
   capture makes scalars trustworthy going forward, unlike the EOD-stamped archive).
3. **Watch item for re-test at ~6–12 months of data:** seasonality_score ≥2 as a skip
   (pre-registered now: expect ExpR < stacked baseline; single test, no threshold
   tuning). Secondary: low-IV-tertile softness.
4. If GEX levels are revisited, test them at a coarser scale (daily closes / larger
   reversion horizons), not 5M touches — the intraday S/R story is dead on this data.
