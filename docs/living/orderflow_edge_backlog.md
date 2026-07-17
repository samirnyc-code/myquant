# Order-Flow × Gamma-Level Edge Backlog (S75)

**Status:** Living. Hypotheses to backtest → break → forward-test. NOTHING here is
validated until it survives our own walk-forward on real data. Sourced from the S75
MzPack 5-indicator research + our validated free footprint pipeline.

## The pipeline we now have (validated)
- **Free footprint reconstruction** from ES ticks via `nt8/FootprintExporter.cs` (Tick
  Replay). **Validated exact vs MzPack** (delta / buy% / sell% / POC — 0 error on 7/16
  14:38–14:44 bars; imbalance cells match their bold highlights). `footprint_metrics.py`
  derives POC/VA/imbalance/absorption-proxy/CVD from the ladder.
- **5yr ES ticks** loaded in NT8 → footprint reconstructable for the full history.
- **MQ gamma-level history** (SPX+Mag7 ~4.8yr, futures ~2yr) — `*_mq_levels_history.csv`.
- **ORATS** (arriving) — per-strike OI+greeks to 2007 for the options side.

## Extraction priority (which MzPack data to pull; all via the public NinjaScript API)
1. **mzVolumeProfile** — `IVolumeProfile` (POC/VAH/VAL/VWAP/Delta/HVN/LVN, naked flags).
   Backtestable. **Strongest structural fit.**
2. **mzVolumeDelta** — `IVolumeDeltaBar` (Delta, CumulativeDelta, DeltaHi/Lo, large-
   trade-filtered CD, IcebergVolume). Backtestable (plain CD robust; iceberg-CD fragile).
3. **mzBigTrade** — tape icebergs / big trades / sweeps = **backtestable**; DOM-refill
   icebergs + DOM pressure = **live-only (L2)**. Verify the event API on trial install.
4. **mzDeltaDivergence** — backtestable; **ZigZag repaints** — timestamp at swing-confirm
   or it leaks future info. (Reconstructable ourselves from CD + our own ZigZag.)
5. **mzMarketDepth** — **live-only, un-backtestable** (no historical L2). Log live only.

## The hypotheses (pre-registered — test THESE, don't fish)
Legend: ★ likely-real core · ◐ conditional · ☂ best idea / least testable

1. **★ {Naked VPOC ≈ MQ put-support → magnet}** — naked VPOC within N ticks below PS/GW0
   → price gravitates to it before the level resolves. Data: `IVolumeProfile.POC`+naked,
   MQ levels. **Backtestable now.**
2. **★ {HVN ≡ HVL → level holds}** — volume HVN coinciding (±N) with HVL → first touch
   mean-reverts; fade. **Backtestable now.**
3. **◐ {LVN between spot & 1D-band → fast traversal}** — air-pocket to the band (cheap
   0DTE directional). Backtestable; LVNs also fail — test carefully.
4. **◐ {CD divergence into CR → fade}** — SHORT delta-divergence confirmed into call-
   resistance → mean-revert. Backtestable (timestamp at swing-confirm). Real only as a
   filtered combo; divergence alone is noise.
5. **★ {Large-filtered-CD absorption at HVL → holds}** — approaching HVL, aggressive
   filtered size absorbed w/o price progress (delta up, price flat) → fade. Uses
   `DeltaHi/Lo`+`TradeFilterMin`. **Backtestable now** (plain delta) / sharper live.
6. **◐ {Tape iceberg at PS/HVL → level defended}** — iceberg within N ticks of the level
   → bounce. Backtestable (tape mode). Sparse events → small-sample risk.
7. **◐ {Sweep through 1D-band, no absorption → continuation}** — distinguishes real breaks
   from fakeouts. Backtestable (sweep range+side). 
8. **☂ {DOM-refill iceberg + positive DOM pressure at PS → strong defense}** — MzPack's
   "Reversal Order Flow Cluster." **Live-only (L2)** — forward-test only; log to build data.

## Skeptic's rules (carried in from the retracted-edge history)
- **Repaint / lookahead:** ZigZag divergence (#4) and iceberg-adjusted CD (#5,#6) can leak
  or differ live-vs-historical if ticks are timestamps-only. Timestamp at confirmation;
  validate iceberg-CD against a live day first.
- **Sample size:** iceberg/sweep events (#6,#7) are rare — 14-day trial ≠ statistical
  power. Hypothesis-generation, not confirmation.
- **Multiple testing:** pre-register the 8 above; require OOS confirmation; treat PF>3 as a
  bug until proven (see [[backtest-fill-realism]]).
- **Core vs noise:** #1/#2/#5 are the likely-real core (structural magnets + absorption are
  documented microstructure). #8 is the best idea but least testable. Deprioritize raw
  mzMarketDepth signals (noisiest, un-backtestable).

## Verify on the 14-day MzPack trial
- Exact public event/property API for mzBigTrade (iceberg/big-trade object) & mzDeltaDivergence signal.
- Whether mzVolumeProfile exposes HVN/LVN/naked flags + the per-price volume array publicly (else recompute).
- Whether our historical ES ticks are full bid/ask or timestamps-only (sets iceberg-CD fidelity).

## Next build steps
1. Re-run the upgraded `FootprintExporter` (emits `ES_bars.csv` MinDelta/MaxDelta/Open/Close/DeltaRate/UnfAuction).
2. Map ES footprint ↔ SPX MQ levels (basis) and run **hypotheses #1,#2,#5** on 7/16 first, then the 5yr history.
3. Build `orderflow_at_levels.py`: for each MQ-level touch, tag the footprint signature (absorption/imbalance/divergence) → forward-return study.
4. Wire the winners into the live desk as **conditioned** entry criteria (criteria stay FROZEN until backtest-validated).
