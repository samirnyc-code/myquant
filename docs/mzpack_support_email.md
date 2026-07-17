# MzPack support email — historical CSV extraction of footprint analytics

Structured for their AI responder: atomic, numbered, each independently answerable.

---

**Subject: Historical CSV export of footprint/delta/absorption — depth, L1-vs-L2, and API tier**

Hi — I run ES on NinjaTrader 8 with ~5 years of tick data already loaded, and I want to
extract mzFootprint's computed values to CSV for offline backtesting in Python. A few
specific questions:

1. Does mzFootprint's **absorption/imbalance** detection work on **Level 1 (tick /
   time-and-sales)** data only, or does any of it require **Level 2 (DOM/order book)**?

2. Using **Tick Replay** over my locally-stored 5-year ES tick history, will
   `StrategyFootprintIndicator.FootprintBars` populate for the **full historical range**
   (i.e., can I read `Delta`, `Imbalances`, absorption S/R zones, `COT`, `POC` per bar
   historically), or only for realtime/recent bars?

3. Is the **`StrategyFootprintIndicator` API / data-access** included in the **€399
   Indicators package**, or only in the **€599 Full Suite**? (I plan to write my own thin
   strategy that reads `FootprintBars` and writes my own CSV — not use the built-in
   exporter — so I need to know which license unlocks that API.)

4. Which NT8 data feed do you recommend for the **deepest historical tick** for this
   (Kinetick / IQFeed / Rithmic-CQG), and are there known differences between historical
   and realtime footprint on reconnect?

5. Can footprint/delta extraction be run in **batch over a date range** on historical data
   (e.g., a strategy in the Strategy Analyzer / on a historical chart), or interactive only?

6. Does the per-cell data expose **bid volume and ask volume separately per price**
   (so I can compute delta/absorption offline), or only aggregates (POC/VAH/total delta)?

7. Is **mzMarketDepth (L2)** the *only* component that cannot be reconstructed/exported
   historically?

Thanks!
