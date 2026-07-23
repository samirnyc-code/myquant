# Grimes Event Tests on ES — Results (one survivor, one underpowered, one inverted)
**Date:** 2026-07-23 (S81) · **Scripts:** `regime_events.py` (RTH daily + 60m/30m) and `regime_events_24h.py` (true 24h CME-session daily, the robustness rerun — Grimes's tests used full-day bars and most ES drift is overnight).
**Data:** ES continuous, 2021-06 → 2026-07 (RTH: 1,305 daily bars; 24h: 1,274). Nulls: 20× shuffled-returns + 20× iid-normal replications per timeframe, detectors + scoring identical, N-weighted aggregate.
**Outputs:** `data/regime/events_real_20260723.csv`, `events_nulls_…`, `events_gate_…`, `events24h_gate_…`, `regime_events_20260723.png`.

## Verdict table (daily; bp = mean event return, short = short P&L; "edge" = vs aggregated null)

| Event | Side | Verdict | Key numbers |
|---|---|---|---|
| **Keltner pullback→20-EMA** | **LONG** | **SURVIVES (plausible, small N)** | RTH: d1 +41bp (13/18 up, t 2.54, edge +33); 24h: d3 +55bp (12/15 up, t 2.13, edge +43), d20 +79 (edge +48). Same sign mean/median at every horizon, both bar constructions. |
| Keltner pullback→20-EMA | short | FAILS | RTH d1 −37 (edge −36); 24h d20 −113 (edge −155). Opposite of Grimes's "shorts stronger in futures". |
| Compression breakout (5/40<0.5) | long+short | **UNDERPOWERED — not falsified, not confirmed** | Only 6–7 events per side in 5 yrs (his freq ~1-in-500 days). At his headline d4–d5 horizon: RTH edge −20, 24h edge +15 with t 0.07. Nothing sayable at this N. |
| Donchian 100/260 long | long | WEAK LEAN, not evidence | d20 edge +31/+39bp but t≈1.0–1.3; medians ≫ means (skew). |
| **Donchian 100/260 short** | short | **INVERTED — strongly negative** | RTH d20 −284bp (3/15 up); 24h d20 −252; 260-day shorts (N=3, the 2022 lows) −583 to −624bp. Shorting ES channel breakdowns was a disaster; the breakdown events were bounce points. |
| Everything at 60m/30m | both | DEAD | All effects <15bp, most negative. Consistent with Grimes (intraday RW violations eaten by costs) and our S80 STMR finding (signal starts ≥30m, really daily). |

## What this means (honest read)
1. **The one Grimes edge that shows up on ES 2021–26 is the with-trend LONG pullback**: close above the upper Keltner band → first touch of the 20-EMA → forward returns positive at every horizon, on both RTH and 24h bars, beating the nulls. This is "impulse → retrace → continue," long side only — and it matches ES's buy-the-dip character. N is 15–18, below the N≈20 rule, so per protocol this is **X-of-Y evidence, not a confirmed edge**.
2. **His flagship compression breakout cannot be tested on 5 years of one instrument.** ~7 events. The program-stopping rule ("if it doesn't replicate, stop") returns *insufficient power*, not refutation.
3. **ES is not the average futures contract in his tables.** His futures results pooled 16 contracts (currencies, commodities — the trending end). ES sits at the mean-reverting end (his own asset-class ranking, book p.314), and our results are exactly that: momentum shorts inverted, breakdown = bounce, longs-only pullback works.
4. **The binding constraint is now history, not method.** 1,300 daily bars cannot power daily event studies. Grimes used decades × hundreds of instruments.

## Recommended next steps
1. **Extend ES daily history to 2010+** (Databento GLBX OHLCV-1d/1h is pennies-cheap and we already have keys/credit) → reruns get 4,000+ bars incl. 2011/2015/2018/2020 regimes; compression breakout becomes testable (~8 events/decade → ~13 total; still thin — consider 1h-adapted spec). **Costs a (small) Databento spend — ask before pulling.**
5-yr sample also spans mostly one macro regime (bull with one bear year) — history extension is the only cure.
2. **Promote the surviving event into the engine**: the regime engine's trend-state definition should be event-anchored — "bull regime = the state in which pullback-to-EMA longs pay" — rather than occupancy-defined. Concretely: band-close-above arms the state; EMA-touch is the entry event; state dies per the 2-step rule.
3. **Keep the inverted Donchian-short finding** as a hard filter for everything else we build: no breakdown-shorting logic on ES daily.

## Files
- `scripts/regime_events.py`, `scripts/regime_events_24h.py` (specs in docstrings).
- Full tables incl. all horizons/sides/timeframes in the four CSVs listed above; chart `regime_events_20260723.png`.
