import sys
sys.path.insert(0, r"c:\Users\Admin\myquant\scripts")
import options_trade_log as tlog
import pandas as pd
df = tlog.load()
print("COLUMNS:", list(df.columns))
ecol = "exit_dt" if "exit_dt" in df.columns else "exit_ts"
open_df = df[df[ecol].isna() | (df[ecol].astype(str).isin(["", "nan", "NaT"]))]
print(f"TOTAL rows {len(df)}, OPEN {len(open_df)}")
cols = [c for c in ["trade_id", "strategy", "opened_ts", "structure", "legs"] if c in open_df.columns]
for _, r in open_df.iterrows():
    legs = r.get("legs", "")
    exp = ""
    try:
        import json
        L = json.loads(legs)
        exp = L[0].get("expiry", "")
    except Exception:
        pass
    print(f"  {r.get('trade_id',''):32s} strat={r.get('strategy',''):14s} exp={exp} opened={str(r.get('opened_ts',''))[:16]}")
