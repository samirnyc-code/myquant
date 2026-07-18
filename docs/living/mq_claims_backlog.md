# MenthorQ Claims Backlog — testable hypotheses mined from 240 KB/wiki/academy pages

**Status:** Living. S73 night-2 synthesis of 4 extraction passes. Each claim = a
hypothesis for the test pipeline; NOTHING here is validated until it survives our own
walk-forward on repaired bars (`_continuous_unadj.parquet`). ✔=tested, ✘=rejected, ★=survived.

## A. Key definitions recovered (data semantics)

- **Call Resistance / Put Support** = strike with highest net call/put gamma exposure
  (widest green/red bar on NetGEX chart). Dynamic — rolls with OI migration.
- **HVL** = inflection point in the slope of the *cumulative* gamma exposure curve;
  the positive↔negative gamma regime divider. Above = pin/mean-revert; below = amplify.
- **1D Max/Min** = options-implied expected daily move boundaries (forward-looking).
- **GEX 1–10** ("JAX") = next-largest gamma strikes after CR/PS, ranked.
- **Q-Score** = composite 0–5 of Option, Momentum, Volatility, Seasonality(−5..+5) sub-scores.
- **GEX Percentile 1Y** = today's GEX rank vs past 252 days. **IV 0DTE 1Y Percentile** =
  frequency-based (days below current)/252 — distinct from range-based IV Rank.
- **Update schedule:** indices/stocks EOD 6pm ET; **futures 11pm ET** (so date-d levels are
  computed from d−1 close → our same-day join is CAUSAL ✔ verified vs user's morning paste);
  intraday snapshots every 5–30 min from 8:00 ET.
- **Four Option-Matrix regimes** = sign(NetGEX)×sign(NetDEX) quadrants with distinct behavior.

## B. Claims with THEIR published numbers (verify first — directive #2)

| # | Claim | Their number | Test with |
|---|---|---|---|
| 1 | SPX closes below 1D Max | ~85% of days (4yr) | levels0 + daily closes ✔ репaired bars |
| 2 | SPX closes above 1D Min | ~87% | same |
| 3 | Full 1D range holds intraday | only ~73% | same |
| 4 | Swing model close-above-lower-band | 88.24% (119d TSLA); BTC 90% | needs swing-level history (QUIN) |
| 5 | Naked 0DTE selling ROI by IV-percentile | improves >30th pct, peaks >70th (10yr) | OptionsDX 2010-23 |
| 6 | IV overstates RV | ~85% of time | OptionsDX / vix vs realized |

## C. Regime claims (GEX/DEX conditioning)

7. Positive gamma → mean-reversion wins, breakouts fail; negative gamma → trends amplify,
   breakouts work. *(Our data: partially — CR-0DTE fade works in BOTH regimes.)*
8. Four-quadrant matrix: −GEX/+DEX most directional; −GEX/−DEX most bearish; +GEX/+DEX choppy.
   Needs NetDEX history (QUIN).
9. GEX Pct>70 + GEX>0 + VolScore≤2 + IVRank>0.5 = prime premium-selling (condor) days.
10. GEX Pct<30 + GEX<0 + Momentum≥4 = dealer-amplified trend days (trend-follow, wide stops).
11. Neg NetGEX + high TotalGEX = "bifurcated": reactive at big strikes, fast through gamma-light zones.
12. **Last-30-min momentum on neg-gamma days** (JFE-published; web list #1) — ES 5m + GEX ✔ ready.
13. "Calm before storm": low RV + rising IV + GEX turning neg + Q bearish → vol spike ahead.
14. Static stops fail across regime flips — ATR/regime-scaled stops (our sweep already hints: wide stops win).

## D. Level-behavior claims

15. CR breakout that HOLDS → old resistance becomes support; dealer flows flip to fuel (BO-PB
    long — PARKED, build entry logic with user).
16. Put Support break → reflexive acceleration; the RETEST decides (reclaim=false breakdown).
17. First-touch vs second-touch react differently; pinning strengthens into expiry (esp. 14:45–15:30 ET "rush hour").
18. Morning touches react stronger than midday (matches our pre-repair hour pattern — retest on repaired bars).
19. Confluence across SPX+SPY+ES chains at same converted price = stronger level.
20. 1D Max touched in pos-gamma → mean-revert; in neg-gamma → continuation. *(Our repaired data: 1D-Max fade E<0 overall — needs the regime split before final verdict.)*
21. High-OI round strikes = pin magnets into expiration (Ni-Pearson-Poteshman 16.5bps published).
22. JPM quarterly collar strikes pin SPX at quarter-end.

## E. Score/flow claims

23. Option-score 1-day jump screener names outperform rest of week (their Tue-open→Fri-close demo: TSLA +14%).
24. Q-Score 0→5 transition marks trend starts; 5→0 precedes declines.
25. Option score ≥4 + seasonality<0 + momentum≤3 divergence → correction risk.
26. Skew leading price (vs lagging) identifies MM-caught-short repositioning on outside-range days.
27. VRP>10% + IV pct>60 = sell premium; VRP<0 = buy premium (their TSLA long-vol case study).
28. High VRP at LOW absolute IV is a trap — require both.
29. OI spike (>40% wow) precedes price/vol attention.
30. CTA max-long + vol spike = deleveraging cascade risk; vol-control releveraging + pos gamma = melt-up cocktail.

## F. Hidden gems / data channels (for the machine)

- NinjaTrader API mode serves **historical levels 30 days back**; Pro tier = **CSV export**;
  public API "in development".
- **Request Levels** tool: Gamma/Blind Spots/**Swing Levels** for 5 tickers incl. HISTORICAL
  snapshot dates → backfill channel for swing bands.
- Levels Conversion auto-ratio updates 9:31 ET (SPX→ES etc.) — matches our measured-basis approach.
- Gamma **scalping** model = tighter top-10 strikes variant.
- 160 academy LESSON bodies now archived (`data/menthorq/knowledge/lessons/`) — deeper
  definitions/playbooks, next mining pass.
- QUIN: 97+ metrics catalog captured; explicitly refuses formulas/direction calls.

## Test order (fit × effort, next up)

1. B1–B3 (their published 1D Max/Min stats — cheap, verifies both their honesty and our data)
2. C12 last-30-min momentum (best pedigree)
3. D20 1D-Max × regime split; D17 first-vs-second touch (repaired bars)
4. C9/C10 quadrant screens once NetDEX history pulled
5. E23 option-score screener replication (qscore CSVs already local)
