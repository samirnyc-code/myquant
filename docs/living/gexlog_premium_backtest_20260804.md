# GexLog premium-selling thesis — baseline backtest (2026-08-04)

Script: `scripts/gexlog_premium_backtest.py`
Outputs: `data/options_sim/gexlog_bt_20260804.csv` (trade-level, L1 wing50 slip.25),
`data/options_sim/gexlog_bt_summary_20260804.csv` (sweep).

## What was tested
Weekly non-overlapping SPX iron condor, ~7 DTE, short strikes at the VIX-implied
expected-move band, fixed wing, held to cash settlement, real OptionsDX bid/ask +
slippage sweep, 2010–2023 (609 trades).
- **L0** = flat 1σ EM band every week.
- **L1** = VIX-regime-scaled band (k=1.0 if VIX<20, 1.15 if 20–30, 1.35 if >30) —
  the operationalization of the GexLog-EM-vs-MQ-1D finding.

## Honest data limits
- GexLog's archive (2026-04+) does NOT overlap historical chains (2010–2023), so the
  GexLog GO/WAIT signal is **not backtested here** — forward-only.
- True daily 0DTE didn't exist pre-2022 → weekly 7-DTE proxy used for regime coverage.
- Only the reconstructable core (VIX-formula EM band + VIX-regime scaling) is tested.

## Result (wing 50, slip 0.25)
| | Total | PF | Win | MaxDD | Tail(worst5%) |
|---|---|---|---|---|---|
| L0 flat 1σ | +$28.1k | 1.23 | 90% | −$18.9k | −$3.5k |
| L1 VIX-scaled | +$33.4k | 1.35 | 92% | −$17.0k | −$3.0k |

**VIX-regime band scaling works:** it flips the 20–30 VIX bucket from −$4.8k (PF 0.91)
to +$3.2k (PF 1.10) and cut the 2020 loss from −$9.6k to −$4.8k.

## Verdict
- Unconditional EM-band premium selling is **marginal** (PF 1.2–1.35), profitable in
  calm 2010–2017, **losing in 2018 (−$5.9k) and 2020 (−$9.6k)**. Fragile to slippage.
- The VIX-regime conditioning (the GexLog finding) adds **real, measurable** value.
- Does **not** prove a tradeable standalone edge. The thesis edge must come from GATING
  (GexLog GO/WAIT + the validated stochastics %K8<15&SMA100 signal) — un-backtestable
  historically, so next step is forward paper-validation + management rules (no stops
  used here; every tail is a full-width loss).

## Next
1. Add management (fast exit / roll) — the STMR system's SMA5 exit gave PF 4.45; the
   held-to-expiry no-stop version here is the floor, not the ceiling.
2. Forward-log GexLog GO/WAIT vs outcomes (pull_archive.py) to test the gate.
3. Layer the stochastics directional skew on the recent/forward window.
