# Intraday Setup Scorecard — running ledger

**What this is:** a persistent record of every intraday setup we test, with its year PnL, so we
keep track of what works. Started S64 (2026-07-10). Update this file every time we test/change a setup.

**Test bench (current):** last **252 trading days** of `_continuous.parquet` (5-min ES RTH).
One position at a time. **Exit = scalp +2 pt.** Stop as each setup defines. Bar-fill sim
(same-bar stop+target tie broken by the bar's close direction). ES = $50/pt.

> ⚠️ **Caveats (gross, optimistic):** (1) **no commissions/slippage** — ES ≈ $4–5 RT ≈ 0.1 pt/trade,
> so subtract ~0.1 pt/trade from `pt/trade`. (2) **limit fills assume touch = fill** (optimistic;
> real limits at an extreme may not fill). (3) 5-min **bar fills**, not tick — the intrabar tie rule
> is a heuristic. Treat these as *relative* rankings + a rough edge estimate, not live P&L.

---

## Results (scalp +2, last 252 days)

| # | Setup | entry | stop | year pt | $/ES | trades | pt/trade |
|---|---|---|---|---|---|---|---|
| 1 | **BB/SA + location** (BB lower-40% / SA upper-40%) | limit | 4t | **+461** | **+$23,050** | 1180 | +0.39 |
| 2 | Fade range EDGES only (SA≥80% / BB≤20%) | limit | 4t | +449 | +$22,450 | 1105 | +0.41 |
| 3 | **BB/SA mean-rev** (buy below bull / sell above bear, every bar) | limit | 4t | +406 | +$20,300 | 974 | +0.42 |
| 4 | **BOPBL** = with-trend limit PB (BB in bull regime / SA in bear regime) | limit | 4t | +376 | +$18,800 | 971 | +0.39 |
| 5 | BB/SA in-range only (regime = neutral) | limit | 4t | +166 | +$8,300 | 368 | **+0.45** |
| — | with-trend **breakout STOP-entry** (buy above bull / sell below bear) | **stop** | 1t beyond SB | **−2,441** | **−$122,050** | 2194 | **−1.11** |
| — | with-trend breakout, small-SB filter only (≤6t) | stop | SB | +5 | +$238 | 36 | ~0 |
| — | fade failed-extreme (breakout fails → fade) | stop | SB | −1,425 | −$71,262 | 1415 | −1.0 |

## The one finding that matters
**LIMIT (pullback) entries win; STOP (breakout) entries lose.** Every *buy-below-bull / sell-above-bear*
variant with a tight 4t stop (2:1 RR) is **positive (+0.39–0.45 pt/trade, +$8k–$23k/yr on 1 ES)**.
The breakout *stop-entry* is catastrophic (−1.11 pt/trade, −$122k). The whole prior failure was the
entry mechanic. Net of ~0.1 pt/trade costs the limit setups are still ≈ +0.3 pt/trade → roughly
**+$16k/yr on 1 ES** for the best variants — modest but real.

## Setups still to test (queue)
- **Triangle BO + pullback** — use the S63 contracting/expanding detector; enter the BP after a triangle break.
- **f1/2EL at range top, f1/2ES at range bottom** — the explicit failed-entry fade (partially captured by #2).
- **Exit variants** on the winners: scalp+BE+run, Brooks 2:1 swing (the RR sweep showed 1R is worst; test the runner).
- **Day-type gating done right** — the winners are mean-reversion; confirm they hold on trend days vs. need a with-trend switch.
- **Smart-tool filters** — ER, EMA-slope, VWAP, IB, Zerolag as signal-quality gates on the limit entries.
- **Realistic costs + limit-fill model + tick sim** before believing any of this live.

## Reproduce
`scripts/` (to be committed) — currently in scratchpad `scorecard.py`. Bench = last 252 days, scalp +2.
