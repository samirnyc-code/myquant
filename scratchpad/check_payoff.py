import sys, pandas as pd
sys.path.insert(0, r"c:\Users\Admin\myquant\scripts")
import options_build_cards as obc
import options_trade_log as tlog

trades = tlog.load()
mk = pd.read_csv(obc.SIM / "marks.csv")
last_marks = mk.groupby("trade_id").last() if len(mk) else None
spot = obc.latest_spot()
for _, r in trades.iterrows():
    if pd.isna(r.exit_dt) and "cal" in str(r.structure).lower():
        t = obc.trade_payload(r, last_marks, spot)
        print("trade:", t["name"], "| exp field:", t.get("exp"))
        print("  multi:", t["multi"], "| payoff present:", t["payoff"] is not None,
              "| breakevens:", t["breakevens"])
        if t["payoff"]:
            v = t["payoff"]["v"]
            print("  payoff range: min", min(v), "max", max(v), "at spot pnl≈", t["pnl"])
