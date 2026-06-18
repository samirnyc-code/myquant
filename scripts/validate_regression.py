"""Regression harness: dump simulate_trades output (all 3 modes) to parquet,
so old vs new engine can be compared trade-for-trade. Use after any engine or
sweep rewrite to prove output is byte-identical to the prior (validated) code.

    python scripts/validate_regression.py dump data/_regress/new
    # (git stash simulation_engine.py; rerun with .../old; git stash pop)
    python scripts/validate_regression.py cmp data/_regress/old data/_regress/new
"""
import sys
from pathlib import Path
import numpy as np, pandas as pd
ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT)); sys.path.insert(0, str(Path(__file__).resolve().parent))
from simulation_engine import simulate_trades
from validate_engine import _load_ticks, DEFAULTS, SIGNALS_PARQUET

cfg = dict(DEFAULTS)
common = dict(entry_slip=cfg["entry_slip"], exit_slip=cfg["exit_slip"], stop_offset=cfg["stop_offset"],
              tick_value=cfg["tick_value"], commission=cfg["commission"])


def _load_sigs():
    s = pd.read_parquet(SIGNALS_PARQUET)
    s["DateTime"] = pd.to_datetime(s["DateTime"])
    if "Date" not in s.columns:
        s["Date"] = s["DateTime"].dt.date
    s = s[(s["DateTime"] >= pd.Timestamp("2021-06-18")) & (s["DateTime"] <= pd.Timestamp("2022-06-19"))]
    tbd = {}
    for d in sorted(s["Date"].unique()):
        t = _load_ticks(d)
        if not t.empty:
            tbd[d] = t
    return s[s["Date"].isin(tbd)].copy(), tbd


def dump(outdir):
    out = Path(outdir); out.mkdir(parents=True, exist_ok=True)
    sigs, tbd = _load_sigs()
    single = simulate_trades(sigs, tbd, cfg["target_r"], **common, contracts=cfg["contracts_t1"])
    multi = simulate_trades(sigs, tbd, cfg["target_r"], **common,
                            contracts=cfg["contracts_t1"] + cfg["contracts_t2"], multileg=True,
                            t1_r=cfg["t1_r"], t1_action="exit",
                            contracts_t1=cfg["contracts_t1"], contracts_t2=cfg["contracts_t2"], ml_pb_r=cfg["ml_pb_r"])
    three = simulate_trades(sigs, tbd, 3.0, **common, contracts=1, threeleg=True,
                            t1_r=1.0, t2_r=2.0, t1_action="exit",
                            contracts_e1=1, contracts_e2=1, contracts_e3=1,
                            pb1_r=0.5, pb1_ticks=0, pb2_r=1.0, pb2_ticks=0)
    for name, df in [("single", single), ("multi", multi), ("three", three)]:
        df.to_parquet(out / f"{name}.parquet")
    print(f"dumped {len(single)}/{len(multi)}/{len(three)} rows to {out}")


def cmp(a, b):
    a, b = Path(a), Path(b)
    total_diff = 0
    for name in ("single", "multi", "three"):
        da = pd.read_parquet(a / f"{name}.parquet")
        db = pd.read_parquet(b / f"{name}.parquet")
        if da.shape != db.shape:
            print(f"[{name}] SHAPE DIFF {da.shape} vs {db.shape}"); total_diff += 1; continue
        cols = [c for c in da.columns if c in db.columns]
        ndiff_cols = {}
        for c in cols:
            sa, sb = da[c], db[c]
            if pd.api.types.is_float_dtype(sa) and pd.api.types.is_float_dtype(sb):
                neq = ~np.isclose(sa.values, sb.values, rtol=0, atol=1e-9, equal_nan=True)
            else:
                neq = ~((sa.values == sb.values) | (pd.isna(sa.values) & pd.isna(sb.values)))
            n = int(neq.sum())
            if n:
                ndiff_cols[c] = n
        if ndiff_cols:
            total_diff += sum(ndiff_cols.values())
            print(f"[{name}] DIFFERS: {ndiff_cols}")
        else:
            print(f"[{name}] identical ({len(da)} rows, {len(cols)} cols)")
    print("\nRESULT:", "IDENTICAL" if total_diff == 0 else f"{total_diff} differences")
    sys.exit(0 if total_diff == 0 else 1)


if __name__ == "__main__":
    if sys.argv[1] == "dump":
        dump(sys.argv[2])
    else:
        cmp(sys.argv[2], sys.argv[3])
