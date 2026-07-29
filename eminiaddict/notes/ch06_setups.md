# Ch 6 — Three Types of Trade Setups

Source: David Halsey, *Trading the Measured Move*, Chapter 6 (PDF pages 89–102). All chart figures sourced from thinkorswim®. Companion video: "The Three Types of Fibonacci Trade Setups," http://eminiaddict.com/?p=5439.

## Summary

The book defines exactly **three trade setups** used to trade the markets:

1. The **traditional 50 percent measured move (MM)**.
2. The **extension 50 percent MM**.
3. The **61.8 percent MM** (the "61.8 percent failure").

Core thesis: high-frequency trading (HFT) / program trades follow measured moves with fixed rules. They trail price during a rally (or sell-off), rest a limit order at the **50 percent retracement** of the trailed swing, fill there, and take profit at a **123 percent profit target** measured off the total distance of the initial trailed swing. Every 50 percent MM has "its own unique profit target."

The stated ORDER of a trend (chapter close, PDF p102): "The market travels in **traditionals, then to extensions, and then straight up**. If we ever fail the 61.8 percent level, the trend changes. Knowing this order gives us a sequence to trade in."

Key sequencing rules:
- Traditionals string into a **series** (50% entry → 123% target → pullback into next traditional 50% → repeat, "indefinitely").
- When a traditional's 123% target is exceeded WITHOUT a pullback, the setup converts to an **extension** (bull/bear flags). Extensions also run in series "indefinitely," all drawn from a single fixed anchor.
- A **61.8 percent failure** (price piercing the 61.8% level on the second test) ends the current series/trend and starts a new one the opposite direction.

---

## The three setups

### 1. Traditional 50% Measured Move

**Definition:** "The traditional setup is when we pull back 50 percent or halfway back of an initial rally." Program trails the market up (long) or down (short) during the initial swing, resting a limit order at the 50% retracement.

**Fib anchoring:**
- LONG: anchor the swing from the initial rally's **low** to the trailed **high**. The 50% is measured on that low→high distance.
- SHORT: anchor from the sell-off **high** (lows referenced) — program follows price down and rests a sell order at the 50% MM in case price pops back up.

**Entry level & trigger:** resting **limit** order at the **50 percent MM** (50% retracement of the initial trailed swing). Fill is passive at that limit price. (Long example Fig 6.1: buy limit at 1.2976. Short example Fig 6.2: sell limit at 1.3865.)

**Profit target:** the **123 percent profit target** = "123 percent of the total distance of the initial rally that was trailed from lows to highs by the program trades." Each 50% MM has its own unique target.
- Fig 6.1 long: target **1.3489** (123%). "the market took 14 days and traveled 513 pips to its target."
- Fig 6.2 short: target **1.3481** (123%). Traveled **384 pips** to target over 4 days after fill.

**Stop / invalidation:** Chapter 6 does NOT state an explicit numeric stop for the traditional. Invalidation logic comes via the **61.8% failure** (setup #3): a failed second test of the 50% level that pierces 61.8% breaks the series (i.e., the 61.8% level acts as the structural invalidation of a traditional/series). Note the target callout uses "-23.6%" framing in the prompt's Fig 6.1 gloss (low 1.2627 / high 1.3324 / 50% 1.2976 / 61.8% 1.2893 / -23.6% 1.3489) — the 123% target sits at the -23.6% extension beyond the 0% high.

**Filters/conditions:** must "examine which setups to trust, and know when to watch for confirmation and participation." Some traditionals are NOT to be trusted without observing participation (see "Traditionals not to trust"); a larger-time-frame profit target can break the last MM in a series.

---

### 2. Extension 50% Measured Move

**Definition:** "The extension 50 percent MM is formed when we rally past the profit target of a traditional MM." Normally a traditional hits its 123% target and pulls back into the next traditional; when instead the market makes **new highs** past the 123% target without pulling back, programs stop looking for a traditional and start a new extension.

**Fib anchoring:**
- The extension is drawn (trailed) **from the top of the last retracement** / **the previous highs** (long) — Fig 6.5: "begins from the previous highs of the 1,268.13."
- In an extension SERIES, all extensions use a **single fixed anchor**. Fig 6.6/6.7 short series: anchor **2,498** (also written "1.2498"/"2498" — same value, decimal placement inconsistent in text). Every subsequent extension in the series re-uses that same anchor.
- Extensions can be longs or shorts.

**Entry level & trigger:** program rests its order and waits for price to pull back into the **new extension 50 percent** level; fill is at that price.
- Fig 6.5 long: extension entry / buy fill at **1,296.59** (this equals the traditional's prior 123% target 1,296.59 — the target level becomes the extension's support/entry).
- Fig 6.6 short: first extension 50% short entry at **2,461** (pop from lows of 2,425).
- Fig 6.7 short: next extension sold at **2,427**.
- Fig 6.8 long: extension support/entry level **2,504** (drawn from highs of last traditional at 2,483).

**Profit target:** the **123 percent profit target** of the extension swing.
- Fig 6.6: 2,461 entry → 123% target **2,408**.
- Fig 6.7: 2,427 entry → 123% target **1.2325** (i.e., 2,325 in the mislabeled decimal).

**Stop / invalidation:** No explicit numeric stop given. Structural rule: **the very FIRST extension after price goes through a 123% target cannot be trusted with a limit order and must only be observed** — because the first extension can fail (Fig 6.8 first extension fails). "Once the first extension is witnessed, the rest of the extensions from that anchor are safe to trade to their profit targets."

**Filters/conditions (HARD):**
- Trigger to switch from traditional → extension: price makes **new highs past the 123% target without pulling back**.
- Do NOT place a limit on the FIRST extension of a new anchor; observe it first. Only after the first extension is witnessed are subsequent extensions from that anchor tradeable.
- Extensions ARE the technical bull-flag / bear-flag pattern ("These specific patterns are how bull and bear flags develop").

---

### 3. The 61.8% Failure

**Definition:** "less of a trade setup and more of a signal that the current series of MMs … is over." It marks "the end of one trend and the beginning of another." Failures can be longs or shorts.

**Mechanics / anchoring:** a traditional 50% MM has been bought (or sold) with a 123% target above (or below). Price **fails to break out of previous highs**, comes **back into the original entry**, **fails the second test** of the 50% MM level, and **pierces the 61.8 percent level** — that piercing **breaks the series** of MMs the market was trending in.
- Fig 6.9 (failed longs): traditional MM long entry / 50% at **1,450.52**, expected 123% target **1,458.94**. Price failed to break previous highs, came back, failed the second test of 1,450.52, pierced 61.8% → series of MM longs broken. Next setup = a MM short (new trend).

**Entry level & trigger (as a trade):** the 61.8% failure of an **opposing** MM signals entry in the direction of the larger trend — you buy/sell the **first pullback after the trend break**. "The first pullback after a trend break is a very successful trading opportunity, and is many times the beginning of a brand new trend."
- Fig 6.10 (first pullback after trend break): a traditional 50% MM is trading with a 123% target above; an **opposing traditional 50% MM short is broken**, signaling to buy the next pullback in the continuation of the larger trend.

**Stop / invalidation & profit-target usage:** The 61.8% failure often serves AS a profit target (exit) for a trend trade you're already in ("disappointing if you are in a trade and are waiting for a trend break as a profit target"). Being kicked out of a profitable trend by a 61.8% failure is defined as a success.

**Filters/conditions — which 61.8% failures NOT to trust (HARD):**
- "If a 61.8 percent failure turns into a **retest of previous highs or lows**, do not trust the next MM."
- Normal case: immediately after a 61.8% failure the market pulls back and gives its entry.
- Dangerous case (Fig 6.11, "Double Top"): traditional 50% MM bought at **1,301.64**; opposing MM fails at **1,311.26** giving entry into the larger trend; BUT instead of pulling back, price runs up and **retests its previous high** → the pullback after that retest is a dangerous trade (sellers participate in a "double top"). "It will more than likely retest its previous support or resistance before continuing in its trend." → avoid this pullback.

---

## Series of measured moves / "traditionals not to trust"

**A Series of Measured Moves (traditionals):** "A series of traditional MMs is when the market moves from its 50 percent entry, to its 123 percent profit target, and after hitting its profit target, pulls back into its next traditional MM." Repeats "indefinitely."

Fig 6.3 (series of traditional MMs) exact prices:
- Rally off **1,195.50**; program waits for pullback.
- First traditional 50% MM buy at **1,223.00** → 123% profit target **1,267.47**.
- After target completes, a NEW program anchors from the last low **1,222.25** and waits for a new pullback.
- Next pullback traditional 50% MM at **1,243.75** → 123% profit target **1,274.31**.
- Series continues indefinitely.

**Which Traditional MMs Not to Trust:**
- Some traditionals should not be trusted without first observing their **participation**.
- Watch for a possible series **failure**; there are specific clues on a questionable MM.
- A **larger time frame's** profit target can break the last MM in a series.

Fig 6.4 ("Traditionals Not to Trust") exact prices:
- A series of smaller traditional MMs runs into a **larger time frame's 123 percent profit target at 1,297.00**.
- After the larger MM target completes, profit-taking breaks the smaller series of MMs at **1,278.53**.
- The next MM in the larger time frame's series is below at **1,246.57**.
- Analogy: "we are too close to the trees to see the forest" (larger-time-frame context; expanded in the next chapter).

**Extensions in a series** (Fig 6.6–6.7): all drawn from the SAME anchor (2,498). Program trails price down, waits for rally back into the 50% extension, fills, targets 123%. Continues indefinitely from that single anchor.

**Which Extensions Not to Trust:** the FIRST extension after a traditional series goes through its 123% target must be **observed only** (no limit order) because it can fail (Fig 6.8). After the first is witnessed, the rest from that anchor are safe.

---

## Figures (6.1–6.11) — what each shows with its prices

- **Fig 6.1 — Traditional Measured Move Long.** Rally from low **1.2627** trailed to high **1.3324**. 50% MM buy limit **1.2976**. 123% profit target **1.3489**. Prompt gloss levels: 50% = 1.2976, 61.8% = 1.2893, -23.6% (target) = 1.3489. 14 days, 513 pips to target.
- **Fig 6.2 — Traditional Measured Move Short.** Lows **1.3600**; 3 days later price pops into 50% MM short, sell fill **1.3865**; 4 more days, 384 pips to 123% target **1.3481**.
- **Fig 6.3 — Series of Traditional Measured Moves.** Rally off **1,195.50**; buy 50% MM **1,223.00** → target **1,267.47**; new anchor low **1,222.25**; next 50% MM **1,243.75** → target **1,274.31**.
- **Fig 6.4 — Traditionals Not to Trust.** Larger-TF 123% target **1,297.00** breaks smaller series at **1,278.53**; next larger-TF MM below at **1,246.57**.
- **Fig 6.5 — Traditional Measured Moves Become Extensions.** Traditional 123% target hit at **1,296.59** with no pullback → extension begins from previous highs **1,268.13**; extension buy fill at **1,296.59**; then targets 123% above. (Bull/bear flag pattern.)
- **Fig 6.6 — Extension Short.** Anchor **2,498**; prior extension 123% target completed at **1.2442**; re-uses prior extension lows **1.2498**; lows **2,425** give pop into next extension 50% short **2,461** → 123% target **2,408**.
- **Fig 6.7 — Continuation of Extension Shorts.** Same anchor **2,498**; second extension sold at **2,427** → new 123% target **1.2325**. Subsequent extensions keep the same 2,498 anchor.
- **Fig 6.8 — Extension Failure.** Traditional 50% MM from **1.2375** goes through 123% target at **2504**; new extension drawn from highs of last traditional **2,483**, extends until pullback into extension support **2,504**; the FIRST extension FAILS → reinforces observe-first rule.
- **Fig 6.9 — Failed Longs (61.8% failure).** Traditional MM long 50% **1,450.52**, 123% target **1,458.94**; fails second test of 1,450.52 and pierces 61.8% → breaks series of MM longs; next setup is a MM short.
- **Fig 6.10 — First Pullback after a Trend Break.** Traditional 50% MM trading with 123% target above; opposing traditional 50% MM short broken → buy the next pullback in continuation of larger trend (start of new trend).
- **Fig 6.11 — Double Top (61.8% failure not to trust).** Traditional 50% MM bought **1,301.64**; opposing MM fails at **1,311.26** (entry into larger trend); price instead runs up and retests previous high → dangerous "double top"; likely retests prior S/R before continuing. Avoid the pullback after the retest.

---

## Codifiable vs discretionary — be explicit per setup

### Traditional 50% MM
- **Codifiable:** identify the initial trailed swing (low→high for long, high→low for short); compute 50% retracement = limit entry; compute 123% target = 100% + 23.6% beyond the swing extreme (target sits at the -23.6% extension of the low→high leg per Fig 6.1 gloss); series logic (entry→target→re-anchor at last low→next pullback). All prices/ratios are fixed.
- **Discretionary:** which swing counts as "the initial rally" (anchor selection); whether to trust a given MM without observing "participation"; recognizing when a larger-TF 123% target (e.g., 1,297.00) will break the smaller series; "confirmation and participation."

### Extension 50% MM
- **Codifiable:** trigger = 123% target exceeded WITHOUT pullback (new highs); anchor = top of last retracement / previous highs (long) or fixed series anchor (2,498 short); entry = pullback into the extension 50%; target = 123%; single-anchor re-use across the series.
- **Discretionary (HARD gate):** the FIRST extension of a new anchor must be OBSERVED, not limit-traded — you must witness it survive/fail before trusting subsequent extensions. Judging "made new highs vs pulled back."

### 61.8% Failure
- **Codifiable:** second test of the 50% level fails + price pierces the 61.8% level → series broken; trade the FIRST pullback after the trend break in the new-trend direction; can be used as an exit/profit target for a trend trade.
- **Discretionary (HARD gate):** do NOT trust the next MM if the 61.8% failure turns into a **retest of previous highs/lows** (double-top/bottom risk); judging whether the post-failure move is a clean pullback vs a retest of the prior extreme.

---

## Cross-refs / open questions

- **Next chapter (Ch 7):** three different time frames the markets move in; expands the "too close to the trees to see the forest" larger-TF interaction (larger-TF 123% target breaking a smaller series).
- **Video:** "The Three Types of Fibonacci Trade Setups," http://eminiaddict.com/?p=5439.
- **Open / ambiguous numbers in the source text:**
  - Decimal inconsistency in the extension short series: anchor written as **2,498 / 1.2498 / 2498**; targets as **1.2442, 2,408, 1.2325** — the "1.2xxx" forms appear to be typos for the "2,4xx" index-point values (same instrument). Treat 2498 anchor, 2461/2427 entries, 2408/2325 targets as the intended series.
  - Fig 6.8: "goes through its 123 percent profit target at **2504**" while the extension support/entry is also **2,504** — the traditional target level becomes the extension entry (consistent with Fig 6.5 where 1,296.59 is both target and extension entry).
  - Explicit **numeric stop-loss** is never stated for traditional or extension setups in Ch 6; invalidation is structural (the 61.8% level / second-test failure). A machine rulebook needs an assumed stop convention (candidate: beyond the swing origin or beyond the 61.8% level) — NOT given in this chapter.
  - "123 percent" target and "-23.6%" extension are the same level (100% swing + 23.6% beyond); confirm sign/anchor convention when coding (target = swing_high + 0.236 * (swing_high - swing_low) for a long).
