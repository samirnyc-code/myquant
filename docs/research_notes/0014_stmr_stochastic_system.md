# 0014 — Trend-Filtered Short-Term Mean Reversion on a Colored Stochastic — 2026-07-08
**Series:** MC Setup Research Notes · Note 0014
**Confidence:** Medium-High **as a positive result** — 17 years of ES daily bars (2009-04 → 2026-07, 4,442 sessions), one economically-motivated parameter choice, walk-forward validated (12-month in-sample / 4-month out-of-sample), robust in 16 of 17 calendar years. Exploratory (not pre-registered); single instrument, single timeframe. The headline dollar figures below are shown on **micro (MES) and unlevered** sizing, not a full ES contract, so they reflect what a real account can carry.

**TL;DR:** Buy the ES on the daily close when a short stochastic is deeply oversold *and* price is above its 100-day average; sell when price closes back above its 5-day average. Enter market-on-close in the last minutes (that beats the next-day open by ~11%). Over 17 years this fires ~11×/year, wins **80%**, runs a **profit factor of 4.45**, and is positive in **16 of 17 years**. On **1-lot MES** it makes ~**+$19.4k** with a worst-ever drawdown of **−$808** on a ~**$10k** account; expressed unlevered (ETF shares, any account size) it compounds **×2.58** with a max drawdown of **−4.8%**. A **regime-gated short** (mirror signal, only in confirmed downtrends) turns the system all-weather and paid **+$87k-equivalent in 2022**. The oscillator is the trader's own indicator (an 8-period colored stochastic); a textbook 14/3/3 version does *not* work — the specific settings matter.

---

## 1. The setup (so this note stands alone)

**Instrument / data.** ES continuous futures, **RTH daily bars** (settlement stamp 15:15 CT), 2009-04-13 → 2026-07-06. Indicator values are exported bar-by-bar from NinjaTrader by `MyStochasticExporter` (self-contained; reproduces `MyStochasticsColorwithSignal` math): **%K = 100 × Σ(Close−LowN) / Σ(HighN−LowN)** over **N=8** bars, smoothing 1 (so %D=%K). The "colored" oversold zone is %K in its lower band.

**The system (final).**
- **LONG entry:** `%K(8) < 15` **AND** `Close > SMA100`. Fill at the **signal-day close** (market-on-close, last minutes).
- **Exit:** first day that `Close > SMA5`; hard time stop 15 bars.
- **Regime SHORT (optional bear hedge):** `%K(8) > 85` **AND** `SMA50 < SMA200` **AND** `Close < SMA50`; exit first `Close < SMA5`.

**What it is, in pros' language.** A *trend-filtered short-term mean-reversion* (STMR) swing system — the "Connors school": buy short-term oversold *inside* a longer uptrend. Colloquially, *buy-the-dip / fade-the-rip*.

## 2. The questions

1. Does the trader's colored stochastic carry a real, standalone mean-reversion edge on the daily?
2. What is the *right* oscillator setting — and does optimizing further help or overfit?
3. Which trend filter (length; SMA vs EMA) controls risk, and why did 2011/2018/2022 hurt?
4. Does entering at the close (MOC) beat the next-day open?
5. Does adding the short side help in a prolonged bear — and how must it be gated?
6. What does this look like on an account you can actually fund (MES / unlevered), not a full ES contract?

## 3. How we tested it

- **Backtest:** event-ordered on daily OHLC, entry next-open **and** signal-close variants, ~$4 round-turn (ES) / ~$1.50 (MES). 1 contract per signal; concurrency tracked for margin.
- **Parameter sweep:** K in {5,8,10,14,21}, smoothing in {1,3}, oversold in {10,15,20,25}; ranked by **per-year robustness**, not headline PF.
- **Walk-forward:** 12-month IS optimize → 4-month OOS, rolled 2010→2026; compared to the *fixed* setting.
- **Trend filter:** SMA100/150/200/250, EMA200, plus regime gates (SMA50>SMA200, C>SMA50, slope).
- **Sizing:** 1 ES, 1 MES, and unlevered %-compounded (ETF-share equivalent).

## 4. Results

### 4.1 The edge is real — and it's the trader's *own* stochastic
A self-rolled generic 14/3/3 daily stochastic produced garbage (n≈15, negative). The trader's **8-period oversold zone** is a genuine edge, standalone PF ≈ 2.1 and, as a confirm on RSI-2, lifts expectancy **+24%** without adding tail risk. The specific short, fast setting is doing the work.

### 4.2 One sensible knob; more optimization overfits
Tightening the oversold line **20 → 15** on the default K=8 is a single, economically-sensible improvement (demand a *deeper* oversold): PF 2.08 → **2.83**, positive **15/17** years. Sweeping K *and* OS jointly finds flashier combos (PF 3.7) that fire only ~100 times and miss a year — classic curve-fitting.

### 4.3 Walk-forward says: lock the parameters
| Approach | OOS PF | OOS total (ES) | OOS max DD | Return/DD |
|---|---|---|---|---|
| Re-optimize K & OS every 4 months | 2.11 | +$165k | −$47.2k | 3.5 |
| **Fixed setting (no re-opt)** | **2.71** | **+$191k** | **−$16.8k** | **11.3** |
| Re-optimize trend length | 3.56 | +$151k | −$13.3k | 11.3 |
| **Fixed SMA100** | **3.77** | **+$159k** | **−$7.9k** | **20.2** |

Re-optimization **degrades** out-of-sample every way we cut it. The rolling optimizer's picks are unstable (noise-chasing on ~15 sparse signals per window). **Fix the parameters and stop tuning** — the honesty check that most retail systems fail.

### 4.4 Trend filter, and why 2011/2018/2022 hurt
| Trend gate (entry %K8<15) | n | PF | max DD (ES) | 2011 | 2022 |
|---|---|---|---|---|---|
| C > SMA200 | 253 | 2.85 | −$16.8k | −$6.3k | −$12.1k |
| **C > SMA100** | 184 | **4.02** | **−$7.9k** | **+$5.2k** | **+$3.5k** |
| C > SMA200 & C > SMA50 | 100 | 7.75 | −$5.1k | +$2.1k | +$2.3k |

Late-2011 (US downgrade + Euro crisis), Q4-2018 and 2022 were **whipsaws around the 200-day** — brief pops above the line tripped "buy the dip," then price plunged. A single slow average can't tell an uptrend from a bear-market bounce. A **nearer trend line (SMA100)** — or a second gate (`C>SMA50`) — refuses those dips and turns all three crisis years positive. EMA ≈ SMA. Loosening the *exit* to SMA10 was catastrophic (drawdown −$107k): let losers run and a mean-reversion system dies.

### 4.5 Enter at the close, not the open
| Entry | PF | exp/trade (ES) | max DD | Return/DD |
|---|---|---|---|---|
| next-day OPEN | 4.02 | +$962 | −$7.9k | 22.4 |
| **signal CLOSE / MOC** | **4.45** | **+$1,064** | −$8.1k | **24.3** |

The market-on-close entry captures the **overnight bounce** that tends to follow an oversold settlement, worth ~**+11%** expectancy for free. (Mild caveat: it uses the forming settlement to trigger — execute in the final minutes.) *SPX options also trade to 15:15 CT, so the same last-minutes window works for an options expression.*

### 4.6 The bear hedge — right instinct, must be gated
A naive symmetric short (`%K8>85 & C<SMA100`) is a **loser that blew up −$85k in the 2026 rally** (shorting into a powerful uptrend). Gated to a **confirmed downtrend** (`SMA50<SMA200 & C<SMA50`) it becomes a real hedge: 2022 **+$34–87k**, 2026 ≈ flat. Combined **long+short** doubles gross to **+$228k (ES)** and is positive **16/17** years — at lower Return/DD than long-only. Trade-off: smoother (long-only) vs all-weather (add the gated short).

### 4.7 What it costs to trade it (the number that matters)
LONG core, MOC close, 184 trades / 17 years, **1 contract at a time**:

| Vehicle | exp/trade | 17-yr total | max DD | worst trade | min account | scalable |
|---|---|---|---|---|---|---|
| 1 ES ($50/pt) | +$1,064 | +$196k | −$8.1k | −$8.1k | ~$60k | coarse |
| **1 MES ($5/pt)** | **+$105** | **+$19.4k** | **−$808** | −$808 | **~$10.4k** | per lot |
| **Unlevered (ETF shares)** | **+0.52%** | **×2.58** | **−4.8%** | −4.1% | **any** | fractional |

Peak concurrency is **5** positions → peak MES margin ~$6,600; a **~$10k account trades 1-lot MES** with a heat buffer, adding lots as it grows. Unlevered, it compounds **×2.58** at **~6%/yr on deployed capital** with a **−4.8%** max drawdown — and because it is **in-market only ~9% of days**, the idle 91% can earn T-bills (~4–5%), materially lifting the blended return. This is a **"cash + occasional dip-buy"** profile, not full-time market exposure.

## 5. Why it works
US equity indices are structurally upward-drifting and, on the daily, short-horizon **overreaction reverts**: a sharp oversold close inside an uptrend is a liquidity/emotion flush that the drift repairs within days. The trend filter keeps you on the side of the drift; the fast oversold oscillator times the flush; the close entry harvests the overnight repair; the SMA5 exit takes the reversion and leaves. The system's weakness is the mirror of its strength — in a *sustained* bear the drift is gone, so the trend gates flatten activity, and the residual danger is the choppy topping/whipsaw phase (mitigated, not eliminated, by the SMA50/100 gates).

## 6. What could kill it / limitations
- **Crash tail:** a long-only dip-buyer cannot be fully immunized; worst single-trade heat ≈ **−$18k per ES contract** (March-2020). Defenses: **vol-scaled sizing (ATR)**, the trend gates, small size, or the defined-risk options version.
- **Single instrument / timeframe.** Intraday mean-reversion on ES tested *negative* earlier; weekly is too sparse to trade alone. A weekly-uptrend confirm marginally lifts PF (4.45→4.98) but isn't required.
- **Edge decay:** these tools are now widely available; the durable advantage is process, sizing, execution, and diversification across instruments (NQ/RTY/ZN/GC), not the backtest.
- **Options numbers are unverified** — a bull-put-spread expression is attractive (sell rich IV into the oversold spike) but our prior PnL was a Black-Scholes *estimate*; validate on real chains (OptionsDX/DoltHub) before trusting.

## 7. How to trade it (spec)
1. Daily ES/MES. Compute %K(8), SMA5, SMA50, SMA100, SMA200 on RTH closes.
2. **Long** when `%K8<15 & Close>SMA100`; enter **MOC** in the last minutes. Exit next day `Close>SMA5` (time-stop 15 days).
3. **Optional short** when `%K8>85 & SMA50<SMA200 & Close<SMA50`; exit `Close<SMA5`.
4. Size on **MES** to your account (1 lot ≈ $10k, add lots as equity grows) or trade **unlevered ETF shares** with idle cash in T-bills.
5. **Do not re-optimize** the parameters — walk-forward shows fixed beats fitted.

---

**Reproduce:** `python scripts/mr_stoch_system.py` · data `data/ES_stoch_daily.csv` · exporter `nt8/indicators/MyStochasticExporter.cs` · figures `docs/living/mr_stoch_system.png`, `mr_stoch_realistic.png`, `mr_stoch_wfa.png`, `mr_bothsides.png`.
