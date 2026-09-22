"""Submit-vs-fill timing from the IB Flex TradeConfirms WITH orderTime.

Input: the Aug Fills re-download carrying orderTime (= when IB accepted the order)
alongside dateTime (= execution time). Delta = IB's queue+work latency per
execution. Excludes expiry-removal rows (exchange='--', no orderTime).

Outputs data/options_log/ib_submit_vs_fill_aug.csv + a latency distribution and
the price question: for multi-second fills, did the desk's marketable order pay
more than the touch it saw at submit? (Price drift needs TD quotes at both stamps
— done separately; this script covers the timing table.)
"""
import re
import sys
import xml.etree.ElementTree as ET
from datetime import datetime
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
SRC = Path(r"C:\Users\Admin\Downloads\Aug_Fills (1).xml")


def parse_ts(s):
    return datetime.strptime(s, "%Y%m%d;%H%M%S") if s else None


def main():
    tree = ET.parse(SRC)
    rows = []
    for tc in tree.iter("TradeConfirm"):
        ot, ft = tc.get("orderTime"), tc.get("dateTime")
        if not ot or not ft or tc.get("exchange") == "--":
            continue
        o, f = parse_ts(ot), parse_ts(ft)
        rows.append(dict(
            date=ot[:8], symbol=tc.get("symbol"), right=tc.get("putCall"),
            strike=float(tc.get("strike")), qty=int(tc.get("quantity")),
            side=tc.get("buySell"), price=float(tc.get("price")),
            order_time=o.strftime("%H:%M:%S"), fill_time=f.strftime("%H:%M:%S"),
            latency_s=(f - o).total_seconds(),
            underlying=tc.get("underlyingSymbol")))
    d = pd.DataFrame(rows)
    d.to_csv(ROOT / "data/options_log/ib_submit_vs_fill_aug.csv", index=False)

    spx = d[d.underlying == "SPX"]
    print(f"executions with orderTime: {len(d)}  (SPX {len(spx)}, XSP {len(d)-len(spx)})")
    print(f"date range: {d.date.min()}..{d.date.max()}\n")
    lat = spx.latency_s
    print("SPX submit->fill latency (seconds):")
    print(f"  median {lat.median():.0f}   mean {lat.mean():.1f}   p75 {lat.quantile(.75):.0f}"
          f"   p90 {lat.quantile(.9):.0f}   p99 {lat.quantile(.99):.0f}   max {lat.max():.0f}")
    print(f"  0s (same second): {(lat==0).mean()*100:.0f}%   <=2s: {(lat<=2).mean()*100:.0f}%"
          f"   <=5s: {(lat<=5).mean()*100:.0f}%   >10s: {(lat>10).mean()*100:.0f}%")
    slow = spx[spx.latency_s > 10].sort_values("latency_s", ascending=False)
    print(f"\nslowest fills (>10s), {len(slow)}:")
    for _, r in slow.head(12).iterrows():
        print(f"  {r.date} {r.order_time}->{r.fill_time} ({r.latency_s:.0f}s) "
              f"{r.side} {r.qty:+d} {r.strike:.0f}{r.right} @ {r.price}")


if __name__ == "__main__":
    main()
