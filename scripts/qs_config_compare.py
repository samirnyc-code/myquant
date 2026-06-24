"""QS Breakouts — config matrix vs the whitepaper's frequency claims.

The shipped indicator default != the config used for the SQN study. This runs
several named configs and compares signals/day to the paper:
    total ~20/day · BO ~5/day (but also "~12% of bars" ≈ 9.4/day) · RevFT ~8/day.

No P&L. Run: python scripts/qs_config_compare.py
"""
from __future__ import annotations
import sys
from pathlib import Path
import pandas as pd

_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(_ROOT))
from qs_setups import detect, QSConfig  # noqa: E402

BARS = _ROOT / "data" / "bars" / "_continuous.parquet"
BARS_PER_DAY = 81  # 08:30..15:10 inclusive 5m RTH bars


def log(m): print(m, flush=True)


# ── named configs ────────────────────────────────────────────────────────────
def configs():
    return {
        # pure primitive: every HH/HL (non-OB) bar, nothing filtered
        "A raw BO only (no range/FT/IBS)":
            QSConfig(range_filter_on=False, require_ft=False),
        # EL Ver5 shipped default: range filter @8, no FT, no IBS
        "B EL-Ver5 default (range@8)":
            QSConfig(range_filter_on=True, range_lookback=8, require_ft=False),
        # whitepaper BO bar: IBS 69/31 on the BO bar + size>ABR(10), no FT yet
        "C WP BO bar (IBS69/31 + range@10)":
            QSConfig(range_filter_on=True, range_lookback=10, require_ft=False,
                     signal_ibs_bull=69, signal_ibs_bear=31),
        # whitepaper BO+FT (FT must-BO, NOT close-beyond) + IBS + range@10
        "D WP BO+FT must-BO (IBS69/31)":
            QSConfig(range_filter_on=True, range_lookback=10,
                     require_ft=True, ft_must_bo=True, ft_must_close_beyond=False,
                     signal_ibs_bull=69, signal_ibs_bear=31,
                     ft_ibs_bull=69, ft_ibs_bear=31),
        # code/Pine FT (must close-beyond) + IBS, range@10
        "E FT close-beyond (IBS69/31)":
            QSConfig(range_filter_on=True, range_lookback=10,
                     require_ft=True, ft_must_close_beyond=True,
                     signal_ibs_bull=69, signal_ibs_bear=31,
                     ft_ibs_bull=69, ft_ibs_bear=31),
        # Pine v7.6 BO defaults: FT close-beyond + IBS, range filter OFF
        "F Pine v7.6 BO (FT+IBS, range off)":
            QSConfig(range_filter_on=False,
                     require_ft=True, ft_must_close_beyond=True,
                     signal_ibs_bull=69, signal_ibs_bear=31),
        # add execution filters (time 10:10 + no-3rd-consec) to D
        "G = D + time10:10 + no3rdconsec":
            QSConfig(range_filter_on=True, range_lookback=10,
                     require_ft=True, ft_must_bo=True, ft_must_close_beyond=False,
                     signal_ibs_bull=69, signal_ibs_bear=31,
                     ft_ibs_bull=69, ft_ibs_bear=31,
                     time_filter_on=True, no_third_consecutive=True),
        # everything painted (BO+OB+CX), BigBO factor 1.8, Pine-style
        "H raw paint ALL (BO+OB+CX)":
            QSConfig.paintbar_raw(big_bar_mult=1.8),
        # all signal types WITH research filters (test "~20/day total")
        "I ALL types + research filters":
            QSConfig(use_bo=True, use_ob=True, use_cx=True,
                     range_filter_on=True, range_lookback=10,
                     require_ft=True, ft_must_bo=True, ft_must_close_beyond=False,
                     signal_ibs_bull=69, signal_ibs_bear=31,
                     ft_ibs_bull=69, ft_ibs_bear=31, big_bar_mult=1.8),
    }


def main():
    bars = pd.read_parquet(BARS)
    n_days = bars["DateTime"].dt.date.nunique()
    log(f"sessions: {n_days}\n")
    hdr = f"{'config':38s} {'tot/d':>6s} {'%bars':>6s} {'BO/d':>6s} {'BO+FT/d':>8s} {'BigBO/d':>8s} {'OB/d':>5s} {'CX/d':>5s} {'ok/d':>6s}"
    log(hdr); log("-" * len(hdr))
    for name, cfg in configs().items():
        sig = detect(bars, cfg)
        if sig.empty:
            log(f"{name:38s}  (none)"); continue
        per = lambda mask: mask.sum() / n_days
        st = sig["SignalType"]
        tot = len(sig) / n_days
        ok = (sig["FilterStatus"] == "ok").sum() / n_days
        log(f"{name:38s} {tot:6.2f} {tot/BARS_PER_DAY*100:5.1f}% "
            f"{per(st=='BO'):6.2f} {per(st=='BO+FT'):8.2f} {per(st=='BigBO'):8.2f} "
            f"{per(st=='OB'):5.2f} {per(st=='CX'):5.2f} {ok:6.2f}")
    log("\nPaper: total ~20/d | BO ~5/d (or ~12pct of bars ~= 9.4/d) | RevFT ~8/d")


if __name__ == "__main__":
    main()
