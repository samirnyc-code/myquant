import sys, json
sys.path.insert(0, r"c:\Users\Admin\myquant\scripts")
import options_trade_log as tlog
df = tlog.load()
opens = tlog.open_trades()
print("open_trades() returns:", list(opens.trade_id))
for _, tr in opens.iterrows():
    print(f"\n{tr.trade_id}  structure={tr.structure}  credit={tr.credit}  close_reason={tr.get('close_reason','')}")
    for l in json.loads(tr.legs):
        print("   ", l)
