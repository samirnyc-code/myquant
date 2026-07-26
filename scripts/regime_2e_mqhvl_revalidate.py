"""RE-VALIDATE the 2E-above-HVL book using MQ's ACTUAL published ES HVL (not my SPX+basis
approximation, which is 34pt median off). Re-classify the existing real-tick 2E trades (2024-26,
where real MQ ES levels exist) by MQ's ES HVL, mapped into the panama frame the trades live in.

Frame: real-tick entry_px is panama-adjusted (_continuous.parquet). MQ HVL is real front-month ES.
offset[D] = panama_close[D] - real_close[D]; hvl_panama = mq_hvl_real + offset. Classify
entry_px > hvl_panama => above. Compare to the OLD (SPX-derived) classification.

  python scripts/regime_2e_mqhvl_revalidate.py
"""
from pathlib import Path
import numpy as np
import pandas as pd

WT = Path(__file__).resolve().parent.parent
DATA = Path(r"C:/Users/Admin/myquant/data")


def pf(s):
    s = np.asarray(s, float); gp = s[s > 0].sum(); gl = -s[s < 0].sum()
    return round(gp / gl, 2) if gl > 0 else 0.0


def mdd(x):
    e = x.sort_values("Date").net.cumsum(); return float((e - e.cummax()).min())


def main():
    d = pd.read_csv(WT / "data" / "regime" / "hvl_2e_realtick_20260725.csv")   # real-tick 2E, panama entry_px
    d = d[d.yr >= 2024].copy()                                                  # MQ ES levels exist 2024-07+

    # MQ real ES HVL per session (prior EOD applied) from the fixed source-of-truth file
    lv = pd.read_csv(DATA / "regime" / "hvl_by_session.csv")
    lv = lv[lv.source == "mq_es"][["session_date", "hvl"]].rename(columns={"session_date": "Date", "hvl": "hvl_mq_real"})
    d = d.merge(lv, on="Date", how="inner")

    # panama offset: _continuous (panama, the real-tick frame) close - unadj (real) close
    pan = pd.read_parquet(DATA / "bars" / "_continuous.parquet"); pan["Date"] = pan["DateTime"].dt.date.astype(str)
    panc = pan.groupby("Date")["Close"].last()
    un = pd.read_parquet(DATA / "bars" / "_continuous_1m_unadj.parquet"); un["Date"] = pd.to_datetime(un["DateTime"]).dt.date.astype(str)
    unc = un.groupby("Date")["Close"].last()
    off = (panc - unc).rename("offset")
    d = d.merge(off, on="Date", how="left").dropna(subset=["offset", "hvl_mq_real"])
    d["hvl_panama"] = d.hvl_mq_real + d.offset
    d["above_mq"] = d.entry_px > d.hvl_panama

    print(f"2024-2026, {len(d)} real-tick 2E trades with MQ real ES HVL\n")
    print("=== CLASSIFICATION: MQ real ES HVL vs my old SPX-derived HVL ===")
    print(f"  classifications that FLIP (old 'above' != new 'above'): {100*(d.above != d.above_mq).mean():.0f}%")
    for tag, col in (("OLD (SPX-derived)", "above"), ("NEW (MQ real ES HVL)", "above_mq")):
        ab = d[d[col]]
        print(f"\n  {tag}:")
        print(f"    ABOVE HVL: n={len(ab):4d} PF {pf(ab.net):.2f} net ${ab.net.sum():+8,.0f} maxDD ${mdd(ab):+,.0f}")
        print(f"      L: PF {pf(ab[ab.dir=='L'].net):.2f} ${ab[ab.dir=='L'].net.sum():+,.0f}  |  S: PF {pf(ab[ab.dir=='S'].net):.2f} ${ab[ab.dir=='S'].net.sum():+,.0f}")
        be = d[~d[col]]
        print(f"    below HVL: n={len(be):4d} PF {pf(be.net):.2f} net ${be.net.sum():+,.0f}")
    print("\n  NEW (MQ HVL) above-HVL by year:")
    ab = d[d.above_mq]
    for y in (2024, 2025, 2026):
        x = ab[ab.yr == y]
        if len(x): print(f"    {y}: n={len(x):3d} PF {pf(x.net):.2f} net ${x.net.sum():+,.0f}")


if __name__ == "__main__":
    main()
