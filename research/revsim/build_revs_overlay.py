"""Build the ENRICHED revs_index.json for the Book Review overlay.
Each entry = [bar, side, typeChar, atExt8, book, taken, net, exitBar, stop]
  taken: 1 if the 1-position book actually took it (else 0 = not-taken/dim)
  net:   $ P&L if taken (win>0 / loss<0), else 0
  exitBar: session bar index of exit (for a line), -1 if not taken
Colors in the app: green=taken win, red=taken loss, type-color hollow=not taken.
"""
import sys
from pathlib import Path
import numpy as np, pandas as pd, json
ROOT = Path(r"c:\Users\Admin\myquant")
sys.path.insert(0, str(ROOT / "research" / "revsim")); sys.path.insert(0, str(ROOT / "research" / "scalp_swing"))
import revsim as R, revdetect as RD
import swing_level_gated as G

df5 = pd.read_parquet(ROOT / "research" / "scalp_swing" / "es_5m_rth.parquet")
df5["DateTime"] = pd.to_datetime(df5["DateTime"])
d = df5.sort_values("DateTime").reset_index(drop=True)
H, L = d.High.values, d.Low.values
sma = G.sma20d_map(df5)
sg = RD.detect(df5, {"FT_ABR": 1.0}).reset_index(drop=True)
rb = sg["rb"].values.astype(int); side = sg["side"].values
hiX = pd.Series(H).rolling(8).max().values; loX = pd.Series(L).rolling(8).min().values
sg["ext8"] = np.where(side > 0, L[rb] <= loX[rb] + 1e-9, H[rb] >= hiX[rb] - 1e-9)
sg["book"] = (sg.rev == "BO") | (sg.rev.isin(["IB", "OB"]) & sg.ext8)

# run the BOOK sim to get outcomes; match back by sig_idx
book = sg[sg.book].copy()
tr = R.sim(book, sma=sma, entry="market", hold_eod=True)
# map sig_idx -> (net, xtime)
outcome = {int(r.sig_idx): (float(r.pnl), pd.to_datetime(r.xtime)) for r in tr.itertuples()}
print(f"{len(sg)} signals, {len(book)} book, {len(tr)} taken trades")

# open time per date for exit-bar calc
opens = df5.groupby("Date").DateTime.min()
tmap = {"Trap": "T", "BO": "B", "OB": "O", "IB": "I"}
out = {}
for i, s in sg.iterrows():
    taken, net, xbar = 0, 0, -1
    if i in outcome:
        taken = 1; net = round(outcome[i][0]); xt = outcome[i][1]
        o = opens[s.Date]; xbar = int((xt - o).total_seconds() // 300)
    out.setdefault(s.Date, []).append([int(s.bar), int(s.side), tmap[s.rev],
                                       int(bool(s.ext8)), int(bool(s.book)),
                                       taken, net, xbar, round(float(s.stop), 2)])
dest = ROOT.parent / "myquant-regime" / "data" / "annotations" / "book_review" / "revs_index.json"
dest.write_text(json.dumps(out))
print(f"wrote {dest}  days={len(out)}  signals={sum(len(v) for v in out.values())}")
print("sample:", out.get(str(tr.Date.iloc[0]))[:4] if len(tr) else "n/a")
