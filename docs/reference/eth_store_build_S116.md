# ETH tick store — build + accuracy record (S116-B, 2026-09-13)

Full-session (ETH+RTH) tick store built from NT8 `.ncd`, PARALLEL to the RTH trove
(`data/ticks_continuous/` — Massive-built, NEVER touched). Store: `data/ticks_continuous_eth/`
(gitignored, like the RTH trove). Scripts: `ingest_nt_ticks_eth.py`, `backfill_eth_from_nt.py`,
`validate_eth_store.py`. Coverage = all NT still held: **301 days, 2025-07-11 → 2026-09-11.**

## Accuracy (validate_eth_store.py vs Massive trove — full detail: eth_store_validation_20260913.csv)
- **230 MATCH** — RTH volume within 0.1% of Massive (exact on Massive-era days, e.g. 2025-07-23 972,780=972,780).
- **51 NT-MORE-COMPLETE** — NT has ~2x the volume, same price range → the **Massive trove day is undercounted**.
  46 of 51 are 2026-07+ : those trove days were built by the buggy `ingest_nt_ticks.py`
  (`drop_duplicates` on (Time,Price,Volume) collapses genuine same-ms/price/size fills, ~halving
  volume — the SAME bug fixed in the ETH ingest). **The recent RTH trove has volume-undercounted
  days.** NOT fixed here (user: do not touch the tick trove) — FLAGGED for a decision.
- **13 NT-light** — NT 0.1–5% below Massive (real minor `.ncd` gaps); Massive is the better RTH source
  on these: 2025-07-30/31, 08-21, 09-02, 11-28, 2026-01-20/29, 02-17, 03-31, 04-02, 05-26, 06-22, 07-06.
- **7 eth-only** — no RTH trove day (holiday/gap); NT overnight kept: 2025-09-01, 2026-01-19, 02-16,
  04-03, 05-25, 06-19, 08-03.
- 0 structure issues, 0 session-keying issues.

## The volume-destroying bug (fixed in ETH ingest, still present in the RTH NT ingest)
`drop_duplicates(subset=[Time,Price,Volume])` treats a sweep's many same-ms/price/size prints as
duplicates and collapses them. Real per-day impact seen: 972,780 → 380,298 volume. The ETH ingest
now takes ONE complete file per session, NO triple-dedup → volume preserved exactly.

## Open decisions
- Fix `ingest_nt_ticks.py` (RTH trove) the same way + re-ingest the 46 undercounted 2026-07+ trove days? (needs user OK — touches the trove)
- The 13 NT-light days: leave (Massive authoritative for RTH) — ETH overnight still valid.
