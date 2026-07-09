# Nine Transitions (Cadaver) — Deep Study & Actionable Extraction

**Source:** *Nine Transitions — Price Action Trading on the Emini*, "Cadaver" (ninetrans.blogspot.com),
2010–2012 article compilation, 405 pp. Brooks-lineage (BPA) discretionary ES price action.
**Method:** full text extracted, mined by 9 parallel reader-agents (one per ~45 pp), then synthesized here.
**Purpose:** convert the book into a categorized, *executable* rule set and map each rule to what we can
test on our ES bar+tick infrastructure (structure engine, tick-sim v3, WFA).

> **Reading note for us:** Cadaver's framework is the discretionary sibling of exactly what S62–S63 has
> been building. His "nine transitions" collapse trend/range/breakout the same way our regime + triangle +
> TTR engine does. Many of his reads (legs, HH/HL/LH/LL, OB traps, TTR, wedges, channels) are things our
> structure engine already computes — so a large fraction is directly backtestable.

---

## 1. The framework in one screen

**Market is only ever going up, down, or flat.** From each state it can transition to any of the three →
**3×3 = 9 transitions**, which collapse into **exactly four trade types:**

1. **Continuation** (up→up, down→down)
2. **Reversal** (up→down, down→up)
3. **Breakout** (flat→up, flat→down)
4. **Failed breakout** (flat→flat)

**The Setup Chart (FROM row × TO column):**

| FROM \ TO | UP | FLAT | DOWN |
|---|---|---|---|
| **UP** | *continuation up:* A2, 1CBO, hH1, G2, BT | *termination:* **TT → exit & stay out** (DT, TTR, fRev+fA2) | *reversal down:* W, W1P |
| **FLAT** | *breakout up:* BO → BP (TRI, XT) | *failed breakout:* **fBO** (WBO, rev-bar, DP) | *breakout down:* BO → BP |
| **DOWN** | *reversal up:* W, W1P | *termination:* **TT → exit** | *continuation down:* A2, 1CBO, hL1, G2, BT |

**The five rules that carry the whole book:**
1. **Counter-trend is low-probability until a trendline break.** *(The author's "if you take only one thing.")*
2. **Never trade the reversal itself — wait for it to succeed, enter the first pullback (1PB) of the new trend.**
3. **Trends = a series of breakout-pullbacks (BP). Trading ranges = a series of failed breakouts (fBO). Termination = exit signal, not a reversal.**
4. **In a trend, take breakouts; in a range, fade breakouts.** (BO succeed with-trend, fail in ranges.)
5. **Trade only well-formed signal bars** (shaved/≤1t entry-side tail, ≥2t body); size the stop to the bar, or skip.

---

## 2. Master actionable table

Deduped across all 405 pp. `Test` column = feasibility on our ES bar+tick data with the S63 structure engine.
`★` = high-value / cleanly-specified / high-priority to test.

### 2A. TREND (continuation / with-trend entries)

| Rule | When | Execute | Test |
|---|---|---|---|
| ★ **A2 / first-2-leg pullback** | Trend, 2-leg PB to ~20-EMA | Enter 1t beyond signal bar at the 2nd attempt (= failed L2/H2); stop 1t beyond bar (~5t) | **Yes** — engine gives legs+ema; measure win/MFE vs shallow PBs |
| ★ **1PB (first pullback)** | After trend establishes / after 1Rev | Enter 1PB; usually the day's best swing; stop often unviolated all day | **Yes** — define 1PB via first pivot after trend start; hold-to-EOD study |
| ★ **Deep-PB filter (4 conditions)** | Any trend | Require (1) trend exists (2) strong signal bar (3) no overlap (4) **PB ≥2 pts from extreme AND deeper than a recent bar** | **Yes ★** — MAE study: best entries pull back **≤4t**; >4t → profitable <10% of time |
| **hH1 / hL1 (hard-trend single-leg)** | Strong/hard trend only | Enter every small with-trend bar regardless of color; short every L1 / buy every H1 | Yes — needs "hard trend" classifier (bar size, no CT success) |
| **G2 (deep gap pullback)** | Strong trend, 1st gap-fill failed | Enter 2nd attempt; only if ≥4 pt potential | Yes |
| **Soft-trend: buy every failed L2** | Soft trend (PBs 1–2t, rarely close below prior) | Buy above any ≥2t body after fL2; sit through dojis/overlap | Yes — define soft trend by PB depth |
| **Spike & channel with-trend** | Strong spike + shallow (~⅓) PB | Enter 1st (maybe 2nd) PB; hold while no close below ema | **Yes** — spike = large bar; channel = overlap; measure MM=spike |
| **Small trend bar after BO bar = strength** | b(n) small trend bar right after strong BO bar | Enter with-trend; stop other end of small bar | Yes |
| **BT (breakout test) continuation** | PB to −1t..+2t of prior entry / ema / broken barrier | Buy limit at BT (doji OK here); stop beyond prior swing | Yes ★ — precise price zone |
| **Trailing-swing channel hold** | Early in a channel/trend day | Trail stop behind each new swing; hold to EOD/reversal | Yes — engine gives swings |

### 2B. TRADING-RANGE (TR / TTR / Barb Wire)

| Rule | When | Execute | Test |
|---|---|---|---|
| ★ **Fade every breakout in a TR** | Confirmed range, **width ≥4 pt** | Fade at range edges; target other end; expect **~half-range** move | **Yes ★** — engine TTR/range detection + fade sim |
| ★ **TR-day box (thirds)** | Not a trend day | Buy only lower third, sell only upper third; skip mid-range | **Yes** — opening-range thirds, quantifiable |
| **fBO = only 2 legs** | Failed breakout | Take fBO; scale out near target; re-enter on deep PB | Yes — measure leg count post-fBO |
| **TTR / Barb Wire → do NOT trade** | 3+ overlapping bars, ≥1 doji, bars <4t | Stand aside; only trade the fBO *out* of the TTR (usually with prior trend) | **Yes ★** — our TTR detector already fires here |
| **DP (double-top/bottom pullback)** | Near correct TR end, 2 failed attempts + 3rd short | Enter DP toward other end; target **~2× prior range**; only fades TRs, never extends | Yes |
| **Overlap = TR: buy below / sell above** | Any overlap bar ≥4 pt | Sell above / buy below the overlap; don't fade a trend bar | Yes |
| **Expanding-triangle (XT) BO** | Series of fBOs widening the range | Trade each move to opposite end until 2HH+2HL (bull) / 2LH+2LL (bear) | **Yes** — our expanding-triangle detector maps here |
| **2-leg move = A2 of the range** | TR day | Any well-formed 2-leg move to an extreme is tradable like an A2 | Yes |

### 2C. TRANSITION (reversal / termination)

| Rule | When | Execute | Test |
|---|---|---|---|
| ★ **Reversal needs TL break + failed test** | Suspected top/bottom | Do NOT trade the reversal; wait TL break, then enter **HL (bull) / LH (bear) = 1PB** of new trend | **Yes ★** — needs TL model; central edge to verify |
| ★ **Definitive reversal = 2 HH + 2 HL** (mirror bear) | Confirming a turn | Only call reversed after 2HH+2HL; take the HL entry, not the exact low | **Yes** — engine emits HH/HL/LH/LL directly |
| **W (wedge) reversal** | Obvious overshoot (>2t), ideally 2nd overshoot | Enter strong rev bar; better: **W1P** (first HL/LH after) | Partly — overshoot vs TCL is discretionary |
| **W1P (wedge first pullback)** | Right after a W reversal | Buy first HL / sell first LH; target = reverse the whole wedge | Partly |
| **fW (failed wedge) → MM** | A true wedge fails | Reverse; MM = size of the wedge to the other side | Yes |
| **Trend Termination (TT), 3 types** | End of trend | **Exit, don't reverse.** Types: (1) TTR (bars shrink to dojis) (2) DT/DB (PBs get shallower) (3) failed-reversal + failed-A2 | **Yes** — all three are bar/pivot-detectable |
| **fH1/fL1 measured move** | Hard trend, weak H1+signal | Enter with-trend on the failure; MM = start-of-move → failure point | Yes ★ — precise MM projection |
| **Failed 1PB/A2/W1P → reverse** | These specific setups fail | Reverse (failed 1PB long → 1PB short, etc.); BT/G2/1CBO are NOT reversible | Yes |

### 2D. BREAKOUT

| Rule | When | Execute | Test |
|---|---|---|---|
| ★ **Trade the BP, not the BO bar** | Any breakout | Enter the first pullback after a *successful* BO (no failure in 2–3 bars) | **Yes ★** — BO + PB, confirm no failure |
| **Strong-BO checklist** | Assessing a BO | Enter with-BO if: BO bar large / ≥½ beyond break point / strong close / no TCL overshoot / 2nd attempt / prior fBO other end | **Yes** — 4–6 boolean features → BO success model |
| **BO into a trend → succeeds; BO in a range → fails** | Regime-dependent | Take BO with-trend, fade BO in range | **Yes ★** — regime classifier + BO outcome |
| **Triangle BO breaks with prior trend** | Contracting triangle | Enter BO in prior-trend direction; run ≥2 legs | **Yes** — our contracting-triangle detector |
| **fBO → MM to other end / half range** | BO fails | Reverse; target other end (or half range) | Yes |
| **Opening-range BO+PB** | First bars form a range | 3-push failure one end → break other end; enter the 2-leg PB; MM = range size (2× on strong close) | Yes ★ |

### 2E. EXECUTION / RISK / MONEY-MANAGEMENT

| Rule | Execute | Test |
|---|---|---|
| ★ **Fixed stop 5t (6t inside/overlap); min risk 5t; need ≥6t to break even** | Never loosen; use 8t "money stop" for oversized bars | **Yes** — pure sim parameters |
| ★ **Reward×prob > risk** | Only take trades offering **≥2× risk** (e.g. 10t reward / 5t stop); skip anything unlikely to give ≥4 pts | **Yes** — trade-selection filter |
| ★ **MAE-tuned stops** | Best winning entries pull back ≤3–4t → 5t stop; tighten → bigger size same risk | **Yes ★** — compute MAE per setup from our sim |
| **Profit often, profit early** | Exit 1 unit at +1; move rest to BE after +1/+5t; trail beyond each new swing | Yes |
| **Enter ≥1t beyond signal bar, never mid-bar, never >1t late** | OCO "fire and forget"; only exit on stop / target / opposite triggered signal | Partly |
| ★ **2-of-5 loss policy** | Stop after 2 losses or 5 trades/day (var 3/6); EV ≈ +1 pt/day with −1.5/+2 | **Yes** — money-management overlay in sim |
| **Two-swing wait after any stop-out** | Don't re-enter until 2 swings form / price moves ~1–2 bar-widths | Yes |
| **Breakeven-swing structure** | −5t full size / +10t half → BE on rest; breakeven at ≥50% win | Yes ★ |
| **First-hour fixed-stop re-entry** | If a *fixed* (not theoretical) stop is hit in hour 1, re-enter (trade hasn't theoretically failed) | Yes |

### 2F. CONTEXT / READ (day-type, time-of-day, filters)

| Rule | Execute | Test |
|---|---|---|
| ★ **First-bar size → day range ≈ b1 × 5** | Nowcast the day's range from bar 1 | **VERIFIED on our data** (median 5.19×, corr 0.56) |
| ★ **Gap size → range, NOT direction** | Big gap → bigger *range*; does not predict trend | **VERIFIED/corrected on our data** (range↑ with gap, ER flat ~0.11) |
| **Open beyond prior range / large gap → trend-day candidate** | Take 1Rev/1PB, hold to EOD | Yes — classify + measure trend-day rate |
| **Open near prior close / no gap → TR day (~80%)** | Fade both directions; expect half-range | Yes |
| **Large first bar (≥3 pt) or huge single bar → TR / spike** | Treat as range; never take 1st reversal | Yes |
| **~80% AM-trend-then-TR; ~20% all-day trend** | Catch AM trend, ride it; end after a winning AM | Yes — measure AM-trend frequency |
| **Time-of-day map** | open→opening-range→OR BO/rev→AM trend→lunch chop→lunch BO→PM trend; sit out lunch or fade its BO | Yes — bucket edge by time |
| **With-trend ~55–60% vs counter-trend ~40–45% win** | Bias every marginal decision with-trend | **Yes ★** — measure directly with our sim |
| **Know your "kryptonite"** | Identify the PA type that kills *your* edge, avoid it | Meta / journaling |

---

## 3. Measured-move & numeric reference card

| Item | Value |
|---|---|
| Min risk (ES) | 5t; need ≥6t to break even (commissions) |
| Fixed stops | 5t normal, 6t inside/overlap, 8t "money stop" for oversized bars |
| Target minimum | ≥4t; won't take trades unlikely to give ≥4 pts; swingable = 2×–4× risk |
| Scalp / swing structure | scalp +2 (later +2.5), swing +4/+8/+10; move to BE after +1/+5t |
| **Day range ≈ b1 × 5** | **verified median 5.19× on 1,260 ES days** |
| Average day | ~10 pts; "large bar" = ≥3 pts (acts as a TR); avg bar ~2 pts |
| Trend-day frequency | ~20% (trend+TR plans cover ~90% of days) |
| Deep pullback | ≥2 pts from extreme AND deeper than a recent bar; ~10t room |
| **MAE of good entries** | pull back **≤4t** after trigger; >4t → profitable <10% of time |
| Range BO success | ~2× range; fBO → other end / ½ range |
| fBO | exactly 2 legs; needs TR ≥4 pt (≥8–10 pt to be worth it) |
| Wedge overshoot | >2t (2nd overshoot preferred); W1P entry not >1t below entry bar |
| fH1/fL1 MM | start-of-move → failure point |
| fW MM | size of the wedge |
| AB=CD | first leg predicts 2nd leg ≈ same points after 1st TL break |
| Tick-failure targets | round numbers +1/+2/+4/+8/+10 attract CT orders → 1tf/5tf/9tf fades |
| Two-strikes EV | ≈ +1 pt/day (−1.5 stop / +2 target); ~75% of days lose trade 1 or 2 |
| Barb Wire bars | <4t, ≥1 doji; TTR day = bars <4t for many bars |
| Channel stop | shallow-wide channel needs >6t (≥2 pt) |

---

## 4. Day-type taxonomy (Cadaver)

- **Trend day (~20%)** — small first reversal → protracted trend; take every with-trend setup, hold to EOD.
- **Trading-range day (~80%)** — series of fBOs; fade extremes; ~half-range moves.
- **Hard trend** — long bars, few entries, big moves; **no counter-trend, ever**; breaks but rarely reverses without hours of TR first.
- **Soft trend / Glacier** — slow grind (usually up); shallow 1–2t PBs; buy every failed L2; shorting bleeds.
- **Spike & Channel** — large spike then a channel (channel is a wedge → 3 pushes → test of channel start); MM = spike size.
- **Channel hierarchy (fractal):** **TRC → LC → TC → Trend** (weakest→strongest). Transition up = breakout coming; down = terminating. *Every reversal inside a channel is a trap; never counter-trend until the shallowest TL breaks.*
- **Expanding-triangle / triangle open**, **narrow / dojistan / poor-bar day** (bars ≤4t → sit out or scalp only), **FOMC/news day** (trade the BO's failure).

---

## 5. Psychology / discipline (condensed)

- Reduce to ~5 trades/day (≈ number of real directional changes). More trades → higher chance of losing.
- Fixed risk & size; grow only with proven consistency (SIM→1→up). Never add to a loser; never loosen a stop.
- Daily/weekly/monthly loss limits → switch to SIM on breach. "First loss is the best loss."
- **Rule of ten** (graduate off SIM): ≥10 pts/wk × 10 wks; ≥10 no-loss days; ≥10 consecutive winning days; worst day ≤ ½ avg winning day.
- Add setups one at a time, ~100-trade proof each, in order: **A2 → W1P → DP → fBO** → 1CBO, G2, 1PB, 1Rev, hard-trend L1/H1, XT.
- "A 70%-one-setup trader beats a 50%-hundred-setup trader." "Fewer parameters → more confidence."

---

## 6. Mapping to OUR project — what's testable now

Our S63 structure engine already emits the primitives most of these rules need: **legs, swing pivots
(HH/HL/LH/LL), OB tick-order decomposition, contracting/expanding triangles, TTR zones**, plus a tick-sim
(v3), ATR/EMA, and a WFA harness. That makes a large fraction of Cadaver directly backtestable.

**Directly testable now (high value, cleanly specified):**
1. ★ **Deep vs shallow pullback edge + MAE ≤4t stop** — we have legs/pivots; measure MFE/MAE by PB depth. Confirms/kills the core "1PB/A2 deep-PB" edge and the 5t-stop choice.
2. ★ **With-trend vs counter-trend win rate** (claim 55–60 vs 40–45) — label entries by regime, measure. Also validates rule #1 (CT only after TL break).
3. ★ **fBO gives ~2 legs / TR fade edge** — our TTR + triangle detectors define the range; sim the fade.
4. ★ **Tick-failure fades at round targets (+1/+2/+4/+8/+10)** — needs tick data (we have it). Novel, concrete, not yet studied here.
5. ★ **Regime-conditioned breakout outcome** (BO succeeds with-trend, fails in range) — feeds directly into the S62 regime fix.
6. **Day-range = b1×5 nowcast** — DONE (verified). Wire into a day-type/context screen.
7. **2-of-5 loss policy & breakeven-swing money management** — pure sim overlays.

**Harder / discretionary (needs a model first):** wedge overshoot vs TCL, "obnoxious" overshoot,
channel-type classification (TRC/LC/TC), signal-bar "quality," reversal "obviousness." Several become
testable once we add a **trendline / TCL model** and a **channel classifier** on top of the pivot engine.

**Empirical results already obtained (this session):**
- Day range ≈ **5.19×** first-bar range (median), corr 0.56 — **usable nowcast**.
- Gap predicts **range not direction** (ER flat ~0.11 across gap quartiles) — matches our S60 IB-width lesson; **do not** use gap as a trend-direction signal.

**Recommended next tests (priority order):**
1. Deep-PB/MAE study on the leg engine → validates the 5t stop and the A2/1PB edge (feeds sim v4).
2. With-trend vs CT win-rate + "CT only after TL break" → **directly informs the S62 regime redesign**.
3. Tick-failure fade at round-number targets → cheap, novel, tick-data study.
4. Regime × breakout outcome → the BO-success checklist as features.

---

## 7. Glossary (condensed)

`A2` 2nd attempt / 2-leg PB to ema · `1PB` first pullback · `1Rev/OR/XOD` first reversal / opening reversal /
extreme-of-day reversal · `H1/H2 L1/L2` first/second with-trend PB entries · `fH1/fL2` failed versions (with-trend
triggers) · `W/W1P` wedge (3-push) reversal / its first pullback · `DP` double-top/bottom pullback · `DT/DB`
double top/bottom · `fBO` failed breakout · `BP` breakout pullback · `BT` breakout test (−1t..+2t of entry) ·
`BO` breakout · `1CBO` first channel breakout (usually fails) · `MM` measured move (1:1) · `TT` trend termination
(exit, not reverse) · `TTR` tight/terminal trading range · `BW` barb wire (3+ overlaps, ≥1 doji) · `XT` expanding
triangle (series of fBOs) · `G/G2` gap-bar with-trend entry · `TL/TCL` trendline / trend channel line · `MTL`
micro-trendline · `FF` final flag · `1tf/5tf/9tf` 1/5/9-tick failure at a target · `S&C` spike & channel ·
`TRC/LC/TC` trading-range / leg / trend channel · `MAE` max adverse excursion · `Glacier` slow bullish grind ·
`Kryptonite` the PA type that kills your edge.

---

*Compiled S63 (2026-07-09). Full extracted text + per-chunk agent extractions in the session scratchpad.
Raw book: `~/Desktop/ninetrans_book.pdf`.*
