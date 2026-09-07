"""thetadata_fetch.py — pull historical OPRA data from a local Theta Terminal to
ground-truth the options-sim's SPX fills. Stdlib only (urllib). SPX (SPXW) only.

Three datasets (vendor-guided, S112):
  at_time      DEFAULT. `option/at_time/quote` — ONE call per FILL EVENT returns the last
               NBBO at/before that millisecond, plus the quote's own stamp (freshness). This
               is the recommended pattern for our 568 fills. Input: thetadata_events_*.csv.
  trade_quote  `option/.../trade_quote` over a ±window around each fill — did a print actually
               hit our price, and on which side. The print-confirmation second-check. Events input.
  quote        `option/history/quote` interval=tick — the WHOLE day of NBBO for a contract.
               Use only where you want to watch size at the touch evolve. Input: pull_list_*.csv.

Vendor-confirmed facts baked in:
  * ROOT = SPXW (SPX root has only AM monthlies / no 0DTE; SPXW is PM, holds every 0DTE).
  * Returned CSV columns (READ BY HEADER, not position):
      symbol,expiration,strike,right,timestamp,bid_size,bid_exchange,bid,bid_condition,
      ask_size,ask_exchange,ask,ask_condition
  * Standard = 4 requests in flight -> we run 4-way parallel (366 contracts / 568 fills = minutes).
  * history default window ends 16:00 ET (fine for 0DTE; SPXW stops at 16:00). end_time only
    matters for non-expiring contracts in the extended session.

PREREQ: Java + Theta Terminal (jar) running, logged in -> serves http://127.0.0.1:25503/v3.
Not installed here yet. `--dry-run` needs no terminal (prints the URLs it WOULD hit).

Run:
  .venv/Scripts/python.exe scripts/thetadata_fetch.py --dry-run          # verify URLs (no terminal)
  .venv/Scripts/python.exe scripts/thetadata_fetch.py --limit 1          # smoke-test 1 fill
  .venv/Scripts/python.exe scripts/thetadata_fetch.py                    # at_time, all fills, 4-way
  .venv/Scripts/python.exe scripts/thetadata_fetch.py --dataset trade_quote
  .venv/Scripts/python.exe scripts/thetadata_fetch.py --dataset quote    # full-day ticks per contract
"""
from __future__ import annotations

import argparse
import csv
import datetime as dt
import io
import socket
import time
import urllib.error
import urllib.parse
import urllib.request
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
PULL_DIR = ROOT / "data" / "options_sim"
V3_HOST, V3_PORT = "127.0.0.1", 25503
V3_BASE = f"http://{V3_HOST}:{V3_PORT}"
MAX_INFLIGHT = 4                                  # Standard tier: 4 requests in flight

SETUP_MSG = (
    "\n!! Theta Terminal is NOT reachable at {base}.\n"
    "   ThetaData needs a LOCAL terminal, not just the subscription:\n"
    "     1. Install Java JRE 11+  (java must be on PATH)\n"
    "     2. Download + launch Theta Terminal (jar), log in with the ThetaData account\n"
    "     3. Re-run this script (it serves REST at {base})\n"
    "   Nothing was fetched. (Use --dry-run to verify URLs without the terminal.)\n"
)


# ----------------------------------------------------------------- URL builders
def _strike_v3(strike) -> str:
    # v3 accepts dollars; 7560 and 7560.000 both work. We send .3f for an unambiguous form.
    return f"{float(strike):.3f}"


def at_time_url(row) -> str:
    q = urllib.parse.urlencode({
        "symbol": row["theta_root"], "expiration": str(row["expiry"]),
        "strike": _strike_v3(row["strike"]), "right": str(row["right_v3"]),
        "start_date": str(row["date"]), "end_date": str(row["date"]),
        "time_of_day": str(row["time_of_day_et"]), "format": "csv",
    })
    return f"{V3_BASE}/v3/option/at_time/quote?{q}"


def trade_quote_url(row) -> str:
    # v3 path/params to CONFIRM with vendor (they described start_time/end_time behavior; exact
    # v3 route not yet given). Best-effort; verify at smoke-test.
    q = urllib.parse.urlencode({
        "symbol": row["theta_root"], "expiration": str(row["expiry"]),
        "strike": _strike_v3(row["strike"]), "right": str(row["right_v3"]),
        "start_date": str(row["date"]), "end_date": str(row["date"]),
        "start_time": str(row["window_lo_et"]), "end_time": str(row["window_hi_et"]),
        "format": "csv",
    })
    return f"{V3_BASE}/v3/option/history/trade_quote?{q}"


def quote_url(row) -> str:
    q = urllib.parse.urlencode({
        "symbol": row["theta_root"], "expiration": str(row["expiry"]),
        "strike": _strike_v3(row["strike"]), "right": str(row["right_v3"]),
        "date": str(row["date"]), "interval": "tick", "format": "csv",
    })
    return f"{V3_BASE}/v3/option/history/quote?{q}"


URL_FN = {"at_time": at_time_url, "trade_quote": trade_quote_url, "quote": quote_url}
INPUT_GLOB = {"at_time": "thetadata_events_*.csv", "trade_quote": "thetadata_events_*.csv",
              "quote": "thetadata_pull_list_*.csv"}


# --------------------------------------------------------------------- terminal
def terminal_up() -> bool:
    try:
        with socket.create_connection((V3_HOST, V3_PORT), timeout=2):
            return True
    except OSError:
        return False


def http_get(url: str, retries: int = 3, backoff: float = 1.5) -> tuple[int, bytes]:
    last = (0, b"")
    for attempt in range(retries):
        try:
            with urllib.request.urlopen(url, timeout=60) as r:
                return r.status, r.read()
        except urllib.error.HTTPError as e:
            body = e.read() if hasattr(e, "read") else b""
            if e.code < 500 and e.code != 429:
                return e.code, body
            last = (e.code, body)
        except (urllib.error.URLError, socket.timeout, OSError) as e:
            last = (0, str(e).encode())
        time.sleep(backoff * (attempt + 1))
    return last


def _rows(body: bytes) -> list[dict]:
    """Parse a Theta CSV body BY HEADER (column order is not guaranteed)."""
    txt = body.decode("utf-8", "replace").strip()
    if not txt or txt[:1] in "{[" or txt.lower().startswith(("error", "no data")):
        return []
    return list(csv.DictReader(io.StringIO(txt)))


# ------------------------------------------------------------------------- load
def newest(glob: str) -> Path | None:
    c = sorted(PULL_DIR.glob(glob))
    return c[-1] if c else None


# ------------------------------------------------------- at_time / trade_quote
def run_at_time(df: pd.DataFrame, dataset: str, force: bool, limit: int | None) -> int:
    """One call per fill event -> a single combined CSV pairing our anchor with the real NBBO."""
    if limit:
        df = df.head(limit)
    out = ROOT / "data" / "thetadata" / f"{dataset}_results_{dt.datetime.now():%Y%m%d}.csv"
    out.parent.mkdir(parents=True, exist_ok=True)
    if out.exists() and not force:
        print(f"{out.relative_to(ROOT)} exists — use --force to overwrite.")
        return 0

    keep = ["trade_id", "strategy", "event", "side_action", "occ_root", "expiry",
            "strike", "right", "time_of_day_et", "time_source", "our_fill_price"]
    results, n_ok, n_empty, n_fail = [], 0, 0, 0
    urls = [(i, URL_FN[dataset](r)) for i, r in df.iterrows()]

    def fetch(item):
        i, url = item
        status, body = http_get(url)
        return i, url, status, body

    with ThreadPoolExecutor(max_workers=MAX_INFLIGHT) as ex:
        for i, url, status, body in (f.result() for f in as_completed(
                [ex.submit(fetch, it) for it in urls])):
            base = {k: df.loc[i, k] for k in keep if k in df.columns}
            rows = _rows(body) if status == 200 else []
            if status != 200:
                n_fail += 1
                results.append({**base, "quote_status": f"http_{status}"})
            elif not rows:
                n_empty += 1
                results.append({**base, "quote_status": "empty"})
            else:
                q = rows[-1]                          # at_time returns the as-of NBBO row
                n_ok += 1
                results.append({**base, "quote_status": "ok",
                                "quote_timestamp": q.get("timestamp", ""),
                                "bid_size": q.get("bid_size", ""), "bid": q.get("bid", ""),
                                "ask_size": q.get("ask_size", ""), "ask": q.get("ask", ""),
                                "bid_exchange": q.get("bid_exchange", ""),
                                "ask_exchange": q.get("ask_exchange", "")})
            if (n_ok + n_empty + n_fail) % 50 == 0:
                print(f"  ...{n_ok} ok / {n_empty} empty / {n_fail} fail")

    pd.DataFrame(results).to_csv(out, index=False)
    print(f"\ndone — ok={n_ok} empty={n_empty} fail={n_fail}")
    print(f"saved -> {out.relative_to(ROOT)}  (our fill vs the real NBBO, per event)")
    print("REMINDER: catalog the new data/thetadata family now that data landed.")
    return 0 if n_fail == 0 else 1


# ------------------------------------------------------- quote (full-day ticks)
def run_quote(df: pd.DataFrame, force: bool, limit: int | None) -> int:
    if limit:
        df = df.head(limit)
    outdir = ROOT / "data" / "thetadata" / "quotes"
    man, n_ok, n_skip, n_empty, n_fail = [], 0, 0, 0, 0
    jobs = []
    for _, row in df.iterrows():
        dest = outdir / str(row["date"]) / (
            f"{row['occ_root']}_{row['expiry']}_{int(round(float(row['strike'])))}{row['right']}.csv")
        jobs.append((row, dest))

    def fetch(job):
        row, dest = job
        if dest.exists() and dest.stat().st_size > 0 and not force:
            return ("skip", dest, None)
        status, body = http_get(quote_url(row))
        if status == 200 and _rows(body):
            return ("ok", dest, body)
        return ("empty" if status == 200 else f"http_{status}", dest, None)

    with ThreadPoolExecutor(max_workers=MAX_INFLIGHT) as ex:
        for kind, dest, body in (f.result() for f in as_completed(
                [ex.submit(fetch, j) for j in jobs])):
            if kind == "skip":
                n_skip += 1
            elif kind == "ok":
                dest.parent.mkdir(parents=True, exist_ok=True)
                dest.write_bytes(body)
                n_ok += 1
            elif kind == "empty":
                n_empty += 1
            else:
                n_fail += 1
            man.append({"file": dest.name, "status": kind})
    stamp = dt.datetime.now().strftime("%Y%m%d")
    pd.DataFrame(man).to_csv(ROOT / "data" / "thetadata" / f"_quote_manifest_{stamp}.csv", index=False)
    print(f"\ndone — ok={n_ok} skip={n_skip} empty={n_empty} fail={n_fail} -> data/thetadata/quotes/")
    return 0 if n_fail == 0 else 1


# ------------------------------------------------------------------------- main
def main() -> int:
    ap = argparse.ArgumentParser(description="Fetch ThetaData for the fill work-list")
    ap.add_argument("--dataset", choices=["at_time", "trade_quote", "quote"], default="at_time")
    ap.add_argument("--worklist", help="input CSV (default: newest for the dataset)")
    ap.add_argument("--dry-run", action="store_true", help="print URLs only; no terminal needed")
    ap.add_argument("--limit", type=int, help="only the first N rows (smoke-test)")
    ap.add_argument("--force", action="store_true", help="overwrite existing output")
    args = ap.parse_args()

    wl = Path(args.worklist) if args.worklist else newest(INPUT_GLOB[args.dataset])
    if not wl or not wl.exists():
        print(f"No input for dataset={args.dataset}. Run scripts/thetadata_worklist.py first.")
        return 1
    df = pd.read_csv(wl)
    print(f"dataset={args.dataset}  input={wl.relative_to(ROOT)}  ({len(df)} rows)\n")

    if args.dry_run:
        show = df.head(args.limit or 8)
        for _, r in show.iterrows():
            print(" ", URL_FN[args.dataset](r))
        if len(df) > len(show):
            print(f"  ... (+{len(df) - len(show)} more)")
        return 0

    if not terminal_up():
        print(SETUP_MSG.format(base=V3_BASE))
        return 2

    if args.dataset == "quote":
        return run_quote(df, args.force, args.limit)
    return run_at_time(df, args.dataset, args.force, args.limit)


if __name__ == "__main__":
    raise SystemExit(main())
