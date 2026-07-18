"""Check MQ session_date vs the chain date its levels were actually computed from,
and whether our CSV matches the raw API payload."""
import json
import pandas as pd
from pathlib import Path
ROOT = Path(__file__).resolve().parents[1]
RAW = ROOT/"data"/"menthorq"/"SPX_mq_levels_history_raw.jsonl"
CSV = pd.read_csv(ROOT/"data"/"menthorq"/"SPX_mq_levels_history.csv").set_index("session_date")

rows=[]
for line in open(RAW, encoding="utf-8"):
    try: r=json.loads(line)
    except Exception: continue
    req=r.get("req"); item=r.get("item") or {}
    lv=(item.get("levels") or [])
    if not lv: continue
    block=lv[0]
    vals={v["name"]: (v.get("value"), v.get("gex")) for v in block.get("level_values",[])}
    rows.append({
        "req": req,
        "levels_date": item.get("date"),
        "prev_eod": item.get("previous_eod_date"),
        "level_price": block.get("price"),
        "eod_price": ((item.get("price") or {}).get("eod") or {}).get("value"),
        "eod_price_date": ((item.get("price") or {}).get("eod") or {}).get("date"),
        "cr": vals.get("Call Resistance",(None,None))[0],
        "cr_gex": vals.get("Call Resistance",(None,None))[1],
        "hvl": vals.get("HVL",(None,None))[0],
        "d1min": vals.get("1D Min",(None,None))[0],
        "d1max": vals.get("1D Max",(None,None))[0],
    })
R=pd.DataFrame(rows).drop_duplicates(subset=["req"], keep="last")
print(f"raw entries: {len(R)}")
R["lag"]=(pd.to_datetime(R.req)-pd.to_datetime(R.levels_date)).dt.days
print("\n=== lag between requested session_date and levels' computation date ===")
print(R.lag.value_counts().sort_index().to_string())
print("\n=== does eod_price_date == req? ===")
print((R.eod_price_date==R.req).value_counts().to_string())

# compare raw vs our CSV for overlapping dates
merged=R.set_index("req").join(CSV[["eod_date","spot_eod","cr","cr_gex","hvl","d1_min","d1_max"]],
                               rsuffix="_csv", how="inner")
print(f"\n=== raw vs CSV agreement (n={len(merged)}) ===")
for a,b,lbl in [("cr","cr_csv","cr strike"),("cr_gex","cr_gex_csv","cr gex"),
                ("hvl","hvl_csv","hvl"),("d1min","d1_min","d1_min"),("d1max","d1_max","d1_max")]:
    if a in merged and b in merged:
        m=(merged[a].round(2)==merged[b].round(2)).mean()*100
        print(f"  {lbl:10}: raw==csv on {m:5.1f}% of days")
print("\n=== CSV eod_date vs raw levels_date ===")
print((merged.eod_date==merged.levels_date).value_counts().to_string())
print("\nsample rows:")
print(merged[["levels_date","eod_date","level_price","spot_eod","cr","cr_csv","cr_gex","cr_gex_csv"]].tail(6).to_string())
