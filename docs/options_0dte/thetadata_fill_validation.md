# ThetaData fill-validation — plan, vendor guidance, and the comparison spec

**Goal:** ground-truth the options-sim's Aug–Sep-2026 SPX fills against real historical
OPRA data, so we know the true backtest-vs-live gap instead of guessing it.
**Scope:** SPX only (root SPXW). XSP retired — excluded (S112).
Source of truth for state stays `docs/living/handoff.md`; this note is the standing spec.

---

## 1. Data tier — Standard $80 (confirmed by ThetaData directly)

Standard gives everything we need:
- **Consolidated NBBO at tick**, with **bid_size / ask_size** on every quote (2016→).
- **Every trade print** with its **condition codes**.
- **Underlying price + timestamp** on every greeks / IV row.
- Real-time data + streaming included (matters for the live paper-trade gap test, §5).

Vendor's framing (verbatim intent): *"the gap between a backtest and live trading is not
really about the data anymore … the question becomes how you model your own execution on
top of it, and that is where most of the difference comes from."*

## 2. How we pull (the data layer — BUILT; vendor-reviewed)

- [scripts/thetadata_worklist.py](../../scripts/thetadata_worklist.py) → SPX-only, 0DTE, from
  `trades.parquet` (+ ET fill anchors from `orders.csv`). Emits three DATED CSVs:
  `thetadata_events_<date>.csv` (**568 fill events** — the at_time/trade_quote input),
  `thetadata_pull_list_<date>.csv` (366 contracts — full-day input),
  `thetadata_worklist_legs_<date>.csv`.
- [scripts/thetadata_fetch.py](../../scripts/thetadata_fetch.py) → three datasets, **4-way
  parallel** (Standard = 4 requests in flight), header-based parse, `--dry-run`/`--limit`.

**Primary = `at_time/quote`** (vendor's recommendation — one call per fill, not a day of ticks):
```
GET http://127.0.0.1:25503/v3/option/at_time/quote
    ?symbol=SPXW&expiration=YYYYMMDD&strike=<dollars>&right=call|put
    &start_date=YYYYMMDD&end_date=YYYYMMDD&time_of_day=HH:MM:SS.mmm&format=csv
-> the last NBBO at/before that ms, WITH the quote's own stamp (= how fresh it was at our fill)
```
**Second-check = `trade_quote`** over a ±window (did a print hit our price, which side).
**Full-day = `history/quote` interval=tick** — only where we want to watch size at the touch move.

Returned CSV columns (**read by header**, order not guaranteed):
`symbol,expiration,strike,right,timestamp,bid_size,bid_exchange,bid,bid_condition,ask_size,ask_exchange,ask,ask_condition`

**Vendor-confirmed (2026-09):**
- **ROOT = SPXW** (SPX = AM monthlies, no 0DTE; SPXW = PM, holds every 0DTE). No `--probe` needed.
- Daily 0DTE exists only since **2022-05-16** (before: Mon/Wed/Fri) — matters only if the window extends back.
- `interval=tick` = every OPRA NBBO update w/ sizes+exchange codes (143k rows for one 0DTE put on 08-04).
- `right=P`/`right=put` and `strike=7560`/`7560.000` are equivalent. Default window ends 16:00 ET
  (fine for 0DTE; SPXW stops at 16:00). `end_time=16:15` only for non-expiring extended-session pulls.

**Blocked on:** local Theta Terminal (Java) — not installed here (state change → needs user OK,
or user runs it). **Open to confirm at smoke-test:** exact v3 `trade_quote` route/params (vendor
described the behavior; we guessed `history/trade_quote?...&start_time&end_time` — verify).

## 3. Vendor's three execution-model pillars → our comparison-script spec (TO BUILD)

The pull is only the data. The faithfulness lives in a **comparison / execution-model
script** (not yet built). It must encode all three:

1. **Fills — model at the touch + small buffer, and CHECK SIZE.**
   Live fills land between mid and touch; our sim already crosses to the marketable touch
   (BUY@ask / SELL@bid). **New requirement:** at each fill's timestamp, read the tick
   `ask_size` (for a buy) / `bid_size` (for a sell) and confirm **size ≥ our order size
   (1 lot)** — a touch price with no size behind it is not a real fill. Flag any fill where
   size was 0/insufficient.

2. **Timing — DO NOT trust our logged timestamp (this is the crux).**
   `orders.csv ts_et` is our MACHINE wall-clock at the fill callback (client-side, +latency,
   1s) — **not** the exchange execution time. On 0DTE that easily lands on the wrong tick, so
   an exact-timestamp match is invalid. Handle it three ways (see §4b): primary validation is
   **price/print-anchored (clock-free)**; only after we've RECOVERED or MEASURED the true time
   do we do a tight time-local check, with a latency offset as a reported parameter. (1-min
   rows are signals/scanning only — never entry/exit truth.)

3. **Prints = confirmation, not a guaranteed fill — and FILTER BY CONDITION.**
   `trade_quote` prints verify a trade printed at/through our price, but can't place us in the
   queue. **Critical (vendor):** we trade multi-leg, so most window prints are complex-order
   codes **130 / 131 / 134** — they trade at PACKAGE prices and can land inside/outside the
   single-leg NBBO, so they DO NOT prove a single-leg fill. Confirm only on **condition 0
   (regular)** and **18 (electronic single-leg)**; treat complex codes as context. Our
   `place_legs` path fills each leg as a single-leg order → 0/18 is exactly our confirmation;
   BAG (`place_combo`) fills appear as complex. Empty window → HTTP **472** "No data" = a valid
   "no prints", NOT a failure (common on 0DTE) — the fetcher classifies it as such.
   Center the window on the fill with **millisecond** bounds once we have ms times.

   **at_time freshness gate:** always compare the returned quote's timestamp to the fill time.
   Quotes update hundreds of times/min on these contracts, so a quote stamped >1–2s before the
   fill = quiet/early (e.g. a 09:30:01 fill returning a 09:25 pre-open quote) — the fetcher
   records `quote_lag_s` + a `quote_stale` flag; don't validate against stale quotes.

## 4. SPX specifics (vendor)

- **Cash-settled; SPXW settles on the CLOSE → model settlement, not assignment.** Our EOD
  trades already book as `cash_settle`; the comparison must value expiry on the close
  settlement basis, not a last-tick mark.
- **Early-close days end 1pm ET.** Already captured — `data/options_sim/market_holidays.json`
  (19 early-closes, imported from NT8). Wire into the comparison's session bounds.

## 4b. Timestamp fidelity — the fill-time problem and the fix (S112)

**Problem.** Our only per-leg time for the Aug fills is `orders.csv ts_et` =
`datetime.now("America/New_York")` written INSIDE the fill callback
([ib_order_test.py](../../scripts/ib_order_test.py)) — machine wall-clock + processing/
network latency, 1s granularity. It is NOT the exchange fill time. IB's real time lives on
`Fill.time`, but the desk never persisted it and `reqExecutions` only reaches the current
session, so it's not in the live API for August anymore.

**Fix — three prongs (all in motion):**

1. **Validate clock-free (primary).** Anchor on PRICE, not our timestamp: pull the contract's
   trade prints + NBBO for the whole day and check whether a real print hit our fill price /
   whether our price was ever at the touch. Answers "was this fill achievable" with zero
   dependence on our clock. This alone gives a fill-realism verdict.

2. **Recover the true time from IB (paper-account Flex Web Service).** Confirmed supported for
   paper accounts (own Flex setup in Account Management; identical API). A **Trade Confirmation
   Flex** query returns each August execution WITH its timestamp, order ID, price, commission.
   Tool: [scripts/ib_flex_executions.py](../../scripts/ib_flex_executions.py) — needs a paper
   Flex token + query ID in env (`IBKR_FLEX_TOKEN` / `IBKR_FLEX_QUERY`); prints the exact
   Client-Portal setup steps if absent. Join on `order_id` → true fill time per leg.

3. **Measure the residual offset.** We logged `quote_px` (the NBBO we saw) next to `ts_et`.
   Find the ThetaData tick whose NBBO matches `quote_px`; the gap to `ts_et` IS our effective
   clock+latency offset. Across all ~196 fills → a distribution: tight ⇒ correct and use a
   narrow ±window; noisy ⇒ widen the window to cover it. Turns the uncertainty into a number.

**Never again (forward fix, DONE S112).** [scripts/exec_logger.py](../../scripts/exec_logger.py)
persists `Fill.time` + `commissionReport` to `data/options_log/ib_executions.csv` on every
future fill — wired (guarded, non-fatal) into `ib_order_test.marketable` and the daemon's
`place_combo`/`close_combo`. Authoritative timestamp = `ib_exec_time_utc`; align ThetaData
ticks on THAT, never `ts_et`.

## 5. The number that actually matters — measure the gap live (vendor)

Standard includes real-time + streaming. Once set up: **paper-trade the strategy live for
~2 weeks, then compare to the backtest for the SAME days.** That per-strategy delta is the
real backtest-vs-live gap — more trustworthy than any modeled estimate. Do this alongside
the historical fill audit, not instead of it.

## 6. Where this leaves us

- Data tier + pull design: DONE and vendor-validated.
- Historical fill audit already run on our own logged NBBO
  ([scripts/fill_vs_nbbo_audit.py](../../scripts/fill_vs_nbbo_audit.py)): median fill at the
  cross, 79% ≤ mid. ThetaData replaces our snapshot NBBO with the full consolidated tape to
  kill the ~21% quote-timing noise.
- **Report BUILT (turnkey):** [scripts/thetadata_fill_report.py](../../scripts/thetadata_fill_report.py)
  — reads `at_time_results` (+ `trade_quote_prints`) → the presentable August HTML: KPI tiles
  (median fill position, % crossed, % size≥1, single-leg print-confirmed, through-book, stale),
  a fill-position histogram, and a per-strategy table. `--mock` renders a CLEARLY-WATERMARKED
  synthetic preview at real scale (no terminal). Tomorrow: pull → `thetadata_fill_report.py` → done.
- **Still to build (needs terminal + data):** nothing for the point-check report; later the §5
  live 2-week gap test + optional full-day size-at-touch evolution.
- Vendor offered to review our quote-pull snippet once we're in — the §2 URL form is what
  we'll send.
