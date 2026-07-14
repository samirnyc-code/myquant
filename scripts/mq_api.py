"""Direct MenthorQ API client (S73) — hit the real REST endpoints QUIN reads from.

Discovered 2026-07-15 via network capture. gateway.menthorq.io needs a Bearer
token; we harvest it live from a dashboard page load (the app attaches it), then
replay endpoints with plain requests. Cookie-only (cf.menthorq.io) endpoints work
with the session cookies too.

Endpoints (SPX/ES1!/... as {sym}):
  gamma-levels/{sym}/eod            all levels + gex_1..10 (TODAY only; date param ignored)
  options/matrix/{sym}?frequency=   net/abs GEX+DEX+OI totals + per-expiration (eod|intraday)
  options/net-gex-by-expiration/{sym}  full per-strike surface (today)
  gamma-insights/{sym}?limit=365    daily GEX + 1y percentile  <= HISTORY (max 365)
  gamma-insights/{sym}/expirations  per-expiration net gex share
  volatility-insights/{sym}         0DTE/1M/3M skew + history array
  metrics/{sym}/eod?fields=...&limit=365   QScore components history (max 365)
  tickers/{sym}/candles?interval=&from=&to=   OHLC bars

Usage:
  from mq_api import MQ
  mq = MQ()                       # grabs token once
  lv = mq.get("gamma-levels/SPX/eod")
  hist = mq.gamma_insights("SPX", 365)
"""
import time
from pathlib import Path

import requests

ROOT = Path(__file__).resolve().parents[1]
AUTH = ROOT / "gamma_tracker" / "auth_state.json"
GW = "https://gateway.menthorq.io/clickhouse-api/api/web/v1"
CF = "https://cf.menthorq.io/clickhouse-api/api/web/v1"


class MQ:
    def __init__(self):
        self.s = requests.Session()
        self.token = None
        self._auth()

    def _auth(self):
        """Load session cookies + harvest a live Bearer token via Playwright."""
        from playwright.sync_api import sync_playwright
        tok = {"v": None}
        with sync_playwright() as pw:
            br = pw.chromium.launch(headless=True)
            ctx = br.new_context(storage_state=str(AUTH))
            page = ctx.new_page()
            page.on("request", lambda r: tok.__setitem__("v", r.headers.get("authorization"))
                    if "gateway.menthorq.io" in r.url and r.headers.get("authorization") and not tok["v"] else None)
            page.goto("https://dashboard.menthorq.io/en/tickers/SPX", wait_until="networkidle", timeout=60000)
            page.wait_for_timeout(5000)
            for c in ctx.cookies():
                self.s.cookies.set(c["name"], c["value"], domain=c["domain"])
            br.close()
        self.token = tok["v"]
        if not self.token:
            raise RuntimeError("no Bearer token captured — session may be stale")

    def get(self, path, base=GW, **params):
        h = {"accept": "application/json", "authorization": self.token}
        for attempt in range(3):
            r = self.s.get(f"{base}/{path}", headers=h, params=params, timeout=30)
            if r.status_code == 200:
                return r.json()
            if r.status_code in (401, 403):
                self._auth()
                h["authorization"] = self.token
                continue
            r.raise_for_status()
            time.sleep(1)
        r.raise_for_status()

    # convenience wrappers
    def gamma_insights(self, sym, limit=365):
        return self.get(f"gamma-insights/{sym}", limit=limit)

    def metrics(self, sym, limit=365):
        return self.get(f"metrics/{sym}/eod", limit=limit,
                        fields=["option", "momentum", "volatility", "seasonality"])

    def vol_insights(self, sym):
        return self.get(f"volatility-insights/{sym}")

    def matrix(self, sym, freq="eod"):
        return self.get(f"options/matrix/{sym}", frequency=freq)

    def levels(self, sym):
        return self.get(f"gamma-levels/{sym}/eod")

    def per_strike(self, sym, freq="eod"):
        return self.get(f"options/net-gex-by-expiration/{sym}", frequency=freq)


if __name__ == "__main__":
    import json
    import sys
    mq = MQ()
    sym = sys.argv[1] if len(sys.argv) > 1 else "SPX"
    gi = mq.gamma_insights(sym, 365)
    print(f"{sym} gamma-insights: {len(gi)} days, "
          f"{gi[-1]['report_date']} .. {gi[0]['report_date']}")
    vi = mq.vol_insights(sym)
    hist = vi.get("skew", {}).get("history", [])
    print(f"{sym} skew history: {len(hist)} days")
    print("sample GEX today:", json.dumps(gi[0], indent=1)[:200])
