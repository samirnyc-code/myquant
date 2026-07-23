"""Does the regime filter help the 2E book? Compare unfiltered vs filter variants.

Reads the committed base-study trades CSV; saves a dated comparison CSV.
  python scripts/regime_2e_filter_compare.py
"""
from pathlib import Path
import pandas as pd

ROOT = Path(__file__).resolve().parent.parent
df = pd.read_csv(ROOT / "data" / "regime" / "second_entries_regime_20260723.csv")
df = df[df["count"] == 2]

FILTERS = {
    "unfiltered (all 2E)":            lambda d: d,
    "with-trend (BULL L + BEAR S)":   lambda d: d[((d.regime == "BULL") & (d.dir == "L")) |
                                                  ((d.regime == "BEAR") & (d.dir == "S"))],
    "counter-trend (BULL S + BEAR L)": lambda d: d[((d.regime == "BULL") & (d.dir == "S")) |
                                                   ((d.regime == "BEAR") & (d.dir == "L"))],
    "drop NEUTRAL (trade both dirs)": lambda d: d[d.regime != "NEUTRAL"],
    "NEUTRAL only":                   lambda d: d[d.regime == "NEUTRAL"],
}


def pf(s):
    gp = s[s > 0].sum(); gl = -s[s < 0].sum()
    return gp / gl if gl > 0 else float("inf")


rows = []
for book in ("T1", "T2"):
    b = df[df.book == book]
    for name, fn in FILTERS.items():
        d = fn(b)
        rows.append((book, name, len(d), round(d.R.mean(), 3),
                     round((d.R > 0).mean() * 100, 1), round(d.net.sum()),
                     round(pf(d.net), 3),
                     round(d.net.sum() / len(d), 1) if len(d) else 0))
out = pd.DataFrame(rows, columns=["book", "filter", "n", "meanR", "win%", "net$", "PF", "$/trade"])
out.to_csv(ROOT / "data" / "regime" / "regime_filter_compare_20260723.csv", index=False)
print(out.to_string(index=False))
