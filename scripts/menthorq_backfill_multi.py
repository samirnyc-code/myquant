"""
MenthorQ historical backfill — multi-instrument
Pulls 5 endpoints per trading day per instrument and saves raw JSON + parsed CSV.

Usage:
  python -X utf8 scripts/menthorq_backfill_multi.py

Auth: reads session cookie from ~/.menthorq/session.txt
      nonce is hardcoded below; update if requests start returning 403.
"""

import json
import re
import time
import csv
import sys
from datetime import date, timedelta
from pathlib import Path

import requests

# ── config ──────────────────────────────────────────────────────────────────
COOKIE_FILE = Path.home() / ".menthorq" / "session.txt"
NONCE = "0e760b6ec4"
START = date(2026, 3, 6)
END = date.today()
DELAY = 0.6  # seconds between requests

INSTRUMENTS = [
    ("6A",  "6AU2026"),
    ("6J",  "6JU2026"),
]
# Full set: [("NQ","nq1!"),("CL","CLQ2026"),("GC","GCQ2026"),("6A","6AU2026"),("6J","6JU2026")]

BASE_DIR = Path("data/menthorq")
# ────────────────────────────────────────────────────────────────────────────

HEADERS = {
    "accept": "application/json, text/javascript, */*; q=0.01",
    "content-type": "application/x-www-form-urlencoded; charset=UTF-8",
    "origin": "https://menthorq.com",
    "referer": "https://menthorq.com/account/",
    "user-agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/149.0.0.0 Safari/537.36",
    "x-requested-with": "XMLHttpRequest",
    "dnt": "1",
}


def load_cookies() -> dict:
    raw = COOKIE_FILE.read_text().strip()
    cookies = {}
    for part in raw.split(";"):
        part = part.strip()
        if "=" in part:
            k, v = part.split("=", 1)
            cookies[k.strip()] = v.strip()
    return cookies


def post(session: requests.Session, data: dict) -> dict:
    r = session.post(
        "https://menthorq.com/wp-admin/admin-ajax.php",
        headers=HEADERS,
        data=data,
        timeout=30,
    )
    r.raise_for_status()
    if not r.text.strip():
        raise ValueError(f"Empty response body for action={data.get('action')} slug={data.get('command_slug','')}")
    return r.json()


def fetch_day(session: requests.Session, ticker: str, d: str) -> dict | None:
    """Fetch all 5 endpoints for a date. Returns None if date unavailable."""
    base = {"security": NONCE, "ticker": ticker, "date": d, "is_intraday": "false"}

    def cmd(slug):
        payload = {**base, "action": "get_command", "command_slug": slug}
        j = post(session, payload)
        time.sleep(DELAY)
        return j

    def ticker_call():
        payload = {"action": "get_ticker", "security": NONCE,
                   "ticker": ticker, "date": d,
                   "auto_fallback": "false", "mode": "eod"}
        j = post(session, payload)
        time.sleep(DELAY)
        return j

    results = {}
    for slug, fn in [
        ("key_levels", lambda: cmd("key_levels")),
        ("bl_levels",  lambda: cmd("bl_levels")),
        ("levels_tv",  lambda: cmd("levels_tv")),
        ("netgex",     lambda: cmd("netgex")),
        ("ticker",     ticker_call),
    ]:
        try:
            j = fn()
        except requests.HTTPError as e:
            sc = e.response.status_code
            if sc in (400, 403):
                print(f"\n  {sc} auth error on {slug} — nonce or cookie expired. "
                      "Refresh your cURL and update ~/.menthorq/session.txt + "
                      "the NONCE in this script, then re-run.",
                      flush=True)
                sys.exit(1)
            raise
        except ValueError as e:
            print(f"  [empty-response] {e} — skipping date")
            return None

        if not j.get("success"):
            err = j.get("data", {}).get("error_type", "")
            if err == "date_unavailable":
                return None
            msg = j.get("data", {}).get("message", "")
            print(f"  [{slug} failed: {msg}]", end=" ", flush=True)
            if slug == "bl_levels":
                # bl_levels is unavailable for some instruments (e.g. forex) — continue
                results[slug] = None
                continue
            return None

        results[slug] = j

    return results


def parse_row(d: str, results: dict) -> dict:
    row = {"date": d}

    # key_levels
    kl_data = results["key_levels"]["data"]["resource"]["data"]
    for k, v in kl_data.items():
        col = k.lower().replace(" ", "_").replace(".", "").replace("/", "_")
        row[col] = v

    # blind spots (may be None for instruments without bl data)
    if results.get("bl_levels") is not None:
        bl_txt = results["bl_levels"]["data"]["resource"]["text_data"]
        bls = dict(re.findall(r"BL (\d+), ([\d.]+)", bl_txt))
        for i in range(1, 11):
            row[f"bl_{i}"] = float(bls[str(i)]) if str(i) in bls else None
    else:
        for i in range(1, 11):
            row[f"bl_{i}"] = None

    # levels_tv (superset: 0DTE HVL, Gamma Wall 0DTE, GEX 1-10)
    tv_txt = results["levels_tv"]["data"]["resource"]["text_data"]
    tv_pairs = {k.strip(): v for k, v in re.findall(r"([A-Za-z0-9 /]+?),\s*([\d.]+)(?=,|$)", tv_txt)}
    def tv(key, default=None):
        return float(tv_pairs[key]) if key in tv_pairs else default
    row["hvl_0dte"]        = tv("HVL 0DTE")
    row["gamma_wall_0dte"] = tv("Gamma Wall 0DTE")
    for i in range(1, 11):
        row[f"gex_{i}"] = tv(f"GEX {i}")

    # netgex
    ng_data = results["netgex"]["data"]["resource"].get("data", {})
    strikes = ng_data.get("Top Net GEX Strikes", [])
    for i, s in enumerate(strikes, 1):
        if i > 3:
            break
        row[f"top_gex_strike_{i}"] = s

    # ticker / qscore
    td = results["ticker"]["data"]["ticker_data"]
    liq = td.get("liq_snapshot", {})
    row["contract"]        = liq.get("Contract")
    row["pc_oi"]           = liq.get("P/C OI")
    row["gamma_condition"] = liq.get("Gamma Condition")
    exp = liq.get("1D Exp Move %", "")
    row["exp_move_1d_pct"] = re.sub(r"[^\d.]", "", exp) or None

    qs = td.get("qscore_data") or {}
    for part in ["option_score", "momentum_score", "volatility_score", "seasonality_score"]:
        sub = qs.get(part) or {}
        row[part] = sub.get(part)

    return row


def trading_days(start: date, end: date):
    d = start
    while d <= end:
        if d.weekday() < 5:
            yield d
        d += timedelta(days=1)


def run_instrument(session: requests.Session, name: str, ticker: str):
    raw_dir = BASE_DIR / f"raw_{name}"
    out_csv = BASE_DIR / f"menthorq_levels_{name}.csv"
    raw_dir.mkdir(parents=True, exist_ok=True)

    all_rows = []
    days = list(trading_days(START, END))
    print(f"\n{'='*50}")
    print(f"{name} ({ticker}) — {len(days)} trading days")

    for i, d in enumerate(days):
        ds = d.isoformat()
        day_dir = raw_dir / ds

        if day_dir.exists() and len(list(day_dir.glob("*.json"))) == 5:
            print(f"  [{i+1:3}/{len(days)}] {ds} — cached")
            raw = {p.stem: json.loads(p.read_text()) for p in day_dir.glob("*.json")}
            try:
                all_rows.append(parse_row(ds, raw))
            except Exception as e:
                print(f"    parse error from cache: {e}")
            continue

        print(f"  [{i+1:3}/{len(days)}] {ds} ... ", end="", flush=True)
        results = fetch_day(session, ticker, ds)

        if results is None:
            print("skip")
            continue

        day_dir.mkdir(parents=True, exist_ok=True)
        for slug, j in results.items():
            (day_dir / f"{slug}.json").write_text(json.dumps(j, indent=2))

        try:
            row = parse_row(ds, results)
            all_rows.append(row)
            print(f"OK (call={row.get('call_resistance')} bl1={row.get('bl_1')})")
        except Exception as e:
            print(f"parse error: {e}")

    if not all_rows:
        print(f"  No rows for {name}")
        return

    all_rows.sort(key=lambda r: r["date"])
    fieldnames = list(all_rows[0].keys())
    for r in all_rows:
        for k in r:
            if k not in fieldnames:
                fieldnames.append(k)

    with open(out_csv, "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=fieldnames, extrasaction="ignore")
        w.writeheader()
        w.writerows(all_rows)

    print(f"  -> {len(all_rows)} days written to {out_csv}")


def main():
    BASE_DIR.mkdir(parents=True, exist_ok=True)
    cookies = load_cookies()
    session = requests.Session()
    session.cookies.update(cookies)

    for name, ticker in INSTRUMENTS:
        run_instrument(session, name, ticker)

    print("\nAll instruments done.")


if __name__ == "__main__":
    main()
