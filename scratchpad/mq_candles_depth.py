"""How deep is MenthorQ's candles endpoint? Probe 5m + 1d history depth for
index / futures / stock. If deep: it becomes our bar source for the whole
universe (actual prices, aligned with their levels)."""
import datetime as dt
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))
from mq_api import MQ

mq = MQ()
now_ms = int(dt.datetime.now().timestamp() * 1000)
year_ms = 365 * 24 * 3600 * 1000

for sym in ["SPX", "ES1!", "AAPL"]:
    for interval, back in [("5m", 400), ("15m", 400), ("1d", 3000)]:
        frm = now_ms - back * 24 * 3600 * 1000
        try:
            c = mq.get(f"tickers/{sym}/candles", interval=interval,
                       **{"from": frm, "to": now_ms})
            if c:
                t0 = dt.datetime.fromtimestamp(c[0]["t"] / 1000)
                t1 = dt.datetime.fromtimestamp(c[-1]["t"] / 1000)
                print(f"{sym:5s} {interval:3s}: {len(c):7,} bars  {t0:%Y-%m-%d} .. {t1:%Y-%m-%d}")
            else:
                print(f"{sym:5s} {interval:3s}: empty")
        except Exception as e:
            print(f"{sym:5s} {interval:3s}: ERR {str(e)[:90]}")
