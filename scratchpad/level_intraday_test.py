"""CR/PS tested on 5-min ES bars with proper SEQUENCING (first-touch race test).

Method
------
- Front-month ES series stitched per session (contract with most volume that day) —
  per-contract prices, NOT back-adjusted, so price levels are valid.
- SPX levels converted to ES via the PRIOR day's basis (ES_close - SPX_close): no lookahead.
- Levels from chain date D are applied to the NEXT session D+1 (how MQ publishes them).

First-touch race: find the first 5-min bar entering the zone around level L.
  resistance (CR): from that bar on, does price fall R pts below L before rising B pts above?
     -> REJECT if down-first, BREAK if up-first.
  support (PS): mirror image.
A real level should REJECT well above 50%, and beat a shifted control.
"""
import glob, os
import numpy as np, pandas as pd
from pathlib import Path
ROOT = Path(__file__).resolve().parents[1]
rng = np.random.default_rng(11)

# ---------- front-month ES 5-min ----------
frames = []
for f in sorted(glob.glob(str(ROOT/"data"/"bars"/"ES*.parquet"))):
    d = pd.read_parquet(f)
    d["contract"] = os.path.basename(f).split(".")[0]
    frames.append(d)
ES = pd.concat(frames, ignore_index=True)
ES["date"] = ES.DateTime.dt.strftime("%Y-%m-%d")
vol = ES.groupby(["date","contract"]).Volume.sum().reset_index()
front = vol.sort_values("Volume").groupby("date").tail(1).set_index("date")["contract"].to_dict()
ES = ES[[c==front.get(d) for d,c in zip(ES.date, ES.contract)]].sort_values("DateTime")
print(f"ES 5-min front-month bars: {len(ES):,} rows, {ES.date.nunique()} sessions "
      f"({ES.date.min()} -> {ES.date.max()})")

# ---------- basis: ES close - SPX close (prior day) ----------
spx = pd.read_csv(ROOT/"data"/"options_sim"/"spx_daily_yahoo.csv")
spx["Date"] = spx.Date.astype(str)
es_close = ES.groupby("date").Close.last()
basis = (es_close - spx.set_index("Date").Close).dropna().sort_index()
print(f"basis days: {len(basis)}  median {basis.median():.1f} pts")
basis_prev = basis.shift(1).dropna()          # prior-day basis -> no lookahead

# ---------- our levels + MQ levels ----------
MQ = pd.read_csv(ROOT/"data"/"menthorq"/"SPX_mq_levels_history.csv")
MQ["session_date"] = MQ.session_date.astype(str); MQ = MQ.set_index("session_date")
ours = {}
for f in sorted(glob.glob(str(ROOT/"data"/"orats"/"SPX"/"SPX_202[456].parquet"))):
    yr = pd.read_parquet(f)
    for c in ["strike","gamma","delta","callOpenInterest","putOpenInterest","dte","spotPrice"]:
        yr[c] = pd.to_numeric(yr[c], errors="coerce")
    yr = yr[(yr.dte>1)&(yr.gamma.abs()<0.1)&(yr.delta.abs()<=1.01)]
    for d,g in yr.groupby("tradeDate"):
        d=str(d)
        p=(g.gamma*(g.callOpenInterest-g.putOpenInterest)).groupby(g.strike).sum(); p=p[np.isfinite(p)]
        if not p.empty: ours[d]={"cr":p.idxmax(),"ps":p.idxmin()}

bars_by_day = {d: g.reset_index(drop=True) for d,g in ES.groupby("date")}
sessions = sorted(bars_by_day)
nxt = {d: sessions[i+1] for i,d in enumerate(sessions[:-1])}

def race(getl, kind, z, R, B, shift=False):
    rej=brk=n=0
    for d in ours:
        s = nxt.get(d)
        if s is None or s not in bars_by_day or d not in basis_prev.index: continue
        L = getl(d)
        if L is None or not np.isfinite(L): continue
        L = L + basis_prev.loc[d]                      # SPX -> ES
        if shift: L = L + rng.choice([-1,1])*rng.uniform(20,40)
        b = bars_by_day[s]
        # first bar entering the zone
        if kind=="cr": hit = np.where(b.High.values >= L - z)[0]
        else:          hit = np.where(b.Low.values  <= L + z)[0]
        if len(hit)==0: continue
        i0 = hit[0]; n += 1
        post = b.iloc[i0:]
        if kind=="cr":
            down = np.where(post.Low.values  <= L - R)[0]
            up   = np.where(post.High.values >= L + B)[0]
        else:
            down = np.where(post.High.values >= L + R)[0]   # favourable = up
            up   = np.where(post.Low.values  <= L - B)[0]   # adverse   = down
        fd = down[0] if len(down) else 10**9
        fu = up[0]   if len(up)   else 10**9
        if fd==fu==10**9: continue
        if fd < fu: rej += 1
        else:       brk += 1
    tot = rej+brk
    return n, tot, (rej/tot*100 if tot else float("nan"))

print("\nFirst-touch race: after entering the zone, does price REJECT (move R away)")
print("before BREAKING (move B through)?  >50% = level has repulsive power.\n")
for z,R,B in [(2.5,10,10),(5,10,10),(5,15,15),(5,20,20),(2.5,5,5)]:
    print(f"--- zone +/-{z}, reject={R}pts, break={B}pts ---")
    for lbl,getl,kind,sh in [
        ("OURS cr", lambda d: ours[d]["cr"], "cr", False),
        ("MQ   cr", lambda d: MQ.loc[d,"cr"] if d in MQ.index else None, "cr", False),
        ("CTRL cr", lambda d: ours[d]["cr"], "cr", True),
        ("OURS ps", lambda d: ours[d]["ps"], "ps", False),
        ("MQ   ps", lambda d: MQ.loc[d,"ps"] if d in MQ.index else None, "ps", False),
        ("CTRL ps", lambda d: ours[d]["ps"], "ps", True)]:
        n,tot,pct = race(getl,kind,z,R,B,sh)
        se = (0.5/np.sqrt(tot)*100) if tot else float("nan")
        print(f"   {lbl}  touches {n:3d}  resolved {tot:3d}  REJECT {pct:5.1f}%  (+/-{se:.1f}pp)")
    print()
