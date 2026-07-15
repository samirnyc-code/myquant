import sys
sys.path.insert(0, "scripts")
import json
import pandas as pd
import options_trade_log as tlog

df = tlog.load()
opens = df[df.exit_dt.isna()]
rows = []
tot_risk = tot_coll = 0.0
for _, r in opens.iterrows():
    legs = json.loads(r.legs)
    exp0 = min(l["expiry"] for l in legs)
    risk = abs(r.max_loss) if pd.notna(r.max_loss) else (r.collateral or 0)
    tot_risk += risk
    tot_coll += r.collateral or 0
    rows.append((r.trade_id, r.strategy_id, exp0, risk, r.collateral))
print(f"{'trade':36s} {'nearest exp':11s} {'max risk':>9s} {'collateral':>10s}")
for t, s, e, k, c in rows:
    print(f"{t:36s} {e:11s} {k:9,.0f} {c:10,.0f}")
print(f"\nOPEN trades: {len(opens)}   TOTAL worst-case risk: ${tot_risk:,.0f}   total collateral: ${tot_coll:,.0f}")
exp_today = sum(k for _, _, e, k, _ in rows if e == "20260714")
print(f"expiring TODAY at 16:00: ${exp_today:,.0f} of that risk")
