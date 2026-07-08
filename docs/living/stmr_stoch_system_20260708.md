# Trend-Filtered Short-Term Mean Reversion (STMR) — built on the user's colored stochastic
**S61 · 2026-07-08 · ES daily, 2009-04 → 2026-07**

## What this is
A **trend-filtered short-term mean-reversion** swing system (pros: "Connors-style
STMR", colloquially *buy-the-dip / fade-the-rip*). Trades the **ES future
outright** ($50/pt); same signal on MES = $5/pt. NOT options (an options
expression is noted at the end). Built on the user's own
`MyStochasticsColorwithSignal` (K=8, D=1, Smooth=1) exported daily to
`data/ES_stoch_daily.csv` via `nt8/indicators/MyStochasticExporter.cs`.

## The system (final)
- **LONG core:** stochastic `%K(8) < 15` AND `Close > SMA100`
- **Regime SHORT (bear hedge):** `%K(8) > 85` AND `SMA50 < SMA200` AND `Close < SMA50`
- **Exit:** first close back through SMA5 (long: `Close>SMA5`; short: `Close<SMA5`); 15-bar time stop.
- **Entry:** signal-day **CLOSE / market-on-close (last minutes)** — beats next-day open by ~11%.

Reproduce: `python scripts/mr_stoch_system.py` (charts → `docs/living/mr_stoch_system.png`).

## Results (ES $50/pt, ~$4 RT, 1 contract, 2009→2026)
| Book | n | win% | PF | exp/trade | total | maxDD | R/DD | +yrs |
|---|---|---|---|---|---|---|---|---|
| LONG core (MOC close) | 184 | 80% | **4.45** | +$1,064 | +$196k | −$8.1k | **24.3** | 16/17 |
| LONG + regime SHORT (MOC) | 243 | 75% | 3.06 | +$939 | **+$228k** | −$17.3k | 13.1 | 16/17 |
| LONG core, next-day OPEN (ref) | 184 | 79% | 4.02 | +$962 | +$177k | −$7.9k | 22.4 | 16/17 |

## How we got here (stones turned)
1. **The stochastic is real — but only the user's, not a generic one.** A self-rolled
   14/3/3 daily stochastic gave garbage (n=15, negative). The user's **8/1/1 "green
   zone" (ZoneSignal=+1, oversold)** is a genuine edge: standalone PF ~2.1, and as an
   RSI-2 confirm it lifts expectancy +24% without adding tail risk.
2. **Optimization:** tighten oversold **20→15** on the default K=8 — single sensible
   knob, 15/17 yrs, PF 2.83. Going further (sweeping K & OS) = overfitting.
3. **Walk-forward (12mo IS / 4mo OOS):** re-optimizing K/OS *hurts* OOS (PF 2.11,
   R/DD 3.5) vs the **fixed** setting (PF 2.71, R/DD 11.3). Same verdict for
   trend-length: fixed SMA100 OOS PF 3.77 / R/DD 20.2 beats re-optimizing. **Lock the
   params, stop tuning.**
4. **Trend filter:** SMA100 > SMA200 for risk (PF 4.02, maxDD −$8k vs −$17k) and it
   turns 2011/2018/2022 positive. EMA ≈ SMA (marginal). Exit must stay `>SMA5`
   (loosening to SMA10 blew DD to −$107k).
5. **Why late-2011 was a disaster:** Aug-2011 (US downgrade + Euro crisis) was a
   **whipsaw around the 200-SMA**, not a clean downtrend — brief pops above the line
   tripped "buy the dip" then plunged. A single long MA can't tell an uptrend from a
   bear bounce. **Requiring `Close>SMA50` (or SMA100 gate) fixes it.**
6. **Both sides / prolonged bear:** a naive symmetric short (`C<SMA100`) is a
   loser that **blew up −$85k in the 2026 rally**. Gating the short to a *confirmed*
   downtrend (`SMA50<SMA200`, `+C<SMA50`) kills the blow-up and keeps the 2022 windfall
   (+$34–87k). Combined books make more money (+$228k) but at lower R/DD — a real
   long-only(smooth) vs all-weather(more $) trade-off.
7. **Entry timing:** MOC/close entry > next-day open by ~11% (captures the overnight
   bounce after an oversold settlement). Limit "deeper fill" looks good per-trade but
   skips half the winners.

## Crash / prolonged-bear behavior
- Sustained downtrend → trend filter keeps you flat (2008/most-2022 = no long trades).
- Danger = the **choppy topping/whipsaw** phase; neutralized by the SMA50/SMA100 gates.
- Cannot fully immunize a long-only dip-buyer: worst single-trade heat ≈ **−$18k/ES
  contract** (Mar-2020). Defenses: vol-scaled sizing, the trend gates, and/or the
  defined-risk options expression.

## Tooling roadmap (what would help next)
1. **Vol-scaled position sizing (ATR / vol-target)** — biggest single upgrade; tames the crash tail.
2. **VIX level + term structure (VIX/VIX3M)** overlay.
3. **Breadth/internals** (% > 50-day, McClellan) for washout confirmation.
4. **Diversify the same engine across NQ/RTY/YM + uncorrelated (ZN/GC)** — breadth beats tuning.
5. **Dealer gamma (MenthorQ/SpotGamma, GEX / gamma-flip)** — direct "is reversion likely today" read.

## Options expression (defined-risk chassis for the same edge)
At the oversold entry, **IV spikes** → sell a **bull put spread**: paid by the bounce
(delta), decay (theta), and vol collapse (vega). Prior model: PF 2.94, ~$82 max risk.
Options traders' key gauges: **IV Rank/Percentile, the Greeks, put skew, VIX term
structure, dealer gamma.** Hours: **SPX/SPXW options trade to 15:15 CT (4:15 ET)** —
matching the ES settlement — so the **MOC entry works for the options version too**;
SPY options stop 15 min earlier (4:00 ET) and overnight options liquidity is thin, so
the RTH close is the one window futures + options are liquid together.

## Data / files
- `data/ES_stoch_daily.csv` — daily colored-stochastic export (4,442 rows, 2009-2026).
- `scripts/mr_stoch_system.py` — canonical system + equity/DD chart.
- Charts: `mr_stoch_system.png`, `mr_stoch_equity.png`, `mr_stoch_wfa.png`, `mr_bothsides.png`.
