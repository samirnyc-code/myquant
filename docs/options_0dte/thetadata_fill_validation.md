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

## 2. How we pull (the data layer — BUILT)

- [scripts/thetadata_worklist.py](../../scripts/thetadata_worklist.py) → enumerates every
  contract from `trades.parquet` (+ ET fill anchors from `orders.csv`). SPX-only, 0DTE.
  Output: `data/options_sim/thetadata_pull_list_<date>.csv` (366 contracts, 24 dates,
  2026-08-04 → 09-04) + `..._worklist_legs_<date>.csv`.
- [scripts/thetadata_fetch.py](../../scripts/thetadata_fetch.py) → v3 NBBO tick pull, one
  file per contract, resumable, manifest. `--dry-run` (no terminal), `--probe`, `--limit`.

v3 request (verified spec; **tick** per the vendor's advice that 0DTE entries/exits belong
on ticks, not 1-min rows):
```
GET http://127.0.0.1:25503/v3/option/history/quote
    ?symbol=SPXW&expiration=YYYYMMDD&strike=<dollars.3f>&right=call|put
    &date=YYYYMMDD&interval=tick&format=csv
-> timestamp,bid_size,bid,ask_size,ask,...
```

**Blocked on:** local Theta Terminal (Java) — not installed here. Installing Java = a
state change (needs user OK), or the user sets up the terminal with their creds.

**Smoke-test items (unresolved until terminal up; `--probe` resolves #1–2):**
1. ThetaData root for SPX weeklys — SPXW vs SPX.
2. v2 `trade_quote` strike digit-count (v3 dollars is unambiguous; v2 = 1/10-cent int).

## 3. Vendor's three execution-model pillars → our comparison-script spec (TO BUILD)

The pull is only the data. The faithfulness lives in a **comparison / execution-model
script** (not yet built). It must encode all three:

1. **Fills — model at the touch + small buffer, and CHECK SIZE.**
   Live fills land between mid and touch; our sim already crosses to the marketable touch
   (BUY@ask / SELL@bid). **New requirement:** at each fill's timestamp, read the tick
   `ask_size` (for a buy) / `bid_size` (for a sell) and confirm **size ≥ our order size
   (1 lot)** — a touch price with no size behind it is not a real fill. Flag any fill where
   size was 0/insufficient.

2. **Timing — ticks + a signal→fill latency delay.**
   Align each booked fill to the tick **at fill-time PLUS a small latency offset**, not the
   exact-second tick. Make the offset a parameter; report sensitivity. (1-min rows are for
   signals/scanning only — we do not use them for entry/exit truth.)

3. **Prints = confirmation, not a guaranteed fill.**
   v2 `trade_quote` prints verify our price was real (a trade printed at/through it) but
   cannot place us in the queue. Use prints to CONFIRM plausibility, never to assert a fill.

## 4. SPX specifics (vendor)

- **Cash-settled; SPXW settles on the CLOSE → model settlement, not assignment.** Our EOD
  trades already book as `cash_settle`; the comparison must value expiry on the close
  settlement basis, not a last-tick mark.
- **Early-close days end 1pm ET.** Already captured — `data/options_sim/market_holidays.json`
  (19 early-closes, imported from NT8). Wire into the comparison's session bounds.

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
- **Next build (needs terminal + data):** the comparison/execution-model script per §3–4,
  then the §5 live 2-week gap test.
- Vendor offered to review our quote-pull snippet once we're in — the §2 URL form is what
  we'll send.
