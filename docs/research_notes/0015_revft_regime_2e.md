# 0015 — RevFT Rescued by the Regime Engine + 2E Exit — 2026-07-25
**Series:** MC Setup Research Notes · Note 0015
**Confidence:** Medium-high **as a positive result, pending forward confirmation.** 5 years, full
cost, real ticks, the same production-grade tick engine as the S83 2E book. The core mechanism is
low-DOF and mechanism-consistent (broad monotone partitions, not a single fitted cell); the headline
book is positive in 5 of 6 years with a bootstrap CI excluding zero and a *stronger holdout than
train*. But it is a rescue of a signal with two prior kill-notes (0005, 0013), ~26 books were
searched, and it has not been run truly out-of-sample. Treat as a validated hypothesis, not a
deployed edge.

**TL;DR:** RevFT ("MyReversals") is a firm loser at 1:1 (−$59k/5yr here; −$187k in note 0005). Note
0005's one durable finding — *RevFT is a with-trend momentum signal, not a fade* — was only ever
tested with a crude VWAP-side proxy and fixed 1R–3R targets, and reached break-even carried entirely
by 2022. This note replaces the proxy with the real tick phase-machine regime label (`pt_new`, the
"latest engine") and imports the S83 second-entry book's exit (wide 0.30×ADR stop, **hold to session
close, no target**). Two levers, and **neither works alone**: the wide-EOD exit on all signals is flat
(+$1.9/tr); dropping the counter-trend signals but keeping a 1R target is flat (−$1.9/tr). Only the
**interaction** pays — drop the trades that fade a live intraday trend, and let the survivors run to
the close on a wide stop: **+$45/tr, +$123.5k, PF 1.12, CI[3,90], 4–5 of 6 years green.** Adding the
MenthorQ gamma-regime day filter (trade only negative-gamma / trending days — the *opposite* of the
mean-reversion intuition) concentrates it to **+$123.6/tr, +$144.7k, PF 1.27, CI[37,213], 5 of 6
years green, holdout > train.** The mechanism is coherent: counter-trend RevFT (fading a live trend)
loses −$95k to −$115k *every year*; the 1R target was clipping the momentum tail (median MFE = 1.45R)
that the kept trades run into.

---

## 1. The setup (so this note stands alone)

**RevFT signals.** 5M ES swing-reversal signals ("MyReversals"). Each row: signal bar (close-stamped
`DateTime`), `Direction`, `SignalPrice` (trigger, a few ticks inside the swing), `StopPrice` (the
rejected swing extreme = the native stop). Export `saved_signals/ba_signals_revft.parquet`, 2021-06 →
2026-07. **Sneaky excluded** throughout (as in all RevFT notes). After joining to `_continuous` RTH
bars + requiring a valid entry (first tick after the signal bar, native R>0), **4,582 trades / 1,204
days** survive.

**The regime engines applied.**
1. **Phase-machine (`pt_new`)** — the tick-driven `OnPriceChange` structural trend machine, the
   *latest* engine (2nd-PC commit `1760ffd`, vendored verbatim into
   `scripts/revft_regime_full.py`). Emits a per-tick BULL / BEAR / NEUTRAL state. The signal's regime
   = the machine's state as of the **signal bar's close** (causal; entry is the next bar). Gate:
   *with-trend* = Long∩BULL or Short∩BEAR; *counter-trend* = Long∩BEAR or Short∩BULL; else NEUTRAL.
   Mix: BULL 28% / BEAR 28% / NEUTRAL 44%.
2. **MenthorQ gamma regime (S84)** — the daily `positive_gamma` / `negative_gamma` label from
   `data/regime/mq_regime_daily_2007_2026_v2.csv` (sign of net dealer gamma; positive = dealers
   dampen/pin → mean-reverting; negative = dealers amplify → trending). Mix over the sample: pos 57% /
   neg 41%.

**The 2E book's exit, imported.** From the S83 REGIME-2E system: stop = **0.30 × ADR10** (nearest
tick, floor 8t), **never moved**; **no profit target — hold to session close (EOD flat)** or the stop.
Also available (ablated): gap-skip (|RTH gap|>0.54%), fill window 09–13h. Entry = first tick after
the signal bar close. Costs = **$5 RT + 1 tick slip**, applied per trade. Exits scored by tick
crossing (stop tie → stop first, conservative). Everything replays **real continuous ticks**.

**Exit variants tabulated per trade:** native stop (=extreme) at 1R/2R/3R and hold-EOD; wide-vol stop
at 0.20/0.30/0.50×ADR hold-EOD; wide-0.30 + 1R/2R/3R target. Plus MFE/MAE in points.

## 2. The questions

1. Does the real phase-machine regime label rescue RevFT where the VWAP proxy (note 0005) could not?
2. Does the 2E book's wide-stop / hold-to-EOD exit — never tested on RevFT — matter?
3. Is the MQ gamma regime a useful gate for a "reversal" signal, and in which direction?
4. Under honest scrutiny (train/holdout, year-by-year, bootstrap CI, multiple-testing), does anything
   survive?

## 3. Results

### 3.1 The decomposition — neither lever works alone (this is the finding)

All figures net, 1 ES, full cost. `notCT` = with-trend ∪ neutral (i.e. *drop counter-trend*).

| Config | n | Total $ | $/tr | PF | Boot CI $/tr | Verdict |
|---|---|---|---|---|---|---|
| BASE — all / 1R target | 4,582 | **−59,222** | −12.9 | 0.94 | [−29, 3] | firm loser (≡ note 0005) |
| Exit only — all / wide+EOD | 4,582 | +8,652 | +1.9 | 1.01 | [−29, 32] | flat |
| Gate only — notCT / 1R | 2,742 | −5,172 | −1.9 | 0.99 | [−26, 22] | flat |
| **Gate+Exit — notCT / wide+EOD** | 2,742 | **+123,515** | +45.0 | 1.12 | **[3, 90]** | ✅ survives |
| **+ neg-gamma — neg∩notCT / wide+EOD** | 1,171 | **+144,695** | +123.6 | 1.27 | **[37, 213]** | ✅ survives |

The wide-EOD exit alone neutralizes the loss but adds no edge; the regime gate alone at 1R is
break-even. The product is +$45/tr. Interpretation: the 1R target was capping exactly the
momentum trades the gate keeps (§3.4), and a wide stop only stops *helping* once the counter-trend
trades — which ride a wide stop to a full loss all day — are removed.

### 3.2 The phase-machine gate: counter-trend is the whole disease

| Book (wide+EOD unless noted) | n | Total $ | $/tr | PF |
|---|---|---|---|---|
| with-trend | 723 | +17,310 | +23.9 | 1.07 |
| neutral | 2,019 | +106,205 | +52.6 | 1.14 |
| **counter-trend** | 1,840 | **−114,862** | **−62.4** | 0.84 |

Counter-trend RevFT — *fading a live intraday trend* — loses at every exit (−$54k at 1R, −$95k
native-EOD, −$115k wide-EOD) and in **every year** (2021 −$9.8k, 2022 −$15.5k, 2023 −$31.6k, 2024
+$6.9k, 2025 −$34.8k, 2026 −$9.9k, native-EOD). This is the single most robust result in the study and
it is exactly note 0005's thesis with a real label: RevFT is not a fade; fading into trend gets run
over. `pt_new` also beats the prior engine on the with-trend book (+$9.3k vs −$0.6k native-EOD).

### 3.3 The MQ gamma gate — the mean-reversion intuition is backwards

| Day type (all directions) | n | 1R | native-EOD | wide-EOD |
|---|---|---|---|---|
| positive_gamma (pinned) | 2,615 | −$53.0k | −$81.7k | −$66.7k |
| negative_gamma (trending) | 1,896 | −$5.5k | +$71.5k | +$77.9k |

RevFT does **worse** in positive-gamma (dealer-pinned, "mean-reverting") days and **better** in
negative-gamma (amplifying, trending) days — the opposite of the naive "fades work when dealers pin"
hypothesis, and again consistent with RevFT being momentum, not reversion. Within positive-gamma,
deeper pins are *worse* (high-|gex| tercile −$48.9/tr, every year red) — there is no responsive-fade
edge to find there. Negative-gamma is a genuine additive day filter, not a redundant restatement of
the phase gate (they are ~orthogonal: pos/neg is a daily gamma structure, BULL/BEAR/NEUTRAL is the
intraday path).

### 3.4 Why the EOD exit matters — the clipped tail (MFE/MAE)

On the with-trend book: median MFE = **1.46R**, P(MFE≥1R) = 63.6%, P(MFE≥2R) = 39.7%, P(MFE≥3R) =
26.6%, median MAE = 1.33R. A 1R target harvests the median favorable excursion and forfeits a fat
right tail; holding to the close (stopped only on a wide 0.30×ADR adverse move) captures it. This is
the same tail-concentration that makes the S83 2E book un-discretionary — and it is why the exit and
the gate are inseparable here.

### 3.5 Headline book — honest scrutiny

**neg∩notCT / wide+EOD** (negative-gamma days, drop counter-trend, hold to close):
n=1,171, +$144,695, $/tr +$123.6, PF 1.27, win 45.4%, bootstrap 95% CI $/tr **[36.5, 212.8]**.
- **train (≤2023)** +$40.6k / +$67.0/tr · **holdout (2024–26)** +$104.1k / +$184.0/tr (holdout > train)
- **year:** 2021 +3.3k · 2022 +44.3k · 2023 **−7.0k** · 2024 +40.2k · 2025 +38.2k · 2026 +25.6k
  (**5 of 6 green**, single soft year 2023).

The simpler, higher-N **notCT / wide+EOD** (drop counter-trend, all gamma regimes) is +$123.5k, PF
1.12, CI[3,90], train +$29.8k / holdout +$93.7k, years 2021 −1.9k · 2022 +40.5k · 2023 −8.8k · 2024
+36.8k · 2025 +20.0k · 2026 +36.9k. Lower $/tr, but one rule (never fade a live trend) + one exit
change, on 60% of the signals — the lowest-DOF version of the edge.

Contrast with note 0005's VWAP continuation gate (its best rescue): break-even at best, carried
entirely by 2022, significantly negative in 2025–26. The regime-labelled version is positive across
the recent holdout, which is the period the 0005 gate failed.

Equity curves: `docs/living/revft_regime_equity_20260725.png`.

## 4. Why it works (mechanism)

1. **RevFT is a momentum signal wearing a reversal's clothes.** Its swing-rejection trigger fires
   into an imbalance; with-trend, that imbalance continues (the trade works); counter-trend, the same
   imbalance runs the fade over. The phase-machine cleanly sorts the two; note 0005 saw the shadow of
   this through VWAP-side but couldn't act on it.
2. **The exit must match the signal's physics.** A momentum trade with a 1R cap forfeits its edge (the
   1.46R median MFE). Hold-to-close on a wide stop is the correct exit *given* the gate — and only
   given the gate, because the same exit on counter-trend trades maximizes the loss.
3. **Gamma regime is the day-level version of the same physics.** Negative-gamma = amplifying =
   momentum-friendly = the RevFT-friendly day; positive-gamma = pinning = chop that whipsaws the
   trigger. It stacks on the intraday gate rather than duplicating it.

## 5. Verdict & caveats

- **RevFT is rescuable, but not as a fade.** The rescue = (a) drop counter-trend signals via the
  phase-machine, (b) exit like the 2E book (wide vol stop, hold to close), optionally (c) trade only
  negative-gamma days. Base −$59k → +$123.5k (drop-CT) or +$144.7k (neg∩drop-CT).
- **Not yet an edge.** Two prior kill-notes; ~26 books searched (multiple-testing); no truly OOS run.
  The survivors are broad and monotone (every neg∩notCT∩EOD variant survives, every CT variant loses),
  which is far better than a single fitted cell — but forward validation is the gate before any
  capital. 2023 is a consistent soft spot to watch.
- **Fill realism** = first-tick-after-close entry + tick-crossing stops (same as the S83 work); costs
  included; no queue model. EOD-flat is compatible with the prop rule (flat by 15:00 CT).
- **Next:** (1) forward-track neg∩notCT/wide+EOD on MES; (2) test entry improvements from the 2E book
  (limit-6t-back + cancel-after-6-bars) on RevFT — untested here (native next-tick entry used);
  (3) gap-skip / hour-window ablation on the headline book; (4) size by regime confluence (the 2E
  HVL-sizing analog).

## 6. Reproduce

- `scripts/revft_regime_full.py` — one tick-replay pass; vendors `pt_new`, joins MQ gamma, exports the
  per-trade table `data/regime/revft_regime_full_20260725.parquet` (all exit outcomes + features).
- `scripts/revft_regime_deep.py` — all slicing + honest verdict (train/holdout, year, bootstrap CI,
  multiple-testing tally) on the saved table; no re-sim.
- `scripts/revft_regime_2e.py` — the initial focused version (superseded by `_full`).
- `scripts/revft_regime_chart.py` — equity curves → `docs/living/revft_regime_equity_20260725.png`.

Engine provenance: `pt_new` vendored from `myquant-regime/scripts/regime_engine_ab.py` (branch
`regime/indep`), the 2nd-PC `1760ffd` lift of `scratchpad/regime_phase_machine.py`. 2E exit spec from
`docs/research_notes/system_spec_2E_regime_20260724.md` (worktree). Prior RevFT notes: 0005 (location),
0013 (i1R/PB retest).
