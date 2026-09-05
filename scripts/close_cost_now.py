"""Cost to close all open 0DTE positions NOW, from the live recorded chain.

Reads the latest snapshot in data/options_sim/chain_YYYYMMDD.csv and computes,
per open spread, the buy-to-close cost using ACTUAL bid/ask:
  - short leg bought back at ASK (we pay)
  - long  leg sold        at BID (we receive)
  cost_to_close = short_ask - long_bid   (marketable/worst-case)
  mid_to_close  = short_mid - long_mid   (mid)
P&L if closed = credit_received - cost_to_close  (x100)

Saves a dated CSV next to the sim log. No inline analysis.
"""
import csv, sys, datetime as dt
from pathlib import Path

DATE = "20260904"
CHAIN = Path(f"data/options_sim/chain_{DATE}.csv")

# open positions: (id, credit, [(side,right,strike), ...])  side: short/long
POS = [
    ("eodic_p",  0.95, [("short","P",7680),("long","P",7655)]),
    ("eodic_c",  0.15, [("short","C",7815),("long","C",7840)]),
    ("eodfly_c", 6.65, [("short","C",7750),("long","C",7775)]),
    ("openic_p", 0.25, [("short","P",7665),("long","P",7640)]),
    ("openic_c", 0.10, [("short","C",7805),("long","C",7830)]),
    ("openfly_c",8.30, [("short","C",7735),("long","C",7760)]),
    ("gx_bps",   0.35, [("short","P",7675),("long","P",7650)]),
    ("gx_bcs",   3.25, [("short","C",7750),("long","C",7775)]),
]

def _f(x):
    try:
        return float(x)
    except (TypeError, ValueError):
        return None

rows = list(csv.DictReader(CHAIN.open()))
# last snapshot that actually has strike rows (skip a mid-write partial)
seen = []
for r in rows:
    if r["ts_et"] not in seen:
        seen.append(r["ts_et"])
last_ts = None
for ts in reversed(seen):
    snap = [r for r in rows if r["ts_et"] == ts]
    if len(snap) >= 20:
        last_ts = ts
        break
snap = [r for r in rows if r["ts_et"] == last_ts]
spot = _f(snap[0]["spot"])
q = {}  # (right,strike) -> (bid,ask); empty quote = worthless leg = 0.0
for r in snap:
    b = _f(r["bid"]); a = _f(r["ask"])
    q[(r["right"], _f(r["strike"]))] = (b if b is not None else 0.0,
                                        a if a is not None else 0.0)

def quote(right, strike):
    return q.get((right, float(strike)))

out_rows = []
tot_mid = tot_mkt = tot_pnl_mid = tot_pnl_mkt = 0.0
print(f"snapshot {last_ts} CT | spot {spot}\n")
hdr = f"{'id':10} {'credit':>7} {'closeMid':>9} {'closeMkt':>9} {'pnlMid':>8} {'pnlMkt':>8}  legs"
print(hdr); print("-"*len(hdr))
for pid, credit, legs in POS:
    short_mid = short_ask = long_mid = long_bid = 0.0
    leg_str = []
    ok = True
    for side, right, strike in legs:
        qq = quote(right, strike)
        if qq is None:
            ok = False; leg_str.append(f"{side} {strike}{right}=NA"); continue
        bid, ask = qq; mid = (bid+ask)/2
        leg_str.append(f"{side} {strike}{right} {bid:.2f}/{ask:.2f}")
        if side == "short":
            short_mid += mid; short_ask += ask
        else:
            long_mid += mid; long_bid += bid
    if not ok:
        print(f"{pid:10} {credit:7.2f}  MISSING QUOTE  {' | '.join(leg_str)}")
        continue
    close_mid = short_mid - long_mid           # per-share cost to close (mid)
    close_mkt = short_ask - long_bid           # marketable/worst-case
    pnl_mid = (credit - close_mid) * 100
    pnl_mkt = (credit - close_mkt) * 100
    tot_mid += close_mid*100; tot_mkt += close_mkt*100
    tot_pnl_mid += pnl_mid; tot_pnl_mkt += pnl_mkt
    print(f"{pid:10} {credit:7.2f} {close_mid*100:9.0f} {close_mkt*100:9.0f} {pnl_mid:8.0f} {pnl_mkt:8.0f}  {' | '.join(leg_str)}")
    out_rows.append({"id":pid,"credit":credit,"close_mid_$":round(close_mid*100,2),
                     "close_mkt_$":round(close_mkt*100,2),"pnl_mid_$":round(pnl_mid,2),
                     "pnl_mkt_$":round(pnl_mkt,2)})

print("-"*len(hdr))
print(f"{'TOTAL':10} {'':7} {tot_mid:9.0f} {tot_mkt:9.0f} {tot_pnl_mid:8.0f} {tot_pnl_mkt:8.0f}")
print(f"\nCost to close ALL now:  mid ${tot_mid:,.0f}   marketable ${tot_mkt:,.0f}")
print(f"Realized today (2 stopped put flies): -412.60")
print(f"Day net if closed now:  mid ${tot_pnl_mid-412.6:,.0f}   marketable ${tot_pnl_mkt-412.6:,.0f}")

outp = Path(f"data/options_sim/close_cost_{DATE}.csv")
with outp.open("w", newline="") as f:
    w = csv.DictWriter(f, fieldnames=list(out_rows[0].keys()))
    w.writeheader(); w.writerows(out_rows)
print(f"\nsaved {outp}")
