# 0016 — ES × MenthorQ Gamma Levels: touch study, a data-corruption incident, and the CR-0DTE fade

**Series:** MC Setup Research Notes · **Session:** S73 night (2026-07-15) · **Instrument:** ES futures 5M RTH

**Confidence: MEDIUM** — one year of level history (that's all that exists), n=60 for the
surviving trade rule, and bar prices repaired via a daily-offset method with ±1–2pt
residual uncertainty. The *negative* findings (retractions) are HIGH confidence.

**TL;DR:** MenthorQ's daily gamma levels were tested against ES 5-minute bars over ~1 year.
A mid-study audit found the continuous ES contract is **back-adjusted** (bars drift up to
+465 pts from the actual prices levels are struck at), which had fabricated an apparent
"negative-GEX Call-Resistance fade" edge — **retracted**, along with a 1D-Max fade. On
price-repaired bars, the major levels (CR/PS) are touched too rarely or too weakly to
trade, but the **0DTE levels** are dense and reactive: **fading the first
approach-from-below touch of Call-Resistance-0DTE earns +$123/trade (~60 trades/yr,
+$7.4K/yr/lot, maxDD −$1K), positive in all 36 stop/target cells and positive
out-of-sample.** Candidate — not yet validated (needs NQ replication + live paper).

---

## 1. The setup (self-contained)

- **MenthorQ levels** (options-dealer positioning analytics, computed EOD 11pm ET for
  futures from the option chain — so date-*d* levels are known before session *d*; causal):
  - **CR / PS** — strike with the largest net call / put gamma concentration (major wall).
  - **HVL** — gamma-regime flip line (inflection of cumulative gamma curve).
  - **CR0 / PS0 / HVL0 / GW0** — same concepts computed from 0DTE options only.
  - **1D Max / 1D Min** — options-implied expected daily move boundaries.
- **GEX regime** — prior-EOD aggregate net gamma exposure (dealer long/short gamma),
  from MenthorQ `gamma-insights` (365-day history).
- **Bars** — ES 5M RTH continuous, **price-repaired to unadjusted front-contract values**
  (see §3.1) — 228–256 sessions overlapping the level history (2025-07 → 2026-07).
- **Touch semantics** (critical, user-caught): a resistance touch requires the prior 3 bars
  to close *below* the level (rally into it); support the mirror. Without this, ~44% of
  "touches" are approaches from the wrong side and every statistic is contaminated.

## 2. Question

Do price bars respect these levels in a tradeable way — raw, or conditioned on GEX regime
and time of day? And do MenthorQ's own published claims hold on our data?

## 3. How we tested it

### 3.1 The data-corruption incident (read before trusting any bar-vs-level study)

`data/bars/_continuous*.parquet` are **back-adjusted**: each quarterly roll shifts all
earlier prices by the roll gap. Levels are struck in actual contract prices, so the
misalignment grows with lookback:

| date | continuous-bar mid vs actual | 
|---|---|
| 2024-07 | **+462 pts** |
| 2025-07 | +225–263 pts |
| 2025-10 | +166 pts |
| 2026-01 | +124 pts |
| 2026-04 | +37 pts |
| 2026-06+ | ~0 (front contract) |

**Repair:** per-session offset = continuous 15:59 close − actual front-contract close
(Yahoo ES=F daily), rolling-median smoothed, subtracted from all OHLC
(`scripts/es_unadjust.py` → `_continuous_unadj.parquet`, audit in `data/bars/es_offsets.csv`).
Residual uncertainty ±1–2 pts (Yahoo close timing vs our 15:10 CT last bar).

### 3.2 Studies (all on repaired bars unless marked)

- **Touch/react:** touch = 5M bar range contains level ±1pt with correct approach; outcome
  race to ±4pt within 40 min → hold (reject) vs break.
- **Fade sim:** short (resistance) / long (support) at the touch; stop/target grid
  {3..10}×{6..20} pts; 1.25pt round-trip friction; ES $50/pt; mark-to-close if neither hits.
- **Conditioning:** prior-EOD GEX sign & 1-yr percentile; hour of day; QScore; CR−HVL distance.
- **OOS:** chronological first-⅔ / last-⅓ split.

## 4. Results

### 4.1 RETRACTED (misaligned-bars artifacts — kept for the record)

| Claimed edge (pre-repair) | Pre-repair result | Post-repair reality |
|---|---|---|
| Neg-GEX morning CR fade | n18, +$104/tr, +$1,875/yr, 35/36 cells + | **n=1 trade/yr. Artifact.** |
| 1D-Max fade (any regime) | n102 touches, 75.5% hold, +$131/tr | n15 touches, fade **−$79/tr** |
| Hour-of-day hold pattern (67.9% AM / 35.3% midday) | looked strong | contaminated; not yet re-established |
| Gap-direction discriminator | looked predictive | dead even pre-repair on full sample |

### 4.2 All levels — repaired bars (touch/react + fade at stop8/tgt10)

| Level | Kind | Touches/yr | Hold % | negGEX hold | posGEX hold | Fade E$/trade | Fade E$ negGEX |
|---|---|---|---|---|---|---|---|
| **CR 0DTE** | res | **103** | **81.6** | 84.2% (n38) | 80.0% (n65) | **+$174** | +$143 |
| PS 0DTE | sup | 115 | 71.3 | 66.1% (n56) | 76.3% (n59) | +$68 | +$52 |
| CR (major) | res | 26 | 80.8 | 80.0% (n5) | 81.0% (n21) | +$255 | −$12 |
| PS (major) | sup | 22 | 72.7 | **86.7% (n15)** | 42.9% (n7) | +$151 | +$198 |
| 1D Min | sup | 52 | 75.0 | 73.0% (n37) | 80.0% (n15) | +$43 | +$73 |
| 1D Max | res | 15 | 86.7 | 88.9% (n9) | 83.3% (n6) | −$79 | −$62 |

Majors confirm the S66 finding: they're rarely reached (PS 22×/yr, CR 26×/yr).
The 0DTE levels hug price → 100+ touches/yr each, with high hold rates **in both GEX regimes**.

### 4.3 The survivor — CR-0DTE first-touch fade (short first from-below touch, any regime)

**60 entries/yr, spread evenly: 2–9 per month across all 12 months (no regime clustering).**

Stop/target sweep, E$/trade (win%): **36/36 cells positive**

| stop\tgt | 6 | 8 | 10 | 12 | 15 | 20 |
|---|---|---|---|---|---|---|
| 3 | +42 (57%) | +44 (47%) | +56 (42%) | +79 (40%) | +115 (38%) | +114 (33%) |
| 4 | +29 (58%) | +28 (48%) | +39 (43%) | +63 (42%) | +100 (40%) | +122 (37%) |
| 5 | +45 (65%) | +56 (57%) | +87 (53%) | +120 (52%) | +171 (50%) | +174 (43%) |
| 6 | +98 (77%) | +116 (68%) | +137 (62%) | +193 (62%) | +258 (60%) | +254 (52%) |
| 8 | +109 (82%) | +151 (77%) | +123 (63%) | +181 (63%) | +247 (62%) | +253 (55%) |
| 10 | +144 (88%) | +188 (83%) | +142 (68%) | +204 (68%) | +276 (67%) | +292 (60%) |

Reference cell (stop 8 / tgt 10): **n60, win 63%, +$123/trade, +$7,400/yr, maxDD −$1,000.**
OOS: in-sample (first ⅔) +$170/trade → **out-of-sample (last ⅓) +$29/trade — degraded but positive.**
Surface structure is coherent: wider stops lift win% 42→88% (rejections are wicky), consistent
with dealer-hedging mechanics at 0DTE strikes (high gamma → aggressive defense on first test).

### 4.4 Comparison sweep for the retracted CR fade (repaired) — the artifact autopsy

Same construction on the *major* CR with the neg-GEX filter produces 1 entry in the year
(the signal effectively never fires with true prices) — the pre-repair 18 "touches" were
bars shifted 100–260 pts onto an untouched level.

## 5. Why it works / fails

0DTE options concentrate the day's heaviest gamma near the money; dealers defending those
strikes hedge aggressively on the *first* test, producing the reject. The effect is
regime-robust (works under positive and negative aggregate GEX) because 0DTE local gamma
dwarfs the aggregate book at that strike, intraday. Majors fail as trades not because they
don't hold (they do, ~80%) but because they're **rarely reached** — a level that triggers
26 times a year with wide dispersion can't carry a strategy alone. 1D-Max fades fail
because reaching the implied-move ceiling requires a strong trend day — exactly when
resistance breaks.

## 6. Recommendation

**Advance the CR-0DTE first-touch fade to live paper trading** (1 MES/ES lot, stop 8 /
target 10, first from-below touch only, journal every trade), running parallel with the
BPS. **Do not size up until:** (a) NQ replication passes, (b) ≥20 live paper samples
roughly match the backtest, (c) MenthorQ-definition cross-check done. Treat 4.2's PS-0DTE
and neg-GEX PS-major rows as the next two candidates to sweep.

## 7. Caveats

- **One year of level history** — that is all that exists anywhere; no way to extend backward.
- Bar repair carries ±1–2pt residual error → touch detection at ±1pt tolerance can
  misclassify borderline touches; direction of bias unknown.
- Level-date causality verified for the majors (dashboard morning levels = QUIN same-date
  row); assumed identical for 0DTE levels (same 11pm ET compute) — verify live.
- Hold-rate metric is definition-sensitive (base rate swings 52–68% across MOVE/LOOK);
  the P&L sim is the number that matters.
- MenthorQ subscribers watch these same levels — crowding effects unknowable from this data.
- n=60; a 1-year sample contains one regime cycle at most.

## 8. Reproduce

```
.venv/Scripts/python.exe scripts/es_unadjust.py         # bar repair (run first)
.venv/Scripts/python.exe scripts/mr_es_all_levels.py    # 4.2
.venv/Scripts/python.exe scripts/es_cr0_sweep.py        # 4.3
.venv/Scripts/python.exe scripts/es_cr_fade_sweep.py    # 4.4 autopsy
```
Data: `data/menthorq/levels_history.csv`, `levels0_history.csv`, `gex_insights_ES1.csv`,
`data/bars/_continuous_unadj.parquet` (+ `es_offsets.csv` audit).
