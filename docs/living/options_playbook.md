# Options Strategy Playbook — rules, regimes, and how we test them

**Status:** Living draft (started S70, 2026-07-12). This is the spec the sim runs against.
One entry per strategy with a FIXED rule set so it's testable, consistent, and comparable.
Every strategy carries an honest **backtest-status** tag and a **data-needed** tag so we
never confuse a validated edge with a hypothesis.

> Companion source of truth: `docs/living/handoff.md`. Research behind these lives in the
> S64–S69 handoff blocks and `docs/research_notes/`.

---

## 0. How to read a strategy entry
Each strategy is specified by:
- **Thesis** — why an edge should exist
- **Universe / instrument** — SPX / SPXW, cash-settled European
- **Entry trigger** — the signal (indicator condition or level touch)
- **Structure** — legs, strike selection (by delta), DTE, width
- **Exit** — profit target / signal exit / time stop / stop-loss
- **Sizing** — contracts, collateral, max concurrent
- **Favorable regime** — the environment where it should work (see §A)
- **Backtest status** — VALIDATED (walk-forward) / SUPPORTED (in-sample) / HYPOTHESIS
- **Data needed to optimize** — what we must have to tune & regime-condition it
- **Verdict** — current call

---

## 1. STMR Bull Put Spread  `bps_stmr`
- **Thesis:** oversold-but-uptrend mean reversion; sell put premium into the bounce.
- **Instrument:** SPX/SPXW put spread.
- **Entry trigger:** ES daily `%K8 < 15 AND Close > SMA100` (the STMR signal).
- **Structure:** sell ~30Δ put / buy put 50pt below (fixed width). **14 DTE.**
- **Exit:** first daily `Close > SMA5`; else settle intrinsic at expiry.
- **Sizing:** 1-lot baseline; collateral = width − credit; cap peak concurrent.
- **Favorable regime:** elevated-but-**falling** IV (vega crush helps); non-crash uptrend.
  Worst case = violent V-recoveries and gap-down clusters (2018/2020).
- **Backtest status:** SUPPORTED (in-sample 2010–2023, OptionsDX EOD). Bid/ask fill:
  146 trades, **PF 1.93, +$18,249, maxDD −$6,321** (thin). Mid fill ~2× that. NOT walk-forward.
- **Data needed to optimize:** OptionsDX EOD (HAVE) + **VIX/IV-rank for regime** (NEED).
- **Verdict:** the one with real (if thin) support. 14DTE/50pt is the capital-efficient cell.
  Next: regime-condition on VIX/IV-rank; walk-forward; then forward-sim on OPRA.

## 2. Iron Condor (BPS + bear call)  `condor_stmr`
- **Thesis:** add call-side credit on ~zero extra collateral.
- **Structure:** `bps_stmr` + bear-call spread, same expiry; call delta sweep tested.
- **Exit:** SMA5 closes BOTH sides (put-only exit is a proven disaster).
- **Backtest status:** SUPPORTED — and it **LOSES to plain BPS** (the STMR bounce runs into
  the short calls; lower total return AND lower RoC-on-capital). Only helps tail/maxDD.
- **Verdict:** DEPRECATED as a standalone; keep only as a benchmark / tail-hedged variant.

## 3. 0DTE premium sell at gamma level  `sell_0dte_gamma`  *(HYPOTHESIS)*
- **Thesis:** on high positive-gamma days price pins; sell defined-risk premium at the
  Call Resistance / Put Support wall for the 0DTE expiry.
- **Entry trigger:** spot within X of CR/PS (from the IB gamma scanner) on a positive-GEX day.
- **Structure:** 0DTE credit spread (put spread below PS / call spread above CR), tight width.
- **Exit:** profit target (e.g. 50% credit) / stop (e.g. 2× credit) / time-flat by 15:45 ET.
- **Backtest status:** HYPOTHESIS. **No historical data to test** (needs intraday chains + OI).
- **Data needed to optimize:** intraday NBBO + OI history → **ThetaData** (2020+) OR forward-only.
- **Verdict:** the strongest reason to want ThetaData; otherwise forward-test on OPRA feed.

## 4. Gamma-level fade / HVL play  `gamma_level_fade`  *(HYPOTHESIS)*
- **Thesis:** dealer gamma walls act as support/resistance; HVL (gamma flip) separates
  pin vs trend regimes.
- **Entry trigger:** spot touches CR/PS (fade) or crosses HVL (regime switch) — from scanner.
- **⚠️ Prior evidence AGAINST:** S66 — MenthorQ's own levels held **~50% once actually
  touched** (headline hold-rates are mostly "level rarely reached"). So a naive fade has ~no edge.
- **Backtest status:** HYPOTHESIS, with a skeptical prior. Needs a real conditioner
  (GEX magnitude, DTE, distance, regime) to beat coin-flip.
- **Data needed:** OI history (ORATS) for backtest, OR forward-log IB scanner + outcomes.
- **Verdict:** do NOT trade naively. Frame a conditioned hypothesis first, then test.

---

## A. Regime / "favorable environment" framework
Every strategy is scored **conditioned on the environment**, not just pooled. Dimensions:

| Dimension | Source | Have? |
|---|---|---|
| **IV level / IV-rank / IV-percentile** | VIX + option IV | VIX **NEED** (free); IV in OptionsDX ✓ |
| **VIX term structure** (contango/backwardation) | VIX + VIX3M/VX futures | NEED (free) |
| **Trend vs range** | Kaufman ER, ADX, `daily_regime` | HAVE (`indicators.py`) |
| **Realized vol / ATR%** | ES bars | HAVE |
| **Dealer gamma regime** (pos/neg GEX, HVL side) | IB scanner / MenthorQ | HAVE (live), NO history |
| **Day-of-week / expiry / event (FOMC/CPI)** | calendar | HAVE / easy |

**Premium-selling prior:** best in elevated-but-**falling** IV and range/positive-gamma;
worst in IV spikes and negative-gamma trend days. Confirm empirically per strategy.

## B. Trade log (unified, split by strategy)
Both the **backtest** and the **forward-sim** write ONE schema so results are comparable.
`data/options_log/trades.parquet` (proposed) — one row per trade:

`strategy_id, source(backtest|sim|paper), symbol, entry_dt, exit_dt, dte, structure,
legs(json: right/strike/delta/expiry), credit, exit_cost, fill_model, slippage,
pnl, roc, collateral, hold_days, win, `
**regime tags:** `vix, vix_rank, er10, adx, gex_regime, hvl_side, dow, event`.

Per-strategy rollups: trades, win%, PF, avg RoC, expectancy, maxDD, avg loser, and the
same **sliced by each regime tag** (the "favorable environment" table).

## C. Data inventory — what we have vs need
| Data | Status | Use |
|---|---|---|
| OptionsDX SPX EOD 2010–2023 (bid/ask/greeks/IV, **no OI**) | HAVE | backtest multi-day spreads |
| ES futures bars 5m/15m/1m + daily (2009/2021→2026-07-09) | HAVE | underlying proxy for signals/indicators |
| Indicator library (ATR/ADX/ER/VWAP/value areas/regime) | HAVE | entry signals + regime tags |
| MenthorQ level logs (`data/menthorq/`, `gamma_tracker/`) | HAVE (forward) | calibrate/validate IB gamma levels |
| IB live: OI + greeks + NBBO (OPRA, ~$1.50/mo) | HAVE (live) | scanner + forward-sim quotes |
| **VIX daily (+ term structure)** | **NEED** (free: CBOE/FRED/Stooq) | regime conditioning — do this first |
| **SPX cash daily** | derive from OptionsDX `UNDERLYING_LAST` / ES proxy / free | signals on the actual underlying |
| **Historical intraday NBBO + OI** | NEED (ThetaData $40, 2020+) | optimize 0DTE + gamma strategies |
| Historical OI deep (2007+) | ORATS (paid, later) | historical gamma-level backtest |

## D. Optimize-first vs forward-test — the honest split
- **Multi-day spreads (BPS family):** optimize NOW on OptionsDX EOD (have the data) —
  DTE/width/delta done; add VIX/IV-rank regime, then walk-forward. No new purchase.
- **0DTE + gamma-level strategies:** CANNOT be optimized on data we own (no intraday, no OI).
  Two roads: (a) **ThetaData** ($40, intraday+OI 2020+) to backtest them, or (b) **forward-test
  on the OPRA feed** (free, but accumulates slowly). Decide per strategy's priority.

## E. Where MenthorQ fits
1. **Ground truth for our gamma math** — the IB scanner recomputes CR/PS/HVL; MenthorQ is the
   reference we calibrate against (`spx_calibration.csv`, `spx_ib_profiles/`). If ours matches
   theirs, we trust ours (and don't need to pay a vendor for live levels).
2. **Candidate signal source** — but S66 says the levels are ~coin-flip once touched, so they're
   a component to *validate*, not assume.

## F. Open decisions
- [ ] Pull VIX (+term structure) daily — cheap, unblocks all regime work. **Do first.**
- [ ] ThetaData $40 yes/no — the gate for backtesting 0DTE + gamma (vs forward-only).
- [ ] Build the unified trade-log writer (§B) before running any sim.
- [ ] Walk-forward the BPS family with regime conditioning.
- [ ] Frame a *conditioned* gamma-level hypothesis (don't trade the naive fade).
