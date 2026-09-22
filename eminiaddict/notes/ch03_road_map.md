# Ch 3 — Drawing a Road Map (Finding Direction)

## Summary (3-5 lines)
Chapter 3 frames trading as navigating a "mountain range of price" whose contours reveal trends and countertrends. It establishes the core map-drawing tools of Measured Move (MM) trading: Fibonacci-based measured moves and Halfway Back (HWB) levels, the daily pivot (DP) as a price attractor, gaps (professional vs amateur) with gap-fill / half-gap-fill targets, and the definition of a trend day via three criteria (professional gap, breadth, tick divergence). It also defines NYSE tick, breadth, and tick divergence, and prescribes a top-down multi-timeframe workflow (20Y Daily → 15-minute → micro).

## Key concepts & definitions
- **Trend / countertrend**: trend = "a line of general direction or movement." A countertrend is "simply a trend in the opposite direction within a prevailing longer-term trend."
- **Measured Move (MM)**: Fibonacci-based measured moves used to identify trends and countertrends. MM trading uses only one Fibonacci type (KISS — Keep It Simple, Stupid).
- **HWB (Halfway Back)**: a critical retracement level that acts as both support and resistance; the most significant "critical juncture" / switchback point. Countertrend toward HWB is what an MM trader expects after a swing low/high.
- **ATWHWB (All The Way Halfway Back)**: special case / MM axiom — "whenever a trend of extended duration breaks, price can and usually does retrace all the way halfway back of the entire move." Example: entire 2007–2009 decline's ATWHWB level = **1,126.25**.
- **61.8 percent failure level**: the last short MM in a series; breaking the 61.8% level (example 837) invokes ATWHWB. HWB in that example was 804.25.
- **Daily Pivot (DP)**: "a kind of weighted average price for yesterday's trading." **Formula: DP = (High + Low + Close) / 3.** Only the central DP is used in MM trading (KISS + it is the most powerful pivot-level attractor). Acts as an "attractor for price much like a magnet does for metal objects." It informs *tomorrow's* trading, not the concluded day's.
- **Gap**: "a difference in price between a trading instrument's opening price and the closing price of the previous trading day." ("Yesterday" = previous trading day, to allow for weekends/holidays.)
- **Professional gap (ES)**: a gap of **10 points or more**.
- **Amateur gap (ES)**: a gap of **less than 10 ES points**.
- **Gap fill**: after the open, a trade executes at yesterday's closing price ("closing the gap").
- **Half-gap fill**: a trade executes at a price halfway between today's open and yesterday's close.
- **Trend day**: "a day in which a single trend, either up or down, is maintained for an entire day."
- **Breadth**: "the ratio of the total trade volume of stocks that are increasing in price to the total trade volume of stocks that are declining in price" (volume in advancing issues to volume in declining issues). Computed separately for NYSE and Nasdaq.
- **NYSE tick**: "a number equal to the difference between the number of stocks on the NYSE that traded up in price over a specified amount of time and the number that traded down." Measures bullishness/bearishness.
- **Tick divergence**: "occurs for a trading instrument whenever a new high (low) tick value for the day is reached without a corresponding new high (low) price for the day."
- **Composite operator (Wyckoff)**: view all price movement as the action of one large operator; underlies why DP/gap levels are self-fulfilling attractors.

## Rules / setups / mechanics
- **DP formula**: DP = (High + Low + Close) / 3.
  - Worked example: yesterday ES High 1,197, Low 1,182, Close 1,191 → DP = (1,197 + 1,182 + 1,191) / 3 = **1,190** (close to the 1,191 close, showing the close "weights" the average).
  - Contrast: (High + Low) / 2 = (1,197 + 1,182)/2 = **1,189.50**, which is .50 further from the close.
- **DP close-price choice**: use the **THO (trading hours only) 4 p.m. ET** close, NOT the Globex 4:15 p.m. ET close. THO-based DP is "much more consistently significant during the regular U.S. market hours of 9:30 a.m. to 4 p.m. Eastern Time." (Globex-close DP works better as an overnight attractor.)
- **Gap classification (ES)**: ≥ 10 pts = professional; < 10 pts = amateur.
  - Example professional: today open 1,195, yesterday close 1,185 (10-pt gap).
  - Example amateur: today open 1,171, yesterday close 1,176 (5-pt gap).
  - Fill example: open 1,195 after prior close 1,185 → trade at 1,185 = gap fill; trade at 1,190 = half-gap fill.
- **Gap behavior**:
  - Professional gaps *typically do NOT fill*; price continues in the same direction away from the prior close (up if open above close; down if open below close).
  - Amateur gaps *typically DO fill* (full or half) and do so **within the first hour of trading**.
  - Final fill/no-fill determination cannot be made until the current trading day has ended.
- **Price attractors on any open**: DP alone attracts price toward it. If a gap is also present there are **three** attractors/targets: the DP, the gap fill, and the half-gap fill.
- **Trend day (UP) — three criteria** (reverse for a down trend day):
  1. Professional gap up
  2. Positive breadth
  3. Positive tick divergence
- **Breadth notation**: advancers = decliners → 1:1; advancers 2× decliners → 2:1; decliners 2× advancers → –2:1. Positive = bullish, negative = bearish; very large magnitudes = extreme sentiment. Use BOTH NYSE (broad U.S. corporate) and Nasdaq (tech-centric).
- **NYSE tick thresholds**: **1,000 = extremely bullish; −1,000 = extreme bearishness.** Caution: reaching ~1,000 usually precedes professional/algo selling → reversal from bullish to bearish (mean-reversion at extremes). "Never buy highs or sell lows" is the implied caution.
- **Tick divergence direction**: new high tick without new high price → positive tick divergence (remains in play until a new high price is reached). New low tick without new low price → negative tick divergence.
- **Multi-timeframe workflow (top-down, done EVERY day)**:
  1. Start on the **20Y Daily** chart; ask where price is relative to the predominant daily trend. Truism: "the longer the trend, the more powerful it is."
  2. Zoom to the **15-minute** chart; draw one or more Fib retracements; ask where price is relative to 15-minute trends.
  3. Zoom to the **micros** (tick or time-based, immaterial which) for finer resolution.
- **Trust the trend**: "trends continue until they fail"; corollary — "trust the trend and take the setups you see."

## Figures / tables
- **Figure 3.1** — "The 2008 Sell-Off": weekly ES chart; decline from **Oct 11, 2007 high 1,586.75** to **Nov 21, 2009 low 665.75** (ES actually hit 665.75 on **March 6, 2009**). Clear downtrend from 1,586.75 to a low **15 weeks later at 1,255.50**; then upward countertrend toward HWB, retraced to full HWB over a **six-week** period before continuing down.
- **Figure 3.2** — "The Countertrend Toward HWB": HWB line acts as strong support/resistance; retouch of resistance followed by others over the next three candles across four full weeks before falling away.
- **Figure 3.3** — "The All the Way Halfway Back (ATWHWB)": full Oct 2007–Mar 2009 decline (~1.5 yrs), a **58 percent price decline** over a **17-month** period. Rebound began after 665.75 low when price failed to reverse at **804.25 HWB** and broke the **837 61.8 percent failure level**. ATWHWB of the entire move = **1,126.25**; touched/breached many times late Dec 2009–Sep 2010 before breaking up in late Sep 2010; also reacted in summer 2011.
- (No numeric data tables in this chapter; DP/gap examples are inline.)

## Codifiable vs discretionary
- **Codifiable**:
  - DP = (High + Low + Close) / 3, using THO 4 p.m. ET close.
  - ES professional gap ≥ 10 pts; amateur < 10 pts.
  - Gap fill = trade at prior close; half-gap fill = trade at midpoint of open and prior close.
  - Amateur-gap fill window = first hour of trading.
  - Breadth = advancing-volume : declining-volume (NYSE and Nasdaq separately); sign/ratio rules.
  - NYSE tick = (# stocks up) − (# stocks down); extreme thresholds ±1,000.
  - Tick divergence = new extreme tick without new extreme price (positive/negative).
  - Trend-day up = professional gap up AND positive breadth AND positive tick divergence.
  - Three attractors when a gap is present (DP, gap fill, half-gap fill).
- **Discretionary**:
  - Identifying HWB anchors and which Fib retracement to draw (anchor selection).
  - Judging "extended duration" for invoking ATWHWB.
  - Choice of micro chart (tick vs time) — "one that feels right to the trader."
  - Trusting the trend / when a setup is valid.

## Cross-refs / open questions
- Ch 2 established the single Fibonacci type used (KISS) — referenced here.
- Ch 4 expands NYSE tick, tick divergence, DP, and both breadth measures (the "toolbox"), plus best/worst times.
- Open: exact "specified amount of time" window for NYSE tick is not given ("over a specified amount of time").
- Open: professional/amateur gap thresholds for instruments other than ES are "different for each trading instrument" but only ES (10 pts) is quantified.
- Open: precise breadth/tick thresholds that qualify a trend day (only "positive" is specified, not a magnitude).
