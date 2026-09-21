# MyWedge — Python port of the NinjaScript MyWedge indicator

Reproduces the MyWedge wedge signals (W_Long / W_Short) from bar data.
Pure Python standard library — **no pip installs**. Needs **Python 3.9+**.

## Files
- `mywedge.py`         — the indicator (`compute_mywedge()`), faithful port of MyWedge.cs
- `run_mywedge.py`     — CLI: reads a bar export, writes a signals CSV
- `regime_tracker.py`  — `compute_regime()`: Bull/Bear/Range classifier built on mywedge's swing pivots
- `run_regime.py`      — CLI: reads a bar export (or generates a synthetic demo), writes `regime_data.json`
- `plot_regime.py`     — renders `regime_data.json` as a hi-res static PNG chart
- `build_artifact.py`  — renders `regime_data.json` as an interactive zoomable HTML chart

## Usage
Export bars from NinjaTrader as a text file, whitespace-separated, one bar per line:
    Date Time O H L C
(Date `dd/mm/yyyy`, Time `HH:MM:SS`; thousands commas OK; header/dashed lines auto-skipped.)

Then:
    python3 run_mywedge.py BARS.txt --out signals.csv

Options:
    --session eth        ETH sessions, 17:00 CT roll (default)
    --session rth-cash   new session each 08:30 CT weekday
    --tz Europe/Berlin   timezone of the bar timestamps (default; use America/Chicago if CT)
    --no-w2l             disable the 2-leg wedge (ShowW2L)
    --validate SIG.txt   compare output vs an author signal export

Output CSV columns:
    Counter, Direction (W_Long/W_Short), Date, Time, O,H,L,C, WedgeSB, MC_Bull, MC_Bear

## Indicator defaults (MyWedge.cs SetDefaults)
lookback=12, wedge_symmetry=4, ol_sensitivity=1, ctsb_ignore=True, ib_ignore=True,
show_wedge_sb=True, signal_bar_ibs=66.0, continue_mc=False, continue_on_gap=False, tick_size=0.25
(ShowW2L on.) These are set inside run_mywedge.py and can be edited there.

Validated: RTH signal layer matched the author's NinjaTrader export 100% on a 95-day sample.

## Regime tracker (Bull / Bear / Trading Range)

Built on top of `compute_mywedge()`'s swing_low/swing_high pivots — classic Dow-theory
structure: a new swing high above the prior swing high + a new swing low above the prior
swing low = Bull; the mirror = Bear; anything else (or too few pivots yet) = Range. A
regime change only takes effect once confirmed by two consecutive pivots in the same
direction, so a single wick-driven swing against an otherwise intact trend doesn't flip
the label on its own.

    python3 run_regime.py [BARS.txt] --out regime_data.json   # same bar format as run_mywedge.py;
                                                                # omit BARS.txt for a synthetic demo series
    python3 plot_regime.py regime_data.json --out regime_chart.png
    python3 build_artifact.py regime_data.json --out regime_artifact.html

`regime_data.json` holds per-bar OHLC, the per-bar regime label, the regime segment list
(start/end bar index + label), and the swing pivot points — everything the two chart
renderers need.
