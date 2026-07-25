"""DURABLE SPEC — long-biased 2E with shorts gated to genuine downtrend/high-vol regimes.
Consumes the enriched per-trade CSV (dir/regime/adr/vix_prev/mae_pts/eod_move/fill_hour) and
attaches causal daily TREND features (prior-day SMA/return regime) from _db_es_5m_rth dailies.

Hypothesis (from the 16yr OOS decomposition): with-trend LONGS are regime-robust; with-trend
SHORTS only pay in real bear/high-vol regimes. So gate shorts, keep longs.

Part 1 (exploratory): short-book PF conditional on each trend/vol gate, split PRE-2021 vs 2021+.
  -> find gates where shorts are positive in BOTH eras (generalizing, not era-fit).
Part 2 (validation): DURABLE book = longs(always) + shorts(gate). Report era splits + walk-
  forward (train gate+params on prior years, test forward) vs the frozen symmetric book.

net(S) re-derived from mae/eod so stop mult is free. $50/pt, $5 RT + 1t slip.

  python scripts/regime_2e_durable.py
Output: data/regime/durable_20260725.csv (durable per-trade book) + tables.
"""
import sys
from pathlib import Path
import numpy as np
import pandas as pd

TICK = 0.25; PT = 50.0; COMM = 5.0; SLIP = 12.5; FLOOR = 8 * TICK
WT = Path(__file__).resolve().parent.parent
DATA = Path(r"C:/Users/Admin/myquant/data")
CSV = WT / "data" / "regime" / "oos_pertrade_20260725.csv"
M5 = DATA / "bars" / "_db_es_5m_rth.parquet"


def pf(s):
    s = np.asarray(s, float); gp = s[s > 0].sum(); gl = -s[s < 0].sum()
    return round(gp / gl, 2) if gl > 0 else 0.0


def netcol(d, m):
    S = np.maximum(np.round(m * d.adr.values / TICK) * TICK, FLOOR)
    move = np.where(d.mae_pts.values >= S, -S, d.eod_move.values)
    return move * PT - COMM - SLIP


def line(name, s):
    s = np.asarray(s, float)
    if not len(s):
        return f"{name:<30} (empty)"
    return (f"{name:<30} n={len(s):5d}  net {s.sum():+9,.0f}  $/tr {s.mean():+6.1f}  "
            f"PF {pf(s):4.2f}  win {100*(s>0).mean():4.1f}%")


def daily_trend():
    b = pd.read_parquet(M5); b["DateTime"] = pd.to_datetime(b["DateTime"]); b["Date"] = b["DateTime"].dt.date.astype(str)
    d = b.groupby("Date").agg(C=("Close", "last")).reset_index().sort_values("Date")
    c = d["C"]
    d["sma20"] = c.rolling(20).mean(); d["sma50"] = c.rolling(50).mean(); d["sma100"] = c.rolling(100).mean()
    d["ret20"] = c.pct_change(20); d["ret50"] = c.pct_change(50)
    d["below50"] = (c < d["sma50"]).astype(int)
    d["below100"] = (c < d["sma100"]).astype(int)
    d["sma50_dn"] = (d["sma50"] < d["sma50"].shift(5)).astype(int)   # 50-SMA falling
    d["downtrend"] = ((c < d["sma50"]) & (d["sma50"] < d["sma50"].shift(5))).astype(int)
    # causal: use PRIOR day's values (known at today's open)
    feat = ["sma50", "sma100", "ret20", "ret50", "below50", "below100", "sma50_dn", "downtrend"]
    for f in feat:
        d[f] = d[f].shift(1)
    return d.set_index("Date")[feat]


def main():
    df = pd.read_csv(CSV)
    tr = daily_trend()
    df = df.merge(tr, left_on="Date", right_index=True, how="left")
    df["pre21"] = df.yr <= 2020
    g = df[df.with_trend].copy()
    L = g[g.dir == "L"].copy(); Sh = g[g.dir == "S"].copy()
    for d_ in (L, Sh, g):
        d_["net30"] = netcol(d_, 0.30)

    print("========== PART 1: SHORT book PF conditional on trend/vol gate (net @0.30) ==========")
    print(f"{'gate':<26}{'PRE-2021 (n/PF/net)':<26}{'2021+ (n/PF/net)':<26}")
    gates = {
        "ALL shorts": np.ones(len(Sh), bool),
        "below sma50": Sh.below50 == 1,
        "below sma100": Sh.below100 == 1,
        "sma50 falling": Sh.sma50_dn == 1,
        "downtrend(50<&fall)": Sh.downtrend == 1,
        "ret20<0": Sh.ret20 < 0,
        "ret20<-2%": Sh.ret20 < -0.02,
        "vix>=18": Sh.vix_prev >= 18,
        "vix>=20": Sh.vix_prev >= 20,
        "below50 & vix>=18": (Sh.below50 == 1) & (Sh.vix_prev >= 18),
        "downtrend & vix>=18": (Sh.downtrend == 1) & (Sh.vix_prev >= 18),
    }
    for name, mask in gates.items():
        s = Sh[mask.values if hasattr(mask, "values") else mask]
        pre = s[s.pre21].net30; pos = s[~s.pre21].net30
        print(f"{name:<26}"
              f"{f'{len(pre)}/{pf(pre)}/{pre.sum():+,.0f}':<26}"
              f"{f'{len(pos)}/{pf(pos)}/{pos.sum():+,.0f}':<26}")

    print("\n========== PART 2: LONG book (baseline, for reference) ==========")
    print(line("longs ALL 2010-2020", L[L.pre21].net30))
    print(line("longs ALL 2021-2026", L[~L.pre21].net30))
    print(line("longs @0.40 stop 2010-2020", netcol(L[L.pre21], 0.40)))
    print(line("longs @0.40 stop 2021-2026", netcol(L[~L.pre21], 0.40)))

    print("\n========== PART 3: DURABLE book = longs(all,0.40 stop) + shorts(below 50d SMA,0.30) ==========")
    # non-fit gate: a standard 50-day trend filter. Longs @0.40 (WFA-preferred), shorts @0.30.
    Lg = L.copy(); Lg["netd"] = netcol(Lg, 0.40)
    Sg = Sh[Sh.below50 == 1].copy(); Sg["netd"] = netcol(Sg, 0.30)
    dur = pd.concat([Lg, Sg]).sort_values("Date")
    dur.to_csv(WT / "data" / "regime" / "durable_20260725.csv", index=False)
    for era, sub in (("2010-2020", dur[dur.pre21]), ("2021-2026", dur[~dur.pre21]), ("FULL 2010-26", dur)):
        print(line(f"DURABLE {era}", sub.netd))
    print("  DURABLE by year:")
    yt = dur.groupby("yr").agg(n=("netd", "size"), net=("netd", "sum"), PF=("netd", pf))
    print(yt.round({"net": 0}).to_string())

    print("\n========== PART 4: DURABLE vs FROZEN symmetric, by era ==========")
    print(line("FROZEN both 2010-2020", g[g.pre21].net30))
    print(line("FROZEN both 2021-2026", g[~g.pre21].net30))
    print(line("DURABLE     2010-2020", dur[dur.pre21].netd))
    print(line("DURABLE     2021-2026", dur[~dur.pre21].netd))

    print("\n========== PART 5: alt short-gates in the durable book (robustness) ==========")
    for gname, gmask in (("below sma50", Sh.below50 == 1), ("below sma100", Sh.below100 == 1),
                         ("sma50 falling", Sh.sma50_dn == 1)):
        Sa = Sh[gmask].copy(); Sa["netd"] = netcol(Sa, 0.30)
        da = pd.concat([Lg, Sa])
        print(f"-- shorts: {gname} --")
        print("   " + line("pre-2021", da[da.pre21].netd))
        print("   " + line("2021+   ", da[~da.pre21].netd))
        print("   " + line("FULL    ", da.netd))

    print("\n========== PART 6: ANCHORED WFA of the durable spec (choose short-gate per yr, OOS) ==========")
    # longs fixed @0.40 all; WFA picks the short-gate each year from prior-years net.
    Lg2 = L.copy(); Lg2["netd"] = netcol(Lg2, 0.40)
    SHG = {"none": Sh.iloc[0:0].index, "below50": Sh[Sh.below50 == 1].index,
           "below100": Sh[Sh.below100 == 1].index, "sma50fall": Sh[Sh.sma50_dn == 1].index}
    Shd = Sh.copy(); Shd["netd"] = netcol(Shd, 0.30)
    years = sorted(g.yr.unique()); oos = []; picks = []
    for y in [yy for yy in years if yy >= 2013]:
        best, bg = -1e18, "none"
        for gn, idx in SHG.items():
            sg = Shd.loc[Shd.index.intersection(idx)]
            tr_net = pd.concat([Lg2[Lg2.yr < y], sg[sg.yr < y]]).netd.sum()
            if tr_net > best:
                best, bg = tr_net, gn
        sg = Shd.loc[Shd.index.intersection(SHG[bg])]
        te = pd.concat([Lg2[Lg2.yr == y], sg[sg.yr == y]])
        oos.append(te.netd.values); picks.append((y, bg, te.netd.sum()))
    for (y, bg, nt) in picks:
        print(f"   {y}: shorts={bg:<9} -> OOS {nt:+,.0f}")
    print("   " + line("ANCHORED-WFA durable OOS 2013-26", np.concatenate(oos)))


if __name__ == "__main__":
    main()
