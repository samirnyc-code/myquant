"""Export QS PaintBar signals to a CSV the NT8 indicator can read.

Signals only (no sim) — for visual validation on a NinjaTrader chart. Uses the
FIXED detector (qs_setups), so DateTime is the signal-BAR CLOSE time (CT), which
matches NinjaTrader's close-stamped intraday bars.

Only DETECTION settings change which bars are marked (sim-side geometry/ESA/BE do
not affect signals). Pick a version; the file is tagged so versions coexist.

    python scripts/qs_export_signals_nt.py --preset paper
    python scripts/qs_export_signals_nt.py --preset paintbar --tag raw
    python scripts/qs_export_signals_nt.py --preset paper --no-ft --no-ibs

Output columns: DateTime(yyyyMMdd HHmmss CT, bar CLOSE), Dir(L/S),
    Type(BO/BO+FT/BigBO/OB/CX), Status(ok/time/consec3/large_bar), Price, Stop, BarNum
Writes data/nt_import/qs_signals[_tag].csv AND the NT user dir.
"""
from __future__ import annotations
import sys, argparse
from pathlib import Path
import pandas as pd

_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(_ROOT))
from qs_setups import detect, detect_wp, QSConfig  # noqa: E402

_BARS = _ROOT / "data" / "bars" / "_continuous.parquet"
_NT_DIR = Path.home() / "Documents" / "NinjaTrader 8"

_PRESETS = {
    "wp":       QSConfig.wp,           # WHITEPAPER page 8-9 (detect_wp): BO+FT, BigBO, Rev+FT
    "paper":    QSConfig.paper,        # PaintBar paper-ish (BO+OB+CX, IBS, range, FT, filters)
    "research": QSConfig.research,
    "ver5":     QSConfig,              # EL Ver5 shipped default (BO, range@8)
    "paintbar": QSConfig.paintbar_raw, # everything painted, no filters
}


def build_cfg(args) -> QSConfig:
    cfg = _PRESETS[args.preset]()
    if args.no_ft:   cfg.require_ft = False
    if args.no_ibs:
        cfg.signal_ibs_bull = cfg.signal_ibs_bear = -1.0
        cfg.ft_ibs_bull = cfg.ft_ibs_bear = -1.0
    if args.no_range: cfg.range_filter_on = False
    if args.no_obcx:  cfg.use_ob = cfg.use_cx = False
    if args.bo_only:  cfg.use_ob = cfg.use_cx = False
    return cfg


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--preset", choices=_PRESETS, default="paper")
    ap.add_argument("--tag", default=None, help="filename suffix (default = preset name)")
    ap.add_argument("--no-ft", action="store_true")
    ap.add_argument("--no-ibs", action="store_true")
    ap.add_argument("--no-range", action="store_true")
    ap.add_argument("--no-obcx", action="store_true")
    ap.add_argument("--bo-only", action="store_true", help="BO family only")
    args = ap.parse_args()

    tag = args.tag or args.preset
    cfg = build_cfg(args)
    bars = pd.read_parquet(_BARS)
    sig = detect_wp(bars, cfg) if args.preset == "wp" else detect(bars, cfg)
    if sig.empty:
        print("no signals"); return

    out = pd.DataFrame({
        "DateTime": pd.to_datetime(sig["DateTime"]).dt.strftime("%Y%m%d %H%M%S"),
        "Dir": sig["Direction"].map({"Long": "L", "Short": "S"}),
        "Type": sig["SignalType"],
        "Status": sig["FilterStatus"],
        "Price": sig["SignalPrice"].round(2),
        "Stop": sig["StopPrice"].round(2),
        "BarNum": sig["BarNum"].astype(int),
    })
    repo = _ROOT / "data" / "nt_import" / f"qs_signals_{tag}.csv"
    repo.parent.mkdir(parents=True, exist_ok=True)
    out.to_csv(repo, index=False)
    wrote = [str(repo)]
    try:
        _NT_DIR.mkdir(parents=True, exist_ok=True)
        ntp = _NT_DIR / f"qs_signals_{tag}.csv"
        out.to_csv(ntp, index=False)
        wrote.append(str(ntp))
    except Exception as e:
        print(f"(could not write NT dir: {e})")

    print(f"[{tag}] wrote {len(out):,} signals ({(out.Status=='ok').sum():,} ok) to:")
    for w in wrote:
        print("  " + w)
    print("by type:", dict(out["Type"].value_counts()))
    print("by status:", dict(out["Status"].value_counts()))


if __name__ == "__main__":
    main()
