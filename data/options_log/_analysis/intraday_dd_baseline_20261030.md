# Intraday drawdown — 2026-10-30, baseline (non-duplicate) trades only

- 10 baseline trade_ids: auto_20261030_083114, auto_20261030_083220, auto_20261030_083331, auto_20261030_083446, auto_20261030_083523, auto_20261030_083640, auto_20261030_083737, auto_20261030_083844, auto_20261030_083944, auto_20261030_085926
- Real marks window: 2026-10-30 09:32:34 -> 2026-10-30 11:48:49 CT (59 snapshots)
- Book unrealized P&L at first mark (2026-10-30 09:32:34): -130.00
- Book unrealized P&L at last real mark (2026-10-30 11:48:49): -1405.00

## Max intraday drawdown OBSERVED (real marks only, 09:32-11:48 CT)

- **-1670.00** at 2026-10-30 10:24:06 CT (book unrealized -1605.00, prior peak 65.00)

## Known gap

- `options_mark.py` died ~11:35 CT, hit its 5/day restart cap, marks.csv has nothing after 11:48:49 CT. There is NO real intraday mark for the baseline trades between 11:48:49 CT and the 16:00 CT close/expiry.
- Actual EOD outcome for these 10 trades (from trades.parquet, all expired at 16:00): **-2507.60**

## Gap bridged with an intrinsic-value estimate (NOT a real mark)

- Used `data/options_sim/underlying_20261030.csv` (spot tape, ~1/min all day) to price the 10 baseline legs by intrinsic value only (credit + intrinsic owed, zero extrinsic/time value) at every tape timestamp.
- Calibration: averaged (real mark - intrinsic estimate) over the 127 tape points inside the real-marks window to correct for the missing extrinsic value -> offset +1080.57. Applied as a constant shift to the post-gap intrinsic series (extrinsic value decays over the afternoon so this constant-offset approximation gets LESS accurate the further past 11:48:49 CT it's read — treat it as directional, not exact).
- **Estimated worst point after the gap: -3029.43 at 2026-10-30 13:53:17 CT** (est. book unrealized -2964.43, spot 7529.30)
- Combined with the observed window, the estimated full-day max intraday drawdown is **-3029.43**, occurring in the UNOBSERVED post-11:48 window (estimate, not a real mark).

- Full extended curve (real marks + post-gap estimate) in `intraday_curve_baseline_extended_20261030.csv`.