"""CR vs CR-0DTE overlap/dedup analysis for the 3-rule fade suite (S73)."""
import numpy as np
import pandas as pd
from pathlib import Path

_ROOT = Path(__file__).resolve().parent.parent
l1 = pd.read_csv(_ROOT / "data" / "menthorq" / "levels_history.csv")
l0 = pd.read_csv(_ROOT / "data" / "menthorq" / "levels0_history.csv")
es1 = l1[l1.symbol == "ES"][["date", "cr", "ps"]]
es0 = l0[l0.symbol == "ES"][["date", "cr0", "ps0"]]
m = es1.merge(es0, on="date", how="inner").dropna(subset=["cr", "cr0"])
m["gap"] = (m.cr - m.cr0).abs()
print(f"days with both CR and CR0: {len(m)}")
for thr in (0, 5, 10, 25):
    print(f"  |CR - CR0| <= {thr:2d} pts: {(m.gap <= thr).mean() * 100:5.1f}% of days")
print(f"  median gap {m.gap.median():.0f} pts, CR0 below CR on {(m.cr0 < m.cr).mean() * 100:.0f}% of days")
mp = es1.merge(es0, on="date").dropna(subset=["ps", "ps0"])
mp["gap"] = (mp.ps - mp.ps0).abs()
print(f"PS vs PS0: identical(<=0) {(mp.gap <= 0).mean() * 100:.1f}%  <=25pts {(mp.gap <= 25).mean() * 100:.1f}%")
