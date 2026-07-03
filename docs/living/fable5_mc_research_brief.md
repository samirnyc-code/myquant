# Fable 5 Research Brief — MC Signal Edge Discovery
**For:** Fable 5 autonomous research agent  
**Date:** 2026-07-04  
**Repo:** `c:\Users\Admin\myquant\`  
**Python env:** `.venv\Scripts\python.exe`

---

## Mission

You are an autonomous quant researcher. Find conditions under which ES MicroChannel (MC) signals produce statistically significant positive expectancy beyond the already-confirmed baseline. Use everything available: price structure, volume, VWAP, value area, auction market theory, stochastic, market structure, day type, books on disk — whatever makes sense. Build features. Run simulations. Iterate. Dig.

**You succeed when** you find at least one filter or combination where:
- n ≥ 100 trades
- E[PnL/R] CI lower bound > 0 at 1R or 2R
- Results hold across at least 4 of 6 years (2021–2026)
- The filter is fully causal (no future data leaked in)

**The baseline to beat:**
```
All MC signals @ 1R: n=5,540  +0.039R  CI [+0.016, +0.062]  WR=52%  $253K net
Longs only    @ 1R: n=2,959  +0.054R  CI [+0.023, +0.086]  WR=53%  $181K net
```
The MC signals already have edge — your job is to isolate WHEN it concentrates.

---

## What Has Already Been Tried — Do Not Repeat, Build On It

### Stochastic (%K/%D) — results known, move past
- K level bins: no lift on MC, all flat or negative
- K slope (K > K_lag1): no lift on MC signals
- ZoneSignal (OS/OB reversal): negative
- K lead-in velocity: negative

### ORB (Opening Range Breakout) — causal version is weak
- ORB agree + after break (CAUSAL only): +0.050R, n=2,546 — marginal lift over baseline
- **Warning:** "ORB agree" without the after-break constraint has lookahead bias (uses end-of-day ORB direction to filter signals that fired before the break). The causal version (signal fires AFTER OR break in direction of break) is real but small.

### What is NOT known yet (your territory)
Everything below is genuinely unexplored on MC signals. This is your research space.

---

## Data Available

### 1. MC Signal File
```
C:\Users\Admin\Desktop\MyMicroChannel Signal Export - ES SEP26 - 5 Minute from 02.07.2026 - 1850 Days.txt
```
Parse with:
```python
import sys; sys.path.insert(0, r'c:\Users\Admin\myquant')
from scripts.revft_stoch_study import parse_signals
from pathlib import Path
mc = parse_signals(Path(r'C:\Users\Admin\Desktop\MyMicroChannel Signal Export - ES SEP26 - 5 Minute from 02.07.2026 - 1850 Days.txt'))
# columns: DateTime (bar close CT), Direction, SignalType (CC1-CC5), SignalPrice, StopPrice
# 5,640 signals 2021–2026
```

### 2. ES 5M Continuous Bars (OHLCV)
```python
import pandas as pd
bars = pd.read_parquet(r'c:\Users\Admin\myquant\data\bars\_continuous.parquet').drop(columns=['Contract'], errors='ignore')
# columns: DateTime (bar close CT), Open, High, Low, Close, Volume
# ~103K bars, 2021–2026
```

### 3. Tick Data (per day)
```python
import massive
ticks = massive.load_continuous_ticks(date)  # date = datetime.date object
# Returns DataFrame: DateTime, Price, Volume  |  ~1,265 days available
```

### 4. Stochastic CSV
```
C:\Users\Admin\Desktop\NT Code Versions\ChartMarker_Files\Data\Stoch\ES_stoch.csv
```
Load and join with:
```python
from scripts.revft_stoch_study import load_stoch, join_stoch
stoch = load_stoch(Path(r'C:\Users\Admin\Desktop\NT Code Versions\ChartMarker_Files\Data\Stoch\ES_stoch.csv'))
mc = join_stoch(mc, stoch)
# Adds: STO_K, STO_D, STO_Zone (OS/mid/OB), STO_KslopeUp, STO_lead_in (K-K_lag3), STO_ZoneSignal
```

### 5. Reference Books (readable with pypdf — installed)
```
C:\Users\Admin\Desktop\MOM.pdf                  — Dalton: Mind Over Markets (350pp)
C:\Users\Admin\Desktop\James_Dalton-Markets_in_Profile-EN (2).pdf  — Dalton: Markets in Profile (225pp)
C:\Users\Admin\Desktop\steidlmayer-on-markets-trading-with-market-profiletm-2nbsped-0471215562_compress.pdf  — Steidlmayer on Markets (239pp)
C:\Users\Admin\Desktop\VOLUME-PROFILE-The-insiders-guide-to-trading-v-1.2.pdf  — Volume Profile Insider's Guide (194pp)
```
Use `pypdf.PdfReader` to read relevant chapters if you want to ground a hypothesis in theory. Dalton Ch.2 (pp28-37): day type definitions. Steidlmayer: TPO profiles, market-generated information.

---

## Pre-Built Feature Library — Use These First

### A. `tag_signals()` — The Most Important Function
`indicators.tag_signals(signals, bars)` attaches 20+ causal features to every signal row in a single call. **Start here.**

```python
from indicators import tag_signals
mc_tagged = tag_signals(mc, bars)
```

**Features added by `tag_signals()`:**

| Column | What it is |
|--------|-----------|
| `VWAP` | Developing session VWAP at signal bar |
| `VWAP_sigma` | Volume-weighted σ of typical price from VWAP |
| `VWAP_dev` | Signed σ-distance of Close from VWAP (NaN for first 3 bars) |
| `EMA_20` | Developing 20-bar EMA on 5M Close |
| `ER_2/6/12/24` | Kaufman Efficiency Ratio at 30m/60m/120m/2hr lookbacks |
| `OOD` | Open of Day |
| `HOY / LOY` | Prior session High / Low |
| `OR60_High/Low` | 60-min Opening Range (frozen after bar 12) |
| `prior_ATR` | Prior day's ATR(14) |
| `prior_ATR_pct` | Prior ATR as % of price (percentile rank) |
| `prior_ADX` | Prior day's ADX(14) |
| `prior_ER` | Prior day's Kaufman ER (trend/chop) |
| `prior_RangeATR` | Prior day's range / ATR |
| `balance_state` | True = opened inside prior range AND still rotating inside it at signal time |
| `prior_inside_day` | Prior day's range fell inside day-before's range (compression) |
| `prior_adr_ext` | Prior day was a trend day (range > 1.6×ADR) |
| `dev_High/dev_Low` | Developing session high/low strictly before the signal bar |
| `vaD_POC/VAH/VAL` | Prior session's POC, VAH, VAL (Value Area) |
| `vaD_loc` | Signal price location relative to prior session VA |
| `vaW_POC/VAH/VAL` | Prior week's value area levels |
| `vaM_POC/VAH/VAL` | Prior month's value area levels |
| `structural_trend` | Swing-based market structure: uptrend / downtrend / ranging |
| `active_floor` | Most recent structural support/resistance level |
| `is_deep_pullback` | Signal is a deep pullback within the structural trend |
| `mss_event` | Market structure shift just occurred at signal bar |

### B. `build_session_features()` — Dalton Day Types + Auction Context

```python
from auction_features import build_session_features
sess = build_session_features(bars)
# One row per session. Columns include:
#   IB_High, IB_Low, IB_width        — Initial Balance (first 60 min)
#   ext_up, ext_dn                    — range extension beyond IB each side
#   first_break                       — 'up' / 'down' / 'none' — which side of IB broke first
#   CLV                               — Close Location Value (0=at low, 1=at high)
#   OLV                               — Open Location Value
#   POC, VAH, VAL, VA_width           — session value area
#   POC_loc                           — POC position in day's range
#   VA_skew                           — POC above/below mid-range (+p-shaped / -b-shaped)
#   bimodal                           — True = double-distribution day (Dalton's DD Trend)
#   DR_pct                            — today's range / ADR (trend day > 160%)
#   prior_High/Low/Close/POC/VAH/VAL  — prior session levels (causal)
#   gap, gap_adr, gap_dir             — overnight gap size and direction
#   open_vs_prior_range               — open 'above' / 'below' / 'inside' prior range
#   open_vs_prior_va                  — open 'above' / 'below' / 'inside' prior VA
#   day_type                          — Dalton label: Normal / NormalVariation / Trend / DoubleDist / Nontrend / Neutral
```

Join session features to signals (use prior session — shift forward 1):
```python
sess_prev = sess.copy()
sess_prev['Date'] = sess_prev['Date'] + pd.Timedelta(days=1)  # shift to next day

mc['_date'] = mc['DateTime'].dt.normalize()
mc = mc.merge(sess_prev.add_prefix('prev_'), left_on='_date', right_on='prev_Date', how='left')
```
Or join today's developing features via `tag_signals` (already in there) and use `build_session_features` for completed-session context (prior day).

### C. VWAP Bands Directly
```python
from indicators import session_vwap_bands
vwap_df = session_vwap_bands(bars)
# columns: DateTime, VWAP, VWAP_sigma, VWAP_dev
# Merge as-of onto signals. VWAP_dev = how many σ above/below VWAP the signal fired.
```

### D. Value Areas Per Period
```python
from indicators import value_areas
# Per session, week, month, quarter, year
va_daily = value_areas(bars, period='session')    # POC/VAH/VAL per day
va_weekly = value_areas(bars, period='weekly')
va_monthly = value_areas(bars, period='monthly')
```

---

## Simulation Engine

```python
from simulation_engine import simulate_trades
import massive
import numpy as np

BASE = dict(
    entry_slip=1, exit_slip=1, stop_offset=1, tick_value=12.5,
    contracts=1, contracts_t1=1, contracts_t2=1, commission=4.36,
    ratchet_r=0.0, pb_round='nearest',
    multileg=False, threeleg=False, overrides=None,
)

# Pre-load ticks (do once):
dates = sorted(mc['DateTime'].dt.date.unique())
ticks_by_date = {d: massive.load_continuous_ticks(d) for d in dates}
ticks_by_date = {d: t for d, t in ticks_by_date.items() if not t.empty}
bars_by_date  = {d: g.reset_index(drop=True) for d, g in bars.groupby(bars['DateTime'].dt.date)}

def sim(label, sigs, target_r=1.0, min_n=40):
    if len(sigs) < min_n:
        print(f'  {label}: n={len(sigs)} skipped'); return
    res = simulate_trades(
        signals=sigs, ticks_by_date=ticks_by_date,
        bars_by_date=bars_by_date, target_r=target_r, **BASE,
    )
    filled = res['Filled'] == True
    pnl  = res.loc[filled, 'NetPnL'].values
    risk = res.loc[filled, 'RiskDollar'].values
    rr   = pnl / risk; rr = rr[np.isfinite(rr)]
    n = len(rr); er = rr.mean()
    rci = 1.96 * rr.std(ddof=1) / np.sqrt(n)
    lo, hi = er - rci, er + rci
    wr = 100 * (pnl > 0).mean()
    net = pnl.sum()
    flag = ' *** CI>0' if lo > 0 else (' *** CI<0' if hi < 0 else '')
    yr = sigs['DateTime'].dt.year
    yrs = '  '.join(f"{y}:${pnl[yr.values==y].sum():+,.0f}" for y in sorted(yr.unique()))
    print(f'  {label:60s}  n={n:4d}  {er:+.3f}R [{lo:+.3f},{hi:+.3f}]  WR={wr:.0f}%  ${net:+,.0f}{flag}')
    print(f'    years: {yrs}')
```

**Entry mechanics (important):** Signal `DateTime` = bar close. Simulation enters on the NEXT bar's open + 1 tick slippage. Stop = signal's `StopPrice` ± 1 tick. Target = entry ± stop_distance × R.

---

## Research Directions — Prioritized

### Tier 1 — Most Likely to Have Edge (try these first)

**1. Price location relative to VWAP**
- Where is the signal relative to developing VWAP? `VWAP_dev` in σ units (already in `tag_signals`)
- Hypothesis: MC Longs fired below VWAP (VWAP_dev < 0) may be stronger (price seeking value) or weaker (no momentum) — test both
- Split by: VWAP_dev quintiles, then by direction × signal type

**2. Value area location (auction theory)**
- Prior session VAH/VAL/POC is the market's "fair value" memory
- Key Dalton insight: trades initiated INSIDE the value area tend to rotate; trades initiated OUTSIDE tend to trend
- Test: signal price vs `vaD_VAH`/`vaD_VAL` — inside VA vs above/below VA
- Also: signal vs `vaW_VAH`/`vaW_VAL` (weekly VA) — bigger structural context
- Signal price location: `(SignalPrice - vaD_VAL) / (vaD_VAH - vaD_VAL)` → 0=at VAL, 1=at VAH, <0=below VA, >1=above VA

**3. Dalton day type as context**
- `build_session_features()` gives `day_type` for each session: Normal / NormalVariation / Trend / DoubleDist / Nontrend / Neutral
- Hypothesis: MC signals on Trend days should work better (momentum context); Nontrend/Neutral days may be choppy
- Important: use PRIOR session's day type (shift by 1) as today's context predictor
- Also test: does today's IB width predict MC signal quality? (wide IB = early trend declaration)

**4. Opening Range and IB structure**
- `OR60_High/Low` (first 60 min) from `tag_signals`
- `first_break` from session features: which side of IB broke first
- Test: MC Longs after IB breaks UP (causal — signal fires after the break)
- Also: distance of signal price from OR60_High/Low in points / ATR units

**5. Market structure state**
- `structural_trend` from `tag_signals`: uptrend / downtrend / ranging
- `mss_event`: market structure shift just happened
- Hypothesis: MC Long signals in a structural uptrend should win more; ranging = noise
- Test: structural_trend × direction interaction

**6. ER (Efficiency Ratio) at signal time**
- `ER_6` (60-min ER) and `ER_12` (120-min ER) from `tag_signals`
- ER near 1.0 = strongly trending market; ER near 0 = choppy
- Known from prior research (S35): CC2/CC5 reward high ER; CC4 is anti-ER; CC3 flat
- Fresh cut: ER at signal time (intraday), not prior-day ER

**7. Stop size (risk in points) as quality signal**
- `StopPrice` distance from `SignalPrice` — absolute points of risk
- Small stops = precise MC signal (tight range); large stops = noisy
- Test: stop size / ATR ratio — tight stops (< 0.3 ATR) vs wide stops (> 0.8 ATR)
- Hypothesis: tight stops indicate high-confidence signal (cleaner microstructure)

### Tier 2 — Auction Theory Deep Cuts

**8. Prior session VA migration**
- Did the prior session's VA expand, contract, or migrate vs the day before?
- VA migrating up = bullish auction; migrating down = bearish
- Derive: `(today_VAL - prior_VAL)` and `(today_VAH - prior_VAH)` — both positive = upward migration

**9. Open location vs prior session context**
- `open_vs_prior_range`: open above/below/inside prior range
- `open_vs_prior_va`: open above/below/inside prior value area
- Dalton: open above VA + strong IB + IB extension up = institutional buying day
- Test: does open location predict which way MC signals work?

**10. Gap fill behavior**
- `gap_dir` and `gap_adr` — overnight gap size
- After a large gap up: does the first MC Short (fade the gap) or Long (follow gap) win?
- Gap fill attempt in progress at signal time: `SignalPrice` heading back toward prior close

**11. Session volume context**
- Cumulative volume at signal time vs average volume at same time of day
- High-volume environment = institutional participation = more likely to follow through
- Low-volume = fades more common

**12. POC rejection (Volume Profile)**
- Signal fires near prior session POC = high-volume node = expect rejection / bounce
- Signal fires near LVN (low volume node) = expect fast price movement through
- LVN detection: thin spots in the volume-at-price distribution between VAL and VAH
- Compute from `value_areas()` output

### Tier 3 — Signal-Type Specific Cuts

**13. CC-type specific filters** — do not treat as one population
- CC5: known strongest performer from prior research (S23)
- CC4: known problematic from prior research — may drag down averages
- Apply every filter above to CC2/CC3/CC5 independently; CC4 may need exclusion
- Also: CC type tells you about the microstructure (channel length, breakout strength) — a CC5 signal is a longer sustained push than CC1

**14. Consecutive same-direction MC signals**
- N signals in the same direction within last M bars = cluster confirmation
- Hypothesis: a 3rd or 4th consecutive Long MC signal in a day has more momentum backing it
- Already suggested in handoff backlog as "consecutive-cluster gate"

**15. Stop size relative to IB width**
- If today's IB is narrow and the stop is small, it's a precise breakout signal
- IB width / ADR × stop / ATR — two-dimensional tightness measure

---

## Causal Constraint — Critical

**Every feature must be computable from data available AT OR BEFORE the signal bar's close.**

- Signal `DateTime` = bar close. Features must use data up to and including this bar.
- Prior-session features (VA, day type, gap): all causal — known at market open
- Developing session features (VWAP, ER, developing range): causal via `tag_signals` — it uses `_causal_at_signal_bar()` internally
- IB features: causal only after bar 12 (09:30 CT). For signals before 09:30, IB is still forming.
- ORB / IB break direction: causal only AFTER the break. Do not use `first_break` from the session features to filter pre-break signals — that's lookahead.

**Test for lookahead:** Verify that your best filter produces similar performance in 2021–2022 as in 2023–2026. A lookahead bug typically shows up as implausibly uniform performance across all years.

---

## Prior Research Notes to Read (PDF, in repo)

These capture prior findings on MC signals — read before forming hypotheses to avoid reinventing:

```
C:\Users\Admin\Documents\MC_Setup_Research_Notes\0001_pb_scalein_mc.pdf    — PB scale-in; 1R is right target; 13CT decay
C:\Users\Admin\Documents\MC_Setup_Research_Notes\0003_keystone_ib_edge_fade.pdf  — IB-edge fade attempt; negative
C:\Users\Admin\Documents\MC_Setup_Research_Notes\0006_quantsystems_breakouts_blueprint.pdf  — QS breakout reproduction
```

Key locked decisions from this codebase (do not re-test these, they are settled):
- **1R is the correct target** — BE/trail/scale-out all fail; flat 1R wins
- **CC4 is problematic** — poor performer historically; exclude or test separately  
- **Afternoon fade (after 13:00 CT)** — edge decays after 13:00, especially on scale-in trades

---

## Output

For each filter:
```
[Filter description]   n=XXXX  +X.XXXr [lo, hi]  WR=XX%  $XXX,XXX  [CI>0 / CI<0 / straddles]
  years: 2021:$XX  2022:$XX  2023:$XX  2024:$XX  2025:$XX  2026:$XX
```

At the end, write your findings to:
```
c:\Users\Admin\myquant\docs\living\fable5_mc_findings.md
```

Structure: What worked (CI>0, year-stable) → What was flat → What was negative → Your single best recommendation with the backing evidence → Open hypotheses you formed but couldn't fully test.

---

## Quick Start

```python
import sys, os
sys.path.insert(0, r'c:\Users\Admin\myquant')
os.environ['PYTHONIOENCODING'] = 'utf-8'

from pathlib import Path
import numpy as np
import pandas as pd
from simulation_engine import simulate_trades
import massive
from scripts.revft_stoch_study import parse_signals, load_stoch, join_stoch
from indicators import tag_signals, session_vwap_bands, value_areas
from auction_features import build_session_features

_MC   = Path(r'C:\Users\Admin\Desktop\MyMicroChannel Signal Export - ES SEP26 - 5 Minute from 02.07.2026 - 1850 Days.txt')
_BAR  = Path(r'c:\Users\Admin\myquant\data\bars\_continuous.parquet')
_STO  = Path(r'C:\Users\Admin\Desktop\NT Code Versions\ChartMarker_Files\Data\Stoch\ES_stoch.csv')

mc   = parse_signals(_MC)
bars = pd.read_parquet(_BAR).drop(columns=['Contract'], errors='ignore')

# Attach all pre-built features
mc = tag_signals(mc, bars)

# Attach stochastic
stoch = load_stoch(_STO)
mc = join_stoch(mc, stoch)

# Build session-level auction features (for prior-day context)
sess = build_session_features(bars)

# Load tick data for simulation
dates = sorted(mc['DateTime'].dt.date.unique())
ticks_by_date = {d: massive.load_continuous_ticks(d) for d in dates}
ticks_by_date = {d: t for d, t in ticks_by_date.items() if not t.empty}
bars_by_date  = {d: g.reset_index(drop=True) for d, g in bars.groupby(bars['DateTime'].dt.date)}

print(f'MC signals: {len(mc):,}')
print(f'Features: {list(mc.columns)}')
print(f'Tick days: {len(ticks_by_date)}')
```
