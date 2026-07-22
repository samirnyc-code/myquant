# Raw extraction — Grimes book, PDF pages 289–384 (Ch.9 Risk end, Ch.10 Trade Examples; Ch.11 psychology skipped)
Extracted 2026-07-22 (S81). PDF page cites.

## Ch.9 remainder — Risk Management (PDF 289–306)
- p.289-293 — Monte Carlo sizing baselines ($100k, 1,000 accounts, ruin = 75% DD): fixed-dollar sweep ($8-10k risk → ~15% bankrupt; $25k → ~half); fixed 2% vs $2k fixed-dollar (mean 163,033 vs 149,259; CoV 0.35 vs 0.23); fixed-fractional terminal values lognormal (skew 0.95, kurt 4.3) — extra variability nearly all upside. Fixed-fraction sweep: 8.333% is exact Kelly for the test system; above Kelly mean rises but MEDIAN collapses (25% risk: median $5.6k, 66.5% of accounts hit ≥75% DD). Random bet sizing ~U[0,8%] underperforms fixed 4% on mean, median, and CoV — any "size by regime" overlay must beat this null.
- p.294 — Equal-volatility sizing (Turtles variant): size so each position's daily P&L contribution is equal, ATR as the standard measure. Warning: dangerous when volatility is compressed and the market is "overdue for a range expansion move" — vol-compression is a distinct regime state where realized ATR understates forward risk.
- p.295-298 — Risk = P(loss) × E[loss size]; dangerous quadrant = low-probability/high-consequence. Tight stops = near-certain small losses; can be higher aggregate risk than a wider stop hit rarely. E = Pw×W − Pl×L; no inherent edge in high-probability vs high-R:R styles.
- p.302 — System control-process: monitor any trading system with a statistical control process — normal variation, violation flags, defined cutoff terminating trading. "Markets evolve and erase certain kinds of trading edges." Applicable as a live kill-switch layer on a regime engine.
- p.302-305 — Tail risk: Flash Crash; continuous option-hedging costs >10%/yr. Correlation spikes in stress: four "3% risk" positions become one 12% position. Margin hikes can break an overextended trend (Silver 2011) — exogenous regime-transition trigger.

## Ch.10 — Trade Examples (PDF 307–359): regime logic embedded in trades
Charts use 20-period EMA Keltner channels + MACD throughout (p.309).

### Trend-health / regime diagnostics
- p.307-308 — Standing management: predefined stop; first target = 1× initial risk, take 25–50% off; play for ONE clean swing. Conservative pullback target = previous swing extreme (p.325, p.351).
- p.310 — Overextension markers: many bars pressing above upper Keltner band + free bars = buying climax; weekly overextension vetoes daily longs. "Change of character" over 3 days flags transition. Complex pullback completes when it reaches the 20-EMA on the higher timeframe.
- p.312 — Warning-sign triad for late-trend entry: divergence after "at least the fifth leg", MACD divergence, slight overextension/potential climax. Permissible only in a strong RS leader.
- p.313 — Large gaps lead to increased volatility. Candle-shadow climax rule: "A session with a long shadow in the direction of the preceding swing is often a small climax"; followed by 2 sessions of vol compression = primed for directional move.
- p.314, 348 — Asset-class trend tendencies: currencies trend longest/best, commodities intermediate, equities most prone to mean reversion and reversal. After a large one-day thrust, a stock/index tends toward a small reversal next day; currencies do not. (ES sits at the mean-reverting end.)
- p.314-315 — Do NOT buy pullbacks following a buying climax; climax must first be worked off by time/consolidation. A lower-TF (60-min) selling climax into the bottom of a daily consolidation flushes weak longs and re-enables longs.
- p.316-319 — High-and-tight flag: strong 1–3 bar thrust, then consolidation holding near the thrust extreme ("mean reversion has failed") = strong pressure; breakout should see immediate vol expansion — "if the trade is going to work well, it should work quickly; be suspicious of markets that go dull and flat following an entry like this."
- p.319-320 — Nested pullback = small consolidation inside a drive from a larger/HTF pattern; Wyckoff spring inside a range validates subsequent breakout.
- p.320-321 — Minor buying-climax spec: parabolic acceleration + free bar + immediate sharp reversal. MACD showed NO divergence while price structure was clearly climactic — price structure > indicator.
- p.322-323 — Complex pullback = two legs down separated by a failed rally = simple pullback on the higher timeframe → moves out of complex pullbacks are cleaner/stronger. Stops can be tighter on complex than simple pullbacks.
- p.325-328 — Pullback failure taxonomy (each = transition signal): (1) failure at/near previous swing (falls short of prior extreme = lack of conviction); (2) failure by strong counter-momentum; (3) failure by going flat — equilibrium, "whatever edge there might have been is gone"; flat multi-bar drift post-entry = scratch. Once a trade is working, tighten stops (a working move that turns back usually becomes complex consolidation, not full reversal).
- p.329 — Trend-termination trades warrant smaller size: extreme volatility/surprise near trend ends.

### Failure test (spring/upthrust)
- p.330-332 — Spec: press beyond a prior extreme, immediate reversal back through it; enter on close of that bar or next; stop just INSIDE the previous trend extreme. Precondition for countertrend trade: a preceding distinct change of character.
- p.332-334 — Variants: second-day entry; stop ≈ high of the small down candle, < one average day's range from entry; trade at ≈half risk. Contexts: after abnormally long consolidation near trend extreme (3–4× the normal 5–8 bar consolidation length — often a trap); after a climax (three pushes, parabolic expansion, free bars); as LTF entry into HTF pattern. Location distinction: consolidations near trend extremes vs breakout bases after protracted ranges.
- p.335-338 — Failure modes: by consolidation (first target should be hit within 3–4 bars, often bar 1 — falling short of first target IS the warning; scratch) and by adverse gap (why half size). Mandatory second entry when high B marginally exceeds high A.

### Parabolic climax regime
- p.339 — Entries inside a climax are problematic (wide spreads, low liquidity, no definable risk point). Two sanctioned plays: failure test on retest of the extreme (must see immediate sharp countertrend follow-through), or an Anti after a sharp change-of-character move.
- p.339-341 — Managing a parabolic trend: trail stop under previous day's low, ratcheted daily. "Overbought/oversold taken alone are dangerous... Strong trends reach overextended levels and just keep going."
- p.341-342 — Climax-failure example (Cotton): FULL classic-climax checklist present (mature trend, accelerating legs, thrusts above channel, glaring divergence, free bars) — and the trend still continued and accelerated. Some large moves offer NO valid entry.

### Anti spec (early new-trend entry)
- p.343-348 — (A) overextended trend; (B) sharp countertrend thrust with distinct change of character (bar out of character, pierces the MA, MACD significant new extreme vs recent history; countertrend swing longer in price AND time than prior counterswings); (C) a reluctant/slow pullback (the Anti) — a sharp clean bounce back to new extremes negates it. Entry on breakdown of prior bar's low; two valid stops only — just beyond the setup-bounce extreme or beyond the trend extreme, never in between. p.345: "slide along the bands" = very strong though potentially overextended trend, no clear fade risk points. p.347: downtrend overextension = multiple tests below lower band + last-gasp sell-off that quickly fails.
- p.349-352 — Anti failures mirror pullback failures: through consolidation (post-entry the market should move immediately; dead/quiet = exit), at previous swing, by strong momentum against. p.350: "it is not necessarily true that better[-looking] patterns have a higher expectancy."

### S/R regime
- p.352-359 — A failure test IS a failed breakout on a lower timeframe. Early-entry-in-base via springs; entering a daily range off a 30-min Anti → stop outside the DAILY range with smaller size. Add-then-fail rule: if you add at the breakout and it fails, exit MORE than you added. Nothing magical about the breakout level; post-breakout pullbacks may violate it. First post-breakout pullbacks are rarely complex (simple = urgency in the new trend; complex pullbacks work off overextension later) → tight stops appropriate there. Early base entry = good location/lower probability; waiting for breakout = poor location/higher probability.

## Ch.11 (skipped) — one regime-relevant claim
- p.369: "Markets exist in different regimes (e.g., trends or trading ranges, high- or low-volatility conditions) and certain kinds of trades will have strings of wins or losses in those conditions" — trade-outcome streaks are regime-conditional (violates i.i.d.); per-setup win-streak clustering is itself a regime detector; Kelly/fixed-fraction math needs regime-conditioning.
