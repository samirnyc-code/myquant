# Dalton — *Mind Over Markets* — IB & Auction-Theory Tenets (extraction)
**Date:** 2026-07-05
**Source:** `~/Downloads/James Dalton - Mind over Markets.pdf` (1993 ed.; PDF index = book page + 14)
**Purpose:** Ground the IB / auction work in source theory; seed new setup hypotheses.
**Bridge thesis (this project):** Dalton day types are the price-realized form of the
same *trend-vs-balance* axis that **dealer gamma** encodes ex-ante. Extension day types
(Trend / Double-Distribution / Normal-Variation) = amplification ≈ negative-gamma days ≈
where the MC **hold-to-close / EOD** edge lives (+$1.7M bucket). Balance types (Normal /
Nontrend / Neutral-center) = pinning ≈ positive-gamma ≈ where the MAGNET / fade works.

---

## 1. Initial Balance
- IB = range set by the **local** in the first hour; any move beyond = **range extension**,
  the footprint of the **other timeframe**. "The local is not responsible for any major
  moves… It is the other timeframe that can move price substantially." (p.14)
- Two populations: *other timeframe* (long-term, enters when price leaves value, "moves and
  shapes the market") vs *day timeframe* (the local/middleman). They trade with the local,
  not each other. (p.14, p.27)
- **Base metaphor:** "The narrower the base, the easier it is to knock the lamp over…
  If the initial balance is narrow, the odds are greater that the base will be upset and
  range extension will occur. Days that establish a wider base… are more likely to maintain
  the extremes for the day." (p.19)
- "The first half hour of trade establishes one of the day's extremes in the large majority
  of cases" — but only useful "if a trader can identify which extreme will hold." (p.62)
- **Wide IB → extremes hold, rotational. Narrow IB → base upset, trend/double-dist likely.**

## 2. Range Extension — initiative vs responsive (classified vs PRIOR day's value area)
- Initiative buying = buying within/**above** prior VA; initiative selling = within/**below**
  prior VA → **strong other-timeframe conviction**, value should migrate that way. (p.46)
- Responsive = buyers below value / sellers above value → defending value, favors rotation.
- Same move is dual: "A responsive buying tail is also initiative selling range extension." (p.46)
- Confidence gradient: activity **outside** prior VA > activity **inside** it. (p.49)
- Valid tail ≥2 TPOs, rejection confirmed in ≥1 more period; last-period extension ≠ tail. (p.15,46)

## 3. Day Types (ascending conviction: Nontrend → Normal → Normal-Var → Neutral → Double-Dist → Trend)
| Type | IB relationship | Tradeable implication |
|---|---|---|
| **Normal** (p.20) | Wide IB base **not upset** all day; both-side tails, rotates inside | Fade IB extremes → middle; both edges hold |
| **Normal Variation** (p.22) | Moderate IB **tipped one side** by extension (usually early) | Trade *with* the extension; un-extended edge holds |
| **Trend** (p.22) | **Open = the extreme**, IB is one edge; one side controls open→close | Highest conviction; position with control, hold. "Failure to recognize a Trend day is one of the most costly mistakes." |
| **Double-Distribution Trend** (p.25) | **Very narrow IB, quiet open**, then LATE one-sided extension to a 2nd distribution | Trade the late break; **single prints between distributions = trigger/invalidation** |
| **Nontrend** (p.27) | Narrow IB, **no extension**, other tf never surfaces | Stay out (p.300) |
| **Neutral** (p.27) | **Extension on BOTH sides** of IB | Neutral-**center** (close mid) = balance, no edge; Neutral-**extreme** (close on high/low) = that side "won," directional |

*(Our `_classify_day_type` already mirrors this: wide-IB+no-ext→Normal, one-ext→Normal-Var,
both-ext→Neutral, one-ext+trend-sized+close-at-extreme→Trend/Double-Dist via `bimodal`.)*

## 4. The Open — four types (conviction High→Low; foreshadows the day, p.63)
| Open type | Behavior | Extreme | Conviction |
|---|---|---|---|
| **Open-Drive** (p.63) | Aggressive one-way, never returns through opening range | **Open = the extreme; holds "majority of cases"** | Highest — enter early, before confirmation; invalidation = trade back through open |
| **Open-Test-Drive** (p.65) | Tests a known reference, fails, drives other way | Failed test = extreme; "2nd most reliable" | High — enter near tested extreme |
| **Open-Rejection-Reverse** (p.68) | One way, then reversed back through opening range (late entry) | **Initial extreme holds <50%** | Lower — patient; expect retest of opening range |
| **Open-Auction** (p.70) | Convictionless around open | Depends on location vs prior day | Lowest in-range; **out-of-range = high-opportunity** (out of balance) → often Double-Dist |

## 5. Value migration
- Classified vs prior VA (p.46,49). **Open outside prior range = out of balance, "greatest
  risk and opportunity," dynamic move likely either way**; open accepted inside prior VA
  (≥1hr) = lower risk, less opportunity. (p.74)
- Range estimate: superimpose prior day's range length from a held extreme, ±10%. (p.76)

## 6. Explicit rules / tells / probabilities
- Open-Drive extreme holds "majority of cases" (p.63); ORR extreme holds "<half the time" (p.68).
- **Value-Area Rule (p.278–280):** open *outside* prior VA, then re-enter & accepted (double
  prints) *inside* → good odds it auctions **completely through** the VA. Reliability ↑ when
  open close to value, prior VA narrow, long-term auction agrees; else "little better than a
  coin flip." ⚠️ This 1993 ed. states it QUALITATIVELY — the "80% rule / two-30-min-periods"
  figure is NOT in this text (traces to Steidlmayer / later eds). **Do not attribute 80%.**
- Directional-conviction reversal: "92% of the time you will have an opportunity to exit your
  long within the previous day's value area" (p.278; one market, limited period — Dalton's caveat).
- Spikes (p.281): open within prior spike → rotation; beyond it → continuation; opposite → rejection.
- Double-Dist invalidation: probe back into the separating single prints = "something changed."
- Stay out: Nontrend, Nonconviction, news days (p.300).

---

## TESTABLE HYPOTHESES (ES 5M RTH 2021–2026) — pre-register before running
Existing features: `IB_High/Low/width`, `ext_up/dn`, `first_break`, `OLV/CLV`, `POC/VAH/VAL`,
`VA_width/skew`, `bimodal`, `ADR/DR_pct`, `prior_*`, `gap*`, `open_vs_prior_range/va`,
`va_migration`, `day_type`, `neutral_subtype`, `day_type_transition_matrix`, `gap_outcome_study`.

- **H0 (do FIRST — the bridge test, full 5.5yr, no gamma needed):** does the MC **hold-to-close /
  EOD profit** concentrate on the extension day types (Trend / Double-Dist / Normal-Var) vs
  the balance types (Normal / Nontrend / Neutral-center)? Uses `day_type` (already coded) ×
  the wide-target exit. If yes → theory-grounded "which days to hold" selector.
- **H1 Narrow-IB→extension continuation** — `IB_width/ADR` bottom tercile, enter first close
  beyond IB edge, with the break. Novel-ish; check it isn't the mirror of counter-IB-break skip.
- **H2 Wide-IB Normal fade** — likely OVERLAPS Keystone origin-at-IB fade; run as a Keystone
  robustness/calibration, not a new edge.
- **H3 Open-Drive extreme holds** ⭐ novel — build `open_type` classifier (first 3–6 bars);
  on Open-Drive enter with drive, invalidate on trade-back-through open. Needs new feature.
- **H4 Open-Rejection-Reverse retest fade** — novel; rides on H3's classifier.
- **H5 Value-Area Rule traverse** ⭐ novel — open outside prior VA, re-enter & hold 2 bars,
  target far VA edge; modifiers = narrow prior VA + long-term-trend agree. Register WITHOUT
  an 80% prior; measure actual traverse rate. Needs VA-traverse event feature.
- **H6 Neutral-extreme → next-session follow-through** — cheap; `neutral_subtype=='extreme'`
  prior day → next-day directional bias. Uses existing labels.

**Gamma tie-in:** H0 is the auction-side confirmation of the gamma synthesis. If extension
day types carry the EOD edge, the next question is whether **causal (prev-day) negative gamma
predicts those day types pre-market** — making gamma a leading indicator of "which playbook,"
tested on the 82 MQ days (thin → hypothesis-gen only).
