"""Build continuous tick caches for all non-ES instruments."""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))
from datetime import datetime
from instruments import load_rolls, ensure_rolls_file
from massive import build_all_instr_continuous_ticks

INSTRUMENTS = ["YM", "GC", "CL", "6E", "6J"]

for key in INSTRUMENTS:
    ensure_rolls_file(key)
    rolls = load_rolls(key)
    t0 = datetime.now()
    print(f"[{t0.strftime('%H:%M:%S')}] Building {key} tick cache...", flush=True)
    try:
        built = build_all_instr_continuous_ticks(key, rolls)
        elapsed = (datetime.now() - t0).total_seconds() / 60
        print(f"  {key} done: {built} days built  ({elapsed:.1f} min)", flush=True)
    except Exception as e:
        print(f"  {key} ERROR: {e}", flush=True)

print("All done.")
