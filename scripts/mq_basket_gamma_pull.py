"""Pull 200d gamma-level history for the full BL-input basket via the qbot /levels
endpoint (level_types=gamma_levels). Caches to scratchpad/bl_basket_gamma.json as
{sym: {session_date: {level_name: value}}}. Enabling data for BL formula reverse-eng.

Includes SECTOR ETFs (the hypothesis under test) + index/ETF proxies + VIX/IBIT, plus
the futures/stocks we care about, so every agent reads ONE cache (no parallel API hits).
"""
import datetime as dt
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from mq_api import MQ, QBOT  # noqa

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "scratchpad" / "bl_basket_gamma.json"
EARLIEST = dt.date(2025, 9, 29)
CHUNK = 5

BASKET = [
    # index / ETF proxies
    "SPX", "SPY", "QQQ", "NDX", "IWM", "RUT", "DIA",
    # sector / thematic ETFs (the sector-ETF hypothesis)
    "XLK", "SMH", "XLF", "XLE", "XLV", "XLY", "XLI", "XLP", "XLU", "XLB", "XLC", "XLRE", "XLG",
    # macro / cross-asset
    "VIX", "IBIT", "GLD", "USO", "TLT", "HYG",
    # futures + mag7 (already have raw jsonl for some, but keep one uniform cache)
    "ES1!", "NQ1!", "RTY1!", "GC1!", "CL1!",
    "AAPL", "MSFT", "NVDA", "AMZN", "GOOG", "META", "TSLA",
]


def cal_days(a, b):
    d = a
    while d <= b:
        if d.weekday() < 5:
            yield d.isoformat()
        d += dt.timedelta(days=1)


def main():
    mq = MQ()
    h = {"accept": "application/json", "authorization": mq.token}
    today = dt.datetime.now(dt.timezone.utc).date()
    days = list(cal_days(EARLIEST, today + dt.timedelta(days=1)))
    cache = {}
    if OUT.exists():
        cache = json.loads(OUT.read_text())
    for sym in BASKET:
      try:
        got = cache.setdefault(sym, {})
        want = [d for d in days if d not in got]  # approx pre-skip
        n0 = len(got)
        for i in range(0, len(want), CHUNK):
            chunk = want[i:i + CHUNK]
            try:
                r = mq.s.get(f"{QBOT}/levels", headers=h, timeout=45,
                             params={"tickers": sym, "level_types": "gamma_levels",
                                     "dates": ",".join(chunk)})
                if r.status_code == 401:
                    mq._auth(); h["authorization"] = mq.token
                    r = mq.s.get(f"{QBOT}/levels", headers=h, timeout=45,
                                 params={"tickers": sym, "level_types": "gamma_levels",
                                         "dates": ",".join(chunk)})
                if r.status_code != 200:
                    continue
                for it in (r.json().get("data") or []):
                    lv = it.get("levels") or []
                    if not lv:
                        continue
                    got[it["date"]] = {v["name"]: v["value"]
                                       for v in lv[0].get("level_values", [])}
            except Exception as e:
                print(f"  XX {sym} {chunk[0]}: {type(e).__name__}: {str(e)[:50]}",
                      flush=True)
        OUT.write_text(json.dumps(cache))
        print(f"  OK {sym:6} {len(got)-n0:+4} new  ({len(got)} sessions)", flush=True)
      except Exception as e:
        print(f"  XX {sym:6} FATAL {type(e).__name__}: {str(e)[:70]}", flush=True)
        OUT.write_text(json.dumps(cache))
    print(f"\nDone. {len(cache)} tickers -> {OUT}")


if __name__ == "__main__":
    main()
