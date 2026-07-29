# Halsey Measured-Move — RULEBOOK (synthesis of all 16 chapters)

Source: David Halsey, *Trading the Measured Move* (Wiley, 2014). Per-chapter
extractions in `ch01..ch16_*.md`. This file consolidates the method into a
testable spec. **Convention:** an UP leg runs from swing low `L` to swing high
`H`; range `R = H − L`. Down leg is the mirror.

---

## 1. Measured-move geometry (the core, Ch 2)

Draw a Fib on a swing leg. For an UP leg (drawn low→high):

| Level | Formula (up leg) | Role |
|---|---|---|
| 100% (start) | `L` | swing low = origin |
| 61.8% | `L + 0.382·R` = `H − 0.618·R` | **FAILURE** — breach kills the MM |
| 50% (HWB) | `L + 0.500·R` | **entry** (half-way-back / continuation) |
| 38.2% | `L + 0.618·R` | Distance-Formula exit (see §5) |
| 0% (end) | `H` | swing high |
| −23.6% = "123%" | `H + 0.236·R` | **TARGET** (also seeds next swing) |

Down leg: `100%=H`, `61.8%=H−0.382·R`, `50%=H−0.5·R`, `0%=L`, `target=L−0.236·R`.
Note: Halsey pronounces the negative Fib levels as positives ("−23.6%" = "123%").

---

## 2. What defines a swing (Ch 2–3)

- **Seed swing = discretionary** — the "significant high-low that jumps off the
  page" on the chosen time frame. THE ONLY non-mechanical step.
- **After the seed, mechanical & recursive:** new peak = prior MM's retracement
  high; new trough = prior MM's 123% target. Series repeats indefinitely.
- **Leg confirmation:** a leg/trend is confirmed real when the **opposing MM's
  61.8% level breaks** (= "trend break").
- **Codify:** replace the seed with a ZigZag/ATR/fractal swing detector; its
  threshold is the one parameter to tune/validate in WFA.

---

## 3. The three setups (Ch 6)

Market order of a trend: **traditionals → extensions → straight up; a 61.8%
failure flips the trend.**

### 3a. Traditional 50% MM
- **Anchor:** initial trailed swing (long: low→high; short: high→low).
- **Entry:** LIMIT at 50% (HWB). Front-run per §4.
- **Target:** 123% (`H + 0.236·R` long).
- **Stop:** not numeric in Ch6 — structural = 61.8% breach. Use §4 tick stops.
- **Series:** entry→target→re-anchor at last low→next pullback, repeat.
- **Filter:** watch "participation"; a larger-time-frame 123% target can break a
  smaller series ("traditionals not to trust").

### 3b. Extension 50% MM (bull/bear flags)
- **Trigger:** price makes new highs PAST a traditional's 123% target WITHOUT
  pulling back → switch from traditional to extension.
- **Anchor:** top of last retracement / previous highs; a series re-uses ONE
  fixed anchor.
- **Entry:** LIMIT at the extension's 50% (often = the prior 123% target level).
- **Target:** 123% of the extension swing.
- **HARD GATE:** the **FIRST extension off a new anchor is observe-only** (no
  limit) — it can fail; only trade subsequent extensions once the first is seen.

### 3c. 61.8% Failure (trend-change signal, not a limit setup)
- **Mechanic:** price fails 2nd test of the 50%, pierces 61.8% → series broken →
  new trend opposite direction.
- **Trade:** buy/sell the **first pullback after the trend break** (Entry #3).
- **Doubles as an EXIT** (a 61.8% failure is a valid profit target for a trend
  trade you're already in).
- **HARD GATE:** if the failure turns into a **retest of the prior high/low
  (double top/bottom), DO NOT trust the next MM** — skip.

---

## 4. Entry strategies — fixed order every MM (Ch 8)

Progression, always in this order: **First Test → Front-Run 2nd Test → Trend
Break & Next MM.** All entries use LIMIT orders front-run in front of the 50%.

**Per-instrument ticks (Fig 8.1):**

| Instr | Init stop | Front-run | 1st target | Adj stop (after 1st tgt) |
|---|---|---|---|---|
| /ES | −6 | +2 | +2 | −4 |
| /YM,/TF,/NQ,/GC | −12 | +4 | +6 | −6 |
| /6A,/6B,/6C,/6E,/6J | −12 | +4 | +6 | −6 |
| /ZB | −8 | +4 | +4 | −4 |

1. **First Test** — 1st pullback into 50%. Highest prob/volume. ES: limit +2t in
   front, stop −6, 1st target +2, then move stop −6→−4 (reduced-risk).
   - If NOT filled → pull the order immediately; never chase; if taken out at
     breakeven → stop and wait for next entry.
2. **Front-Run 2nd Test** — riskiest, best R:R. Front-run the first-test price by
   2t, stop 2t beyond the participation low/high (**4-tick total**), **all-in/
   all-out, smaller size** (not a reduced-risk trade).
3. **Trend Break & Next MM** — break of the **opposing MM** confirms (a) the
   trend + new pullback and (b) the profit target. Trade the next MM with
   **first-test specs** (Fig 8.1).

Shorts mirror longs. "Fade the first test, go with the second."

---

## 5. Position management / taking profit (Ch 5, 13, 14)

**Rule:** each MM has a unique entry+target; **take profit on the time frame you
entered.** Four methods:

1. **Distance Formula** = `|50% − 38.2%|` = `0.118·R`. Fast scalp / first target.
   Best: Fri PM, Mon AM, doldrums 11:30–13:30 ET, choppy or very volatile days.
2. **Trail the series** — trail the **61.8%** through traditional→extension MMs;
   when a 61.8% fails, take profit. Best: trending Tue–Thu.
3. **Confirmation of trend** — take partial when an opposing MM breaks (also
   confirms target + gives next-MM add).
4. **−23% (123%) target** — the "exact reversal point"; for intraday swings too
   big for EOD.

**Execution discipline (Ch 5 "90% factor" / "Job One"):** trade ≥2 contracts;
sell half at 1st target (ES +2t) and move stop so max loss = 0 → a **free
trade**. Hard caps: **≤1% account risk/trade**, **≥2:1 reward:risk**. Single
contract → close at target. "No trader has gone broke taking profit."

---

## 6. Gap fills (Ch 12) — ES playbook

- **Gap fill** = price reaches prior day's **4 pm cash close** during RTH.
- **±10-pt gap-and-go level** = prior close ± 10 (arithmetic).
- **Filter (historical fill rate, 2010–12):** open **<10 pt from fill → ~77–79%**
  fill; open **>10 pt (professional gap-and-go) → ~9–26%** (let it run). Avg ~66–70%.
- **Workflow (all four YES to trade):** (1) NOT options-ex / rollover Thu / 1st
  day of month or quarter; (2) time within **08:00–09:30 ET**; (3) price inside
  the 10-pt band; (4) a large S/R or micro/next-MM points toward the fill.
- **Entry origin:** 50% retrace, daily pivot, or the 10-pt level; use the 3
  entry strategies (2nd-test most common); trade toward the fill; reduced-risk.
- **Broken gap (opened <10 but stopped out):** likely fills later — trade the
  series of MMs until trend breaks (new high/low tick OR 61.8% pierce), re-enter
  toward fill. Opened >10 → expect run into close, no fill.
- **Best entry window:** 08:00–08:30 ET.

---

## 7. Session & timing rules (Ch 9, 11, 16)

- **US sessions:** 08:00–11:30 ET and 13:30–16:00 ET only.
- **No-trade zones:** 09:30–10:00 ET (open); **no new trades after 15:45 ET**.
- **10:00 ET** volume push → most entries; often the day's high/low; lasts ~90m.
- **Doldrums 11:30–13:30 ET** → distance-formula scalps only.
- **Half size** on Mon, Fri, options-ex, rollover Thu, post-rollover Fri (or don't
  trade). Trend days Tue–Thu.
- **NYSE tick timing:** in MM-long series buy **low ticks**; in MM-short series
  sell **high ticks**. Tick extremes ±1000 = reversal risk.
- **EUR/USD (wealth trades):** trade 03:00–11:30 ET; after 11:30 goes silent
  (~10-pip range).
- **Daily pivot (DP)** = `(H+L+C)/3` (prior session) — attractor/target.
- **Gap def:** professional gap = open ≥10 pts from prior close; amateur <10
  (amateurs fill within the 1st hour).

---

## 8. Ch 16 trading-plan rules (31, condensed)

**General (10):** never add money · never trade without a stop · target for every
trade · enter at MMs with the trend · use limit orders · **≤1% risk/trade** ·
don't pick tops/bottoms — wait for the MM failure at S/R · don't rush undefined
trades · focus on rules not money · half-size Mon/Fri/opt-ex/rollover.

**Gap (8):** enter 08:00–08:30 EST · ES gap **≥5 and ≤10 pts** else pass · pro
gap no-fill → trade first signal WITH the gap direction · record unfilled gaps ·
stay in till fill or stop · avoid opt-ex Fri / rollover Thu / 1st day of month ·
narrow-range day then gap > prior range or outside prior H/L → stay away · ES
leads (take profit on YM/TF/NQ when ES fills).

**NYSE (9):** trade only **15-min 50% setups** (5–7/day) · strong breadth → longs
only · weak breadth → shorts only · use NYSE tick to time · confirm 2nd test via
time & sales · Nasdaq Bank confirmation · two sessions only · no new trades after
15:45 · EOD review.

**Euro (4):** income trade (EOD) vs wealth trade (week+) · identify & trade the
larger-TF trend (path of least resistance) · rank setups by R:R · trade
03:00–11:30 ET.

**Setup priority:** Daily (≈1/wk, spot 24–36h ahead, −23% target) > 15-min (3–7/
day) > Micro (overtrading risk). **Journal everything.**

---

## 9. What to build for WFA (codifiable core)

Deterministic once the seed swing is fixed:
1. **Seed-swing detector** (ZigZag/ATR/fractal) — the one tunable knob.
2. **MM level engine** — 61.8/50/38.2/0/123% off any leg; series chaining.
3. **Setup classifier** — traditional vs extension vs 61.8%-failure per the §3
   triggers (incl. first-extension observe-only, double-top skip).
4. **Entry model** — first-test / 2nd-test / trend-break with ES tick table (§4).
5. **Exit model** — distance-formula / trail-61.8 / −23% target (§5).
6. **Session/calendar filter** (§7) + **gap-fill module** (§6) as standalone book.
7. **Risk** — 1% sizing, 2:1 floor, free-trade bracket.

**Discretionary (needs proxy or manual flag):** seed selection, "participation"/
time-&-sales, breadth/Nasdaq-Bank bias, "trust this MM?" judgments,
double-top/retest recognition, choosing among the 4 exit methods.

Next: encode §3–§5 as a machine-readable config and backtest on ES with the
seed-detector parameter swept.
