# MzPack follow-up — the €599 decision question (draft)

**To:** Mikhail Zhelnov (MzPack)
**Re:** Data Export API — historical depth over imported ticks

Context: Mikhail confirmed (2026-07-17) that the Full Suite **Data Export** can export
historical (Tick Replay) footprint + volume delta + **absorption/imbalance flags + COT**
to CSV over a given range, L1 only, bounded by *the data feed's tick history*. The one
thing that decides whether we buy is below.

---

Hi Mikhail,

Thank you — that's very clear and helpful.

One decisive follow-up before we commit to the Full Suite:

Our deep ES tick history (several years) was **imported into NinjaTrader from flat files**
(not pulled from a live feed's tick server). It is stored in NT8 as tick data and replays
fine under NT8 Tick Replay.

**Can `Data_Export` in Historical mode replay over those already-imported NT8 ticks — i.e.
export footprint clusters + delta + absorption/imbalance counts + COT for a date range that
exists in NT8 but predates anything the connected live feed (IQFeed / Rithmic) still serves?**

Or is the exportable range effectively bounded to whatever the connected live feed's own
tick server will hand back (typically only months for ES)?

In other words: is the limit "whatever ticks NT8 has for that instrument," or "whatever the
live feed re-serves on request"?

If it's the former, the Full Suite export is exactly what we need across our full history.

Thanks again,
Samir

---

**Why this is the whole decision:** IQFeed/Rithmic ES tick windows are ~months. Our 5-yr
came from Massive flat files. If Data_Export reads NT8's stored ticks → €599 gives us their
absorption + COT across the full study. If it re-requests from the live feed → it caps at a
few months and isn't worth it (we already reproduce everything else free).
