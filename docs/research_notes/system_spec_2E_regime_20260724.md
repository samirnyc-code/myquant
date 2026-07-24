# ES Regime × Second-Entry System — Spec & Forward Expectations
**For review — Samir / Thomas · 2026-07-24 · branch `regime/indep` (S83)**
Everything below is tick-backtested 2021-06→2026-07 (1,267 sessions), strict fills,
net of $5 RT + 1 tick exit slip, 1 ES. Every claim traces to a committed CSV.

## 1. The system (exact parameters)

| component | rule |
|---|---|
| Instrument / chart | ES futures, **5-minute time bars, RTH session**, day-scoped (all state resets at open). Tick-level execution |
| Regime | Tick-driven phase machine v4: day opens NEUTRAL; tick > latest swing-high pivot with a higher-low present → BULL (mirror → BEAR); tick through standing major HL/LH → NEUTRAL. **Wick break, not close** |
| Signal | S61 second entry only (2EL/2ES; origin-reset count; increment #2). No first entries, no third entries |
| Direction | 2EL only while machine = BULL; 2ES only while machine = BEAR, **evaluated at the trigger tick**. Regime flips while in a trade are ignored |
| Day filter | **Skip the day's new entries when \|RTH open − prior RTH close\| / prior close > 0.54%** (threshold = 75th pctile of train years — derived, not swept) |
| Entry | On trigger touch (S61 level + 1t): **limit 6 ticks back from the trigger**. Never chase. Backtest requires trade-through + 1 tick |
| Entry window | Fills allowed session open +30 min → +330 min (09:00–13:59 machine-tz). Working orders cancelled at window end |
| Order lifetime | **Cancel unfilled limit 6 bars (30 min) after the trigger** — operational rule; its PF contribution is NOT counted in expectations |
| Stop | **0.30 × ADR10** (prior 10-day avg daily RTH range), rounded to nearest tick, floor 8 ticks. Median ≈ 15.75 pts. Never widened, never tightened |
| Target | **None. Exit at session close (EOD flat), or the stop.** Every fixed target tested destroys the edge |
| Concurrency | Same-direction adds allowed (≤3); never opposing positions; opposite qualifying fill = stop-and-reverse |
| Costs modeled | $5 RT + 1 tick exit slip; entry slip zero by limit construction (verified robust at 2 ticks) |

## 2. Backtested record (the audited numbers)

| view | n | net | $/tr | PF |
|---|---|---|---|---|
| Lifetime | 630 | +$82.7k | +131 | 1.39 |
| Train ≤2023 | 283 | +$40.8k | +144 | 1.44 |
| **Test 2024-26** | **347** | **+$41.9k** | **+121** | **1.36** |
| Ex-2022 | 540 | +$52.1k | +97 | 1.30 |
| 2-tick slip | 630 | +$74.8k | +119 | 1.35 |

Long PF 1.44 / Short PF 1.35 — sides alternate leadership by year (not a directional bet).
Green all 6 calendar years (1.10–1.79). All ADR-vol quintiles green (1.14–1.92).
Win 45% · avg win ≈ +$1,010 · avg loss ≈ −$700 · ~10.4 trades/month.

**Validation that passed:** out-of-sample split; parameter plateaus on every free
parameter (stop mult, retest depth, gap threshold, window); gap filter transfers to an
untuned config (PF 1.12→1.27 both halves); removed gap-day trades are broadly bad
(median −$517), not tail-driven; causality audit (fully causal, live-portable).
**Known concentration:** top 10 trades ≈ 42% of net (intrinsic to no-target EOD books) —
the system must be traded so it cannot miss runners (automated, no discretionary exits).

## 3. Forward-looking expectations (plan, not hope)

| metric | planning value | basis |
|---|---|---|
| PF | **1.25–1.30** | below test-half 1.36; discounts residual selection |
| Expectancy | **+$85–105 / trade** | ~20–30% haircut off test-half $121 |
| Frequency | ~10 trades / month | 630 / 60.5 months |
| Monthly | **≈ +$900–1,100 per ES**, highly lumpy | tail-driven; flat months are normal |
| Max drawdown to size for | **−$21k per ES** (MC worst-5%), realized-typical −$13k | 5,000-path reshuffle |
| Underwater stretches | expect 6–18 months without new highs | 2023-like years pay ≈ flat |
| Account per 1 ES | **$30–35k** | worst-5% DD × 1.5 + margin |
| MES at $5 RT | **not viable** (commission-dead) | costs table |
| Best / worst weather | trending years (2022-like: PF ~1.8) / chop+high-vol (PF ~1.1) | yearly + ADR buckets |

## 4. Live watch flags (review monthly)
1. **2026 gap days flipped positive** (+$258/tr, PF 1.46) — first place gap-filter decay
   would show. If it persists 2 more quarters, re-examine the filter.
2. **Strong signal-bar cut** is era-unstable (train 0.78 / test 2.9) — track as a paper
   book; do not trade it.
3. **Gap-day side book** (RevFT:BO both dirs, MicroChannel CC4 longs — both halves green,
   ~+$60k/5yr candidate) — forward-validate before capital.
4. Kill criteria: 12-month PF < 1.0, or DD beyond −$25k (MC worst-1%), or either side
   (L/S) persistently < 1.0 for 2+ quarters.

## 5. What was tried and failed (so it isn't re-litigated)
Raw 2E (PF 0.78) · every fixed target 0.5R–4R · exits on regime flips (destroys edge) ·
first entries (fail OOS) · close-confirmed regime · sticky regime · 1m/15m/30m/60m and
6500-volume bars (5m time is the peak) · ETH/overnight (dead; 24h machine even hurts RTH) ·
BE-moves, scale-outs, 30-min stop-tighten (fill fantasy — retracted) · MES at $5 RT ·
EMA-touch M2B on ES (inverts) · chase entries on gap days.

*Reproduction: scripts + dated CSVs on `regime/indep`; validation battery in
`data/regime/`; full report artifact available on request.*
