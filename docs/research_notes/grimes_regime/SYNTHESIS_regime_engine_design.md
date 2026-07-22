# Grimes → Regime Engine: Synthesis & Design Candidates
**Date:** 2026-07-22 (S81) · **Sources:** Grimes, *The Art & Science of Technical Analysis* (Wiley 2012, 480pp) + *The Art & Science of Trading* course workbook (609pp) — full-text extraction, 11 chunks, see `raw_*.md` in this folder for page-cited detail.
**Goal:** a regime engine for ES that classifies **BULL / BEAR / TRANSITION / NO-TRADE**.
**Constraint (memory `brooks_regime_engine_broken`):** the old Brooks always-in engine is banned; only structure/fill primitives may be reused.

---

## 1. Grimes's regime model in one paragraph

Markets are near-random most of the time (default state = no-edge). All action lives between two poles: **range expansion (momentum / positive autocorrelation)** and **mean reversion (negative autocorrelation)** — aggregated they cancel, which is why unconditioned stats find nothing; the engine's whole job is *conditioning first* (workbook p.438). The cycle is Wyckoff's: accumulation → markup → distribution → markdown, with the interfaces (breakout, termination, reversal) being where both the opportunity and the failure modes live. The one robust nonrandom feature is **volatility clustering**: *mean reversion follows expanded volatility; range expansion follows compressed volatility* (workbook p.594–602). "Most trading losses come from incorrectly identifying the emerging volatility environment."

Two critical asset-class facts for us:
- **Futures behave differently from equities** in Grimes's own tests: MA-slope/triple-MA states have the CORRECT sign in futures (equities invert); futures show continuation after big single days and after Donchian breakouts; equities/indices mean-revert. The S&P **cash index** mean-reverts after multi-day runs (P(continue|5-day run)≈47.5%, |6-day run) = 39%).
- **Intraday index products rarely extend beyond 3 trend legs** (book p.170) and ~1 in 5 sessions rewards trend-pressing (workbook p.403) — ES intraday is chop-dominant.

---

## 2. The four states, defined in Grimes terms

### BULL / BEAR (trend regime)
Structural (primary — Grimes: structure leads indicators):
- Dow: higher pivot highs AND higher lows (both required); mirror for bear. Pivots = order-1/order-2 recursion; swings via ATR-filtered zigzag ("first-level pivots qualified by movement of a certain ATR away" — workbook p.507; his own hand chart used 3× average bar range).
- Swing asymmetry: with-trend swings longer than countertrend swings in BOTH price and time (book p.34, p.99).
- Retracements hold ≤100% of the setup leg (higher low). Futures retracement distribution (qualified): mean ~62%, SD ~21% → **40–80% retracement is NORMAL, not weakness**. Deeper retracements actually precede LARGER extensions (workbook Table 13.8 — monotone).
Indicator confirmation (secondary):
- Price stays one side of the 20-EMA; MA slope non-flat (3-state: up/down/undefined — the undefined zone is mandatory, book p.97).
- Modified MACD (SMA 3-10-16): fast line makes new momentum extremes with-trend; **failed divergences accumulating is itself trend confirmation** ("trends roll over momentum divergences", book p.223); fast line "drive and hold" = strong trend, never fade.
- Keltner (20-EMA ± 2.25 ATR, ~85% containment): closes beyond the band with-trend, pullbacks to mid-channel.
Trend-health checklist (stay-in-state conditions, book p.236):
- Each with-trend leg momentum ≈ consistent with prior legs; no sharp countertrend momentum on pullbacks; ≤3 legs (suspicion rises per leg, ES rarely >3 intraday); no climax; pullbacks on reduced activity.

### TRANSITION
Grimes's hard rule (workbook p.373): transition requires a **two-step sequence** — (1) a trend-break event from the named set {climax/exhaustion, three pushes, failure test at extreme, momentum divergence, price rejection}, then (2) **change of character = new momentum extreme in the OPPOSITE direction** (countertrend swing longer in price AND time than prior counterswings, MACD new opposite extreme). Absent step 2, stay in trend state.
Break-event detectors (each codable):
- **Climax:** bar range ≥3× recent average at a new extreme breaking the trend's rhythm; free bars (entire bar outside Keltner — base rate ~3.8% in futures); parabolic acceleration; swing 2–3× average swing length; consecutive closes at bar extremes (statistically exhaustion, not strength).
- **Three pushes:** three time/price-symmetric drives to new extremes with compressed spacing vs earlier trend.
- **Failure test (spring/upthrust):** probe beyond a prior extreme, close back inside within 1–3 bars (≤2–3 bars outside max); "common for trends to end with a final failure test at the highs."
- **Divergence:** only valid after the fast line touched/neared zero between compared points; resets on return to 20-EMA, fast-line zero-cross, or 10+ bars.
- **First countertrend swing larger than the preceding with-trend swing** (in time OR price) — "the single most important pattern in length of swing analysis" (book p.100).
- **Structure flag:** repeated failed breakouts from with-trend consolidations = "character has changed" (workbook p.109-111).
Confirmation state machine (Dow, book p.95-96): failed new high → **UNCERTAIN** (not bear); bear only when LH + LL both present. Must special-case complex (two-legged) pullbacks or the machine flips at exactly the wrong spot. First countertrend thrust typically exhausts at the measured-move objective (AB=CD); if MMO holds → old trend likely resumes.
Base rate: **most trend terminations lead to ranges, not reversals** — transition should default-resolve to NO-TRADE/range, not the opposite trend.

### NO-TRADE (chop / equilibrium / range interior)
- **Default state.** "Markets are usually near-efficient; most price movement is random."
- Primary detector: price chopping BOTH sides of the intermediate (20-period) MA with no significant departure — "absence of departure virtually guarantees that an imbalance does not exist" (book p.208-209).
- Range interior is a random walk: direction, timing, and exit of a range are all unpredictable — only the EDGES are tradable (springs/upthrusts/failure tests).
- Additional no-trade sub-states:
  - **Spike through both Keltner bands in opposite directions** → triangle/oscillation regime, "best avoided" (book p.217).
  - **Expanding ranges** → resolve into random low-vol ranges, not strong moves — avoid.
  - **Post-climax cooldown**: after a climax, no with-trend entries until worked off by time/consolidation.
  - **Runaway "slide along the bands" trend**: strongly directional but untradeable by pullback logic (no retracements; ends in sharp counter-pops) — flag as its own sub-state: directional but no-entry.
- Range default prior = **continuation** of the preceding trend ("innocent until proven guilty"); accumulation vs distribution discriminated by spring-vs-upthrust behavior and which edge price hugs.

---

## 3. The volatility layer (Grimes's strongest quantitative result)

Run a volatility state machine PARALLEL to the directional one — it conditions which force dominates:
- **Compressed** (5-day/40-day ATR ratio < 0.5, or HV in bottom 20th percentile): expect RANGE EXPANSION. His vol-compression-breakout test is the strongest futures continuation signal in either book: trigger = day's TR ≥ 5-day ATR with close top-half and above prior close → +128bp** by d4, 73% up d5. In this state: suppress mean-reversion plays, trust breakouts.
- **Expanded** (post σ-spike ≥2.5–3.0, spike = return ÷ yesterday's 20-day return-stdev): expect MEAN REVERSION — but note in FUTURES big single days lean continuation (Table 16.1 not significant for fading futures). Vol shocks persist (GARCH); "do not expect a quick return to quiet markets."
- Vol clustering is NON-directional: it predicts magnitude, not direction.
- Slow regime markers: rolling new-high/new-low day counts (bull decades ~300 high-days vs single-digit low-days); realized-vol level (high-vol = bear/crisis); "declining markets are more volatile" is what makes any long-only MA filter work, not the MA period.

---

## 4. Codable feature set (candidate inputs)

| # | Feature | Spec | Source |
|---|---------|------|--------|
| 1 | ATR-zigzag swings | first-order pivots qualified by k×ATR move (k≈3 avg bar range start) | wb p.507, p.64 |
| 2 | Swing asymmetry | up-leg vs down-leg length in price AND bars, rolling | book p.34, 99 |
| 3 | Dow state machine | HH/HL vs LH/LL on order-2 pivots, with UNCERTAIN state + complex-pullback exception | book p.94-96 |
| 4 | Keltner position | 20-EMA ± 2.25×ATR; %closes outside, free-bar count, slide-along-band flag, both-band-spike flag | book p.212-218, wb p.589 |
| 5 | Modified MACD | SMA 3-10-16; new-extreme flags, divergence (with validity+reset rules), zero-cross, drive-and-hold | book App.B |
| 6 | MA slope 3-state | slope of 50-SMA via 5-point linear regression on the average; undefined zone | book p.97, wb p.548 |
| 7 | Triple MA order | 10/20/50 SMA ordered = trend, interleaved = undefined (futures short side strongest) | wb Table 14.11 |
| 8 | Vol ratio | 5d ATR / 40d ATR (<0.5 = compressed); or 10d/60d HV | wb p.595-598 |
| 9 | σ-spike | return ÷ prior 20d return-stdev; flag ≥2.5–3.0 | wb p.450, book p.273 |
| 10 | Climax bar | range ≥3× recent avg at new extreme + rhythm break; long shadow with-trend | wb p.192, book p.313 |
| 11 | Leg counter | trend legs since regime start; ≥3 → elevated failure prob (ES intraday rarely >3) | book p.150, 170 |
| 12 | Retracement depth | BC/AB of current pullback; ≤100% = trend intact; 40–80% normal | wb Ch.13 |
| 13 | Failure test detector | probe beyond level, close back inside ≤2–3 bars; stop-run quality (≥ ~10 ES handles flush) | book p.146, wb p.316 |
| 14 | Consolidation-resolution counter | direction of consolidation breakouts + large-σ bars by direction = bias-contradiction evidence | wb p.206 |
| 15 | Followthrough clock | bars since signal without new extreme; "flat and dull" = downgrade | wb p.317, book p.262 |
| 16 | Level-test counter | ≥3 tests of a level → break bias; tight sub-range <25% of range height at edge → breakout bias | book p.126, 140 |
| 17 | Runs state (index) | exact-N run lengths on cash index; mean-reversion pressure after 3–6 day runs | wb Table 16.5 |
| 18 | Efficiency Ratio | Kaufman ER as chop/trend scalar | book glossary p.430 |

Warning (wb p.372): items 4/5/6/7/18 are correlated — do NOT vote-count them as independent evidence.

## 5. Proposed state machine (v0 sketch)

```
            ┌────────────────────────────────────────────┐
            │              NO-TRADE (default)            │
            │  chop both sides of 20-EMA / range interior│
            └───────┬───────────────────────────▲────────┘
     impulse: close beyond Keltner band +       │ most terminations
     MACD new momentum extreme, esp. out of     │ resolve here (range)
     vol-compression (5/40 ATR < 0.5)           │
            ▼                                   │
   ┌─────────────────┐   break-event + opposite ┌┴──────────────┐
   │  BULL / BEAR    │──── momentum extreme ───▶│  TRANSITION   │
   │  (trend; health │   (2-step rule, wb p373) │ (Dow UNCERTAIN│
   │  checklist keeps│◀── MMO holds / complex ──│  + Anti watch)│
   │  state alive)   │    pullback resolves     └───────┬───────┘
   └─────────────────┘                                  │ LH+LL (or HL+HH)
        sub-states: runaway slide-along-band            ▼ confirmed
        (directional, no-entry); post-climax     opposite trend state
        cooldown (no with-trend entries)
```
Key asymmetries to encode: entry to trend state is EASY to miss but cheap (breakout base rate: most fail — require the pre-conditions: higher lows into level / tight sub-range <25% at edge / vol expansion at break, adverse slippage); exit from trend to transition needs the 2-step rule (don't flip on divergence alone — "divergences fail about as often as they work"); transition defaults back to NO-TRADE, not to reversal.

## 6. Validation protocol (copy Grimes's Pythia discipline)
1. Per-state baseline: assign each bar's return to the PREVIOUS bar's state (no look-ahead); compare mean excess return/StDev/%Up per state vs unconditional ES baseline, bars +1..+20.
2. Nulls: random walk, AR(2), GARCH synthetic series — any classifier feature must show nothing on these.
3. ≤3 conditions per rule; single-use OOS; exclude effects <10bp or mean/median sign disagreement; exact-run definitions; report X-of-Y under N≈20.
4. Regime classification must be a priori (no post-hoc trend/range labeling — circular).
5. Test across vol regimes (our tick data 2021-06→2026-07 spans low-vol 2021, 2022 bear, 2024-26).
6. Sanity: trailing stops on a random walk = zero edge; use as harness check.

## 7. What to NOT build on (Grimes-tested dead ends)
- Fibonacci anything (retracements indistinguishable from random walk; median unfiltered retracement ≈100%).
- MAs as support/resistance; golden/death cross (death cross = 1-week R2K effect only); MA touch-and-hold.
- Floor-trader pivots (≈ random lines); day-of-week/month seasonality (leakage); opening skew (arcsine-law artifact); Bollinger "95% containment" claim; volume confirmation around springs/upthrusts (he could not substantiate it).
- Fading big single days IN FUTURES (continuation-leaning); fading breakouts in compressed vol.

## 8. Next steps proposed (not started)
1. Build feature extractors #1–#12 on ES (data: `data/ticks_continuous/` 1-min continuous, 2021-06→2026-07; daily from same).
2. v0 state machine (Section 5) on daily + 30m/1h/4h (intraday STMR found 30m+ is where signal lives; timeframes related 3–5×).
3. Pythia-style per-state excess-return tables vs ES baseline + the three nulls.
4. Only then: attach trade logic (pullback-continuation in trend states; failure-test at range edges; Anti in transition).
