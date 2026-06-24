# ER10 look-ahead — headless rerun WITH the bug (2026-06-24)

> ⚠️ This DELIBERATELY reproduces the pre-S34 `merge_asof` look-ahead to show its inflation. The live pipeline is fixed (causal); nothing here changes production code — it imports the reproduction helpers from `er_lookahead_tab.py` and drives the production engine.

**Signal set:** `ba_signals_mc.parquet` (5,580 signals)  **Gate:** ER10 ≥ 0.70  **Exec:** 1.0R single-leg, 1c, entry_slip=1t, exit_slip=0, stop_offset=1t, comm $4.36 RT.

## Gate decision impact (rows with a defined causal ER10)

- valid: **5,566** — pre-fix gate passes **3,368**, causal passes **5,398**.
- decisions FLIPPED by the look-ahead: **2,266** (40.7%) — phantom PASS (chop snuck in) **118**, phantom BLOCK (good signal tossed) **2,148**.

## Metrics — Pre-fix (look-ahead) vs Causal (now live)

| Metric | Pre-fix (look-ahead) | Causal (live) |
|---|---|---|
| Signals (total) | 5,580 | 5,580 |
| Filtered out (gate) | 2,304 | 279 |
| Trades (filled) | 3,276 | 5,301 |
| Win % | 61.7% | 52.4% |
| Net P&L $ | $629,692 | $269,863 |
| Expectancy $/trade | $192.21 | $50.91 |
| Expectancy R | 0.212 | 0.052 |
| Profit Factor | 1.78 | 1.17 |
| SQN | 2.51 | 0.60 |
| PROM | 34.32 | 7.77 |
| Max Drawdown $ | $-17,128 | $-28,332 |
| Avg Win $ | $722 | $723 |
| Avg Loss $ | $-660 | $-688 |
| Win/Loss ratio | 1.09 | 1.05 |
| Sharpe (notional) | 4.68 | 1.55 |
| CAGR (notional) % | 0.6% | 0.3% |

**Net P&L:** causal − pre-fix = **$-359,829**  |  **Expectancy/trade:** **$-141.31**.  The pre-fix column is the inflated look-ahead result; the gap is the bug.
