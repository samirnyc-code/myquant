# 0006 — QuantSystems "Breakouts & Reversals" — Reproduction & Edge Study — 2026-06-24
**Series:** MC Setup Research Notes · Note 0006
**Confidence:** High (on the verdict). A 5-year, tick-level, full-cost reproduction of Ali
Moin-Afshari's *actual* PaintBar code (TradeStation Ver 2 & Ver 5, cross-checked against his
Pine v7.6) **and** his whitepaper's page-8/9 research definitions. The signal *detection* is
faithful (our per-day frequencies match the paper); the *edge* verdict is firmly negative and
is corroborated by his own source video and research worksheet.

**TL;DR.** We set out to reproduce and test Ali Moin-Afshari's breakout/reversal setups
(*Breakouts Research Whitepaper, Rev 3*). We obtained his real **PaintBar source** and his
**research worksheet + a mentoring video**, so this is a faithful decode, not a guess.
**The signal *detection* reproduces** — the bars his indicator paints (which Al Brooks
personally validated) — and our mechanical detector's per-day counts match his paper
(BO+FT ~5/day, Rev+FT ~6.6/day). **But traded mechanically over 5 unselected years
(2021-06->2026-06), the setups have no edge:** ~48–49% win, ~0 to slightly *negative*
expectancy even **frictionless**, and negative after costs. His headline numbers
(SQN 6.3–14.9, win 76–99%) come from **100 hand-picked 2020 trades with discretionary
filtering**. An early in-app **+$359k/contract was an intrabar look-ahead bug** (caught and
fixed; the edge vanished with it). His own video is explicit: the system is **discretionary
second-leg trading with pullback scale-in and "ignore the questionable"** — *"the computer
marks the bars… but you still have to judge — that's your experience."* **Verdict: the
signals are reproducible; the edge is discretionary and not mechanizable.**

---

## 1. What this is, and the sources (so it stands alone)

- **Instrument/timeframe:** ES 5-minute, RTH. ES = $50/pt, 1 tick = $12.50.
- **Three primary sources, in order of authority for the *rules*:**
  1. **PaintBar `AMA_Breakouts_PB`** EasyLanguage source — **Ver 2 (Aug 2022)** and **Ver 5
     (Feb 2023)** — plus the **Pine v7.6** port. These agree on the core logic; the Pine is the
     most recent and adds a Z-score "big breakout." This is the ground truth for *what a signal is*.
  2. **The whitepaper (Rev 3, Nov 2023)** — pages 8–9 give the *research-sampling* definitions
     (BO+FT, Big Breakout, Reversal+FT) used to produce the SQN stats. These differ slightly from
     the paint code (see §3.3).
  3. **A mentoring video + his research worksheet** (`Dev_BO Detector_PB`, `AMA_Breakout
     Detector_PB_X` v11X; ES.D, 24-Aug->20-Nov-2020). These reveal the *trading method* and the
     *provenance of the numbers* — decisive for the verdict (§6).
- **What "reproduce" means here:** a pure, headless, sweepable Python detector
  (`qs_setups.py`) that emits the project-standard signal schema, fed through the audited
  tick-level engine (`simulation_engine.simulate_trades`) with the real cost model — the same
  pipeline as every other note in this series.

## 2. The questions
1. Can the signals be defined precisely enough to reproduce mechanically? (Yes.)
2. Do they carry a tradeable edge on unselected, out-of-2020 data with realistic execution?
3. If the paper shows SQN 6–15, where does that actually come from?

## 3. The signals — precise, codeable definitions

### 3.1 Building blocks (verbatim from the code)
- **IBS** = (Close − Low) / (High − Low) x 100. Degenerate bar (H=L) -> 50.
- **BarDir** (±1): the paper's exact cascade — C vs O combined with IBS-vs-50; dojis and
  body/close conflicts resolve by close; perfect dojis & ambiguous bars inherit the prior bar.
- **ABR / AvgRange:** average bar range. *Two conventions exist:* the whitepaper uses **prior
  10 bars** ("within the last 10 bars"); the Ver 5 range filter uses **`Average(range, 8)`
  including the current bar**. Both are exposed as parameters.
- **Outside bar (OB):** H>H[1] & L<L[1] (plus two equal-edge variants unless `_StrictOB`).
- **Inside bar (IB):** contained by the prior bar (+ equal-edge variants).
- **Micro gap (MIG):** gap between two non-adjacent bars (3-bar). Tagged, not gated.

### 3.2 PaintBar primitives (what the indicator actually marks)
Priority **CX > OB > BO**. (Ver 5 geometry; `>=`/`<=` and OB-gated.)
- **BO (breakout):** bull = `H>H[1] AND L>=L[1]` and **not** an OB; bear = `H<=H[1] AND L<L[1]`
  and not OB. **No IBS / ABR / FT in the bare paint signal** — those are optional filters.
- **OB (outside-bar) directional bias:** compare breakout above prior high (`H−H[1]`) vs below
  prior low (`L[1]−L`); bigger-above => bullish bias; tie & perfect-doji => neutral (magenta).
- **CX (climax) — `_CXfactor` resolved = 1.8** (placeholder P3 from the first draft, now known):
  on a clean directional BO bar, `HHdist > LLdist x 1.8` (a thrust), filtered out if the prior
  bar is inside, the bar is an OB, BarDir≠BarDir[1], or it doesn't close beyond the prior extreme.
- **Range filter (Ver 5 default ON, lookback 8):** drop a signal whose bar range < AvgRange.
- **Follow-through (`_PaintFTBar`, default OFF):** relabels a bar as FT when the prior bar was a
  signal and this bar closes beyond it; also filters mid-leg non-close-beyond breakouts.

### 3.3 Whitepaper page-8/9 RESEARCH setups (the SQN study's definitions)
These are a *layer on top of* the primitives, and are what the paper's stats describe. Built as
`detect_wp()`:
- **1. BO+FT (2-bar):** breakout bar (1 tick beyond the prior bar) + a **same-direction** FT bar
  (*need not close beyond*); **>=1 of the two bars > ABR(10)**; breakout-bar **IBS >=69 / <=31**.
- **2. Big Breakout:** a bar **> 2x ABR(10)**, breakout, strong IBS (1-bar or 2-bar).
- **3. Reversal+FT (2-bar):** both bars >= ABR(10) (not breakout-big), **bar 2 closes beyond
  bar 1**, at a reversal turn, signal-bar **IBS >=69 / <=31**. *(Item 3's "not big enough to be a
  breakout bar" is self-contradictory in the paper (A4); we relaxed it to match his count.)*

> Note: OB and CX have **no mechanical rules in the whitepaper** ("I have not provided detailed
> rules for the last two signals") — those live only in the paint code. And the shipped detector
> is **version 24 with ~60 price-action rules** (some firing once a quarter); the Ver5/Pine we
> coded is a faithful **subset**.

### 3.4 iStop and target (corrected from the worksheet)
- **iStop = 1x the signal-bar range** (R = entry − stop). His worksheet's actual-risk column
  (`a.Risk Dist`) averaged **~4.74 pt** in 2020 low-vol ES ~ one bar range — *not* the
  2x-combined-range rule the first draft assumed. (Variants for small / much-bigger bars exist.)
- **Target "1R" = a second leg ~ the size of the signal bar** (his "symmetry") -> roughly
  symmetric 1:1 with the 1x stop.

## 4. Entry methodology (whitepaper §"Trading Techniques" + Fig 12–13, p. 22)
Entry is **off the signal bar**, three techniques:
1. **Buy-The-Close (BTC)** — his preferred (limit) style: enter at the **close of the signal
   bar** — either **B2** (setup complete / FT bar, confirmed) or **B1** (early, before FT).
2. **Market** — market order at the signal-bar close.
3. **Scaling-In** — add with **limit orders on the pullback** at prior support/resistance.

Stop = iStop. Target = 1R (symmetric second leg). The R-multiple study measured two:
**(a) entry bar 2, hold 1R** -> BO SQN 6.3 / Rev SQN 4.4; **(b) entry bar 1, add on the pullback
(scale-in), look for 1R** -> BO SQN 10.2 / Rev SQN 9.2 — **(b) is his real, preferred method.**

## 5. How we reproduced & tested it
- **Detection:** `qs_setups.py` — `detect()` (PaintBar primitives) and `detect_wp()` (whitepaper
  setups); every parameter on a `QSConfig` dataclass (fully sweepable). Presets: `wp()`,
  `paper()`, `research()`, `paintbar_raw()`.
- **Simulation:** `simulation_engine.simulate_trades` — replays **real continuous ticks** per
  day, R = |entry−stop|, exits at target_r·R or stop, house costs ($5 RT + slip), ESA execution
  models. Entry = market at signal-bar close (~ BTC).
- **In-app:** `🎯 QS Breakouts` tab (detector selector, geometry, ESA, BE, Quick View, Y/Q/M/W
  breakdowns, trade list, CSV export) -> results push to `ba_results` so the **Prop Sim** tab runs
  on QS trades. NT indicator `QSBreakoutSignals.cs` paints the exported signals on a chart.

## 6. Results

### 6.1 Frequency — detection is faithful [OK]
`detect_wp` over 1,249 RTH sessions vs the paper:

| Setup | ours (ok/day) | ours (raw/day) | paper |
|-------|---------------|----------------|-------|
| BO+FT | **5.2** | 8.0 | ~5/day |
| Rev+FT | 4.2 | **6.1** | ~6.6/day |
| BigBO | 1.0 | 1.5 | (subset) |

Right order on every setup — the signal definitions reproduce his population.

### 6.2 The look-ahead bug (the headline cautionary tale)
An early in-app run showed **+$359k/contract, 78% win, SQN 10** — exciting, and **wrong**. The
detector timestamped each signal at the bar's **open**; the engine then filled at the **first
tick after the open** = *inside the signal bar*, ~5 min before the signal exists. 100% of fills
were intra-signal-bar, always favorable (longs filled near the low, shorts near the high).
**Fixed** by emitting the bar **close** time. The "edge" was entirely this leak.

### 6.3 Honest edge — WP setups, correct geometry, look-ahead-free, **frictionless**

| Setup @ target | n | win% | exp R | SQN | net $ (1 ES) |
|---|---|---|---|---|---|
| **BO+FT @ 1R** | 5,692 | 48.6% | **−0.026** | −2.0 | −$14k |
| BO+FT @ 2R | 5,692 | 34.6% | −0.013 | −0.7 | +$16k |
| **Rev+FT @ 1R** | 5,144 | 48.5% | **−0.028** | −2.1 | −$69k |
| Rev+FT @ 2R | 5,144 | 35.2% | −0.020 | −1.1 | −$33k |
| **Ali (2020, 100 hand-picked)** | 100 | **76%** | +0.60 | 6.3 | — |

Coin-flips, slightly **negative even before costs** -> firmly negative after. No mechanical edge.
(Trade-level audit confirmed clean execution: 0 entry-bar target wins, median ~17-bar holds,
fills strictly after the signal close.)

## 7. Why it fails mechanically — and where Ali's edge actually lives
His own materials make this unambiguous, so this is not speculation:

- **It's discretionary second-leg trading, not a signal-bar system.** Video: *"the only trade
  you have to look at is second legs… >90% chance… that's why I programmed this breakout
  detector — it's designed for second-leg trading."* The detector marks the **first** leg; the
  **trade** is the **second leg after a pullback**, entered by **scaling in** during the pullback.
- **The edge is the "ignore" judgment.** Video (the *Heat* analogy): *"disqualify the
  questionable… if it's questionable for any reason, just ignore it."* He then rejects setups by
  eye (3rd legs, a red bar on the MA, wedge/magnet targets, range-compression breakouts). And:
  *"the computer marks the bars… but you still have to judge — that's your experience."*
- **The numbers are 100 hand-picked 2020 trades + discretionary filters.** Worksheet: 100 trades,
  done **by hand** ("you want to live through the trades"), Aug–Nov 2020 (a trending regime). The
  **filter-ablation table** shows the lift comes from removing **legs 3 & 4** (76%->83%) and
  **time-of-day** (->86%) — and "legs 3 & 4" is a **hand-labeled column** (his channel read), i.e.
  exactly the part that **can't be mechanized**.
- **Brooks's endorsement was about the *bars*, not an edge:** *"it's picking up the bars I'm
  interested to trade."* That's signal *detection* — which we reproduced — not profitability.

## 8. Recommendation / verdict
- **The signals are faithfully reproducible** (detection [OK]) — useful as a charting/marking layer
  and as a research substrate.
- **There is no standalone mechanical edge** in BO+FT or Rev+FT on 5 unselected years, at any of
  the geometries tested, frictionless or with costs.
- **Do not trade these as a mechanical signal-bar system.** The reported SQN 6–15 is a
  *discretionary, hand-curated, single-regime* result; treat it as a description of a skilled
  manual trader's process, not a backtestable system.

## 9. Caveats & open questions
- **Not yet tested:** the *faithful* version of his method — **bar-1 entry + pullback scale-in,
  symmetric second-leg target** (his SQN-10.2 line). Prior: note 0001 found PB scale-in helps
  win% but not $ on the MC setup; expectation is similar here, but it's the honest final check.
- **Legs-3/4 + deep-PB + "ignore" filters** are discretionary and unmechanizable; we can only
  *approximate* them, and approximations won't recover a hand-trader's judgment.
- The full detector is **~60 rules (v24)**; we reproduced the documented subset. A fuller port
  would mark more bars but doesn't change the edge conclusion (the edge isn't in detection).
- In-sample on 2021–2026; **2020 (his sample) is not in our tick set** (our data starts
  2021-06-18), so a direct match against his hand-logged trades isn't possible yet. **Strongest
  outstanding validation:** fetch Aug–Dec 2020 ES, run `detect_wp` on his exact worksheet
  dates/times, and check signal-by-signal whether his logged setups are a subset of our
  detections. Ground-truth seed (partial, transcribed from the worksheet frames) saved at
  `docs/living/ali_2020_worksheet_trades.csv`; full numeric extraction needs the actual `.xlsx`.

## 10. Reproduce (artifacts)
- **Detector:** `qs_setups.py` — `detect()`, `detect_wp()`, `QSConfig` (+ presets).
- **Scripts:** `scripts/qs_breakouts_detect.py` (frequency), `qs_config_compare.py`,
  `qs_ali_geometry.py`, `qs_breakouts_sim.py`, `qs_wp_sim.py`, `qs_breakouts_periods.py`,
  `qs_breakouts_be_sweep.py`, `qs_stop_target_sweep.py`, `qs_dump_trades.py`,
  `qs_export_signals_nt.py`.
- **App:** `qs_tab.py` (🎯 QS Breakouts tab) -> pushes to Prop Sim.
- **NT:** `QSBreakoutSignals.cs` (racing-stripe signal marker) + `qs_signals_*.csv`.
- **Sources:** whitepaper Rev 3; PaintBar Ver 2 / Ver 5 / Pine v7.6; mentoring video + worksheet.
- **Companion:** note 0007 (build/test mechanism); the inflated pre-fix numbers there are voided
  by §6.2 above.
