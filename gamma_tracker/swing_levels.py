#!/usr/bin/env python3
"""MenthorQ Swing Levels puller — SPX + MAG7.

Discovered 2026-07-19: this data is served by a clean REST endpoint on the
NEW dashboard.menthorq.io app (NOT the old wp-admin/admin-ajax.php API that
scrape.py/menthorq_backfill*.py use — that's a different, older product
surface). Endpoint:

    GET https://gateway.menthorq.io/clickhouse-api/api/web/v1/swing-levels/{TICKER}

Auth is a short-lived Cognito Bearer JWT (~12h) that the app's own JS mints
client-side from the NextAuth session cookies. We get it by loading the
chart page once (headless, reusing the saved login session) and capturing
the real Authorization header off the live request — never hardcode the
token, it expires.

**CONFIRMED HARD CAP: exactly 5 trading days, no more.** Every query-param
variant tried (days=, limit=, from/to, start/end, range=, period=) returns
the identical 5-row payload — the API ignores unknown params silently and
there is no way to get deeper history from it. The ONLY way to build a
longer record is to run this daily and accumulate it ourselves, same
rationale as the gamma-level tracker in this same directory.

Response shape per ticker, e.g. GET .../swing-levels/SPX:
    [{"date": "2026-07-17", "trigger": 7310.73, "band": 7604.65, "direction": "upper"}, ...]
`direction` tells you which side the model's bias points that day:
  - "lower" -> Bullish bias -> MenthorQ's rule: sell a PUT spread struck at `band`
  - "upper" -> Bearish bias -> MenthorQ's rule: sell a CALL spread struck at `band`
`trigger` is the "Risk Trigger" level (third line on the chart) -- semantics
still not fully pinned down (it sits on the OPPOSITE side from `band` in
every observed row so far); not used by MenthorQ's own published strategy,
treat it as an optional stop candidate to test, not a given.

Usage:
    python swing_levels.py run
        -> pulls SPX + MAG7, appends any new (ticker, date) rows to
           ../data/menthorq/swing_levels/swing_levels_history.csv (dedup'd)

Auth: reuses auth_state.json (same file scrape.py uses/creates -- it's the
same MenthorQ login, same dashboard.menthorq.io app). If it doesn't exist
yet or is stale, run `python scrape.py discover` first to create/refresh it
(headed, one-time manual login).
"""
from __future__ import annotations

import csv
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
AUTH_STATE = HERE / "auth_state.json"
OUT_CSV = HERE.parent / "data" / "menthorq" / "swing_levels" / "swing_levels_history.csv"

CHART_URL = "https://dashboard.menthorq.io/en/charts/price?symbol=SPX&interval=5&indicators=swingLevels"
API_BASE = "https://gateway.menthorq.io/clickhouse-api/api/web/v1/swing-levels"

TICKERS = ["SPX", "AAPL", "MSFT", "GOOGL", "AMZN", "META", "NVDA", "TSLA"]


def get_bearer_token() -> str:
    """Load the chart page headless and capture the live Authorization header."""
    from playwright.sync_api import sync_playwright

    if not AUTH_STATE.exists():
        sys.exit(
            f"No saved session at {AUTH_STATE.name} -- run "
            "`python scrape.py discover` first (one-time headed login)."
        )

    token_holder = {}
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        ctx = browser.new_context(storage_state=str(AUTH_STATE))
        page = ctx.new_page()
        try:
            with page.expect_request(
                lambda r: "swing-levels" in r.url, timeout=20000
            ) as req_info:
                page.goto(CHART_URL, wait_until="domcontentloaded")
            req = req_info.value
            auth = req.all_headers().get("authorization", "")
            token_holder["token"] = auth.replace("Bearer ", "").strip()
        except Exception:
            # headless sometimes doesn't auto-fire the indicator request --
            # fall back to a headed run if this keeps happening.
            sys.exit(
                "Could not capture a live swing-levels request headlessly. "
                "Try running headed once (edit headless=True -> False above) "
                "to confirm the indicator still auto-loads from the URL params."
            )
        finally:
            ctx.storage_state(path=str(AUTH_STATE))  # refresh saved session
            browser.close()

    if not token_holder.get("token"):
        sys.exit("Captured request but no Authorization header found.")
    return token_holder["token"]


def fetch_ticker(token: str, ticker: str) -> list[dict]:
    import requests

    r = requests.get(
        f"{API_BASE}/{ticker}",
        headers={
            "authorization": f"Bearer {token}",
            "accept": "*/*",
            "origin": "https://dashboard.menthorq.io",
            "referer": "https://dashboard.menthorq.io/",
        },
        timeout=20,
    )
    r.raise_for_status()
    return r.json()


def run() -> None:
    token = get_bearer_token()
    print("Got bearer token, pulling tickers...")

    existing = set()
    if OUT_CSV.exists():
        with open(OUT_CSV) as f:
            for row in csv.DictReader(f):
                existing.add((row["ticker"], row["date"]))

    all_new = []
    for ticker in TICKERS:
        try:
            data = fetch_ticker(token, ticker)
        except Exception as e:
            print(f"  {ticker}: FAILED ({e})")
            continue
        fresh = [
            {
                "ticker": ticker,
                "date": r["date"],
                "direction": r["direction"],
                "band": r["band"],
                "trigger": r["trigger"],
            }
            for r in data
            if (ticker, r["date"]) not in existing
        ]
        all_new.extend(fresh)
        latest = data[0] if data else None
        print(
            f"  {ticker}: {len(fresh)} new row(s)"
            + (f" -- latest {latest['date']} {latest['direction']} band={latest['band']:.2f}" if latest else "")
        )

    OUT_CSV.parent.mkdir(parents=True, exist_ok=True)
    write_header = not OUT_CSV.exists()
    with open(OUT_CSV, "a", newline="") as f:
        w = csv.DictWriter(f, fieldnames=["ticker", "date", "direction", "band", "trigger"])
        if write_header:
            w.writeheader()
        w.writerows(all_new)

    print(f"\n{len(all_new)} new rows appended -> {OUT_CSV}")


if __name__ == "__main__":
    if len(sys.argv) < 2 or sys.argv[1] != "run":
        sys.exit(__doc__)
    run()
