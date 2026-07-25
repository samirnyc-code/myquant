# REGIME-2E · Order-Flow Research Design (PAUSED — come back to this)

Status: design agreed 2026-07-25, execution deferred. Guards against overfitting are the point.

## Data tiers = each source's JOB (decided by history depth)
| source | metrics | history | role |
|---|---|---|---|
| **Footprint** (reconstructed from ticks, validated vs MzPack) | delta, CVD, bar-imbalance, absorption, VP/POC/VAH/VAL, HVN/LVN, single prints | **5yr full** | **CONFIRMATORY** — only tier allowed to validate an edge |
| **L2 / MBP-10** | resting liquidity, book imbalance, walls, thinning, pull/stack | partial | **SUPPORTING** |
| **L3 / MBO** | true absorption vs replenishment, iceberg, queue position, spoof/pull | **6mo (growing)** | **EXPLANATORY + FILL-REALISM only — never its own backtest** |

L3 reframe (dodges small-sample trap): NOT new alpha. Use for (a) mechanism confirmation of a footprint
signal (is "absorption" a real refilling iceberg?), (b) FILL REALISM — does the 6t retest limit fill given
queue position? (closes an open validation gate, zero overfit risk).

## Pre-registered hypotheses (mechanism + ONE directional prediction each; written before testing)
1. WT pullback: absorption of the counter-trend push at the pullback extreme → continuation.
2. Signal bar: delta/CVD divergence (2nd entry on lower opposing delta = exhaustion) → better.
3. **Fade location (highest value — thin 105-trade book):** failed 2EL fails AT a real ceiling (prior POC/VAH/HVN)
   with absorption of trapped breakout buyers → fade works; fades in no-man's-land fail.
4. Regime flip: flip carried by aggressive delta expansion (real) vs on absorption/thin delta (false) → condition the engine.
5. VP context: entry into value / at HVN (support) vs in LVN (air pocket) → HVN continues, LVN fails.
6. Entry fill (L2): favorable book imbalance at the retest level → better outcome.

## Anti-overfitting protocol (the HVL playbook + order-flow guards)
1. **Conditioner, NOT a new signal** — test on the existing 678 trades (winner/loser separation), never invent new trades.
2. **Hypothesis-first + comparison budget** — pre-register the list; log EVERY test incl. failures (no silent dropping).
3. **Univariate + coarse thresholds only** (median/tercile); report the full monotonic relationship, not the best cut.
4. **Two mandatory gates:** hold on BOTH train(≤2023) & test(2024+); orthogonal to gap filter & to each other.
5. **Mechanism gate** — reject anything that works without a coherent microstructure reason.
6. **Tiered confirmation** — footprint validates, L3 explains, L2 supports; nothing graduates on L3 alone.
7. **Final bar (HVL's):** improves risk-adj on existing trades + survives OOS + orthogonal + mechanistic → *candidate size-lean, forward-unproven*. Not shipped.

## First moves when resumed
1. Catalog L2/L3 pulls on arrival; re-validate footprint reconstruction on current data.
2. Fade-location hypothesis (#3) first — highest value, conditioner on the 105 fades.
3. L3 fill-realism (closes a gate, no overfit risk).
4. Then pullback-absorption (#1) + regime-flip confirmation (#4) on the full 678.

## Bridge to the annotation gallery
Structured annotations (tags + bar-range) from the trade-review gallery BECOME the candidate features here:
a tag like "absorption before entry" → aggregate across trades → test as a conditioner under this protocol.
The gallery is the hypothesis generator; this protocol is the filter.
