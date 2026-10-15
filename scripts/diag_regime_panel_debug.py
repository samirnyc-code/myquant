"""Diagnose RegimeTrackerPanel.cs disappearing/blanking reports.

Reads the indicator's own DebugLog CSV (Documents\\regime_tracker_panel_debug_<instrument>.csv,
one row per OnBarUpdate + a throttled ~1s OnRender heartbeat row, see RegimeTrackerPanel.cs)
and reports:
  - gaps in the OnRender heartbeat (>3s = OnRender stopped firing -> the panel actually
    stopped painting, not just showing an unchanging value)
  - every CurrentRegime value transition with timestamp/bar, so a reported "it disappeared
    around <time>" can be cross-checked against what the engine was doing right then
  - any row where ChartBarsNull/BarsNull/RenderTargetNull tripped (the early-return guards
    in OnRender -- any of these would mean OnRender ran but painted nothing that pass)

Saves a dated findings CSV/txt next to the source so this is a committed work product, not
a throwaway inline check (S80 persist rule).
"""
import csv
import sys
from datetime import datetime
from pathlib import Path

SRC = Path(r"C:\Users\Admin\Documents\regime_tracker_panel_debug_ES.csv")
OUT_DIR = Path(__file__).resolve().parent.parent / "scratchpad_out"
OUT_DIR.mkdir(exist_ok=True)


def main():
    rows = []
    with SRC.open() as f:
        for row in csv.DictReader(f):
            rows.append(row)

    print(f"source: {SRC}")
    print(f"total rows: {len(rows)}")
    if not rows:
        print("EMPTY FILE")
        return

    render_rows = [r for r in rows if r["Source"] == "OnRender"]
    print(f"OnRender rows: {len(render_rows)}")

    # gaps in the OnRender heartbeat
    prev_t = None
    gaps = []
    for r in render_rows:
        t = datetime.strptime(r["WallClock"], "%Y-%m-%d %H:%M:%S.%f")
        if prev_t is not None:
            delta = (t - prev_t).total_seconds()
            if delta > 3:
                gaps.append((prev_t.isoformat(), t.isoformat(), delta))
        prev_t = t

    print(f"\nOnRender heartbeat gaps > 3s: {len(gaps)}")
    for g in gaps:
        print(f"  {g[0]} -> {g[1]}  ({g[2]:.1f}s gap)")

    # null-guard trips
    null_trips = [r for r in rows if r["ChartBarsNull"] == "1" or r["BarsNull"] == "1" or r["RenderTargetNull"] == "1"]
    print(f"\nrows with a null-guard tripped: {len(null_trips)}")
    for r in null_trips[:20]:
        print(f"  {r['WallClock']} {r['Source']} ChartBarsNull={r['ChartBarsNull']} BarsNull={r['BarsNull']} RenderTargetNull={r['RenderTargetNull']} Note={r['Note']}")

    # regime value transitions
    prev_reg = None
    changes = []
    for r in rows:
        reg = r["CurrentRegime"]
        if reg != prev_reg:
            changes.append((r["WallClock"], r["Source"], r["BarsInProgress"], r["CurrentBar"], reg))
            prev_reg = reg

    print(f"\nCurrentRegime transitions: {len(changes)}")
    for c in changes:
        print(f"  {c[0]}  src={c[1]} bip={c[2]} bar={c[3]}  regime={c[4]}")

    # first/last timestamp overall
    first_t = datetime.strptime(rows[0]["WallClock"], "%Y-%m-%d %H:%M:%S.%f")
    last_t = datetime.strptime(rows[-1]["WallClock"], "%Y-%m-%d %H:%M:%S.%f")
    print(f"\nlog spans: {first_t.isoformat()} -> {last_t.isoformat()}  ({(last_t-first_t).total_seconds():.1f}s)")

    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    out_path = OUT_DIR / f"regime_panel_debug_diag_{stamp}.txt"
    with out_path.open("w") as f:
        f.write(f"source: {SRC}\n")
        f.write(f"total rows: {len(rows)}\n")
        f.write(f"log spans: {first_t.isoformat()} -> {last_t.isoformat()}\n\n")
        f.write(f"OnRender heartbeat gaps > 3s: {len(gaps)}\n")
        for g in gaps:
            f.write(f"  {g[0]} -> {g[1]}  ({g[2]:.1f}s gap)\n")
        f.write(f"\nrows with a null-guard tripped: {len(null_trips)}\n")
        for r in null_trips:
            f.write(f"  {r['WallClock']} {r['Source']} ChartBarsNull={r['ChartBarsNull']} BarsNull={r['BarsNull']} RenderTargetNull={r['RenderTargetNull']} Note={r['Note']}\n")
        f.write(f"\nCurrentRegime transitions: {len(changes)}\n")
        for c in changes:
            f.write(f"  {c[0]}  src={c[1]} bip={c[2]} bar={c[3]}  regime={c[4]}\n")
    print(f"\nwrote {out_path}")


if __name__ == "__main__":
    sys.exit(main())
