"""Calibration proof-of-concept: reproduce MenthorQ's stored SPX GEX levels
from ORATS raw per-strike gamma+OI, for ONE overlap day (2026-07-15).

Convention (per ORATS AI): dealers long call gamma, short put gamma.
NetGEX_strike($/1% move) = gamma * (cOi - pOi) * 100 * spot^2 * 0.01
Same gamma applies to call & put at a strike. OI = prior-session settled.
"""
import pandas as pd, requests
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
TOKEN = (ROOT / "scratchpad" / "orats_token.txt").read_text().strip()
DATE = "2026-07-15"

# MQ stored row for SPX 2026-07-15 (from SPX_mq_levels_history.csv)
MQ = dict(spot=7572.4, cr=7600, ps=7300, hvl=7535, cr0=7600, ps0=7555,
          hvl0=7555, gw0=7600,
          gex_walls=[(7600,106.0),(7550,36.9),(7575,55.2),(7620,46.8),
                     (7580,41.6),(7625,39.7),(7500,16.6),(7650,68.9),
                     (7675,26.2),(7475,-9.95)])

r = requests.get("https://api.orats.io/datav2/hist/strikes",
                 params={"token": TOKEN, "ticker": "SPX", "tradeDate": DATE}, timeout=60)
r.raise_for_status()
df = pd.DataFrame(r.json()["data"])
for c in ["strike","gamma","callOpenInterest","putOpenInterest","dte","stockPrice"]:
    df[c] = pd.to_numeric(df[c], errors="coerce")
spot = df["stockPrice"].median()
print(f"SPX {DATE}: {len(df)} strike-rows, spot={spot:.1f}, "
      f"expiries={df['expirDate'].nunique()}, dte range {df.dte.min()}-{df.dte.max()}")
if "expiryTod" in df.columns:
    print("expiryTod split:", df.expiryTod.value_counts().to_dict())

def gex_profile(sub, label):
    g = sub.copy()
    # MQ scaling = per $1 move: gamma * netOI * 100 * spot  (NOT spot^2*0.01)
    g["net"] = g.gamma * (g.callOpenInterest - g.putOpenInterest) * 100 * spot
    prof = g.groupby("strike")["net"].sum().sort_index()
    prof_m = prof / 1e6  # to $millions
    cr = prof_m.idxmax(); ps = prof_m.idxmin()
    # gamma flip = cumulative-net zero-crossing NEAREST spot (band +/-5%)
    cum = prof_m.cumsum()
    band = cum[(cum.index >= spot*0.95) & (cum.index <= spot*1.05)]
    flip = None; best = 1e18
    for i in range(1, len(band)):
        a, b = band.iloc[i-1], band.iloc[i]
        if (a < 0 <= b) or (a > 0 >= b):
            k = band.index[i]
            if abs(k - spot) < best: best = abs(k - spot); flip = k
    top = prof_m.reindex(prof_m.abs().sort_values(ascending=False).index).head(10)
    print(f"\n--- {label} ({len(g)} rows, {g.expirDate.nunique()} expiries) ---")
    print(f"  CR (max +GEX)   = {cr:.0f}   [MQ cr={MQ['cr']}]")
    print(f"  PS (max -GEX)   = {ps:.0f}   [MQ ps={MQ['ps']}]")
    print(f"  HVL (gamma flip)= {flip}   [MQ hvl={MQ['hvl']}]")
    print(f"  top-10 |GEX| strikes ($M): "
          + ", ".join(f"{int(k)}:{v:.0f}" for k,v in top.items()))
    return prof_m

# aggregation candidates
gex_profile(df, "ALL expirations")
gex_profile(df[df.dte <= 8], "<=1 week (dte<=8)")
gex_profile(df[df.dte <= 35], "<=1 month (dte<=35)")
if "expiryTod" in df.columns:
    gex_profile(df[df.expiryTod.str.lower()=="pm"], "PM-settled only (SPXW)")

print("\nMQ gex_1 wall was 7600 @ $106M positive. Watch for that strike/magnitude match.")
