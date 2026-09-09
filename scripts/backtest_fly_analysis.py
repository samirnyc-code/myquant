"""Fly-stream baseline (2022-2026) + full-book portfolio vs the IC streams.

Answers: (1) do the desk's ATM fly verticals carry edge over 4+ years?
(2) does the full 8-stream book (4 IC vix252 + 4 fly) diversify or just add risk?
(3) do the robust IC rules (side, credit band) transfer to the flies?

Outputs: backtest_full/fly_summary.csv, portfolio_daily.csv
"""
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "data/options_sim/backtest_full"


def dd(daily):
    cum = daily.cumsum()
    return (cum - cum.cummax()).min()


def block(d, label):
    daily = d.groupby("date").pnl.sum()
    print(f"{label:26} total {d.pnl.sum():>+11,.0f}  win% {100*(d.pnl>0).mean():>3.0f}"
          f"  stop% {100*(d.exit_kind=='stop').mean():>3.0f}  avg_cr {d.credit.mean():>5.2f}"
          f"  maxDD {dd(daily):>+10,.0f}  worst_day {daily.min():>+8,.0f}")
    return dict(label=label, total=d.pnl.sum(), win=100 * (d.pnl > 0).mean(),
                stop=100 * (d.exit_kind == "stop").mean(), maxdd=dd(daily))


def main():
    fly = pd.read_csv(OUT / "fly_rows.csv")
    fly = fly[fly.pnl.notna()].copy()
    ic = pd.read_csv(OUT / "rows.csv")
    ic = ic[(ic.pnl.notna()) & (ic.method == "vix252")].copy()

    print("=== FLY BASELINE (ATM 25-wide verticals, level-accept stop) ===")
    rows = [block(fly, "fly book (all 4)")]
    for s in ["eodfly_p", "eodfly_c", "openfly_p", "openfly_c"]:
        rows.append(block(fly[fly.strat == s], s))
    print("\nby year:")
    fly["year"] = fly.date.str[:4]
    print(fly.pivot_table(index="year", columns="strat", values="pnl", aggfunc="sum").round(0).to_string())

    print("\n=== validity anchor: model vs desk live book (Aug 2026) ===")
    aug = fly[(fly.date >= "2026-08-01") & (fly.date <= "2026-08-31")]
    print(f"model Aug fly total: {aug.pnl.sum():+,.0f}   (desk booked +3,928 on its actual entries)")

    print("\n=== PORTFOLIO: IC(vix252) + fly, daily ===")
    di = ic.groupby("date").pnl.sum().rename("ic")
    df_ = fly.groupby("date").pnl.sum().rename("fly")
    p = pd.concat([di, df_], axis=1).dropna()
    p["book"] = p.ic + p.fly
    print(f"IC total {p.ic.sum():+,.0f}   fly total {p.fly.sum():+,.0f}   book {p.book.sum():+,.0f}")
    print(f"daily corr(ic,fly): {p.ic.corr(p.fly):.2f}")
    print(f"maxDD: ic {dd(p.ic):+,.0f}   fly {dd(p.fly):+,.0f}   book {dd(p.book):+,.0f}")
    p.to_csv(OUT / "portfolio_daily.csv")

    print("\n=== do the IC rules transfer to flies? ===")
    spx = pd.read_csv(OUT / "spx_daily_ohlc.csv").set_index("date")
    spx["gap"] = 100 * (spx["open"] - spx["close"].shift(1)).abs() / spx["close"].shift(1)
    fly["gap"] = fly.date.map(spx["gap"])
    tr = fly[fly.date < "2025-01-01"]
    te = fly[fly.date >= "2025-01-01"]
    fly["cr_ok"] = fly.credit.between(3.0, 12.0)     # fly credits are ~5x IC credits
    rules = {
        "puts_only": fly.strat.str.endswith("_p"),
        "calls_only": fly.strat.str.endswith("_c"),
        "no_big_gap>0.75": fly.gap.le(0.75),
        "eod_only": fly.strat.str.startswith("eod"),
        "open_only": fly.strat.str.startswith("open"),
    }
    base_tr, base_te = tr.pnl.sum(), te.pnl.sum()
    for name, keep in rules.items():
        keep = keep.fillna(False)
        a = tr[keep.reindex(tr.index, fill_value=False)].pnl.sum() - base_tr
        b = te[keep.reindex(te.index, fill_value=False)].pnl.sum() - base_te
        tot = fly[keep].pnl.sum()
        print(f"  {name:18} kept {tot:>+10,.0f}  train {a:>+9,.0f}  test {b:>+9,.0f}"
              f"  robust {'YES' if a > 0 and b > 0 else 'no'}")

    pd.DataFrame(rows).to_csv(OUT / "fly_summary.csv", index=False)
    print("\n-> fly_summary.csv, portfolio_daily.csv")


if __name__ == "__main__":
    main()
