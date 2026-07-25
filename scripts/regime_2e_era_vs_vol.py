"""ERA vs VOL — the decisive natural experiment. Is the long-2E edge driven by VIX LEVEL,
or by a STRUCTURAL era change (0DTE/retail microstructure, ~2020+)? Compare the edge on
MATCHED VIX buckets across eras: low-VIX-2024 vs low-VIX-2015 have the same vol but different
microstructure. If the edge is positive in low-VIX MODERN days but absent in low-VIX OLD days,
the driver is STRUCTURAL (sticky, good for forward trading), not vol (cyclical).

Long with-trend book, 0.30xADR, 09-13, no gap. era: OLD=<=2019, MODERN=>=2020 (0DTE/retail on).

Reads oos_pertrade_full_20260725.csv (dir/vix_prev/adr/mae/eod).

  python scripts/regime_2e_era_vs_vol.py
"""
import sys
from pathlib import Path
import numpy as np
import pandas as pd

TICK = 0.25; PT = 50.0; COMM = 5.0; SLIP = 12.5; FLOOR = 8 * TICK
WT = Path(__file__).resolve().parent.parent
CSV = WT / "data" / "regime" / "oos_pertrade_full_20260725.csv"


def pf(s):
    s = np.asarray(s, float); gp = s[s > 0].sum(); gl = -s[s < 0].sum()
    return round(gp / gl, 2) if gl > 0 else 0.0


def main():
    d = pd.read_csv(CSV); d = d[d.with_trend & (d.dir == "L")].copy()
    d = d[d.fill_hour.astype(int).isin({9, 10, 11, 12, 13})]
    S = np.maximum(np.round(0.30 * d.adr.values / TICK) * TICK, FLOOR)
    move = np.where(d.mae_pts.values >= S, -S, d.eod_move.values)
    d["net"] = move * PT - COMM - SLIP; d["Rn"] = d.net / (S * PT)
    d["era"] = np.where(d.yr <= 2019, "OLD(<=19)", "MODERN(>=20)")

    print("========== long-2E edge by ERA x VIX bucket (matched-vol natural experiment) ==========")
    vbins = [(0, 14, "VIX<14"), (14, 18, "VIX 14-18"), (18, 24, "VIX 18-24"), (24, 99, "VIX>24")]
    print(f"{'VIX bucket':<12}{'OLD n/meanR/PF':<26}{'MODERN n/meanR/PF':<26}")
    for lo, hi, lab in vbins:
        o = d[(d.era == "OLD(<=19)") & (d.vix_prev >= lo) & (d.vix_prev < hi)]
        m = d[(d.era == "MODERN(>=20)") & (d.vix_prev >= lo) & (d.vix_prev < hi)]
        print(f"{lab:<12}"
              f"{f'{len(o)}/{o.Rn.mean():+.3f}/{pf(o.net)}' if len(o) else '-':<26}"
              f"{f'{len(m)}/{m.Rn.mean():+.3f}/{pf(m.net)}' if len(m) else '-':<26}")

    print("\n========== the killer cut: LOW-VIX days (<15) only, OLD vs MODERN ==========")
    lowo = d[(d.era == "OLD(<=19)") & (d.vix_prev < 15)]
    lowm = d[(d.era == "MODERN(>=20)") & (d.vix_prev < 15)]
    print(f"  OLD  low-VIX (<15): n={len(lowo):4d}  meanR {lowo.Rn.mean():+.3f}  PF {pf(lowo.net)}  net ${lowo.net.sum():+,.0f}")
    print(f"  MODERN low-VIX(<15): n={len(lowm):4d}  meanR {lowm.Rn.mean():+.3f}  PF {pf(lowm.net)}  net ${lowm.net.sum():+,.0f}")
    print("  -> if MODERN low-VIX is POSITIVE but OLD low-VIX is NEGATIVE, the edge is STRUCTURAL")
    print("     (0DTE/retail era), not vol-level -> forward-robust as long as that structure persists.")

    print("\n========== same for HIGH-VIX days (>20), OLD vs MODERN (control) ==========")
    ho = d[(d.era == "OLD(<=19)") & (d.vix_prev >= 20)]
    hm = d[(d.era == "MODERN(>=20)") & (d.vix_prev >= 20)]
    print(f"  OLD  high-VIX(>=20): n={len(ho):4d}  meanR {ho.Rn.mean():+.3f}  PF {pf(ho.net)}")
    print(f"  MODERN high-VIX(>=20): n={len(hm):4d}  meanR {hm.Rn.mean():+.3f}  PF {pf(hm.net)}")


if __name__ == "__main__":
    main()
