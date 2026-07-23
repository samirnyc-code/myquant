"""Strong-SB cut ON the final headline book (WT | h09-13 | retest4 through | 4pt | EOD).

Joins SB anatomy (brooks_filters_2e CSV, keyed Date+dir+sig_bar) onto the strict
headline trades and reports every SB cut with train/test columns.

  python scripts/regime_2e_sb_on_headline.py
Output: data/regime/sb_on_headline_20260723.csv
"""
from pathlib import Path
import pandas as pd

ROOT = Path(__file__).resolve().parent.parent
R = ROOT / "data" / "regime"
TRAIN_END = "2023-12-31"

det = pd.read_csv(R / "headline_trades_detail_20260723.csv")
det["sig_bar1"] = det.sig_bar + 1                      # detail stores 0-based sig_bar
bk = pd.read_csv(R / "brooks_filters_2e_20260723.csv")
bk = bk[bk.book == "T2"][["Date", "dir", "sig_bar", "sb_ibs_o", "sb_body",
                          "sb_dirok", "sb_rngx", "ema_side_ok", "ema_dist", "warm"]]
bk = bk.drop_duplicates(["Date", "dir", "sig_bar"])
d = det.merge(bk, left_on=["Date", "dir", "sig_bar1"], right_on=["Date", "dir", "sig_bar"],
              how="left", suffixes=("", "_bk"))
print(f"join match: {d.sb_ibs_o.notna().mean()*100:.1f}%  (n={len(d)})")
d = d[d.sb_ibs_o.notna()].copy()
d["is_tr"] = d.Date <= TRAIN_END

strong = (d.sb_ibs_o >= 0.7) & d.sb_dirok.fillna(False) & (d.sb_rngx >= 1.0)
CUTS = [
    ("headline (no SB cut)", pd.Series(True, d.index)),
    ("SB strong (ibs>=.7 & dir & rng>=ABR)", strong),
    ("SB NOT strong", ~strong),
    ("SB ibs_o >= .7 only", d.sb_ibs_o >= 0.7),
    ("SB ibs_o < .4 (weak)", d.sb_ibs_o < 0.4),
    ("SB dir-agreeing close", d.sb_dirok.fillna(False)),
    ("SB big (rngx >= 1)", d.sb_rngx >= 1.0),
    ("SB strong + EMA side", strong & d.ema_side_ok.fillna(False) & d.warm.fillna(False)),
]


def pf(s):
    gp = s[s > 0].sum(); gl = -s[s < 0].sum()
    return gp / gl if gl > 0 else float("inf")


rows = []
for name, m in CUTS:
    x = d[m]; trn = x[x.is_tr]; tst = x[~x.is_tr]
    rows.append((name, len(trn), round(trn.net.sum()), round(pf(trn.net), 2),
                 len(tst), round(tst.net.sum()), round(pf(tst.net), 2),
                 round(x.net.mean(), 1)))
out = pd.DataFrame(rows, columns=["cut", "n_tr", "net_tr", "PF_tr",
                                  "n_te", "net_te", "PF_te", "$/tr"])
out.to_csv(R / "sb_on_headline_20260723.csv", index=False)
print(out.to_string(index=False))
