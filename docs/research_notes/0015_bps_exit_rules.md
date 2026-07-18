# 0015 — BPS/STMR Exit-Rule Study: the exit signal IS the edge

**Series:** MC Setup Research Notes · **Session:** S73 (2026-07-14/15) · **Instrument:** SPX/SPXW options (signal on ES daily)

**Confidence: HIGH** — 142 trades over 14 years, identical pricing engine as the prior
validated backtests (OptionsDX EOD bid/ask, real fees), and the result is a *ranking* of
exit rules on the same entries, which is robust to most data issues.

**TL;DR:** The STMR bull-put-spread's profit comes **entirely from its timing exit**
(first daily close > SMA5) — not from premium decay. Hold-to-expiry turns the strategy
*negative*. The famous tastylive "manage winners at 50%" rule is ~flat here. Price stops
are actively destructive. Separately, VIX-level/rank filters were tested and **rejected
out-of-sample**: trade the strategy unconditioned. Practical rule: **enter on signal,
exit on signal, no stops, no targets, never hold to expiry.**

---

## 1. The setup (self-contained)

- **STMR signal (entry):** ES daily stochastic `%K8 < 15 AND Close > SMA100` — an
  oversold-pullback-in-uptrend mean-reversion signal (validated walk-forward as a futures
  system in note 0014: PF 4.45, 80% win, 16/17 years).
- **Options expression:** sell a SPX/SPXW **bull put spread** — short ~30Δ put, long put
  50 pts lower, ~14 DTE. Defined risk = width − credit (~$4–4.9K/lot).
- **Baseline exit:** first daily `Close > SMA5` → buy the spread back; else cash settlement.
- **Pricing:** OptionsDX SPX EOD chains 2010–2023, **bid/ask fills** (sell at bid, buy at
  ask), $1.30/contract/leg, settlement at intrinsic from official close.

## 2. Question

Does the exit rule matter — and specifically, would the industry-standard management
rules (profit-take at 50% of credit; 2×credit stop; hold to expiration) beat the SMA5
signal exit? Secondarily: does conditioning entries on VIX level/rank/direction improve results?

## 3. How we tested it

- Entries fixed: all 142 priceable daily-close STMR signals 2010–2023 (14 DTE / 50pt / 30Δ).
- The open spread was **re-priced at every EOD** it remained open (targeted per-strike scan
  of the chains — 12,312 strike-day marks over 2,588 sessions), giving a daily
  cost-to-close path per trade (buy short back at ask, sell long at bid).
- Six exit rules simulated on identical entries; early exits pay double fees.
- VIX study: each trade tagged with VIX close, 252-day rank, and 5-day change at entry
  (CBOE daily); in-sample filter table + tercile split + **yearly walk-forward** (train
  trailing 4y → pick best filter by expectancy (min 8 trades) → trade next year OOS).

## 4. Results

### 4.1 Exit-rule shootout (142 trades, bid/ask, $1.30/ct, ES $ values are per 1-lot)

| Exit rule | Win % | PF | Avg $/trade | Total | maxDD |
|---|---|---|---|---|---|
| **SMA5 signal exit (baseline)** | 84% | **1.74** | **+$103** | **+$14,668** | **−$6,321** |
| TP 50% of credit + SMA5 | 84% | 1.72 | +$101 | +$14,298 | −$6,321 |
| TP 50% of credit alone | 87% | 0.97 | −$12 | −$1,757 | −$18,056 |
| Hold to expiry | 82% | 0.95 | −$29 | −$4,164 | **−$27,740** |
| TP50 + 2×credit stop | 63% | 0.71 | −$116 | −$16,495 | −$16,586 |
| 2×credit stop alone | 58% | 0.84 | −$77 | −$10,904 | −$18,239 |

### 4.2 VIX conditioning — in-sample filters (139 VIX-taggable trades, full sample; descriptive only)

| Filter at entry | n | Win % | PF | Avg | Total |
|---|---|---|---|---|---|
| none | 139 | 84% | 1.75 | +$105 | +$14,627 |
| VIX rank > 33% | 108 | 84% | 1.44 | +$75 | +$8,143 |
| VIX rank > 50% | 82 | 83% | 1.76 | +$106 | +$8,672 |
| VIX falling (5d) | 13 | 100% | ∞ | +$335 | +$4,352 |
| rank>33 & falling | 8 | 100% | ∞ | +$366 | +$2,931 |
| VIX rank ≤ 33% | 31 | 84% | **6.15** | +$209 | +$6,484 |

By rank tercile: low 67.3%→PF 6.15 (n31) · mid PF 1.27 (n51) · high PF 1.67 (n57).

### 4.3 VIX walk-forward (train 4y → OOS next year)

| Year | Filter chosen (in-sample) | OOS n | OOS win | OOS total |
|---|---|---|---|---|
| 2014 | rank>50 | 17 | 76% | +$2,244 |
| 2015 | rank>50 | 7 | 71% | +$1,413 |
| 2016 | rank>50 | 3 | 100% | +$937 |
| 2017 | rank>33 | 8 | 100% | +$3,163 |
| 2018 | rank>33 | 1 | 0% | **−$3,355** |
| 2019 | none | 7 | 100% | +$1,929 |
| 2020 | none | 9 | 78% | −$599 |
| 2021 | none | 6 | 100% | +$619 |
| 2022 | none | 6 | 83% | −$61 |
| 2023 | none | 17 | 88% | +$5,452 |

**OOS filtered: n81, PF 2.13, +$11,741 · OOS unfiltered (2014+): n87, PF 2.24, +$12,948.**
The filter UNDERPERFORMS no-filter out-of-sample.

## 5. Why it works / fails

The STMR trade is a **mean-reversion timing play expressed in options**, not a theta
play. The SMA5 exit captures the bounce and leaves before the next leg down; every
management rule that overrides it degrades the trade in a diagnosable way:

- **TP50** exits winners before the bounce completes AND leaves losers unmanaged to
  expiry — it keeps the worst of both worlds.
- **Price stops** trigger during the drawdown that *precedes* the bounce being traded —
  they systematically sell the local bottom (win rate collapses 84%→58%).
- **Hold-to-expiry** re-exposes the position for ~2 weeks after the bounce is done;
  the tail events land in that window (maxDD quadruples to −$27.7K).
- **VIX filters** mostly re-time the same trades and, per fold, latch onto whatever the
  last 4 years rewarded; 2018's single-trade disaster shows the failure mode. The
  "elevated-but-falling IV" folk prior is unsupported (n≤13 buckets); if anything the
  low-VIX tercile is cleanest — consistent with mean-reversion working best in orderly
  regimes.

## 6. Recommendation

**Trade the BPS exactly as specified: enter on the causal 15:59 STMR signal, exit on the
first 15:59 spot > SMA5, otherwise settle. NO price stops, NO profit targets, NO expiry
holds, NO VIX filter.** The defined-risk structure (width − credit) is the only stop.
Forward-test live on the paper pipeline (running since 2026-07-14).

## 7. Caveats

- Daily-close signal set (research view); the *executable* causal-15:59 set differs on
  ~13% of signals (see S70) — rankings should transfer, absolute totals may not.
- EOD marks understate intraday mark extremes; stop rules were evaluated on EOD closes,
  which if anything *flatters* stop rules (intraday stops would trigger more often).
- 2010–2023 window contains only two major vol events; expiry-hold tail risk is likely
  *understated*.
- Fees modeled at $1.30/contract; live SPX all-in is similar but verify vs IB statements.

## 8. Reproduce

```
.venv/Scripts/python.exe scripts/mr_bps_exit_rules.py     # 4.1
.venv/Scripts/python.exe scripts/mr_bps_regime_wf.py      # 4.2 / 4.3
```
Data: `data/optionsdx/*.txt`, `data/ES_stoch_daily.csv`, `data/vix_daily.csv`.
Trade files: `data/options_sim/bps_regime_trades.csv`.
