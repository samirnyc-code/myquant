import pandas as pd, numpy as np, requests
from pathlib import Path
ROOT = Path(__file__).resolve().parents[1]
TOKEN = (ROOT/"scratchpad"/"orats_token.txt").read_text().strip()
DATE = "2026-07-15"

def pull(tkr):
    f = ROOT/"scratchpad"/f"orats_{tkr}_{DATE}.parquet"
    if f.exists(): return pd.read_parquet(f)
    r = requests.get("https://api.orats.io/datav2/hist/strikes",
                     params={"token":TOKEN,"ticker":tkr,"tradeDate":DATE}, timeout=90)
    r.raise_for_status(); df=pd.DataFrame(r.json()["data"]); df.to_parquet(f)
    print(f"  pulled {tkr}: {len(df)} rows"); return df

def profile(df, spot):
    for c in ["strike","gamma","callOpenInterest","putOpenInterest","dte"]:
        df[c]=pd.to_numeric(df[c],errors="coerce")
    g=df[df.dte>1].copy()
    g["net"]=g.gamma*(g.callOpenInterest-g.putOpenInterest)*100*spot
    return (g.groupby("strike")["net"].sum()/1e6).sort_index()

# MQ NQ targets for the day
mq = pd.read_csv(ROOT/"data"/"menthorq"/"NQ1!_mq_levels_history.csv")
row = mq[mq.session_date==DATE].iloc[0]
mq_cr, mq_ps, mq_hvl = row.cr, row.ps, row.hvl
mq_walls = [row[f"gex_{i}"] for i in range(1,11) if pd.notna(row.get(f"gex_{i}"))]

qqq = pull("QQQ")
ndx = pull("NDX")
qspot = pd.to_numeric(qqq["spotPrice"],errors="coerce").median()
nspot = pd.to_numeric(ndx["spotPrice"],errors="coerce").median()
k = nspot/qspot                       # QQQ -> NDX/NQ scale
print(f"QQQ spot={qspot:.2f}  NDX spot={nspot:.2f}  k=NDX/QQQ={k:.3f}")
print(f"MQ NQ: cr={mq_cr:.0f} ps={mq_ps:.0f} hvl={mq_hvl:.0f}  spot~{nspot:.0f}")

pq = profile(qqq, qspot)
# scale QQQ strike index into NQ points
pq_scaled = pd.Series(pq.values, index=(pq.index*k))
cr_q = pq.idxmax()*k; ps_q = pq.idxmin()*k
print(f"\nQQQ-derived (scaled x{k:.2f}):")
print(f"  cr : QQQ {pq.idxmax():.1f} -> NQ {cr_q:.0f}   [MQ {mq_cr:.0f}]  d={cr_q-mq_cr:+.0f}")
print(f"  ps : QQQ {pq.idxmin():.1f} -> NQ {ps_q:.0f}   [MQ {mq_ps:.0f}]  d={ps_q-mq_ps:+.0f}")

# top-10 scaled QQQ walls, match to MQ walls within tolerance
top = pq_scaled.reindex(pq_scaled.abs().sort_values(ascending=False).index)
top = [s for s in top.index if abs(s-cr_q)>1][:10]
tol = 0.004*nspot   # ~0.4% ≈ ±118 NQ pts (QQQ $1 ≈ 41 NQ pts, so ~half a QQQ strike)
def near(s, arr):
    return any(abs(s-a)<=tol for a in arr)
hit = sum(near(s, mq_walls) for s in top)
print(f"\nscaled-QQQ top-10 walls (NQ pts): {[int(round(s)) for s in sorted(top)]}")
print(f"MQ NQ walls:                     {[int(x) for x in sorted(mq_walls)]}")
print(f"overlap within ±{tol:.0f} pts: {hit}/{len(mq_walls)}")

# compare: raw NDX overlap same tolerance
pn = profile(ndx, nspot)
topn = pn.reindex(pn.abs().sort_values(ascending=False).index)
topn = [s for s in topn.index if abs(s-pn.idxmax())>1][:10]
hitn = sum(near(s, mq_walls) for s in topn)
print(f"raw-NDX top-10 overlap within ±{tol:.0f} pts: {hitn}/{len(mq_walls)}")
