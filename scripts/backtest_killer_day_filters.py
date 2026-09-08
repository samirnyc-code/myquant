"""Can the 14 killer days be dodged ex-ante? Filter study on the vix252 book.

Every filter uses ONLY information available BEFORE entry:
  credit_rich : entry credit > threshold -> the market prices far more risk than
                the EM implies (the tell: 2025-04-09 call credit 3.90 vs avg 1.17).
                Skip that vertical.
  vix_spike   : VIX (prior close) rose >20% over its 5-day-ago close -> skip day.
  vix_high    : VIX prior close > 25 -> skip day.
  gap         : |open - prior close| > 0.75% -> skip the day's verticals.
  prior_wild  : prior day high-low range > 1.5% -> skip day.
  puts_only   : never sell the call side (structural, from the side split).

For each: total P&L, P&L on the 14 killer days, P&L given up on all other days,
and how many killer days are dodged. In-sample exploration -> hypothesis, then
holdout check (fit 2022-2024, verify 2025).
"""
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]

KILLERS = ["2025-04-09", "2025-03-03", "2024-12-18", "2025-10-10", "2025-02-28",
           "2024-04-30", "2023-12-20", "2024-12-20", "2022-06-09", "2024-08-01",
           "2023-05-02", "2024-08-05", "2023-08-29", "2023-12-13"]


def main():
    d = pd.read_csv(ROOT / "data/options_sim/backtest_full/rows.csv")
    d = d[(d.pnl.notna()) & (d.method == "vix252")].copy()

    spx = pd.read_csv(ROOT / "data/options_sim/backtest_full/spx_daily_ohlc.csv").set_index("date")
    spx["prior_close"] = spx["close"].shift(1)
    spx["gap_pct"] = 100 * (spx["open"] - spx["prior_close"]).abs() / spx["prior_close"]
    spx["prior_range"] = (100 * (spx["high"] - spx["low"]) / spx["prior_close"]).shift(1)

    vix = pd.read_csv(ROOT / "data/vix_daily.csv")[["date", "close"]].set_index("date")["close"]
    vix_prior = vix.shift(1)
    vix_5ago = vix.shift(6)
    vix_spike = (vix_prior / vix_5ago - 1) * 100

    d["gap"] = d.date.map(spx["gap_pct"])
    d["prior_range"] = d.date.map(spx["prior_range"])
    d["vix_prior"] = d.date.map(vix_prior)
    d["vix_spk"] = d.date.map(vix_spike)
    d["is_killer"] = d.date.isin(KILLERS)

    base_total = d.pnl.sum()
    base_kill = d[d.is_killer].pnl.sum()
    print(f"baseline vix252: total {base_total:+,.0f}   on the 14 killer days {base_kill:+,.0f}\n")

    filters = {
        "credit_rich>2.5": d.credit <= 2.5,
        "credit_rich>2.0": d.credit <= 2.0,
        "vix_spike>20%": d.vix_spk <= 20,
        "vix_high>25": d.vix_prior <= 25,
        "gap>0.75%": d.gap <= 0.75,
        "gap>0.5%": d.gap <= 0.5,
        "prior_wild>1.5%": d.prior_range <= 1.5,
        "puts_only": d.strat.str.endswith("_p"),
        "puts+credit>2.5": d.strat.str.endswith("_p") & (d.credit <= 2.5),
        "gap0.5+credit2.5": (d.gap <= 0.5) & (d.credit <= 2.5),
    }

    print(f"{'filter':18}{'total P&L':>11}{'vs base':>9}{'killer P&L':>12}{'dodged$':>9}"
          f"{'other-days cost':>16}{'killers hit':>12}")
    results = []
    for name, keep in filters.items():
        keep = keep.fillna(False)
        kept = d[keep]
        tot = kept.pnl.sum()
        kill = kept[kept.is_killer].pnl.sum()
        dodged = base_kill - kill
        other_cost = (base_total - base_kill) - (tot - kill)
        k_hit = kept[kept.is_killer & (kept.pnl < -500)].date.nunique()
        results.append(dict(filter=name, total=tot, vs_base=tot - base_total,
                            killer_pnl=kill, dodged=dodged, other_cost=other_cost,
                            killers_still_hit=k_hit))
        print(f"{name:18}{tot:>11,.0f}{tot-base_total:>+9,.0f}{kill:>12,.0f}{dodged:>9,.0f}"
              f"{other_cost:>16,.0f}{k_hit:>9}/14")

    # holdout: pick best on 2022-2024, report 2025 separately
    print("\nholdout check (rule chosen on 22-24, scored on 25):")
    tr = d[d.date < "2025-01-01"]; te = d[d.date >= "2025-01-01"]
    for name, keep in filters.items():
        keep = keep.fillna(False)
        a = tr[keep.reindex(tr.index, fill_value=False)].pnl.sum() - tr.pnl.sum()
        b = te[keep.reindex(te.index, fill_value=False)].pnl.sum() - te.pnl.sum()
        print(f"  {name:18} 22-24 delta {a:>+9,.0f}   2025 delta {b:>+9,.0f}")

    pd.DataFrame(results).to_csv(ROOT / "data/options_sim/backtest_full/killer_day_filters.csv", index=False)
    print("\n-> killer_day_filters.csv")


if __name__ == "__main__":
    main()
