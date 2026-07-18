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
    r.raise_for_status()
    df = pd.DataFrame(r.json()["data"]); df.to_parquet(f)
    print(f"  pulled {tkr}: {len(df)} rows"); return df

def mq_row(mqtkr):
    m = pd.read_csv(ROOT/"data"/"menthorq"/f"{mqtkr}_mq_levels_history.csv")
    r = m[m.session_date==DATE]
    return r.iloc[0] if len(r) else None

def compute(df, spot):
    for c in ["strike","gamma","callOpenInterest","putOpenInterest","dte"]:
        df[c] = pd.to_numeric(df[c], errors="coerce")
    g = df[df.dte>1].copy()
    g["net"] = g.gamma*(g.callOpenInterest-g.putOpenInterest)*100*spot
    p = (g.groupby("strike")["net"].sum()/1e6).sort_index()
    return p

def run(mqtkr, otkr):
    print(f"\n########## {mqtkr}  (ORATS {otkr})  {DATE} ##########")
    mq = mq_row(mqtkr)
    if mq is None: print("  no MQ row for date"); return
    df = pull(otkr)
    sp_stock = pd.to_numeric(df["stockPrice"],errors="coerce").median()
    sp_spot  = pd.to_numeric(df["spotPrice"],errors="coerce").median()
    print(f"  ORATS spot: stockPrice={sp_stock:.2f} spotPrice={sp_spot:.2f}   MQ cr={mq.cr} ps={mq.ps} hvl={mq.hvl}")
    spot = sp_spot
    p = compute(df, spot)
    cr, ps = p.idxmax(), p.idxmin()
    print(f"  --- primary levels ---")
    print(f"    cr : MQ={mq.cr:.0f} @ {mq.cr_gex/1e6:.2f}M   MINE={cr:.0f} @ {p.max():.2f}M")
    print(f"    ps : MQ={mq.ps:.0f} @ {mq.ps_gex/1e6:.2f}M   MINE={ps:.0f} @ {p.min():.2f}M")
    print(f"    hvl: MQ={mq.hvl:.0f} @ {mq.hvl_gex/1e6:.2f}M")
    # MQ walls
    walls=[(mq[f"gex_{i}"], mq[f"gex_{i}_gex"]/1e6) for i in range(1,11)
           if pd.notna(mq.get(f"gex_{i}"))]
    print(f"  --- gex_1..N (MQ strike : MQ mag : my mag at that strike) ---")
    for k,mv in walls:
        print(f"    {k:8.1f}  MQ={mv:8.2f}M  MINE={p.get(k, np.nan):8.2f}M")
    top=[float(k) for k in p.reindex(p.abs().sort_values(ascending=False).index).index if k!=cr][:10]
    mqset={float(k) for k,_ in walls}
    print(f"  my top-10 strikes:  {sorted(int(x) for x in top)}")
    print(f"  MQ wall strikes:    {sorted(int(x) for x in mqset)}")
    print(f"  overlap: {len(set(int(x) for x in top)&set(int(x) for x in mqset))}/{len(mqset):.0f}")

run("AAPL","AAPL")
run("NQ1!","NDX")
