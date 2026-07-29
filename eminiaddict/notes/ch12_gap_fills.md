# Ch 12 — Profiting from Gap Fills

## Summary
This chapter is a complete playbook for trading the gap fill, focused on the E-mini S&P 500 (ES). A gap is the distance between where the market closed (the previous day's 4 p.m. cash close) and where it reopens the next morning after nearly-24-hour futures trading. A gap is considered **filled only if price reaches the previous day's close during trading hours**. The core edge is that ES gaps fill ~66–70% of the time on average, but a simple filter — whether the open is **less than 10 points** from the fill level vs. **greater than 10 points** — sharply separates high-probability fills (~77–79%) from low-probability "professional gap-and-go" days (~8.8–26.4%). The chapter covers: the three gap-fill scenario types, days/conditions to avoid, the exact gap-fill statistics table (Fig 12.1), the tools (thinkorswim study drawing the 4 p.m. close + the ±10-pt levels), a traditional vs. conservative entry approach, a morning mental-checklist workflow/filter, three entry origination levels, three ranked entry strategies, and what to do when a gap that opened *within* the 10-pt band breaks/doesn't fill (trade a series of MMs until trend fails, then re-enter toward the gap fill). Ties to the measured-move (MM) machinery from earlier chapters (50% retracements, series of micros, 61.8% pierce).

## Key concepts & definitions
- **Gap**: distance between the prior-day close and the next-day open, created by after-hours (nearly 24 hr) futures trading during the week.
- **Gap fill (definition)**: a gap is only considered filled if price **reaches the previous day's close during trading hours**.
- **Gap-fill level**: the previous day's **4 p.m. close** price (the target line; drawn red in figures).
- **Instruments with the most consistent gap fills**: futures tied to main indexes — **E-mini S&P 500 (ES)**, **E-mini Dow (YM)**, **E-mini Russell 2000 (TF)**, **E-mini Nasdaq 100 (NQ)**. **ES has the most consistent price action** and the most statistical info on gap-fill frequency.
- **Premarket entry gap fill** (a.k.a. **less-than-10-point gap fill**): the standard way the market fills its gap in the morning. High-probability.
- **Premarket runaway gap-and-go** (a.k.a. **greater-than-10-point gap**, a.k.a. **professional gap-and-go**): market gaps **more than 10 points** above (or below) its cash close at the opening bell; tends to run away from the fill (rally all day if gap-up; sell off all day if gap-down). Low-probability of same-day fill.
- **10-point gap-and-go level**: the ±10-point line above/below the gap-fill level; established as a resistance/support level and thus usable as an entry into the gap fill.
- **No-trade zone**: consistently dangerous times; entering has low success likelihood. The named one is **9:30–10:00 a.m. ET** ("the first hour"), when overnight action whips traders, forcing market-order exits → stop runs / shakeouts.
- **Safe entry window**: **8:00 a.m. – 9:30 a.m. ET** (a 90-minute window) to enter in the direction of the gap fill. After 9:30 a.m., a gap-fill trade should only take profit or manage an existing position.
- **Options max pain**: on options-expiration days the underlying tends to move toward the point of maximum loss for option buyers, causing the market to gap and run away from its fill.
- **Contract rollover**: futures roll one contract to the next each **Thursday**; expiration is the **third Friday** of March, June, September (quarterly).
- **Mutual fund Monday**: first trading day of a new quarter is historically a strong bullish/gap-up day.
- **MM (measured move)**: the retracement/target framework from earlier chapters used to time conservative entries (50% retracement, micros, 61.8% levels, −23% target).

## Rules / setups / mechanics

### The three gap-fill scenario types
1. **Premarket entry gap fill** (less-than-10-point): standard morning fill. This is the tradable, high-probability case.
2. **Premarket runaway gap-and-go** (greater-than-10-point / professional gap-and-go): gaps >10 pts and runs away from the fill; do **not** fight it.
3. **The rare "broken" gap fill** (covered under "When Gaps Don't Fill"): market opens **within** the 10-pt band, gives a clean premarket entry, but a chain reaction of stops (often in the 9:30–10 a.m. no-trade zone) takes out the entry before the fill. Because it opened within 10 pts, it still has potential to fill **later in the day**.

### Gap fills to AVOID (lower probability of filling)
- **Options Expiration Fridays** — max-pain behavior makes the market gap and run away.
- **Rollover Thursday and the day after** — contract rollover (quarterly expiration = 3rd Friday of Mar/Jun/Sep).
- **First trading day of the new quarter** — "mutual fund Monday," historically strong bullish gap-up; avoid the fill.
- **10-point gap-and-go levels** — opening ≥10 pts above/below prior close = professional gap-and-go; very low expectancy of same-day fill.
- **No-trade zone 9:30–10:00 a.m. ET** — do not enter here.
- (Workflow also excludes the **first trading day of a new month**, see checklist.)

### The gap-fill workflow / filter (morning mental checklist)
Answer each in order; if **yes**, proceed to the next; if **no**, do **not** trade the gap:
1. Is it a day **other than** options ex, futures rollover, or the first trading day of a new **month or quarter**?
2. Check the time: are we within the **8:00–9:30 a.m. ET** safe time to trade?
3. Is the market **inside the 10-point gap-fill level**?
4. Has the market traded a **large support or resistance level** that could provide a change in trend or a micro / next MM toward the gap fill?

If **yes to all four**, you have a potential gap fill and an opportunity to enter.

### Entries — where reversals into the gap fill originate (three levels)
1. **A 50 percent retracement** — overnight price often finds a 50% retracement, forming a support/resistance level used to enter toward the fill (Fig 12.3).
2. **A daily pivot** — the next day's daily pivot acts as support/resistance leading into a fill.
3. **The 10-point gap-and-go level** — well-established as resistance/support; the overnight high or low is frequently the 10-pt mark, usable as an entry.

### Which entry strategy? (three retracement strategies, ranked by importance/priority)
1. **The first test of resistance.**
2. **The second test methodology.** ← **most common entry into the gap fill** (premarket action is technical/efficient; most setups are a retest of an already-traded S/R level).
3. **The series of micros after the trend break.**
Always trade in the direction of the gap-fill level.

### Traditional way vs. Conservative way
- **Traditional trader's way**: enter at the opening bell with a market order, often **no stop**, exit at the gap fill (profit target) or at the close if it doesn't fill. Emulates the old NY/Chicago pit. Described as **"incredibly dangerous"** because the non-fill days are huge pro gap-ups/downs; traders lacked the filtering info.
- **Conservative way**: use MM knowledge + the three retracement entry strategies. If **above** the fill and **within** the 10-pt gap-up-and-go level, look for **resistance or a series of micros** to enter toward the fill. If **below** the fill and **within** the 10-pt gap-down-and-go level, look for **support or a series of micros**. Use **reduced-risk trades**; stay in until the gap fills or the stop is hit. Modern electronic entries allow **much tighter stops** → better risk-reward.

### When gaps don't fill (the "broken" gap fill) — what to do
- Applies when the market opened **within** the 10-pt band, gave a clean premarket entry, then a chain reaction of stops (often in the 9:30–10 a.m. no-trade zone) took out the entry.
- **Key decision fact**: whether the market opened **within or outside** the 10-pt gap-and-go level. If **within**, expect it to **fill its gap later in the day**.
- Since it's not a professional gap-and-go, **trade the series of MMs until the trend fails.** A break in trend gives the first buy/sell signal back toward the gap fill.
- **A break in trend is produced by one of two events:**
  1. **A new high/low tick of the day** produces a reversal.
  2. **The pierce of a 61.8 percent level of the series of MMs.**
- Sequence (Figs 12.4–12.6): morning entry breaks → participants become fuel for the breakout → extension long trades and fails → break in trend → first sell signal drawn as an **MM short** → new MM short gives entry back toward the gap fill → because it opened **within** the 10-pt level, it filled the same day. Had it opened **outside** the 10-pt level, expect a rally into the close (professional gap-and-go day).

### Tools
- A thinkorswim study (Fig 12.2) draws the **4 p.m. close of the previous day** (the gap-fill level) plus the **±10-point gap-and-go levels** above and below. These can be drawn manually: once you know the prior day's 4 p.m. close, the ±10 levels are "just a matter of arithmetic."

## Figures / tables

### FIGURE 12.1 — Gap Fill Statistics (verbatim cells)
Columns: Monday | Tuesday | Wednesday | Thursday | Friday | TOTAL | Filled if Open <10 | Filled if Open >10 | Options Ex | 1st Monthly Trading Day

**2010**
| Row | Mon | Tue | Wed | Thu | Fri | TOTAL | Open <10 | Open >10 | Options Ex | 1st Monthly Trading Day |
|---|---|---|---|---|---|---|---|---|---|---|
| Filled | 33 | 34 | 34 | 34 | 37 | 172 | 161 | 11 | 7 | 4 |
| Occurrences | 47 | 52 | 52 | 51 | 50 | 252 | 207 | 45 | 12 | 12 |
| Percent | 70.2% | 65.4% | 65.4% | 66.7% | 74.0% | 68.3% | 77.8% | 24.4% | 58.3% | 33.3% |

**2011**
| Row | Mon | Tue | Wed | Thu | Fri | TOTAL | Open <10 | Open >10 | Options Ex | 1st Monthly Trading Day |
|---|---|---|---|---|---|---|---|---|---|---|
| Filled | 23 | 34 | 33 | 34 | 31 | 155 | 136 | 19 | 7 | 6 |
| Occurrences | 46 | 52 | 52 | 51 | 51 | 252 | 180 | 72 | 12 | 12 |
| Percent | 50.0% | 65.4% | 63.5% | 66.7% | 60.8% | 61.5% | 75.6% | 26.4% | 58.3% | 50.0% |

**2012**
| Row | Mon | Tue | Wed | Thu | Fri | TOTAL | Open <10 | Open >10 | Options Ex | 1st Monthly Trading Day |
|---|---|---|---|---|---|---|---|---|---|---|
| Filled | 32 | 36 | 40 | 38 | 30 | 176 | 173 | 3 | 7 | 6 |
| Occurrences | 47 | 50 | 51 | 51 | 52 | 251 | 217 | 34 | 12 | 12 |
| Percent | 68.1% | 72.0% | 78.4% | 74.5% | 57.7% | 70.1% | 79.7% | 8.8% | 58.3% | 50.0% |

**2010–2012 (combined)**
| Row | Mon | Tue | Wed | Thu | Fri | TOTAL | Open <10 | Open >10 | Options Ex | 1st Monthly Trading Day |
|---|---|---|---|---|---|---|---|---|---|---|
| Filled | 88 | 104 | 107 | 106 | 98 | 503 | 470 | 33 | 21 | 16 |
| Occurrences | 140 | 154 | 155 | 153 | 153 | 755 | 604 | 151 | 36 | 36 |
| Percent | 62.9% | 67.5% | 69.0% | 69.3% | 64.1% | 66.6% | 773.8% *(sic — printed value; should read ~77.8%)* | 21.9% | 58.3% | 44.4% |

Notes on the table (verbatim claims in the text):
- Average ~**70%** gap fill on any given day (the number traditional gap-fill traders use as their win %).
- **If gap opens <10 pts from fill: 77–79% chance of filling** (2010 77.8%, 2011 75.6%, 2012 79.7%; text says "between a 77 percent and 79 percent chance"). Combined printed as "773.8%" — an obvious OCR/typo for **77.8%**.
- **If gap opens >10 pts from fill: 8.8% to 26.4% chance of filling** (2010 24.4%, 2011 26.4%, 2012 8.8%; combined 21.9%). Confirms letting a professional gap-and-go run.
- **Options Ex** column is **58.3%** in every single year (7 of 12 each year) — lower than the <10 case.
- **1st Monthly Trading Day**: 2010 33.3% (4/12), 2011 50.0% (6/12), 2012 50.0% (6/12), combined 44.4% (16/36).

### Other figures (image figures, thinkorswim; not reproducible from text)
- **FIGURE 12.2 Pro Gap-and-Go Levels** — study showing prior 4 p.m. close (fill level) + ±10-pt gap-and-go levels.
- **FIGURE 12.3 Reversal Point for a Gap Fill** — price traded off a 50% MM, formed a resistance level, used as entry into the red gap-fill line.
- **FIGURE 12.4 Broken Gap Fill Entry** — morning gap-fill entry breaks; participants become breakout fuel; opened within 10 pts so may fill later.
- **FIGURE 12.5 Gap Fill Entry Signal** — series of MMs later that day; extension long fails → break in trend → first sell signal → drawn as MM short.
- **FIGURE 12.6 Entry into the Gap Fill** — new MM short gives entry back toward fill; opened within 10 pts → filled same day.

## Codifiable vs discretionary

**Codifiable (mechanical, testable):**
- Gap fill definition (reach prior 4 p.m. close during RTH).
- ±10-point gap-and-go level = prior close ± 10 pts (pure arithmetic).
- The <10 vs >10 open filter and its historical fill probabilities.
- Calendar exclusions: options-ex Fridays; rollover Thursday + day after; first trading day of new month/quarter (mutual fund Monday); quarterly expiry = 3rd Friday Mar/Jun/Sep.
- Time gates: safe window 8:00–9:30 a.m. ET; no-trade zone 9:30–10:00 a.m. ET; after 9:30 only manage/take profit.
- "Opened within 10 pts" → expect same-day fill (possibly later); "opened outside 10 pts" → expect run into close (no fill).
- Break-in-trend triggers: (1) new high/low tick of day, (2) pierce of 61.8% level of the series of MMs.

**Discretionary (judgment / references earlier-chapter methods):**
- Identifying the actual MM structure, 50% retracements, "series of micros," daily pivot placement.
- The three ranked entry strategies (first test / second test / series of micros) require reading price action.
- Choosing whether a support/resistance level is "large" enough (checklist item 4).
- Reduced-risk trade sizing / stop placement ("reduced-risk trades," "tighter stops").
- Recognizing the rare broken-gap chain-reaction and re-drawing the MM short in real time.

## Cross-refs / open questions
- **Cross-refs**: relies on the three retracement entry strategies and MM/micro machinery from earlier chapters; 61.8% and −23% targets and "series of MMs" are defined elsewhere (see Ch 13 for target/exit mechanics). Daily pivot calc not defined here.
- **Open questions / ambiguities**:
  - Combined "<10" percent printed as **773.8%** — clearly a typo for **77.8%** (verify against source PDF if exact figure matters).
  - Units: chapter uses "points" for ES gap size (10-pt band) but figures elsewhere reference "pips"; ES gap distances are in index points.
  - Exact definition of "trading hours" for fill (RTH cash session vs. globex) not spelled out; implied cash session vs. 4 p.m. close.
  - "Reduced-risk trades" sizing not quantified here.
  - Whether the <10/>10 threshold is measured at the **open** relative to prior close (the table label is "Filled if Open <10 / >10").
  - Video reference: "Profiting from Gap Fills," http://eminiaddict.com/?p=5933.
