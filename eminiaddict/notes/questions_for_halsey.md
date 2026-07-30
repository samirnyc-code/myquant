# Questions for David Halsey (method clarification)

Grounded in the full-book extraction (`notes/ch*.md`, `RULEBOOK.md`). Ordered by
priority. The starred (★) ones are Samir's original asks, expanded.

## A. Market selection & instrument portability (★ Samir's core questions)
1. ★ **Are the NYSE internals (NYSE TICK, market breadth, Nasdaq Bank) — and the
   VIX — only useful on the ES, or do you apply them to YM/TF/NQ too?** They're
   equity-index tools; do they carry any weight when trading currencies (6E),
   gold (GC), or bonds (ZB)?
2. ★ **You've said the ES is the *hardest* market to trade. Which markets are
   *easier*, and why?** Is "easier" about cleaner trends, less algo noise, wider
   ranges, or fewer fake-outs at the 50%?
3. ★ **When you move to an easier market, do you still need VIX / breadth / TICK,
   or does the method run on price structure alone there** (since those internals
   are equity-specific)? If you drop them, what replaces the "participation"
   confirmation you get from time & sales / TICK on the ES?
4. ★ **What's the *best* market to trade this method right now, and how do you
   decide?** Is it volatility, trend cleanliness, participation, tick liquidity,
   time-of-day overlap? **How often does the "best market" rotate** — daily,
   weekly, per regime — and what triggers the switch?
5. Do the **50% / 61.8% / 123% ratios stay identical across every instrument**, or
   have you found some markets respect different fib levels?

## B. The seed leg / what defines a swing (★ Samir)
6. ★ **How do you objectively pick the *initial* swing (the seed) that anchors the
   very first Fib?** Everything after chains mechanically, but the seed looks
   discretionary. Is there a bar-count, a % move, an ATR threshold, or is it
   purely "the significant high-low that jumps off the page"?
7. On which **time frame do you seed** — always the 20-yr daily for context, then
   step down, or do you seed on the frame you intend to trade?
8. When two people draw the seed slightly differently (e.g. a spike low vs the
   close), the whole level stack shifts. **How much does seed precision matter,
   and how do you reconcile disagreements?**

## C. Trigger precision (needed to codify / backtest)
9. **What exactly counts as a "test" of the 50%?** A single tick touch, a close, a
   time-at-level? And is the 61.8% *failure* a wick pierce or a **close** beyond?
10. The book gives tick stops per instrument (ES −6) but calls the 61.8% the
    "structural" invalidation. **Which is the real stop — the −6 tick bracket, or
    the 61.8% level?** Do you ever hold to 61.8% if the tick stop wasn't hit?
11. **Extensions:** you say the *first* extension off a new anchor is observe-only.
    **How do you know the first extension has "completed/survived"** so the second
    is safe to limit-trade?
12. Front-run is 2 ticks on ES, "3 in a very aggressive rally." **How do you judge
    'aggressive' in real time** — a specific tick/volume/velocity read?

## D. Durability of the statistics
13. The gap-fill table is **2010–2012**. **Do the <10-pt (~77–79%) vs >10-pt
    (~9–26%) fill rates still hold today?** Algo participation has changed a lot —
    has the edge degraded, and do you re-measure it?
14. **Breadth and Nasdaq Bank** — what exact data/feeds do you use for these now
    (several classic internals feeds have disappeared)?

## E. Targets & management
15. When a wide-range MM target is too big for one day, you switch to the Distance
    Formula / −23% intraday. **Is the target anchor time-frame-dependent** — i.e.
    does the same swing produce different targets on 15-min vs daily?
16. **Take profit on the time frame you entered** — how do you map an entry frame
    to the exit target frame mechanically?
