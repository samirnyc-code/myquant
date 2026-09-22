import json, glob
from pathlib import Path
D = Path(r'c:\Users\Admin\myquant-regime\data\annotations\book_review')
idx = json.load(open(D/'bo_setup_index.json'))
bad=0; tot=0; missing_day=0
for date, trades in idx.items():
    f = D/f'{date}.json'
    if not f.exists(): missing_day+=1; continue
    bars = json.loads(f.read_text())['bars']; nb=len(bars)
    for t in trades:
        tot+=1; ft=t[0]
        if ft>=nb: bad+=1
print(f"trades {tot}, ft out-of-range vs ChartSim bars: {bad}, dates missing ChartSim day: {missing_day}")
# sample: show one date's trades mapped to ChartSim bars
sd='2026-06-06' if '2026-06-06' in idx else sorted(idx)[-1]
print(f"\nsample {sd}:")
bars=json.loads((D/f'{sd}.json').read_text())['bars']
for t in idx[sd]:
    ft,dr,btc,estop,pnl,reason,xb=t
    b=bars[ft]; entry=b[5]; shift=entry-btc; stop=estop+shift; risk=abs(btc-estop)
    tgt=entry+2*risk if dr>0 else entry-2*risk
    print(f"  bar{ft+1} {b[1]} {'long' if dr>0 else 'short'}  entry={entry} stop={round(stop,2)} 2Rtgt={round(tgt,2)} "
          f"exit b{xb+1} {'stop' if reason==0 else '2R' if reason==1 else 'close'} pnl=${pnl}")
