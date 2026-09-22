# Grimes Event Tests, POWERED RERUN — ES 2010–2026 (4,155 daily bars) — Final Verdicts
**Date:** 2026-07-23 (S81-b) · **Script:** `regime_events_2010.py` · **Data:** `_db_es_daily_24h.parquet` + `_db_es_1h_continuous.parquet` (Databento ohlcv-1h batch `GLBX-20260723-QSMLGGLMWB`, $0.69; volume-roll continuous, panama back-adjusted, 65 rolls audited).
**Data quality:** DB series refereed against SPX cash on all 19 days where it disagreed with our NT-derived 24h series by >20bp: **DB closer 17–2** → DB is now the canonical ES daily source. ⚠️ The NT `_continuous_1m_24h.parquet` has ~20 bad daily closes in 2021–23 (worst: 2022-09-26 shows −4.98% vs actual −1.0%) — **the S82 STMR-MES tearsheet was built on that series and should be re-run on the DB series.** Audit: `db_overlap_audit_20260723.csv`.
**Nulls:** 20× shuffled-returns + 20× iid-normal per timeframe, same detectors, N-weighted aggregate.

## Final verdicts (daily unless noted; edge = real mean − null mean, bp)

| Event | N | Verdict |
|---|---|---|
| **Keltner pullback→EMA LONG** | 49 | **CONFIRMED-SMALL, short-horizon.** d1 +14 (edge +9), **d3 +32 (edge +23, t 1.99, 35/49 up)**, d5 +32 (edge +11). d20 edge ≈ 0 → it's a 1–5 day continuation pop, not a swing edge. Consistent sign in all three samples (RTH 2021+, 24h 2021+, DB 2010+). ~3 events/yr; d3 ≈ +32bp ≈ 22 ES pts. |
| Keltner pullback SHORT | 36 | FAILS: d20 −141 (edge −119, t −2.30). Confirmed inverted. |
| **Compression breakout (flagship)** | 21 L / 18 S | **DOES NOT REPLICATE on ES.** At his d3–d5 headline horizon the edge is NEGATIVE (−20 to −27 long). d20 long +71 (edge +37, t 1.31) = weak lean only. With 16 yrs this is a genuine non-replication at his horizons, not just low power. 60m version: N=2,778, d20 edge +1.5bp — statistically nonzero, economically nothing (<10bp floor). |
| Donchian 100/260 LONG | 244 / 209 | NO momentum edge: edges vs null negative at nearly every horizon (breakout longs don't even beat the null's drift). Momentum-entry on ES daily is dead at these specs. |
| **Donchian 100/260 SHORT** | 30 / 14 | **THE most robust finding of the whole program, third sample in a row: strongly negative.** d20 edge −271 (t −2.58) / −514 (t −3.32, 2/14 up). Shorting ES breakdowns lost consistently for 16 years; breakdown events are bounce zones. |
| All events at 60m | 1,100–2,800 per cell | Economically dead (every effect <5bp). Closes the intraday question with real N. |

## Program conclusion (the Fable read)
1. **Grimes's trend-continuation framework survives on ES as exactly one small edge and one large prohibition:**
   - Edge: with-trend **pullback long** after an upper-band impulse, worth ~+23bp over null at 3 days, ~3×/yr. Real but thin — a **filter/sizing input, not a standalone strategy**.
   - Prohibition: **never trade downside momentum on ES daily** (breakdown shorts −270 to −510bp vs null). This is the regime engine's most valuable output: ES's "bear regime" is not a short-momentum regime, it is a bounce-risk regime.
2. **The flagship compression breakout is not an ES phenomenon.** Kill it as an engine block.
3. **A standalone Grimes regime engine is not supported by the evidence.** Recommended redirection: fold the two surviving facts into the existing desk instead —
   - STMR is a dip-buyer: check its entries against the kelt-pull-long event (overlap = independent confirmation; also STMR must be **re-run on the DB series** given the NT data fault).
   - Hard rule for any future ES daily system: no breakdown-short logic; treat lower-band/channel breaks as bounce-watch zones (failure-test long territory), which is where Grimes's failure-test material re-enters with the grain of the market.
4. If the engine idea continues, the honest next candidate is a **mean-reversion-regime engine** (when to fade vs stand aside), because every piece of evidence across v0, the events, and Grimes's own index-runs table says ES daily is a mean-reverting instrument.

## Files
`events2010_gate_20260723.csv` (full tables), `db_roll_audit_20260723.csv`, `db_overlap_audit_20260723.csv`, builder `databento_build_continuous.py`, downloader `databento_dl_ohlcv1h.py`.
