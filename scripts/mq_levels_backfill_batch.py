"""Batched multi-ticker MenthorQ gamma-levels backfill (S75).

Same endpoint/fields as mq_levels_backfill.py, but requests up to 5 tickers per
call (tickers=A,B,C,D,E) — ~5x fewer requests — and works for tickers that carry
NO price block (index futures ES1!/NQ1!/… return price:null).

KEYING: each row is keyed on the levels' own EOD date (`data.date`) — the trading
day the levels were computed from that day's close. Spot (when the endpoint
supplies a price block: SPX + single stocks) is joined on the same EOD date; for
futures spot stays blank (the endpoint doesn't return it). One row per real
trading session, uniform across every ticker.

Writes data/menthorq/<TKR>_mq_levels_history.csv (+ _raw.jsonl). Dedup on write.

Run:
  .venv/Scripts/python.exe scripts/mq_levels_backfill_batch.py
  .venv/Scripts/python.exe scripts/mq_levels_backfill_batch.py --tickers ES1!,NQ1! --from 2021-09-28
"""
import csv
import datetime as dt
import json
import sys
import time
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
from mq_api import MQ  # noqa
from mq_levels_backfill import COLS, STEM, EARLIEST  # noqa

ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "data" / "menthorq"
BASE = "https://cf.menthorq.io/qbot-service/api/web/v1/levels"
DEFAULT_TICKERS = ["ES1!", "NQ1!", "RTY1!", "CL1!", "GC1!",
                   "AAPL", "MSFT", "NVDA", "AMZN", "GOOGL", "META", "TSLA"]


def parse_levels(item):
    """Return (edate, {stem:[value,gex]}) for the eod block, or None."""
    edate = item.get("date")
    if not edate:
        return None
    blocks = item.get("levels") or []
    block = next((b for b in blocks if b.get("kind") == "eod"), blocks[0] if blocks else None)
    if not block:
        return None
    L = {}
    for lv in block.get("level_values") or []:
        stem = STEM.get(lv.get("name"))
        if stem:
            L[stem] = [lv.get("value"), lv.get("gex")]
    return (edate, L) if L else None


def plausible(v, spot):
    if v is None or spot is None:
        return v
    return v if 0.5 * spot <= v <= 1.5 * spot else None


def chunks(xs, n):
    for i in range(0, len(xs), n):
        yield xs[i:i + n]


def build_rows(levels_map, spot_map):
    rows = []
    for edate in sorted(levels_map):
        L = levels_map[edate]
        sp = spot_map.get(edate, (None, None))
        spot = sp[0]
        row = {c: "" for c in COLS}
        row["session_date"] = edate
        row["eod_date"] = edate
        row["spot_eod"] = spot if spot is not None else ""
        row["spot_intraday"] = sp[1] if sp[1] is not None else ""
        for stem, (v, g) in L.items():
            pv = plausible(v, spot)
            row[stem] = pv if pv is not None else ""
            row[f"{stem}_gex"] = (g if pv is not None else "")
        rows.append(row)
    return rows


def flush(tkr, rows):
    csv_f = DATA / f"{tkr}_mq_levels_history.csv"
    existing = list(csv.DictReader(open(csv_f, encoding="utf-8"))) if csv_f.exists() else []
    allr = existing + [{c: ("" if r.get(c) is None else r[c]) for c in COLS} for r in rows]
    seen, dedup = set(), []
    for r in sorted(allr, key=lambda x: x["session_date"]):
        if r["session_date"] in seen:
            continue
        seen.add(r["session_date"])
        dedup.append(r)
    with open(csv_f, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=COLS)
        w.writeheader()
        w.writerows(dedup)
    return dedup


def main():
    a = sys.argv
    tickers = a[a.index("--tickers") + 1].split(",") if "--tickers" in a else DEFAULT_TICKERS
    if "--recent" in a:  # incremental: only sweep the last N calendar days (daily job)
        n = int(a[a.index("--recent") + 1])
        start = (dt.date.today() - dt.timedelta(days=n)).isoformat()
    else:
        start = a[a.index("--from") + 1] if "--from" in a else EARLIEST
    DATA.mkdir(parents=True, exist_ok=True)

    mq = MQ()
    # sweep to today+3 so the most recent EOD (surfaced by the next session's request) is captured
    days = [d.date().isoformat()
            for d in pd.bdate_range(start, dt.date.today() + dt.timedelta(days=3))]
    print(f"{len(tickers)} tickers · {len(days)} request-dates ({days[0]}..{days[-1]})")

    levels_map = {t: {} for t in tickers}   # t -> edate -> {stem:[v,g]}
    spot_map = {t: {} for t in tickers}     # t -> price.eod.date -> (eod, intraday)
    raw = {t: open(DATA / f"{t}_mq_levels_history_raw.jsonl", "a", encoding="utf-8") for t in tickers}
    req = 0

    for i, d in enumerate(days):
        for batch in chunks(tickers, 5):
            for attempt in range(3):
                try:
                    r = mq.s.get(BASE, headers={"accept": "application/json",
                                                "authorization": mq.token},
                                 params={"tickers": ",".join(batch),
                                         "level_types": "gamma_levels", "dates": d}, timeout=30)
                    req += 1
                    if r.status_code in (401, 403):
                        mq._auth()
                        continue
                    r.raise_for_status()
                    js = r.json()
                    break
                except Exception as e:
                    if attempt == 2:
                        print(f"  {d} {batch}: FAILED {str(e)[:50]}")
                        js = None
                    time.sleep(2)
            if not js:
                continue
            for item in js.get("data") or []:
                t = item.get("ticker")
                if t not in levels_map:
                    continue
                price = item.get("price") or {}
                eod = price.get("eod") or {}
                if eod.get("date") and eod.get("value") is not None:
                    spot_map[t][eod["date"]] = (eod.get("value"),
                                                (price.get("intraday") or {}).get("value"))
                parsed = parse_levels(item)
                if parsed:
                    edate, L = parsed
                    if edate not in levels_map[t]:
                        raw[t].write(json.dumps({"req": d, "item": item}) + "\n")
                    levels_map[t][edate] = L
            time.sleep(0.07)
        if i % 100 == 99:
            tot = sum(len(v) for v in levels_map.values())
            print(f"  ...{i+1}/{len(days)} dates  {tot} level-days  ({req} requests)", flush=True)

    for t in tickers:
        raw[t].close()
        dedup = flush(t, build_rows(levels_map[t], spot_map[t]))
        rng = f"{dedup[0]['session_date']}..{dedup[-1]['session_date']}" if dedup else "—"
        nospot = sum(1 for r in dedup if not r["spot_eod"])
        print(f"{t:7s}: {len(dedup)} sessions  {rng}"
              + (f"  (no-spot rows: {nospot})" if nospot else ""))
    # freshness marker for the command center
    mode = "recent" if "--recent" in a else ("range" if "--from" in a else "full")
    marker = {"finished_utc": dt.datetime.utcnow().isoformat(timespec="seconds") + "Z",
              "tickers": tickers, "requests": req, "mode": mode}
    (DATA / "levels_db_status.json").write_text(json.dumps(marker, indent=1), encoding="utf-8")
    print(f"\nDONE — {req} requests used.")


if __name__ == "__main__":
    main()
