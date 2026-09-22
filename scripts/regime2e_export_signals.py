"""Export REGIME-2E entries in the ES-sim dashboard's signal-upload format.

Format (bar_analysis.parse_signals): whitespace-delimited, one row per signal:
    Num  Type  Dir  DD/MM/YYYY  HH:MM:SS  BarNum  Price  Stop
  - Dir   : Long / Short
  - Price : SignalPrice = the retest LIMIT entry (trigger -/+ 6t)   [engine's entry]
  - Stop  : StopPrice   = 0.30 x ADR10 from entry (8t floor)        [ref; sweeps override]
  - BarNum: the 5-min bar index within the session (fill bar)

This exports RAW gate-passing 2E entries (every signal, both directions) — the
dashboard applies its OWN execution/stop/target/flip/prop logic on top, so upload
this, then drive the Bar Analysis sweeps + Prop Sim tab against it. That is how the
entry LOGIC gets into the sim: the dashboard consumes these entries and re-simulates
fills independently (an external check on the python fills).

  python scripts/regime2e_export_signals.py [--limit N]
Output: reports/regime2e/regime2e_signals_for_dashboard.txt  (+ .csv mirror)
"""
import sys
from collections import deque
from pathlib import Path

import numpy as np
import pandas as pd

TICK = 0.25
STOP_MULT = 0.30; STOP_FLOOR_T = 8
GAP_MAX = 0.54; SMA_N = 20; ADR_N = 10; TREND_MULT = 1.6
REPO = Path(__file__).resolve().parent.parent
TICKD = REPO / "data" / "ticks_continuous"
OUTDIR = REPO / "reports" / "regime2e"

sys.path.insert(0, str(REPO / "scripts"))
from regime2e_nt_diff import day_frames                          # noqa: E402
from regime2e_flip_scale_sim import signals_for_day             # noqa: E402


def main():
    limit = int(sys.argv[sys.argv.index("--limit") + 1]) if "--limit" in sys.argv else None
    dates = sorted(p.stem for p in TICKD.glob("2*.parquet"))
    if limit:
        dates = dates[-limit:]
    ranges = deque(maxlen=ADR_N); closes = deque(maxlen=SMA_N)
    prev_close = prev_range = None
    rows = []; num = 0
    for d in dates:
        g, tP, tbar = day_frames(d)
        if g is None or len(g) < 30:
            continue
        day_hi, day_lo = float(np.max(tP)), float(np.min(tP))
        day_cl, day_op = float(tP[-1]), float(tP[0])
        adr_prior = np.mean(ranges) if len(ranges) == ADR_N else None
        tdy = (prev_range > TREND_MULT * adr_prior) if (adr_prior is not None and prev_range is not None) else None
        if prev_range is not None:
            ranges.append(prev_range)
        if prev_close is not None:
            closes.append(prev_close)
        sma20 = np.mean(closes) if len(closes) == SMA_N else None
        adr10 = np.mean(ranges) if len(ranges) == ADR_N else None
        if not (adr10 is None or sma20 is None or prev_close is None or tdy is None):
            if abs(day_op - prev_close) / prev_close * 100.0 <= GAP_MAX and not tdy:
                stop_pts = max(round(STOP_MULT * adr10 / TICK) * TICK, STOP_FLOOR_T * TICK)
                for jfl, dr, lim in signals_for_day(g, tP, tbar, sma20, adr10):
                    num += 1
                    short = dr == "S"
                    stop_px = lim + stop_pts if short else lim - stop_pts
                    bar = int(tbar[jfl])                       # tick index -> 5-min bar index
                    dt = pd.Timestamp(g["DateTime"].iloc[min(bar, len(g) - 1)])  # bar-END time
                    rows.append({
                        "Num": num, "Type": "2E", "Dir": "Short" if short else "Long",
                        "Date": dt.strftime("%d/%m/%Y"), "Time": dt.strftime("%H:%M:%S"),
                        "BarNum": bar, "Price": round(lim, 2), "Stop": round(stop_px, 2),
                    })
        prev_close, prev_range = day_cl, day_hi - day_lo

    OUTDIR.mkdir(parents=True, exist_ok=True)
    txt = OUTDIR / "regime2e_signals_for_dashboard.txt"
    with open(txt, "w") as f:
        for r in rows:
            f.write(f"{r['Num']}\t{r['Type']}\t{r['Dir']}\t{r['Date']}\t{r['Time']}\t"
                    f"{r['BarNum']}\t{r['Price']}\t{r['Stop']}\n")
    pd.DataFrame(rows).to_csv(OUTDIR / "regime2e_signals_for_dashboard.csv", index=False)
    print(f"exported {len(rows)} 2E signals  ({rows[0]['Date']} .. {rows[-1]['Date']})")
    print("sample:")
    for r in rows[:3]:
        print(f"  {r['Num']}\t{r['Type']}\t{r['Dir']}\t{r['Date']}\t{r['Time']}\t{r['BarNum']}\t{r['Price']}\t{r['Stop']}")
    print(f"\nupload file: {txt}")


if __name__ == "__main__":
    main()
