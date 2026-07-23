"""Brooks-style filters on the 2E book: SIGNAL-BAR STRENGTH + EMA(20), on top of regime.

Joins bar anatomy onto the base-study trades (data/regime/second_entries_regime_20260723.csv):
  SB strength (per Brooks: strong signal bar = trend bar closing near its extreme
  in the entry direction, decent size):
    sb_ibs_o   : oriented close location 0-1 (long: (C-L)/rng, short: (H-C)/rng)
    sb_body    : |C-O|/rng
    sb_dirok   : closes in the trade direction (C>O long / C<O short)
    sb_rngx    : sb range / ABR10 (day-scoped avg bar range)
  EMA(20) (day-scoped on 5m closes):
    ema_side_ok: fill on the with-trade side (long above EMA / short below)
    ema_dist   : (fill - EMA)/ATR10, oriented (+ = with-trade side)
    ema_touch  : pullback touches the EMA (sb Low <= EMA <= sb High)

Tables: each filter alone, then Brooks combos on top of with-trend regime.
Saves: data/regime/brooks_filters_2e_20260723.csv (enriched per-trade rows)
       data/regime/brooks_filters_tables_20260723.csv (all table rows)

  python scripts/regime_2e_brooks_filters.py
"""
from pathlib import Path
import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parent.parent
DATA = Path(r"C:/Users/Admin/myquant/data")

tr = pd.read_csv(ROOT / "data" / "regime" / "second_entries_regime_20260723.csv")
tr = tr[tr["count"] == 2].copy()

b = pd.read_parquet(DATA / "bars" / "_continuous.parquet")
b["Date"] = b["DateTime"].dt.date.astype(str)

# per-day bar anatomy + EMA20/ATR10, day-scoped
feat = {}
for dstr, g in b.groupby("Date", sort=True):
    g = g.sort_values("DateTime").reset_index(drop=True)
    O, H, L, C = (g[c].values for c in ["Open", "High", "Low", "Close"])
    rng = np.maximum(H - L, 1e-9)
    a = 2.0 / 21.0
    ema = np.empty(len(C)); ema[0] = C[0]
    for i in range(1, len(C)):
        ema[i] = a * C[i] + (1 - a) * ema[i - 1]
    abr10 = pd.Series(rng).rolling(10, min_periods=1).mean().values
    feat[dstr] = (O, H, L, C, rng, ema, abr10)

rows = []
for t in tr.itertuples():
    f = feat.get(t.Date)
    if f is None:
        continue
    O, H, L, C, rng, ema, abr10 = f
    sb = int(t.sig_bar) - 1
    if sb >= len(C):
        continue
    short = t.dir == "S"
    ibs = (C[sb] - L[sb]) / rng[sb]
    ibs_o = (1 - ibs) if short else ibs
    body = abs(C[sb] - O[sb]) / rng[sb]
    dirok = (C[sb] < O[sb]) if short else (C[sb] > O[sb])
    rngx = rng[sb] / max(abr10[sb], 1e-9)
    ema_d = (ema[sb] - t.fill) / max(abr10[sb], 1e-9) if short else (t.fill - ema[sb]) / max(abr10[sb], 1e-9)
    side_ok = ema_d > 0
    touch = L[sb] <= ema[sb] <= H[sb]
    warm = sb >= 10                      # EMA/ABR warmed up (skip first 10 bars in EMA cuts)
    rows.append((t.Index, ibs_o, body, dirok, rngx, ema_d, side_ok, touch, warm))

f = pd.DataFrame(rows, columns=["idx", "sb_ibs_o", "sb_body", "sb_dirok", "sb_rngx",
                                "ema_dist", "ema_side_ok", "ema_touch", "warm"]).set_index("idx")
d = tr.join(f, how="inner")
d.to_csv(ROOT / "data" / "regime" / "brooks_filters_2e_20260723.csv", index=False)

wt = ((d.regime == "BULL") & (d.dir == "L")) | ((d.regime == "BEAR") & (d.dir == "S"))
strong_sb = (d.sb_ibs_o >= 0.7) & d.sb_dirok & (d.sb_rngx >= 1.0)
weak_sb = d.sb_ibs_o < 0.4

CUTS = [
    ("ALL 2E", pd.Series(True, d.index)),
    ("SB strong (ibs>=.7 & dir & rng>=ABR)", strong_sb),
    ("SB weak (ibs<.4)", weak_sb),
    ("SB dirok only", d.sb_dirok),
    ("SB big (rngx>=1)", d.sb_rngx >= 1.0),
    ("EMA side ok", d.ema_side_ok & d.warm),
    ("EMA wrong side", ~d.ema_side_ok & d.warm),
    ("EMA touch pullback", d.ema_touch & d.warm),
    ("EMA far (+1.5 ATR beyond)", (d.ema_dist >= 1.5) & d.warm),
    ("WITH-TREND regime", wt),
    ("WT + SB strong", wt & strong_sb),
    ("WT + EMA side ok", wt & d.ema_side_ok & d.warm),
    ("WT + EMA touch", wt & d.ema_touch & d.warm),
    ("WT + SB strong + EMA side", wt & strong_sb & d.ema_side_ok & d.warm),
    ("WT + SB strong + EMA touch", wt & strong_sb & d.ema_touch & d.warm),
    ("BROOKS FULL: WT+SBstrong+side+touch", wt & strong_sb & d.ema_side_ok & d.ema_touch & d.warm),
]


def pf(s):
    gp = s[s > 0].sum(); gl = -s[s < 0].sum()
    return gp / gl if gl > 0 else float("inf")


out = []
for book in ("T1", "T2"):
    bb = d[d.book == book]
    for name, mask in CUTS:
        x = bb[mask.reindex(bb.index, fill_value=False)]
        if not len(x):
            out.append((book, name, 0, np.nan, np.nan, 0, np.nan, np.nan)); continue
        out.append((book, name, len(x), round(x.R.mean(), 3),
                    round((x.R > 0).mean() * 100, 1), round(x.net.sum()),
                    round(pf(x.net), 3), round(x.net.sum() / len(x), 1)))
res = pd.DataFrame(out, columns=["book", "filter", "n", "meanR", "win%", "net$", "PF", "$/trade"])
res.to_csv(ROOT / "data" / "regime" / "brooks_filters_tables_20260723.csv", index=False)
for book in ("T1", "T2"):
    print("\n==", book, "==")
    print(res[res.book == book].drop(columns="book").to_string(index=False))

# oriented-IBS deciles for shape
print("\n== sb_ibs_o quintiles (T2 book) ==")
bb = d[d.book == "T2"].copy()
bb["q"] = pd.qcut(bb.sb_ibs_o, 5, duplicates="drop")
print(bb.groupby("q", observed=True).agg(n=("R", "size"), meanR=("R", "mean"),
                                         net=("net", "sum"), PF=("net", pf)).round(3).to_string())
print("\n== ema_dist buckets (T2, warm, with-trend) ==")
cc = d[(d.book == "T2") & wt.reindex(d.index, fill_value=False) & d.warm].copy()
cc["q"] = pd.cut(cc.ema_dist, [-np.inf, -1.5, -0.5, 0, 0.5, 1.5, np.inf])
print(cc.groupby("q", observed=True).agg(n=("R", "size"), meanR=("R", "mean"),
                                         net=("net", "sum"), PF=("net", pf)).round(3).to_string())
