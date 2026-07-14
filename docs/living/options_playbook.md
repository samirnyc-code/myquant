# Options Strategy Playbook — rules, parameters, regimes, and how we test them

**Status:** Living. Started S70 (2026-07-12); S73 (2026-07-14) major expansion: every
strategy family now has a FIXED parameter set + a test grid, after all 8 structures were
executed and logged on the paper account (first live-pipeline day).
One entry per strategy so results are testable, consistent, and comparable.
Every strategy carries an honest **backtest-status** tag and a **data-needed** tag so we
never confuse a validated edge with a hypothesis.

> Companion source of truth: `docs/living/handoff.md`. Infrastructure: the sim daemon
> (`scripts/options_sim_daemon.py`), manual trades (`scripts/options_manual_trade.py`),
> sampler (`scripts/options_strategy_sampler.py`), marks (`scripts/options_mark.py`),
> dashboard (`scripts/options_app.py`, Streamlit :8511). All trades land in ONE log:
> `data/options_log/trades.parquet` (§B schema).

---

## 0. How to read a strategy entry
- **Thesis** — why an edge should exist
- **Entry trigger** — the signal; must be readable at a defined time (causality!)
- **Structure & DEFAULT params** — the ONE parameter set forward-tests run with
- **Test grid** — the parameter sweep we'd optimize over once data allows
- **Exit** — profit target / signal exit / time stop / settlement
- **Sizing** — contracts, collateral, max concurrent
- **Favorable regime** — where it should work (§A framework)
- **Status** — VALIDATED (walk-forward) / SUPPORTED (in-sample) / HYPOTHESIS / ANTI (evidence against)
- **Verdict** — current call

**Grading scale for individual trades** (logged per trade): A+ = trigger + regime +
level all aligned; A/B = most aligned; C = structure test or off-signal; F = broken
execution (e.g. zero-credit fill — see 2026-07-14 bcs example).

---

## 1. STMR Bull Put Spread  `bps_stmr`  — THE FLAGSHIP
- **Thesis:** oversold-but-uptrend mean reversion; sell put premium into the bounce.
- **Entry trigger (CAUSAL):** at 15:59 ET, stoch `%K8 < 15 AND spot > SMA100`
  (daily series + today's session H/L + 15:59 spot). Fill 16:00–16:15.
- **Structure & DEFAULT:** SPXW put spread, sell **~30Δ** put / buy **50pt** lower, **14 DTE**.
- **Test grid:** DTE {7, 14, 21, 30} × width {25, 50, 100} × short-delta {20, 30, 40}
  — S67/S68 swept this on EOD marks: 14DTE/50pt was the capital-efficiency winner.
- **Exit:** first day spot(15:59) > SMA5 → buy back 16:00+; else settle at expiry.
  **S73 exit shootout (`scripts/mr_bps_exit_rules.py`, 142 trades): the SMA5 exit IS the
  edge** — hold-to-expiry is NEGATIVE (PF 0.95, maxDD −$27.7K), tastylive TP-50% ≈ flat
  (0.97), price stops are poison (0.71–0.84; they sell the pre-bounce low). SMA5: PF 1.74,
  +$14.7K, maxDD −$6.3K. This is a mean-reversion TIMING play, not a theta play. NO price
  stops, NO expiry holds, NO profit targets — exit on the signal only.
- **Sizing:** 1-lot; collateral = width − credit (~$4.0–4.9K); max 3 concurrent.
- **Regime:** elevated-but-falling IV; non-crash uptrend. Worst: gap-down clusters.
- **Status:** SUPPORTED in-sample (146 trades 2010–23, PF 1.93 bid/ask, +$18.2K, maxDD −$6.3K).
  Causal executable subset (2021-07→2023-12): 29 trades, PF 3.78 — n too small, regime-flattered.
- **Verdict:** the ONLY strategy with real support. Forward-test is LIVE as of 2026-07-14
  (daemon). **S73 walk-forward result (`scripts/mr_bps_regime_wf.py`): VIX-rank filters DO
  NOT help — OOS filtered PF 2.13 < unfiltered 2.24 (2014-23); the "elevated-but-falling"
  prior is unsupported (falling-VIX buckets n≤13; LOW VIX-rank was actually the best
  tercile, PF 6.15 n=31). Trade it UNCONDITIONED.** Trades: `data/options_sim/bps_regime_trades.csv`.

## 2. Iron Condor on STMR  `condor_stmr`  — ANTI (as an STMR variant)
- **Thesis:** add call-side credit on ~zero extra collateral.
- **Status:** SUPPORTED-NEGATIVE — S68 sweep: LOSES to plain BPS (the bounce runs into the
  short calls). Only helps tail/maxDD.
- **Verdict:** DEPRECATED on the STMR signal. Condor lives on as `condor_0dte` (§3b).

## 3. 0DTE premium sell at gamma level  `sell_0dte_gamma`  *(HYPOTHESIS — forward-test live)*
- **Thesis:** positive-gamma days pin; sell defined-risk premium at the walls.
- **Entry trigger:** morning (9:45–10:30 ET), positive-gamma day (spot > HVL), short strike
  AT the MenthorQ PS0 (puts) or CR0 (calls); require spot ≥ 40pts from the short strike
  AND net credit ≥ 0.80.
- **Structure & DEFAULT:** 0DTE credit spread, **25pt width**, short AT the wall.
- **Test grid:** entry time {9:45, 11:00, 13:00} × width {10, 25, 50} × wall {PS0, CR0, GW}
  × min-distance {25, 50, 75}.
- **Exit:** hold to settlement (cash) by default; test grid adds 50%-credit target and 2×-credit stop.
- **Sizing:** 1-lot; collateral = width − credit (~$2.4K).
- **Regime:** positive GEX, VIX < 20, no FOMC/CPI.
- **Status:** HYPOTHESIS. No historical intraday data owned → forward-only.
  First live sample 2026-07-14 (7475/7450 P, $130 credit, settled — see log).
- **Verdict:** the daily forward-test workhorse — cheap, fast feedback, one per day max.

### 3b. 0DTE iron condor inside the walls  `condor_0dte`  *(HYPOTHESIS)*
- **Structure & DEFAULT:** short put AT/inside PS0 + short call AT/inside CR0, **25pt wings**,
  entered 9:45–10:30 on a positive-gamma day; both strikes ≥ 40pts OTM, total credit ≥ 1.50.
- **Exit:** settlement; grid adds close-both at 50% credit.
- **Status:** HYPOTHESIS (2026-07-14 sample: $180 credit, POP 96% at entry).
- **Caveat:** asymmetric risk on trend days — skip when |spot − HVL| < 15 (regime ambiguity).

## 4. Gamma-level fade / HVL  `gamma_level_fade`  — ANTI (naive)
- S66: MenthorQ levels hold ~50% once touched. Do NOT trade naively. Only revisit with a
  conditioned trigger (GEX magnitude + distance + time-of-day). Calibration continues daily
  (`mq_logger.py`); our CR matches MenthorQ exactly, PS/HVL formulas still wrong.

## 5. Long ATM straddle  `straddle_0dte` / `straddle_event`  *(HYPOTHESIS, counter-regime by default)*
- **Thesis:** buy vol when realized > implied is likely: event days, negative-gamma days.
- **Entry trigger:** ONLY on (a) scheduled events (FOMC/CPI before 16:00) or (b) negative-gamma
  (spot < HVL) mornings with VIX term inverted. NEVER on a positive-gamma pin day
  (2026-07-14 sample bought at VIX 15 on a pin day = −$1.3K unrealized within hours — the
  textbook counter-example, grade C−).
- **Structure & DEFAULT:** buy ATM C + P, 0DTE (event day) or nearest-weekly.
- **Test grid:** trigger {event, neg-gamma, both} × DTE {0, 2–4} × exit {close-before-event-fade,
  fixed 2× debit target / 50% stop, hold-to-close}.
- **Sizing:** risk = full debit (~$2.5–2.7K ATM 0DTE); 1-lot.
- **Status:** HYPOTHESIS with a skeptical prior (theta on 0DTE is brutal).
- **Verdict:** forward-test ONLY on trigger days; expect few samples/month.

## 6. Butterfly at the pin  `fly_gw_0dte`  *(HYPOTHESIS — most regime-aligned 0DTE long)*
- **Thesis:** positive-gamma days settle near the Gamma Wall; a cheap fly centered there has
  convex payoff into the pin.
- **Entry trigger:** positive-gamma day, enter 10:00–12:00, center = GW0 (fallback: max-GEX
  strike); require debit ≤ 40% of wing width.
- **Structure & DEFAULT:** call butterfly, **25pt wings**, centered ON the wall, 0DTE.
- **Test grid:** wings {10, 25, 50} × center {GW0, CR0, spot-rounded} × entry time.
- **Exit:** settlement (max value AT the pin); grid adds 2× debit target intraday.
- **Sizing:** risk = debit (~$0.9K on 25pt). Defined, small.
- **Status:** HYPOTHESIS. 2026-07-14 sample: $9.05 debit, peaked +$742 unrealized mid-day
  (SPX hovering 7540s vs 7550 wall) — encouraging single sample, means nothing yet.
- **Verdict:** alongside §3, the second daily forward-test candidate.

## 7. Directional verticals  `bull_cs_wk` / `bear_cs_wk`  *(HYPOTHESIS — needs a signal)*
- **Thesis:** none yet — a debit vertical is a delta bet; without a validated directional
  signal it's a coin flip minus spread. 2026-07-14 sample = momentum chase, grade C+.
- **Only sanctioned use:** expressing an EXISTING validated futures signal (STMR long) in
  defined-risk form: buy 50Δ / sell 25Δ, 7–14 DTE, on signal days, exit with the signal.
- **Test grid:** deferred until a signal is chosen. Do not sweep blind.
- **Status:** HYPOTHESIS.

## 8. Calendars  `put_cal_wk`  *(structure-test only)*
- **Thesis:** short-leg theta > long-leg theta near ATM; vega hedge.
- **Status:** logged once (2026-07-14) to prove multi-expiry handling. No thesis we can
  test with owned data (needs term-structure history). PARKED.

---

## A. Regime framework (unchanged, now partially LIVE)
| Dimension | Source | Have? |
|---|---|---|
| IV level / rank | VIX daily (auto-refreshed by `options_mark.py`) + live IB delayed | **LIVE** ✓ |
| VIX term structure | VIX/VIX3M | NEED (free) — next |
| Trend vs range | ER/ADX on SPX daily (Yahoo, auto) | LIVE ✓ |
| Dealer gamma regime | MenthorQ manual AM + IB scanner (`mq_logger.py`) | LIVE ✓ (CR exact; PS/HVL formulas wrong) |
| Session position vs walls | parity-spot rig vs levels | LIVE ✓ |
| Calendar events | manual | easy, add to daemon |

**Premium-selling prior:** best in elevated-but-falling IV + positive-gamma range days;
worst in IV spikes and negative-gamma trends. 2026-07-14 was the archetypal positive-gamma
pin day and behaved exactly to type (credit structures +, straddle −).

## B. Trade log — unified schema (S73: extended)
`data/options_log/trades.parquet`: trade_id, strategy_id, source(backtest|sim|paper),
symbol, entry_dt, exit_dt, dte, structure, legs(json), credit, exit_cost, fill_model,
slippage, pnl, roc, collateral, hold_days, win, regime tags (vix, vix_rank, er10, adx,
gex_regime, hvl_side, dow, event), **commentary, grade, max_gain, max_loss, pop**.
Marks (running PnL + VIX) in `data/options_sim/marks.csv` every ~5 min.

## C. Data inventory
| Data | Status |
|---|---|
| OptionsDX SPX EOD 2010–2023 | HAVE |
| SPX daily (Yahoo ^GSPC, auto-refresh) | LIVE ✓ |
| VIX daily (auto-refresh) + live delayed | LIVE ✓ |
| OPRA realtime NBBO on paper acct | LIVE ✓ (verified 2026-07-14) |
| Realtime SPX spot | LIVE ✓ via 0DTE put-call parity rig (no index sub needed) |
| ES realtime | NT8 only (no bridge yet — see handoff S73 open items) |
| Historical intraday NBBO + OI | NEED (ThetaData $40) — the gate for backtesting §3/3b/6 |

## D. Forward-test protocol (the daily loop)
1. **Morning (9:30–10:30 ET):** paste MenthorQ levels → `scratchpad/mq_levels_today.json`;
   run `mq_logger.py` (calibration row). If regime qualifies: place §3 and/or §6 (one each,
   1-lot, DEFAULT params ONLY — no improvising strikes), commentary + grade at entry.
2. **All day:** `options_mark.py --watch 300` (running PnL + VIX), daemon sampling spot.
3. **15:59 ET:** daemon decides `bps_stmr` causally; 16:00–16:15 fill tape logged.
4. **After close:** settle 0DTE trades at SPX settle, book realized PnL, review in the app.
5. **Rule:** every trade gets commentary + grade AT ENTRY. Parameters are FIXED per §s
   above — a param change = a NEW strategy_id (e.g. `fly_gw_0dte_w50`).
6. **Sample-size honesty:** nothing graduates from HYPOTHESIS until ≥30 forward samples
   AND the equivalent backtest (once ThetaData decision is made).

## E. Where MenthorQ fits — unchanged (calibration ground truth + regime tag, not a signal)

## F. Open decisions
- [ ] ThetaData $40/mo — the gate for backtesting all 0DTE strategies. Decide after ~2 weeks
      of forward samples show which strategy deserves the spend.
- [x] ~~VIX daily~~ — LIVE (auto-refresh, S73)
- [x] ~~unified trade-log writer~~ — LIVE (S73)
- [ ] VIX term structure (VIX3M) — free, next data add
- [x] ~~Walk-forward the BPS family with VIX-rank conditioning~~ — DONE S73: filters don't
      help OOS (2.13 vs 2.24 PF); trade unconditioned. Prior §A "elevated-but-falling" demoted.
- [ ] NT8→repo ES bridge (exporter indicator) if ES-based signals return to the sim
- [ ] Event calendar (FOMC/CPI) into the daemon for §5 triggers + §3 skips
