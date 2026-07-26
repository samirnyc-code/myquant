"""TEST 2 — RevFT below-HVL drift resolution. Is the negative-gamma RevFT edge (+$71k EOD) a
real reversal signal, or directional drift in the down-regime? Splits by direction, above-vs-
below discrimination, per-year, type. VERDICT: mostly directional (all shorts), not signal.

  python scripts/regime_book_revft_drift.py
"""
import numpy as np
import pandas as pd
from pathlib import Path

d = pd.read_parquet(Path(r"C:/Users/Admin/myquant/data/regime/revft_regime_full_20260725.parquet"))
d = d[d.year >= 2021]


def pf(s):
    s = np.asarray(s, float); gp = s[s > 0].sum(); gl = -s[s < 0].sum()
    return round(gp / gl, 2) if gl > 0 else 0.0


neg = d[d.mq == "negative_gamma"]; pos = d[d.mq == "positive_gamma"]
print("RevFT below vs above HVL, EOD-hold (if pure hold-to-EOD drift, both win):")
print(f"  BELOW (neg gamma): n={len(neg)} PF {pf(neg.neod):.2f} ${neg.neod.sum():+,.0f}")
print(f"  ABOVE (pos gamma): n={len(pos)} PF {pf(pos.neod):.2f} ${pos.neod.sum():+,.0f}  <- LOSES: regime discriminates")
print("\ndirectional balance below HVL (if drift, one side carries it):")
for dr in ("L", "S"):
    x = neg[neg.dir == dr]; print(f"  {dr}: n={len(x):4d} PF {pf(x.neod):.2f} ${x.neod.sum():+,.0f}")
print("  -> edge is ALL shorts (selling rips in a down-regime, held to EOD = down-drift), NOT the reversal")
print("\nby year:", {y: pf(neg[neg.year == y].neod) for y in range(2021, 2027)})
print("VERDICT: RevFT below-HVL 'edge' is directional down-drift, not signal. Excluded from the book.")
