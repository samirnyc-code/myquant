# v0 Regime Engine — Validation Result (GATE FAILED)
**Date:** 2026-07-23 (S81) · **Data:** ES, `_continuous_1m.parquet` resampled, 2021-06→2026-07 (1305 daily bars).
**Scripts:** `regime_features.py` → `regime_v0.py` → `regime_validate.py`. Outputs: `data/regime/validate_*_20260723.csv`, `regime_validate_20260723.png`.

## Verdict
**v0 does not show a real regime edge. The one large effect it produces is fully reproduced by shuffled-return nulls → it is a construction artifact, not a market edge.** No trade logic should be built on v0 state occupancy as-is. The Pythia gate did its job: it stopped us before we built on a mirage.

## What the numbers say (daily, forward return by PRIOR-bar state)
| horizon | bull mean (bp) | bear mean (bp) | bear real vs SHUFFLE-null |
|---|---|---|---|
| h=1  | −1.0 (t −0.20) | +11.8 (t 1.66) | null +12.7 (t 2.00) |
| h=5  | −0.9 (t −0.08) | +62.8 (t 4.72) | null +71.5 (t 4.58) |
| h=20 | −50.7 (t −2.39) | +225.8 (t 8.54) | null +248.5 (t 6.32) |

Two fatal reads:
1. **"Bear" state is followed by big POSITIVE returns** (a bounce), and **"bull" state by flat-to-negative** — the classifier is effectively inverted (index mean-reversion). That alone would be tradeable in reverse *if it were real*.
2. **It is not real.** At every horizon the shuffled-return null (real returns with their order destroyed — no market structure left) reproduces the bear-bounce at the same or larger magnitude. Real h=20 bear +226 bp vs shuffle-null +249 bp. Real is actually *weaker* than noise. The effect is a mechanical property of the state machine, not the market.

## Why (root cause)
- The entry conditions select extremes: BULL fires on a close beyond the **upper** Keltner band + MACD new high (i.e., it buys a top); BEAR fires on a close beyond the **lower** band + MACD new low (buys a bottom). On *any* series — including shuffled noise — points selected at extremes revert. That is what the table measures.
- **State-occupancy is the wrong unit of test.** Grimes never validates "being in a trend"; he validates **events** (a compression breakout bar, a pullback-to-EMA touch) and measures excess return vs baseline. I tested occupancy; occupancy is contaminated by the entry-selection above.
- **Overlapping windows inflate every t-stat.** States dwell ~26 daily bars, so consecutive "bear" bars share 4/5 (h=5) or 19/20 (h=20) of their forward window. The effective N is ~1/h of the reported N; the t=8.54 is not 8.54 independent-sample sigmas. Even the artifact's "significance" is overstated.
- 30m: everything is < 5 bp with modest t — no edge there either, artifact or otherwise.

## What this does NOT mean
- It does **not** mean Grimes is wrong or the features are useless. It means *this composite state machine, tested by occupancy, on ES, does not separate returns beyond mechanical selection.*
- The features themselves (Keltner, MACD 3-10-16, compression ratio, GER, Dow zigzag) are computed correctly and are reusable.

## Recommended next step — test his EVENTS, not our states
Replicate Grimes's own event studies on ES, scored the same way (excess vs baseline at +1..+20, against the rw/shuffle/ar1 nulls). These are the ones he reports as *surviving in futures*:
1. **Volatility-compression breakout** (5/40-day ATR < 0.5 on prior bar; trigger day TR ≥ 5-day ATR, close top-half & above prior close). He reports +128 bp** by d4, 73% up d5. If this does not replicate on ES vs the shuffle null, the futures edge he claims is absent in our sample and the program stops.
2. **Keltner pullback to 20-EMA** after a band close (his "essence of trend trading"). Reported futures sell −59 bp** d1.
3. **Donchian 100/260-day breakout** (futures momentum).
Only events that beat the nulls become state-machine building blocks. Rebuild the engine around *those*, not around band-touch occupancy.

## Files
- `data/regime/validate_daily_20260723.csv`, `validate_30m_20260723.csv` — full per-state × horizon tables.
- `data/regime/validate_nulls_20260723.csv` — rw / shuffle / ar1 null tables.
- `data/regime/regime_validate_20260723.png` — bars = real daily mean forward return by state; gold = null min/max band. Real bars sit inside the null band → no separation.
