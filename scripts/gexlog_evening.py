"""Pull GexLog's EVENING report (~19:45 ET) and archive the realized session verdict.

The evening report scores the session: session_type (TREND/RANGE...), whether the
morning forecast was accurate, whether the expected move held — the REALIZED
day-type our P&L buckets need (the morning brief only has the forecast).

Saves the full report to data/options_sim/evening_YYYYMMDD.json, annotates the
day's gameplan with a compact `gexlog_evening` block, and pushes a Telegram recap
(their verdict + our realized day P&L). Retries until today's stamp appears
(publishes ~18:45 CT; we poll to ~20:30 CT then give up).

Run (Task Scheduler ~19:05 CT, or manual):
  .venv/Scripts/python.exe scripts/gexlog_evening.py [--once]
"""
import argparse
import datetime as dt
import json
import sys
import time
from pathlib import Path
from zoneinfo import ZoneInfo

import requests

ROOT = Path(__file__).resolve().parents[1]
SIM = ROOT / "data" / "options_sim"
CT = ZoneInfo("America/Chicago")
ET = ZoneInfo("America/New_York")
H = {"User-Agent": "Mozilla/5.0 (myquant)", "Referer": "https://gexlog.com/dashboard/",
     "Accept": "application/json"}


def fetch_evening():
    r = requests.get("https://gexlog.com/dashboard/api/report.php",
                     params={"type": "evening"}, headers=H, timeout=20)
    r.raise_for_status()
    return r.json()


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--once", action="store_true", help="single fetch, no retry loop")
    args = ap.parse_args()

    date = dt.datetime.now(CT).strftime("%Y%m%d")
    today_et = dt.datetime.now(ET).strftime("%Y-%m-%d")
    deadline = dt.datetime.now(CT).replace(hour=20, minute=30, second=0, microsecond=0)

    d = None
    while True:
        try:
            d = fetch_evening()
        except Exception as e:
            print(f"fetch failed: {e}")
            d = None
        ga = str((d or {}).get("meta", {}).get("generatedAt", ""))
        if ga.startswith(today_et):
            break
        if args.once or dt.datetime.now(CT) >= deadline:
            print(f"today's evening report not available (last: {ga or 'none'}) — giving up")
            return 1
        print(f"[{dt.datetime.now(CT):%H:%M CT}] evening not out yet (last {ga}); retry in 10min")
        time.sleep(600)

    out = SIM / f"evening_{date}.json"
    out.write_text(json.dumps(d, indent=2), encoding="utf-8")
    sa = d.get("session_analysis", {}) or {}
    print(f"saved {out.name}: session={sa.get('session_type')} forecast_accurate="
          f"{sa.get('forecast_accurate')} em_hit={sa.get('expected_move_hit')}")

    # annotate the day's gameplan (append-only key; never touches triggers)
    gp_path = SIM / f"gameplan_{date}.json"
    if gp_path.exists():
        try:
            gp = json.loads(gp_path.read_text(encoding="utf-8"))
            gp["gexlog_evening"] = {
                "generated_at": d.get("meta", {}).get("generatedAt"),
                "session_type": sa.get("session_type"),
                "forecast_accurate": sa.get("forecast_accurate"),
                "expected_move_hit": sa.get("expected_move_hit"),
                "spx_change": sa.get("spx_change"), "vix_change": sa.get("vix_change"),
            }
            gp_path.write_text(json.dumps(gp, indent=2), encoding="utf-8")
            print("gameplan annotated with gexlog_evening")
        except Exception as e:
            print(f"gameplan annotate failed: {e}")

    # Telegram recap: their verdict + our realized day P&L
    try:
        sys.path.insert(0, str(ROOT / "scripts"))
        from notify_telegram import send
        import pandas as pd
        t = pd.read_parquet(ROOT / "data" / "options_log" / "trades.parquet")
        t = t[(t.entry_dt.astype(str).str[:10] == f"{date[:4]}-{date[4:6]}-{date[6:]}") & t.exit_dt.notna()]
        pnl = float(pd.to_numeric(t.pnl, errors="coerce").sum()) if len(t) else 0.0
        ico = "🟢" if pnl >= 0 else "🔴"
        send(f"🌙 <b>EVENING RECAP {date}</b>\n"
             f"their verdict: <b>{sa.get('session_type', '?')}</b> · forecast "
             f"{'✅' if sa.get('forecast_accurate') else '❌'} · EM held "
             f"{'✅' if sa.get('expected_move_hit') else '❌'}\n"
             f"{ico} our day: <b>${pnl:+,.0f}</b> ({len(t)} closed)\n"
             f"🔗 <a href='https://gexlog.com/dashboard/'>evening brief</a>",
             level="info", html=True, no_preview=True)
        print("pushed evening recap to Telegram")
    except Exception as e:
        print(f"telegram recap skipped: {e}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
