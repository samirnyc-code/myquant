"""Test the qbot-service /levels endpoint: response shape + how far back it goes."""
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path.cwd() / "scripts"))
from mq_api import MQ  # noqa

BASE = "https://cf.menthorq.io/qbot-service/api/web/v1/levels"
mq = MQ()

def fetch(date, tickers="SPX", lt="gamma_levels"):
    h = {"accept": "application/json", "authorization": mq.token}
    r = mq.s.get(BASE, headers=h,
                 params={"tickers": tickers, "level_types": lt, "dates": date}, timeout=30)
    return r.status_code, (r.json() if r.status_code == 200 else r.text[:200])

# 1) structure for a known date
st, js = fetch("2026-07-15")
print("=== 2026-07-15 status", st, "===")
Path("scratchpad/mq_levels_sample.json").write_text(json.dumps(js, indent=1), encoding="utf-8")
print(json.dumps(js, indent=1)[:1500])

# 2) probe depth — does it return data for old dates?
print("\n=== depth probe (does date return non-empty?) ===")
def nonempty(js):
    """Heuristic: response has actual level values."""
    s = json.dumps(js)
    return len(s) > 50 and ("call_resistance" in s or "gamma" in s.lower() or "gex" in s.lower())

for d in ["2026-06-16", "2026-01-02", "2025-07-01", "2025-01-02", "2024-07-01",
          "2024-01-02", "2023-01-03", "2022-01-03", "2021-01-04", "2020-01-02",
          "2015-01-02", "2010-01-04", "2007-01-03"]:
    st, js = fetch(d)
    ne = nonempty(js) if st == 200 else False
    marker = "DATA" if ne else "empty"
    print(f"  {d}  status={st}  {marker}  len={len(json.dumps(js)) if st==200 else '-'}")
