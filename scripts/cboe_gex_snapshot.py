"""FREE proxy gamma levels from CBOE delayed quotes (_SPX.json): has OI + greeks.
Compute SpotGamma/MQ-style levels and sanity-check vs the latest MenthorQ row
(distance-from-spot comparison, ES-vs-SPX basis cancels).
"""
import json
import re
import sys
import urllib.request
from pathlib import Path

import numpy as np
import pandas as pd

sys.stdout.reconfigure(encoding="utf-8", errors="replace")
ROOT = Path(r"c:\Users\Admin\myquant")
sys.path.insert(0, str(ROOT)); sys.path.insert(0, str(ROOT / "scripts"))

URL = "https://cdn.cboe.com/api/global/delayed_quotes/options/_SPX.json"
req = urllib.request.Request(URL, headers={"User-Agent": "Mozilla/5.0"})
with urllib.request.urlopen(req, timeout=60) as r:
    j = json.load(r)
data = j["data"]
spot = float(data.get("current_price") or data.get("close"))
print(f"SPX spot (delayed): {spot:.2f}; options rows: {len(data['options'])}")

pat = re.compile(r"^(SPXW?)(\d{6})([CP])(\d{8})$")
rows = []
for o in data["options"]:
    m = pat.match(o["option"])
    if not m:
        continue
    root, ymd, cp, k = m.groups()
    rows.append(dict(root=root, exp=pd.to_datetime("20" + ymd, format="%Y%m%d"),
                     cp=cp, strike=int(k) / 1000.0,
                     oi=float(o.get("open_interest") or 0),
                     gamma=float(o.get("gamma") or 0),
                     iv=float(o.get("iv") or 0)))
ch = pd.DataFrame(rows)
today = pd.Timestamp.now().normalize()
ch = ch[(ch["exp"] >= today) & (ch["exp"] <= today + pd.Timedelta(days=45))]
ch = ch[(ch["oi"] > 0) & (ch["gamma"] > 0)]
print(f"usable rows (<=45d expiries, OI>0): {len(ch)}; expiries: {ch['exp'].nunique()}")

# dealer-sign GEX per strike: calls +, puts - ; $GEX = gamma*OI*100*spot
ch["gex"] = ch["gamma"] * ch["oi"] * 100 * spot * np.where(ch["cp"] == "C", 1, -1)
cg = ch[ch["cp"] == "C"].groupby("strike")["gex"].sum()
pg = -ch[ch["cp"] == "P"].groupby("strike")["gex"].sum()   # positive magnitudes
net = ch.groupby("strike")["gex"].sum().sort_index()

call_res = cg[cg.index > spot].idxmax()
put_sup = pg[pg.index < spot].idxmax()
w = net[(net.index > spot * 0.93) & (net.index < spot * 1.07)]
hvl = np.nan
sgn = np.sign(w.values)
for i in range(1, len(w)):
    if sgn[i - 1] < 0 <= sgn[i]:
        hvl = w.index[i]; break
top_gex = net.abs().sort_values(ascending=False).head(3).index.tolist()

print(f"\nPROXY (SPX pts):  CallRes {call_res:.0f} ({call_res-spot:+.0f} vs spot)  "
      f"PutSup {put_sup:.0f} ({put_sup-spot:+.0f})  HVL {hvl:.0f} ({hvl-spot:+.0f})")
print(f"top |GEX| strikes: {[f'{k:.0f}' for k in top_gex]}")

# compare with latest MQ row in DISTANCE-FROM-SPOT space (basis cancels)
import os
os.environ["MQ_APPLY_NEXT_DAY"] = "0"
from menthorq_edge_study import load_mq, BARS_PQ
mq = load_mq()
last = mq.sort_values("date").iloc[-1]
bars = pd.read_parquet(BARS_PQ)
bars["DateTime"] = pd.to_datetime(bars["DateTime"])
es_close = bars[bars["DateTime"].dt.normalize() == pd.to_datetime(last["date"]).normalize()]["Close"].iloc[-1]
# MQ levels are front-contract prices; continuous ESU6 offset = 0, so es_close comparable
print(f"\nMQ row {pd.to_datetime(last['date']).date()} (ES front): "
      f"CallRes {last['call_resistance']:.0f} ({last['call_resistance']-es_close:+.0f} vs ES close)  "
      f"PutSup {last['put_support']:.0f} ({last['put_support']-es_close:+.0f})  "
      f"HVL {last['high_vol_level']:.0f} ({last['high_vol_level']-es_close:+.0f})")
print(f"MQ GEX1-3: {last['gex_1']:.0f}, {last['gex_2']:.0f}, {last['gex_3']:.0f} "
      f"(dist {last['gex_1']-es_close:+.0f}, {last['gex_2']-es_close:+.0f}, {last['gex_3']-es_close:+.0f})")
print(f"\nDIST-FROM-SPOT deltas (proxy - MQ): "
      f"CallRes {abs((call_res-spot)-(last['call_resistance']-es_close)):.0f} pts  "
      f"PutSup {abs((put_sup-spot)-(last['put_support']-es_close)):.0f} pts  "
      f"HVL {abs((hvl-spot)-(last['high_vol_level']-es_close)):.0f} pts")
