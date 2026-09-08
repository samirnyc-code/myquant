"""Pull the gexlog.com report archive (morning+evening) via the archive API.

Endpoint discovered 2026-08-04: api/archive.php?action=report&type={morning|evening}&date=YYYY-MM-DD
History spans 2026-04-06 .. present, ~2 reports/day. No history route exists for
per-strike gex_profile beyond what each report embeds. Saves raw JSON per report +
a flattened per-day CSV for backtesting.

Modes:
  (default / --full)  fetch EVERY date the archive lists (re-scrapes everything).
  --incremental       fetch only dates whose raw JSON is missing on disk, then
                      rebuild the CSV from ALL saved raw files. Self-healing:
                      a report published later just lands on the next run.
                      This is what the twice-daily scheduled task uses.

The CSV is always rebuilt from the raw files ON DISK, so it stays complete
regardless of mode.
"""
import argparse
import csv
import glob
import json
from pathlib import Path

from playwright.sync_api import sync_playwright

ROOT = Path(__file__).resolve().parents[1]
RAW = ROOT / "data/gexlog/raw"
RAW.mkdir(parents=True, exist_ok=True)
OUT = ROOT / "data/gexlog"
DATES_URL = "https://gexlog.com/dashboard/api/archive.php?action=dates"
REPORT_URL = "https://gexlog.com/dashboard/api/archive.php?action=report&type={typ}&date={dt}"


def g(d, *path, default=None):
    for k in path:
        if isinstance(d, dict):
            d = d.get(k)
        else:
            return default
    return d if d is not None else default


def flat_morning(d):
    lv = g(d, "levels", default={})
    gm = g(d, "forecast", "factors", "gamma", default={})
    return dict(
        regime=gm.get("value"), net_gex=gm.get("net_gex"), gex_flip=gm.get("gex_flip"),
        gex_method=gm.get("gex_method"),
        putWall=lv.get("putWall"), callWall=lv.get("callWall"), current=lv.get("current"),
        r2=lv.get("r2"), r1=lv.get("r1"), s1=lv.get("s1"), s2=lv.get("s2"),
        expectedMove=lv.get("expectedMove"), emUpper=lv.get("emUpper"), emLower=lv.get("emLower"),
        signal=g(d, "guidance", "signal"), risk_level=g(d, "risk", "level"),
        forecast_type=g(d, "forecast", "type"), confidence=g(d, "forecast", "confidence"),
        es=g(d, "market", "es", "price"), vix=g(d, "market", "vix", "price"),
        regime_streak=g(d, "forecast", "regime_streak", "regime_count"),
        day_type_label=g(d, "forecast", "regime_streak", "day_type_label"),
    )


def flat_evening(d):
    sa = g(d, "session_analysis", default={})
    lv = g(d, "levels", default={})
    gm = g(d, "forecast", "factors", "gamma", default={})
    return dict(
        e_spx_change=sa.get("spx_change"), e_vix_change=sa.get("vix_change"),
        e_session_type=sa.get("session_type"), e_forecast_accurate=sa.get("forecast_accurate"),
        e_em_hit=sa.get("expected_move_hit"),
        e_net_gex=gm.get("net_gex"), e_putWall=lv.get("putWall"), e_callWall=lv.get("callWall"),
        e_current=lv.get("current"), e_regime=gm.get("value"),
    )


FLAT = {"morning": flat_morning, "evening": flat_evening}


def rebuild_csv():
    """Rebuild gexlog_daily.csv from every raw JSON currently on disk."""
    by_date = {}
    for f in sorted(glob.glob(str(RAW / "*_*.json"))):
        name = Path(f).stem  # YYYY-MM-DD_morning
        dt, _, typ = name.partition("_")
        if typ not in FLAT:
            continue
        try:
            j = json.loads(Path(f).read_text(encoding="utf-8"))
        except Exception:
            continue
        row = by_date.setdefault(dt, {"date": dt})
        row.update(FLAT[typ](j))
    rows = [by_date[d] for d in sorted(by_date)]
    cols = sorted({k for r in rows for k in r}, key=lambda c: (c != "date", c))
    with open(OUT / "gexlog_daily.csv", "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=cols)
        w.writeheader()
        w.writerows(rows)
    return len(rows), len(cols)


def fetch(incremental):
    fetched, skipped, failed = 0, 0, 0
    with sync_playwright() as p:
        b = p.chromium.launch()
        pg = b.new_page()
        dates = pg.request.get(DATES_URL).json()
        all_dates = sorted(set(dates.get("morning", [])) | set(dates.get("evening", [])))
        if not all_dates:
            print("archive returned no dates — aborting (CSV untouched)")
            b.close()
            return 0, 0, 0
        print(f"archive lists {len(all_dates)} dates ({all_dates[0]}..{all_dates[-1]}); "
              f"mode={'incremental' if incremental else 'full'}")
        for dt in all_dates:
            for typ in ("morning", "evening"):
                dest = RAW / f"{dt}_{typ}.json"
                if incremental and dest.exists() and dest.stat().st_size > 0:
                    skipped += 1
                    continue
                url = REPORT_URL.format(typ=typ, dt=dt)
                try:
                    j = pg.request.get(url).json()
                    if isinstance(j, dict) and "error" not in j:
                        dest.write_text(json.dumps(j), encoding="utf-8")
                        fetched += 1
                    else:
                        failed += 1  # not published yet / no report
                except Exception as ex:
                    failed += 1
                    print(f"  {dt} {typ}: {str(ex)[:60]}")
        b.close()
    return fetched, skipped, failed


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--incremental", action="store_true",
                    help="fetch only missing dates (scheduled-task mode)")
    ap.add_argument("--full", action="store_true", help="re-scrape every date (default)")
    a = ap.parse_args()
    incremental = a.incremental and not a.full

    fetched, skipped, failed = fetch(incremental)
    nrows, ncols = rebuild_csv()
    print(f"fetched={fetched} skipped={skipped} not-ready/failed={failed}")
    print(f"CSV rebuilt: {nrows} rows x {ncols} cols -> data/gexlog/gexlog_daily.csv")


if __name__ == "__main__":
    main()
