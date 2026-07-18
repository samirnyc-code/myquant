import datetime as dt
import sys

sys.path.insert(0, r"C:\Users\Admin\myquant\scripts")
from mq_api import MQ, GW

mq = MQ()
now_s = int(dt.datetime.now().timestamp())


def probe(sym, interval, ds, de, cb=20000):
    r = mq.s.get(f"{GW}/tickers/{sym}/candles",
                 headers={"authorization": mq.token},
                 params={"interval": interval, "from": (now_s - 86400 * ds) * 1000,
                         "to": (now_s - 86400 * de) * 1000, "countBack": cb}, timeout=60)
    if r.status_code != 200:
        print(f"{sym} {interval} [{ds}..{de}d]: HTTP {r.status_code}")
        return
    c = r.json()
    if not c:
        print(f"{sym} {interval} [{ds}..{de}d]: EMPTY")
        return
    t0 = dt.datetime.fromtimestamp(c[0]["t"] / 1000)
    t1 = dt.datetime.fromtimestamp(c[-1]["t"] / 1000)
    print(f"{sym} {interval} [{ds}..{de}d]: {len(c):,} bars {t0:%Y-%m-%d} .. {t1:%Y-%m-%d}")


probe("SPX", "5m", 10, 0)
probe("SPX", "5m", 20, 10)
probe("SPX", "5m", 25, 15)
probe("SPX", "1D", 4000, 0)
probe("AAPL", "1D", 4000, 0)
probe("ES1!", "1D", 4000, 0)
probe("AAPL", "1h", 60, 0)
probe("AAPL", "30m", 30, 0)
