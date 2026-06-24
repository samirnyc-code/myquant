# 0005 — RevFT Trade Location: VWAP Deviation & Value Area — 2026-06-24
**Series:** MC Setup Research Notes · Note 0005
**Confidence:** High **as a negative result** — 5 years, full-cost, real-tick, the headline gate was **pre-registered** and judged in R with year-by-year CIs. We are confident there is *no tradeable location edge* here; we are *not* claiming a positive system.

**TL;DR:** We tried to rescue the RevFT ("MyReversals") signal set — a firm net loser at 1:1 — by finding *where* it should be traded. Three location axes: distance to the day's developing extremes (prior work), deviation from the developing-session VWAP, and position vs the prior-day value area. **The obvious intuition — that a reversal works better when price is stretched far from VWAP — is not just unsupported, it is backwards: the deeper the stretch, the worse the fade (it gets run over).** The only coherent signal points the *other* way: RevFT behaves weakly like a *with-trend continuation* trade (better on the far side of VWAP in the trade's direction, improving with a wider target). But when we pre-registered that as a gate and tested it honestly, it only reaches **break-even**, and its entire result is carried by a single year (2022); 2025 and 2026 are significantly negative. **Recommendation: there is no location fix for RevFT. Retire it as a fade. Its problem is directional/structural, not where you take the trade.**

---

## 1. The setup (so this note stands alone)

**The RevFT trade.** "RevFT" (a.k.a. *MyReversals*) is a swing-**reversal** signal on 5-minute ES: it fires when price rejects a recent swing extreme, betting on a turn. You enter at the first tick after the signal bar closes, stop just beyond the rejected extreme (`StopPrice`), and exit at a fixed multiple of **R** (R = entry-to-stop distance). ES: 1 point = $50/contract, 1 tick = $12.50. Two price anchors are recorded per signal: `SignalPrice` (the trigger, a few ticks back inside the swing) and `StopPrice` (just beyond the extreme the reversal formed off).

**Why we're even here.** At a 1:1 target RevFT loses money outright — **−$187k net / −$79k even frictionless**, 6,133 trades over five years (Note: this is a real *directional* loss, not pure cost bleed). Earlier work showed you cannot fade or flip your way out of it. The remaining hope was **selection**: maybe a *subset*, defined by trade location, clears the ~$15/trade cost hurdle. This note tests that hope and closes it.

**The two location features (both look-ahead-safe).**
- **VWAP deviation (`VWAP_dev`).** The developing-session VWAP is the volume-weighted average price *so far today* (resets each RTH session, uses only bars up to the signal). `VWAP_dev = (Close − VWAP) / σ`, where σ is the volume-weighted standard deviation of price from VWAP so far. It is the signed **number of σ** the signal sits from VWAP: negative = below VWAP, positive = above. For a **long**, a mean-reversion fade (buy an oversold dip) is **below** VWAP (`VWAP_dev < 0`); for a **short**, it is **above** (`VWAP_dev > 0`).
- **Prior-day value area (VAH / VAL).** The price band containing 70% of *yesterday's* volume (POC = point of control, VAH/VAL = its high/low). We use the **prior completed** session's value area as today's reference — never today's developing one — so it is causal. `vaD_loc` = signal above / inside / below it; `vaD_dist` = signed distance beyond the edge.

**Cost model.** $4.36 round-turn commission + 1 tick entry slippage, 0 exit. All sims replay **real continuous ticks day-by-day** through the production engine. Signal set: `ba_signals_revft.parquet` (6,328 signals, 2021-06 → 2026-06; 6,133 fill). Features are tagged **causally** through the S34-corrected `tag_signals` chokepoint (see Note 0002 for the look-ahead fix this depends on).

---

## 2. The question

1. **Is there a subset of RevFT, defined by where the signal sits relative to VWAP and to value, that turns the loser into a winner — or at least clears the cost hurdle?**
2. **Specifically: do reversals work better when price is *extended* from VWAP** (the standard mean-reversion intuition)?
3. **If a pattern appears, is it a real edge or a single-regime artifact?** (Pre-register the gate; judge in R; check every year.)

---

## 3. How we tested it (the menu)

Three descriptive bucket studies, each on the real tick engine, pinned single-leg, with ±95% CIs, judged **in R** (not dollars — see §4.6 on why):

1. **Static location** *(prior work, recapped):* signed distance from the **developing HOD/LOD** and **prior-year HOY/LOY**, both anchors.
2. **VWAP deviation:** bucket filled trades by `VWAP_dev`. First a coarse directional pass, then **0.5σ slices, long-only and short-only separately** (no sign transform — read straight off the table), at **1R / 2R / 3R** to test whether a tight exit was hiding a reversion edge.
3. **Prior-day value area:** categorical location (above / inside / below) and signed distance beyond the responsive-fade edge.
4. **Confirmation:** the one coherent pattern (a *continuation* tilt) was written down as a **pre-registered gate** and tested full-sample + year-by-year at 1R/2R/3R.

Engine: tick-by-tick first-touch (entry at first tick after the signal; stop/target by tick crossing), unlimited-positions scoring.

---

## 4. Results

### 4.1 Static location (prior work) — already dead

Bucketing by distance to the **developing day extreme** (the "catch the knife at the low/high" idea): the *at-the-extreme* band (±0.05 ADR) is the **worst** bucket, with no gradient toward it.

| Distance to developing extreme (ADR, SignalPrice) | n | Exp R | PF | Win % |
|---|---|---|---|---|
| **−0.05 .. 0.05 (AT the extreme)** | 74 | **−0.296** | 0.68 | 36.5% |
| 0.05 .. 0.15 | 1,622 | −0.130 | 0.81 | 44.3% |
| 0.15 .. 0.30 | 2,001 | −0.056 | 0.94 | 47.5% |
| > 0.60 (deep inside range) | 782 | −0.034 | 0.88 | 48.1% |

Firing right at a *still-forming* extreme = catching a knife into a level still being made. Prior-year HOY/LOY proximity was equally null. **Static location: closed.**

### 4.2 VWAP deviation, directional view — no edge, hint of the wrong sign

Re-expressing `VWAP_dev` as "stretch on the mean-reversion-favorable side" (S = −dev for longs, +dev for shorts; S>0 = the textbook fade location), 1R, both directions:

| Directional stretch S (σ) | n | Exp R | PF | Win % |
|---|---|---|---|---|
| < −1.0 (fading on the *continuation* side) | 1,368 | −0.052 | 0.95 | 47.6% |
| −0.25 .. 0.25 (at VWAP) | 675 | −0.055 | 0.93 | 47.7% |
| 1.0 .. 2.0 (favorable stretch) | 1,550 | −0.087 | 0.88 | 46.3% |
| **2.0 .. 3.0 (deep favorable stretch)** | 54 | **−0.566** | 0.28 | 22.2% |

Every bucket loses, and the **most "favorable" (deep) stretch is catastrophic**. The gradient runs the wrong way. This coarse view flagged the result; the slices below nail it.

### 4.3 The decisive test — 0.5σ slices, no sign transform (1R)

Raw `VWAP_dev`, long-only and short-only, so there is zero sign ambiguity. For a **long**, the mean-reversion fade is the **left** (negative) cells; for a **short**, the **right** (positive) cells.

**LONG only (1R):**

| VWAP_dev (σ) | n | Exp R | ±R CI | PF | Win % |
|---|---|---|---|---|---|
| −2.5 .. −2.0 *(deep fade)* | 15 | −0.479 | ±0.464 | 0.35 | 26.7% |
| −2.0 .. −1.5 | 170 | −0.107 | ±0.143 | 0.84 | 45.3% |
| −1.5 .. −1.0 | 522 | −0.052 | ±0.082 | 0.98 | 48.9% |
| −1.0 .. −0.5 | 498 | −0.107 | ±0.084 | 0.84 | 45.8% |
| −0.5 .. 0.0 | 389 | −0.132 | ±0.093 | 0.77 | 43.2% |
| 0.0 .. +0.5 | 306 | −0.050 | ±0.106 | 0.95 | 47.4% |
| **+1.0 .. +1.5** *(continuation)* | 412 | **+0.005** | ±0.091 | 1.17 | 49.8% |
| +2.0 .. +2.5 | 74 | +0.016 | ±0.213 | 1.17 | 52.7% |

**SHORT only (1R):**

| VWAP_dev (σ) | n | Exp R | ±R CI | PF | Win % |
|---|---|---|---|---|---|
| **−3.0 .. −2.5** *(continuation)* | 30 | **+0.197** | ±0.344 | 2.28 | 60.0% |
| −2.5 .. −2.0 | 83 | −0.099 | ±0.203 | 0.84 | 44.6% |
| −0.5 .. 0.0 | 321 | −0.055 | ±0.105 | 0.77 | 47.7% |
| +0.5 .. +1.0 | 484 | −0.075 | ±0.085 | 0.91 | 46.5% |
| +1.0 .. +1.5 *(favorable fade)* | 568 | −0.062 | ±0.079 | 0.91 | 47.0% |
| +1.5 .. +2.0 | 290 | −0.188 | ±0.111 | 0.63 | 41.0% |
| **+2.0 .. +2.5** *(deep favorable fade)* | 38 | **−0.641** | ±0.250 | 0.23 | 18.4% |

Read it directly: **fading *into* a 2σ+ VWAP stretch (long far below / short far above) is the worst thing you can do** — the extension keeps going and runs over the fade. The only green cells are on the **continuation** side (long *above* VWAP, short *below*). RevFT signals are also nearly symmetric around VWAP (longs median −0.10σ, shorts +0.37σ) — they mostly fire *near* VWAP, so "extended reversal" is a small, hostile corner.

### 4.4 Was a tight 1:1 hiding it? No — 2R and 3R say the same

If the reversion edge were real but clipped at 1R, widening the target would reveal it. It doesn't — the reversion (deep-fade) cells stay red at every target, while the *continuation* cells get *better* with a wider target (a momentum signature). Same two cells across targets:

| Cell | 1R | 2R | 3R |
|---|---|---|---|
| Long deep fade (−2.5..−2.0σ) | −0.479 | −0.319 | −0.452 |
| Short deep fade (+2.0..+2.5σ) | −0.641 | −0.573 | −0.588 |
| Long continuation (+1.0..+1.5σ) | +0.005 | +0.032 | **+0.091** |
| Short continuation (−3.0..−2.5σ) | +0.197 | +0.393 | **+0.505** |

(Full 14-band × long/short × 1R/2R/3R grids in the saved artifact.) The exit is not the problem. The *direction of the premise* is.

### 4.5 Prior-day value area — same story, no independent edge

**Categorical location (1R, both directions):**

| Signal vs prior value area | n | Exp R | PF | Win % |
|---|---|---|---|---|
| above prior VAH | 2,287 | −0.067 | 0.95 | 46.9% |
| inside | 1,897 | −0.093 | 0.87 | 46.0% |
| below prior VAL | 1,949 | −0.096 | 0.83 | 45.4% |

"Above value" is least-bad — again the *continuation/breakout* side, not the responsive-fade side. The directional "distance beyond the responsive-fade edge" (V) trends the wrong way too: the **deeper beyond the value edge, the worse** (V > 0.60 → −0.134R). No value-area cell clears the hurdle with a CI excluding zero.

### 4.6 The continuation inversion — pre-registered, then judged honestly

Every coherent signal pointed one way: **RevFT works (weakly) with the trend, not against it.** We wrote that down *before* testing as a fixed gate:

> `continuation = (Long & VWAP_dev > +0.5σ) OR (Short & VWAP_dev < −0.5σ)`

and judged it in R, full sample, at three targets. A caution first: the apparently positive dollar pockets in §4.5/§4.2 are a **wide-stop illusion** — they win in *dollars* only because their trades carry bigger stops (more $ per R), while their *R* is flat-to-negative. The Keystone note hit the same trap; we judge in R for exactly this reason.

| Target | CONTINUATION gate | R 95%-interval | REVERSION complement | NEUTRAL (\|dev\|≤0.5) |
|---|---|---|---|---|
| 1R | −0.072 | [−0.113, −0.031] **loser** | −0.099 | −0.081 |
| 2R | −0.034 | [−0.088, +0.021] incl. 0 | −0.108 | −0.113 |
| 3R | −0.016 | [−0.078, +0.046] incl. 0 | −0.104 | −0.074 |

Two honest readings:
- **The split is real and robust.** Continuation beats reversion by ~0.07–0.09R at every target, and the reversion complement's interval excludes zero on the *negative* side throughout. RevFT is structurally a continuation signal, not a fade.
- **But continuation alone only reaches break-even.** It climbs −0.072 → −0.034 → −0.016R as the target widens and *asymptotes at zero* — it never becomes positive-significant. Avoiding the loss is not making money.

### 4.7 Year-by-year — the gate is one regime, not an edge

The continuation gate at 3R, by year — the test that decides it:

| 2021 | 2022 | 2023 | 2024 | 2025 | 2026 |
|---|---|---|---|---|---|
| −0.149 (incl. 0) | **+0.185** [+0.035,+0.336] | −0.037 (incl. 0) | +0.081 (incl. 0) | **−0.150** [−0.274,−0.025] | **−0.203** [−0.389,−0.017] |

The entire break-even result is **carried by 2022** (+$45,650 on one contract — a strongly trending bear year where continuation paid). Strip 2022 and the gate is a loser, with **2025 and 2026 significantly negative**. This is the textbook one-regime artifact. Pre-registering the gate and demanding year-by-year stability is precisely what stops this from being mis-logged as a "continuation edge."

---

## 5. Why it fails

**Why the fade premise is wrong.** A VWAP that price has stretched 2σ away from is not an exhausted rubber band on this signal — it is an *imbalance in progress*. RevFT's swing-rejection trigger fires into that imbalance, and the imbalance wins more often than it reverts. Fading deeper extension just buys a worse spot in a continuing move. That the deepest-stretch cells are the *most* negative (long −2.5σ → −0.48R; short +2.0σ → −0.64R) is the clean fingerprint of "trend, not mean-reversion."

**Why even the continuation inversion isn't an edge.** Selection can only *concentrate* structure that exists; it cannot manufacture it. RevFT's base population has a real negative directional edge (it loses even frictionless). Slicing it by VWAP side finds the *least-negative* corner — the with-trend trades — and that corner happens to be ~zero on average and strongly positive only when the whole market trends (2022). It is regime beta, not a stable selection edge. No exit (1R–3R) and no location (extremes, VWAP, value) repairs a signal whose core directional sign is wrong.

---

## 6. Recommendation

> **1. There is no trade-location fix for RevFT. Retire it as a fade.** Every location axis is dead: static extremes (§4.1), VWAP deviation (§4.2–4.4), prior-day value area (§4.5). The mean-reversion intuition is *falsified*, not merely unconfirmed — extended fades are the worst trades in the book.
>
> **2. Do not deploy the "continuation" version either.** It is break-even at best (§4.6) and its positive years are one regime (2022); 2025–26 are significantly negative (§4.7). It would fail forward.
>
> **3. The only durable takeaway:** *if* RevFT is ever used at all, it must be **with-trend** (on the far side of VWAP, in the trade's direction) and **never as a fade into extension** — but treat even that as a 2022 artifact until proven on truly held-out data. The honest conclusion is that RevFT's problem is **directional/structural, not locational**, and effort is better spent elsewhere (e.g. the audited MC IB-edge fade, Note 0003).

---

## 7. Caveats & open questions

- **This is a negative result, stated with confidence.** Five years, full cost, real ticks, pre-registered gate, judged in R with CIs — strong evidence of *absence* of a location edge. It is not proof that *no* conceivable feature rescues RevFT, only that the two the structure most strongly suggested (VWAP stretch, value-area edge) do not.
- **In-sample thresholds.** The +0.5σ continuation cut was chosen on this same 5-year set; §4.7 shows it fails year-by-year anyway, which only strengthens the negative.
- **The continuation tilt is real but small and regime-bound** — worth remembering as a *property of the signal* (RevFT ≈ momentum, not reversion), not as a tradeable rule.
- **Developing (intraday) value area untested.** We used the *prior-day* value area (the look-ahead-safe one). A causal *developing* VA-at-the-bar is buildable but, given how decisively both the VWAP and prior-VA axes failed, is low-priority.
- **Selectivity-at-wider-R for the whole set** (trade far less, not by location) remains formally open, but two independent location studies plus a falsified premise make it a poor bet.

---

## 8. Reproduce

Scripts (headless, day-by-day tick replay against the production engine; no production code changed):

- `scripts/reversal_at_extreme_study.py` — static location: developing HOD/LOD & HOY/LOY buckets (§4.1)
- `scripts/revft_vwap_va_location.py` — directional VWAP stretch, prior-day value area, 2-D cross (§4.2, §4.5)
- `scripts/revft_vwap_slices.py` — 0.5σ VWAP_dev slices, long/short, at 1R/2R/3R + sign sanity (§4.3, §4.4)
- `scripts/revft_continuation_gate.py` — pre-registered continuation gate, full-sample + year-by-year (§4.6, §4.7)

Saved artifacts (in `docs/living/`): `reversal_at_extreme_study_20260624.md`, `revft_vwap_va_location_20260624.md`, `revft_vwap_slices_20260624.md`, `revft_continuation_gate_20260624.md`.

Feature definitions (look-ahead-safe, via `tag_signals`): `VWAP_dev = (Close − VWAP)/σ` on the developing session VWAP (`auction_features.session_vwap_bands`); prior-day value area `vaD_VAH/VAL/loc/dist` from the prior completed session's 70%-volume profile. Continuation gate: `(Long & VWAP_dev > +0.5) OR (Short & VWAP_dev < −0.5)`, judged in R at 1R/2R/3R.
