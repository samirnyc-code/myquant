"""
MenthorQ historical backfill — ES1! gamma/blind spot levels
Pulls 5 endpoints per trading day and saves raw JSON + parsed CSV.

Output:
  data/menthorq/raw/YYYY-MM-DD/{key_levels,bl_levels,levels_tv,netgex,ticker}.json
  data/menthorq/menthorq_levels.csv

Auth: reads session cookie from ~/.menthorq/session.txt
      nonce is hardcoded; update if requests start returning 403.
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
TICKER = "es1!"
START = date(2026, 3, 6)
END = date.today()
DELAY = 0.6  # seconds between requests

RAW_DIR = Path("data/menthorq/raw")
OUT_CSV = Path("data/menthorq/menthorq_levels.csv")
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
    return r.json()


def fetch_day(session: requests.Session, d: str) -> dict | None:
    """Fetch all 5 endpoints for a date. Returns None if date unavailable."""
    base = {"security": NONCE, "ticker": TICKER, "date": d,
            "is_intraday": "false"}

    def cmd(slug):
        payload = {**base, "action": "get_command", "command_slug": slug}
        j = post(session, payload)
        time.sleep(DELAY)
        return j

    def ticker_call():
        payload = {"action": "get_ticker", "security": NONCE,
                   "ticker": TICKER, "date": d,
                   "auto_fallback": "false", "mode": "eod"}
        j = post(session, payload)
        time.sleep(DELAY)
        return j

    results = {}
    for slug, fn in [
        ("key_levels",  lambda: cmd("key_levels")),
        ("bl_levels",   lambda: cmd("bl_levels")),
        ("levels_tv",   lambda: cmd("levels_tv")),
        ("netgex",      lambda: cmd("netgex")),
        ("ticker",      ticker_call),
    ]:
        try:
            j = fn()
        except requests.HTTPError as e:
            if e.response.status_code == 403:
                print(f"\n  ✗ 403 auth error on {slug} — nonce or cookie expired. "
                      "Refresh your cURL and update ~/.menthorq/session.txt + "
                      "the NONCE in this script, then re-run.",
                      flush=True)
                sys.exit(1)
            raise

        # 422 = date unavailable (weekend / holiday / out of window)
        if not j.get("success"):
            err = j.get("data", {}).get("error_type", "")
            if err == "date_unavailable":
                return None
            # unexpected error on first slug — bail on this date
            print(f"  ⚠ unexpected error on {slug}: {j.get('data',{}).get('message','')}")
            return None

        results[slug] = j

    return results


def parse_row(d: str, results: dict) -> dict:
    row = {"date": d}

    # ── key_levels ───────────────────────────────────────────────────────────
    kl_data = results["key_levels"]["data"]["resource"]["data"]
    for k, v in kl_data.items():
        col = k.lower().replace(" ", "_").replace(".", "").replace("/", "_")
        row[col] = v

    # ── blind spots ──────────────────────────────────────────────────────────
    bl_txt = results["bl_levels"]["data"]["resource"]["text_data"]
    bls = dict(re.findall(r"BL (\d+), ([\d.]+)", bl_txt))
    for i in range(1, 11):
        row[f"bl_{i}"] = float(bls[str(i)]) if str(i) in bls else None

    # ── levels_tv (superset: adds 0DTE HVL, Gamma Wall 0DTE, GEX 1-10) ─────
    tv_txt = results["levels_tv"]["data"]["resource"]["text_data"]
    tv_pairs = {k.strip(): v for k, v in re.findall(r"([A-Za-z0-9 /]+?),\s*([\d.]+)(?=,|$)", tv_txt)}
    def tv(key, default=None):
        return float(tv_pairs[key]) if key in tv_pairs else default
    row["hvl_0dte"]       = tv("HVL 0DTE")
    row["gamma_wall_0dte"]= tv("Gamma Wall 0DTE")
    for i in range(1, 11):
        row[f"gex_{i}"] = tv(f"GEX {i}")

    # ── netgex (top GEX strikes) ─────────────────────────────────────────────
    ng_data = results["netgex"]["data"]["resource"].get("data", {})
    strikes = ng_data.get("Top Net GEX Strikes", [])
    for i, s in enumerate(strikes, 1):
        if i > 3:
            break
        row[f"top_gex_strike_{i}"] = s

    # ── ticker / qscore ──────────────────────────────────────────────────────
    td = results["ticker"]["data"]["ticker_data"]
    liq = td.get("liq_snapshot", {})
    row["contract"]         = liq.get("Contract")
    row["pc_oi"]            = liq.get("P/C OI")
    row["gamma_condition"]  = liq.get("Gamma Condition")
    exp = liq.get("1D Exp Move %", "")
    row["exp_move_1d_pct"]  = re.sub(r"[^\d.]", "", exp) or None

    qs = td.get("qscore_data") or {}
    for part in ["option_score", "momentum_score", "volatility_score", "seasonality_score"]:
        sub = qs.get(part) or {}
        row[part] = sub.get(part)

    return row


def trading_days(start: date, end: date):
    d = start
    while d <= end:
        if d.weekday() < 5:  # Mon-Fri
            yield d
        d += timedelta(days=1)


def main():
    RAW_DIR.mkdir(parents=True, exist_ok=True)
    OUT_CSV.parent.mkdir(parents=True, exist_ok=True)

    cookies = load_cookies()
    session = requests.Session()
    session.cookies.update(cookies)

    all_rows = []
    days = list(trading_days(START, END))
    print(f"Fetching {len(days)} trading days ({START} to {END}) ...\n")

    for i, d in enumerate(days):
        ds = d.isoformat()
        day_dir = RAW_DIR / ds

        # skip if already fully fetched (all 5 raw files exist)
        if day_dir.exists() and len(list(day_dir.glob("*.json"))) == 5:
            print(f"  [{i+1:3}/{len(days)}] {ds} — cached")
            # load from disk for CSV rebuild
            raw = {p.stem: json.loads(p.read_text()) for p in day_dir.glob("*.json")}
            try:
                all_rows.append(parse_row(ds, raw))
            except Exception as e:
                print(f"    parse error from cache: {e}")
            continue

        print(f"  [{i+1:3}/{len(days)}] {ds} … ", end="", flush=True)
        results = fetch_day(session, ds)

        if results is None:
            print("unavailable (skip)")
            continue

        # archive raw JSON
        day_dir.mkdir(parents=True, exist_ok=True)
        for slug, j in results.items():
            (day_dir / f"{slug}.json").write_text(json.dumps(j, indent=2))

        try:
            row = parse_row(ds, results)
            all_rows.append(row)
            print(f"✓  (kl={row.get('call_resistance')}  bl1={row.get('bl_1')}  gex1={row.get('gex_1')})")
        except Exception as e:
            print(f"  ✗ parse error: {e}")

    if not all_rows:
        print("No rows collected — nothing to write.")
        return

    # write CSV
    all_rows.sort(key=lambda r: r["date"])
    fieldnames = list(all_rows[0].keys())
    # union in case any day has extra/missing keys
    for r in all_rows:
        for k in r:
            if k not in fieldnames:
                fieldnames.append(k)

    with open(OUT_CSV, "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=fieldnames, extrasaction="ignore")
        w.writeheader()
        w.writerows(all_rows)

    print(f"\nDone. {len(all_rows)} days written to {OUT_CSV}")


if __name__ == "__main__":
    main()
