"""August 2026 (8/6-8/31): LIVE sim trades vs the v2 desk-faithful engine,
side by side per trade, with full metric deltas — credit, P&L, win rate,
PF, expectancy — per stream and total. Matched streams only (the 8 engine
streams; gx walls/STMR have no engine counterpart).

Engine side = august_rerun_v2_20260909.csv (policies eod + deskwait).
Live side  = trades.parquet. Output: dated CSV + stdout.
"""
import json
import datetime as dt
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
BT = ROOT / "data" / "options_sim" / "backtest_full"
STAMP = dt.date.today().strftime("%Y%m%d")

v2 = pd.read_csv(BT / "august_rerun_v2_20260909.csv")
v2 = v2[v2["policy"].isin(["eod", "deskwait"])]
v2 = v2[["date", "strat", "short_k", "credit", "exit_kind", "pnl"]].rename(
    columns={"short_k": "k_bt", "credit": "cr_bt", "exit_kind": "exit_bt",
             "pnl": "pnl_bt"})

t = pd.read_parquet(ROOT / "data" / "options_log" / "trades.parquet")
t["entry_dt"] = pd.to_datetime(t["entry_dt"])
t = t[(t["entry_dt"] >= "2026-08-06") & (t["entry_dt"] <= "2026-08-31 23:59")
      & t["pnl"].notna()].copy()
t["date"] = t["entry_dt"].dt.strftime("%Y-%m-%d")
t["k_live"] = t["legs"].apply(
    lambda s: next((l["strike"] for l in json.loads(s) if l["side"] == "sell"), None))
live = t[t["strategy_id"].isin(v2["strat"].unique())][
    ["date", "strategy_id", "k_live", "credit", "close_reason", "pnl"]].rename(
    columns={"strategy_id": "strat", "credit": "cr_live", "pnl": "pnl_live"})
live["exit_live"] = live.pop("close_reason").fillna("").map(
    lambda r: "stop" if r.startswith("level") else
              ("time" if r.startswith("time") else "exp"))

m = live.merge(v2, on=["date", "strat"], how="outer").sort_values(["date", "strat"])
m["d_cr"] = (m["cr_live"] - m["cr_bt"]).round(2)
m["d_pnl"] = (m["pnl_live"] - m["pnl_bt"]).round(1)
m.to_csv(BT / f"live_vs_v2_aug_{STAMP}.csv", index=False)

pd.set_option("display.width", 220)
cols = ["date", "strat", "k_live", "k_bt", "cr_live", "cr_bt", "exit_live",
        "exit_bt", "pnl_live", "pnl_bt", "d_pnl"]
print(m[cols].to_string(index=False))

def metrics(pnls, credits):
    p = pnls.dropna()
    gw, gl = p[p > 0].sum(), p[p < 0].sum()
    return dict(n=len(p), credit=round(credits.dropna().sum(), 2),
                pnl=round(p.sum()), win=round(100 * (p > 0).mean(), 1),
                pf=round(gw / abs(gl), 2) if gl else None,
                exp=round(p.mean(), 1))

both = m[m["pnl_live"].notna() & m["pnl_bt"].notna()]
print("\n===== per-stream metrics (rows where BOTH traded) =====")
out = []
for strat, g in both.groupby("strat"):
    a, b = metrics(g["pnl_live"], g["cr_live"]), metrics(g["pnl_bt"], g["cr_bt"])
    out.append(dict(strat=strat, n=a["n"],
                    cr_live=a["credit"], cr_bt=b["credit"],
                    d_cr=round(a["credit"] - b["credit"], 2),
                    pnl_live=a["pnl"], pnl_bt=b["pnl"], d_pnl=a["pnl"] - b["pnl"],
                    win_live=a["win"], win_bt=b["win"],
                    pf_live=a["pf"], pf_bt=b["pf"],
                    exp_live=a["exp"], exp_bt=b["exp"]))
per = pd.DataFrame(out)
print(per.to_string(index=False))
per.to_csv(BT / f"live_vs_v2_aug_metrics_{STAMP}.csv", index=False)

a, b = metrics(both["pnl_live"], both["cr_live"]), metrics(both["pnl_bt"], both["cr_bt"])
print("\n===== TOTAL (both traded) =====")
print(f"n        : {a['n']}")
print(f"credit   : live {a['credit']:8.2f}   bt {b['credit']:8.2f}   delta {a['credit']-b['credit']:+.2f}")
print(f"pnl      : live {a['pnl']:8.0f}   bt {b['pnl']:8.0f}   delta {a['pnl']-b['pnl']:+.0f}")
print(f"win rate : live {a['win']:7.1f}%   bt {b['win']:7.1f}%   delta {a['win']-b['win']:+.1f}pp")
print(f"PF       : live {a['pf']:8.2f}   bt {b['pf']:8.2f}   delta {a['pf']-b['pf']:+.2f}")
print(f"exp $/tr : live {a['exp']:8.1f}   bt {b['exp']:8.1f}   delta {a['exp']-b['exp']:+.1f}")
only_live = m[m["pnl_live"].notna() & m["pnl_bt"].isna()]
only_bt = m[m["pnl_live"].isna() & m["pnl_bt"].notna() & (m["exit_bt"] != "SKIP")]
print(f"\nlive-only rows (engine skipped/gated): {len(only_live)}  pnl {only_live['pnl_live'].sum():.0f}")
print(f"engine-only rows (live absent): {len(only_bt)}  pnl {only_bt['pnl_bt'].sum():.0f}")
