"""Regime slices + filter suite on the COMPLETE IC dataset (1082 days, 2022-2026).

All conditioning info is ex-ante (prior VIX close, overnight gap, prior-day move,
weekday, entry credit). Goal: find WHERE the EM condor bleeds vs pays, with a
train(2022-24)/test(2025-26) split on every candidate rule.

Outputs: data/options_sim/backtest_full/regime_slices.csv + filters_full.csv
"""
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]


def load():
    d = pd.read_csv(ROOT / "data/options_sim/backtest_full/rows.csv")
    d = d[(d.pnl.notna()) & (d.method.isin(["vix252", "vix365"]))].copy()
    spx = pd.read_csv(ROOT / "data/options_sim/backtest_full/spx_daily_ohlc.csv").set_index("date")
    spx["prior_close"] = spx["close"].shift(1)
    spx["gap_pct"] = 100 * (spx["open"] - spx["prior_close"]) / spx["prior_close"]
    spx["prior_ret"] = (100 * (spx["close"] / spx["prior_close"] - 1)).shift(1)
    spx["prior_range"] = (100 * (spx["high"] - spx["low"]) / spx["prior_close"]).shift(1)
    vix = pd.read_csv(ROOT / "data/vix_daily.csv")[["date", "close"]].set_index("date")["close"]
    d["vix"] = d.date.map(vix.shift(1))
    d["gap"] = d.date.map(spx["gap_pct"])
    d["prior_ret"] = d.date.map(spx["prior_ret"])
    d["dow"] = pd.to_datetime(d.date).dt.day_name().str[:3]
    d["side"] = d.strat.str[-1]           # p / c
    return d


def slice_table(d, key, label):
    g = d.groupby([key, "side"]).agg(n=("pnl", "size"), total=("pnl", "sum"),
                                     avg=("pnl", "mean"), win=("pnl", lambda s: 100 * (s > 0).mean()))
    print(f"\n--- {label} (vix252 only, per-trade) ---")
    piv = g.reset_index().pivot(index=key, columns="side")
    print(piv.round(1).to_string())
    return g.reset_index().assign(slice=label)


def main():
    d = load()
    v = d[d.method == "vix252"].copy()
    v["vix_b"] = pd.cut(v.vix, [0, 15, 20, 25, 99], labels=["<15", "15-20", "20-25", ">25"])
    v["gap_b"] = pd.cut(v.gap, [-9, -0.5, -0.2, 0.2, 0.5, 9],
                        labels=["gap<-0.5", "-0.5..-0.2", "flat", "+0.2..0.5", "gap>+0.5"])
    v["pr_b"] = pd.cut(v.prior_ret, [-99, -1, 0, 1, 99], labels=["<-1%", "-1..0", "0..1", ">1%"])
    v["cr_b"] = pd.cut(v.credit, [-9, 0.5, 1.0, 1.5, 2.5, 99],
                       labels=["<0.5", "0.5-1", "1-1.5", "1.5-2.5", ">2.5"])

    out = []
    out.append(slice_table(v, "vix_b", "VIX regime"))
    out.append(slice_table(v, "gap_b", "overnight gap"))
    out.append(slice_table(v, "pr_b", "prior-day return"))
    out.append(slice_table(v, "dow", "weekday"))
    out.append(slice_table(v, "cr_b", "entry credit"))
    pd.concat(out).to_csv(ROOT / "data/options_sim/backtest_full/regime_slices.csv", index=False)

    # ---- candidate rules, train 22-24 / test 25-26 ----
    print("\n=== rules: train 2022-24, test 2025-26 (delta vs baseline, vix252) ===")
    tr = v[v.date < "2025-01-01"]
    te = v[v.date >= "2025-01-01"]
    rules = {
        "puts_only": v.side.eq("p"),
        "credit<=2.5": v.credit.le(2.5),
        "drop_credit<0.5": v.credit.ge(0.5),
        "calls_only_if_gap_dn": v.side.eq("p") | (v.gap < -0.2),
        "puts+credit<=2.5": v.side.eq("p") & v.credit.le(2.5),
        "puts+credit0.5-2.5": v.side.eq("p") & v.credit.between(0.5, 2.5),
        "no_day_after_-1%": v.prior_ret.gt(-1.0),
        "puts+no_big_gap": v.side.eq("p") & v.gap.abs().le(0.75),
        "puts+vix<25": v.side.eq("p") & v.vix.le(25),
    }
    res = []
    for name, keep in rules.items():
        keep = keep.fillna(False)
        a = tr[keep.reindex(tr.index, fill_value=False)].pnl.sum() - tr.pnl.sum()
        b = te[keep.reindex(te.index, fill_value=False)].pnl.sum() - te.pnl.sum()
        tot = v[keep].pnl.sum()
        res.append(dict(rule=name, kept_total=tot, train_delta=a, test_delta=b,
                        robust=("YES" if a > 0 and b > 0 else "no")))
        print(f"  {name:22} kept-total {tot:>+10,.0f}   train {a:>+9,.0f}   test {b:>+9,.0f}"
              f"   robust: {'YES' if a>0 and b>0 else 'no'}")
    pd.DataFrame(res).to_csv(ROOT / "data/options_sim/backtest_full/filters_full.csv", index=False)
    print("\n-> regime_slices.csv, filters_full.csv")


if __name__ == "__main__":
    main()
