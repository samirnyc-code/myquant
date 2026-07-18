"""Pull SPX 2026-07-15 full chain once, cache to parquet for free iteration.
Also print MQ's exact stored targets for that date (named columns)."""
import pandas as pd, requests, json
from pathlib import Path
ROOT = Path(__file__).resolve().parents[1]
TOKEN = (ROOT / "scratchpad" / "orats_token.txt").read_text().strip()
DATE = "2026-07-15"
OUT = ROOT / "scratchpad" / f"orats_SPX_{DATE}.parquet"

if not OUT.exists():
    r = requests.get("https://api.orats.io/datav2/hist/strikes",
                     params={"token": TOKEN, "ticker": "SPX", "tradeDate": DATE}, timeout=60)
    r.raise_for_status()
    df = pd.DataFrame(r.json()["data"])
    df.to_parquet(OUT)
    print(f"cached {len(df)} rows -> {OUT.name}")
else:
    df = pd.read_parquet(OUT)
    print(f"loaded cache {len(df)} rows")
print("columns:", list(df.columns))

mq = pd.read_csv(ROOT / "data" / "menthorq" / "SPX_mq_levels_history.csv")
row = mq[mq.session_date == DATE].iloc[0]
print(f"\n=== MQ stored targets for {DATE} ===")
for c in mq.columns:
    v = row[c]
    if pd.notna(v) and c not in ("session_date", "eod_date"):
        print(f"  {c:14} = {v}")
