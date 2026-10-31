# Correct-trades-only intraday DD — 2026-10-30 (shadow_stop_monitor's exact methodology)

## The 10 trades that were supposed to execute under the gameplan's rules

- auto_20261030_083114 (eodic_p): entered 2026-10-30 08:31, final pnl -1703.26
- auto_20261030_083220 (eodic_c): entered 2026-10-30 08:32, final pnl -8.26
- auto_20261030_083331 (eodfly_p): entered 2026-10-30 08:33, final pnl -103.26
- auto_20261030_083446 (eodfly_c): entered 2026-10-30 08:34, final pnl 26.74
- auto_20261030_083523 (openic_p): entered 2026-10-30 08:35, final pnl 96.74
- auto_20261030_083640 (openic_c): entered 2026-10-30 08:36, final pnl 16.74
- auto_20261030_083737 (openfly_p): entered 2026-10-30 08:37, final pnl -1443.26
- auto_20261030_083844 (openfly_c): entered 2026-10-30 08:38, final pnl 916.74
- auto_20261030_083944 (gx_bps): entered 2026-10-30 08:39, final pnl -333.26
- auto_20261030_085926 (gx_bcs): entered 2026-10-30 08:59, final pnl 26.74  [FLAG] late fill +29min -- NOT a clean on-time execution

**Final P&L, correct trades only: -2507.60**
(gx_bcs's only available fill is included above since there is no clean alternative in the log -- flagged, not fabricated.)

## Intraday DD (shadow_stop_monitor.portfolio_curve, same method as the Analytics tab)

- Real-marks window: 2026-10-30 09:32:34 -> 2026-10-30 11:48:49 CT
- **Trough: -1605.00 at 10:24:06 CT**
- Crossed WARN (-2000): no
- Crossed STOP (-3000): no

- Same gap as every other intraday reconstruction this session: `options_mark.py` died ~11:35 CT, so this trough is only provable up to 2026-10-30 11:48:49 CT -- it is a FLOOR, not a full-day guarantee.

## For comparison, the CURRENT (bug-inflated, n=27) shadow_stop_log.csv row

- `2026-10-30,27,-3590,10:24,True,10:12,-2015,True,10:24,-3590,-3010,HURT,...`
- trough -3590 @ 10:24 (27 trades) vs trough -1605.00 @ 10:24:06 CT (10 correct trades)