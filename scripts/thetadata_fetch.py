"""thetadata_fetch.py — pull historical OPRA NBBO (and optionally trade prints) from a
local Theta Terminal for every contract in the ThetaData work-list, to ground-truth the
options-sim fills.  Stdlib only (urllib) — no extra deps.

PREREQ (NOT present on this machine yet — see handoff S111 §5):
  1. Java JRE 11+ on PATH.
  2. Theta Terminal (jar) running, logged in with the ThetaData account.
     -> serves REST at  http://127.0.0.1:25503/v3  (v2 at :25510).
Without the terminal this script fetches NOTHING and says so (it never fabricates a pull).
`--dry-run` needs no terminal and just prints the URLs it WOULD hit — use it to verify now.

INPUT: the newest data/options_sim/thetadata_pull_list_*.csv (from thetadata_worklist.py),
       or pass --worklist <path>.

VERIFIED endpoint specs (handoff S111 §5):
  v3 NBBO   GET /v3/option/history/quote
            ?symbol=<root>&expiration=YYYYMMDD&strike=<dollars.3f>&right=call|put
            &date=YYYYMMDD&interval=tick&format=csv
            -> csv: timestamp,bid_size,bid,ask_size,ask,...
  v2 prints GET /v2/hist/option/trade_quote
            ?root=<root>&exp=YYYYMMDD&strike=<1/10-cent int>&right=C|P
            &start_date=YYYYMMDD&end_date=YYYYMMDD
UNCONFIRMED until smoke-test: ThetaData root for SPX weeklys (SPXW vs SPX).  `--probe`
tries both on one contract and reports which returns rows.

OUTPUT:
  data/thetadata/quotes/<date>/<root>_<expiry>_<strike><R>.csv    (one file per contract)
  data/thetadata/_fetch_manifest_<YYYYMMDD>.csv                   (per-contract status log)
Resumable: a contract whose output exists and is non-empty is skipped unless --force.

Run:
  .venv/Scripts/python.exe scripts/thetadata_fetch.py --dry-run            # no terminal needed
  .venv/Scripts/python.exe scripts/thetadata_fetch.py --probe              # confirm root (terminal up)
  .venv/Scripts/python.exe scripts/thetadata_fetch.py --limit 1            # smoke-test 1 contract
  .venv/Scripts/python.exe scripts/thetadata_fetch.py                      # full pull
"""
from __future__ import annotations

import argparse
import datetime as dt
import socket
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
PULL_DIR = ROOT / "data" / "options_sim"
OUT = ROOT / "data" / "thetadata" / "quotes"

V3_HOST, V3_PORT = "127.0.0.1", 25503
V2_HOST, V2_PORT = "127.0.0.1", 25510
V3_BASE = f"http://{V3_HOST}:{V3_PORT}"
V2_BASE = f"http://{V2_HOST}:{V2_PORT}"

SETUP_MSG = (
    "\n!! Theta Terminal is NOT reachable at {base}.\n"
    "   ThetaData needs a LOCAL terminal, not just the subscription:\n"
    "     1. Install Java JRE 11+  (java must be on PATH)\n"
    "     2. Download + launch Theta Terminal (jar), log in with the ThetaData account\n"
    "     3. Re-run this script (it serves REST at {base})\n"
    "   Nothing was fetched. (Use --dry-run to verify URLs without the terminal.)\n"
)


# ----------------------------------------------------------------- URL builders
def v3_url(root: str, expiry: str, strike_v3: str, right_v3: str, date: str) -> str:
    q = urllib.parse.urlencode({
        "symbol": root, "expiration": expiry, "strike": strike_v3,
        "right": right_v3, "date": date, "interval": "tick", "format": "csv",
    })
    return f"{V3_BASE}/v3/option/history/quote?{q}"


def v2_url(root: str, expiry: str, strike_v2: int, right: str, date: str) -> str:
    q = urllib.parse.urlencode({
        "root": root, "exp": expiry, "strike": strike_v2, "right": right,
        "start_date": date, "end_date": date,
    })
    return f"{V2_BASE}/v2/hist/option/trade_quote?{q}"


def build_url(row, dataset: str, root_override: str | None = None) -> str:
    # Derive strike encodings from the authoritative float so a CSV round-trip can't
    # drop the required decimals (v3 wants 7560.000, not 7560.0).
    root = root_override or row["theta_root"]
    strike = float(row["strike"])
    if dataset == "quote":
        return v3_url(root, str(row["expiry"]), f"{strike:.3f}",
                      str(row["right_v3"]), str(row["date"]))
    return v2_url(root, str(row["expiry"]), int(round(strike * 1000)),
                  str(row["right"]), str(row["date"]))


# --------------------------------------------------------------------- terminal
def terminal_up(port: int) -> bool:
    try:
        with socket.create_connection((V3_HOST, port), timeout=2):
            return True
    except OSError:
        return False


def http_get(url: str, retries: int = 3, backoff: float = 1.5) -> tuple[int, bytes]:
    """GET with small retry/backoff. Returns (http_status, body). status 0 = connection error."""
    last = (0, b"")
    for attempt in range(retries):
        try:
            with urllib.request.urlopen(url, timeout=60) as r:
                return r.status, r.read()
        except urllib.error.HTTPError as e:
            body = e.read() if hasattr(e, "read") else b""
            # 4xx won't improve on retry; 5xx / 429 might
            if e.code < 500 and e.code != 429:
                return e.code, body
            last = (e.code, body)
        except (urllib.error.URLError, socket.timeout, OSError) as e:
            last = (0, str(e).encode())
        time.sleep(backoff * (attempt + 1))
    return last


def _is_data(body: bytes) -> bool:
    """A CSV body with at least one data row beyond the header."""
    if not body:
        return False
    txt = body.decode("utf-8", "replace").strip()
    if not txt or txt.lower().startswith(("{", "error", "no data")):
        return False
    return txt.count("\n") >= 1          # header + >=1 row


# ------------------------------------------------------------------------- load
def newest_worklist() -> Path | None:
    cands = sorted(PULL_DIR.glob("thetadata_pull_list_*.csv"))
    return cands[-1] if cands else None


def out_path(row, dataset: str) -> Path:
    sub = "quotes" if dataset == "quote" else "trade_quote"
    d = ROOT / "data" / "thetadata" / sub / str(row["date"])
    fn = f"{row['occ_root']}_{row['expiry']}_{int(round(float(row['strike'])))}{row['right']}.csv"
    return d / fn


# ------------------------------------------------------------------------ probe
def probe(df: pd.DataFrame, dataset: str) -> None:
    """Try both root candidates on ONE contract; report which returns data."""
    if not terminal_up(V3_PORT if dataset == "quote" else V2_PORT):
        print(SETUP_MSG.format(base=V3_BASE if dataset == "quote" else V2_BASE))
        return
    row = df.iloc[0]
    cands = [row["theta_root"], row.get("theta_root_alt", row["theta_root"])]
    seen = []
    print(f"Probing roots {cands} on {row['occ_root']} {row['expiry']} "
          f"{row['strike']} {row['right']} ({dataset})...\n")
    for root in dict.fromkeys(cands):            # unique, preserve order
        url = build_url(row, dataset, root_override=root)
        status, body = http_get(url)
        ok = status == 200 and _is_data(body)
        rows = body.decode("utf-8", "replace").count("\n")
        print(f"  root={root:5s}  HTTP {status}  data={'YES' if ok else 'no'}  (~{rows} lines)")
        print(f"    {url}")
        seen.append((root, ok))
    winners = [r for r, ok in seen if ok]
    print("\n  -> use root:", winners[0] if winners else "NONE returned data — check terminal/entitlement")


# ------------------------------------------------------------------------- main
def run(df: pd.DataFrame, dataset: str, dry: bool, force: bool, limit: int | None) -> int:
    if limit:
        df = df.head(limit)
    port = V3_PORT if dataset == "quote" else V2_PORT
    base = V3_BASE if dataset == "quote" else V2_BASE

    if dry:
        print(f"DRY RUN — {len(df)} contract(s), dataset={dataset}. URLs only, no network.\n")
        for _, row in df.head(limit or 10).iterrows():
            print(" ", build_url(row, dataset))
        if len(df) > (limit or 10):
            print(f"  ... (+{len(df) - (limit or 10)} more)")
        print(f"\n  out dir: {out_path(df.iloc[0], dataset).parent.parent.relative_to(ROOT)}/<date>/")
        return 0

    if not terminal_up(port):
        print(SETUP_MSG.format(base=base))
        return 2

    stamp = dt.datetime.now().strftime("%Y%m%d")
    man_path = ROOT / "data" / "thetadata" / f"_fetch_manifest_{stamp}.csv"
    man_path.parent.mkdir(parents=True, exist_ok=True)
    log = []
    n_ok = n_skip = n_empty = n_fail = 0
    t0 = time.time()
    for _, row in df.iterrows():
        dest = out_path(row, dataset)
        tag = f"{row['occ_root']} {row['expiry']} {int(round(float(row['strike'])))}{row['right']}"
        if dest.exists() and dest.stat().st_size > 0 and not force:
            n_skip += 1
            log.append({"contract": tag, "status": "skip_exists", "rows": "", "bytes": dest.stat().st_size})
            continue
        url = build_url(row, dataset)
        status, body = http_get(url)
        if status == 200 and _is_data(body):
            dest.parent.mkdir(parents=True, exist_ok=True)
            dest.write_bytes(body)
            nrows = body.decode("utf-8", "replace").count("\n")
            n_ok += 1
            log.append({"contract": tag, "status": "ok", "rows": nrows, "bytes": len(body)})
        elif status == 200:
            n_empty += 1
            log.append({"contract": tag, "status": "empty_no_data", "rows": 0, "bytes": len(body)})
        else:
            n_fail += 1
            log.append({"contract": tag, "status": f"http_{status}", "rows": "",
                        "bytes": len(body), "detail": body[:200].decode("utf-8", "replace")})
        if (n_ok + n_fail + n_empty) % 25 == 0:
            print(f"  ...{n_ok} ok / {n_skip} skip / {n_empty} empty / {n_fail} fail")

    pd.DataFrame(log).to_csv(man_path, index=False)
    dur = time.time() - t0
    print(f"\ndone in {dur:.0f}s — ok={n_ok} skip={n_skip} empty={n_empty} fail={n_fail}")
    print(f"manifest -> {man_path.relative_to(ROOT)}")
    print("REMINDER: catalog the new data/thetadata family (catalog.yaml) now that data landed.")
    return 0 if n_fail == 0 else 1


def main() -> int:
    ap = argparse.ArgumentParser(description="Fetch ThetaData NBBO/prints for the work-list")
    ap.add_argument("--worklist", help="pull-list CSV (default: newest thetadata_pull_list_*.csv)")
    ap.add_argument("--dataset", choices=["quote", "trade_quote"], default="quote",
                    help="quote=v3 NBBO (default), trade_quote=v2 prints")
    ap.add_argument("--dry-run", action="store_true", help="print URLs only; no terminal needed")
    ap.add_argument("--probe", action="store_true", help="confirm root on 1 contract (terminal up)")
    ap.add_argument("--limit", type=int, help="only the first N contracts (smoke-test)")
    ap.add_argument("--force", action="store_true", help="re-fetch even if output exists")
    args = ap.parse_args()

    wl = Path(args.worklist) if args.worklist else newest_worklist()
    if not wl or not wl.exists():
        print("No work-list found. Run: .venv/Scripts/python.exe scripts/thetadata_worklist.py")
        return 1
    df = pd.read_csv(wl)
    print(f"work-list: {wl.relative_to(ROOT)}  ({len(df)} contracts)\n")

    if args.probe:
        probe(df, args.dataset)
        return 0
    return run(df, args.dataset, args.dry_run, args.force, args.limit)


if __name__ == "__main__":
    raise SystemExit(main())
