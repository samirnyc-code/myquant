"""ib_flex_executions.py — recover IB's REAL execution timestamps (+ commissions) for PAST
trades via the IBKR Flex Web Service, then reconcile them onto our orders.csv.

WHY (S112): orders.csv `ts_et` is our machine wall-clock at the fill callback (+latency, 1s),
NOT the exchange execution time.  reqExecutions only reaches the current session, so the
Aug-2026 exec times aren't in the API anymore.  BUT IBKR keeps every execution server-side
— including for PAPER accounts (paper has its own Flex setup in Account Management; identical
API).  A Trade Confirmation Flex query returns each execution WITH its timestamp, for any
past date.  This pulls it and gives us the true fill time to align ThetaData ticks against.

ONE-TIME SETUP the user must do in the *paper* account's Client Portal (I can't — it's your
login + secrets):
  1. Settings -> Account Settings -> Flex Web Service -> ENABLE -> copy the TOKEN.
  2. Performance & Reports -> Flex Queries -> Trade Confirmation Flex -> new query:
       include Executions; fields: symbol, underlyingSymbol, expiry, strike, put/call,
       dateTime, quantity, price, ibCommission, exchange, orderID, execID, tradeID.
       Date period: custom -> August 2026 (or "Last 365 Days"). Save -> copy the QUERY ID.
  3. Provide them here (env vars keep them out of the repo):
       IBKR_FLEX_TOKEN=... IBKR_FLEX_QUERY=... .venv/Scripts/python.exe scripts/ib_flex_executions.py
     or:  --token <TOKEN> --query <QUERYID>

Stdlib only (urllib + xml.etree). Writes DATED CSV + catalogs. Secrets never printed/saved.

Flex Web Service v3 flow:
  SendRequest?t=TOKEN&q=QUERYID&v=3      -> ReferenceCode + Url   (or Warn/Fail)
  <Url>?t=TOKEN&q=REFERENCECODE&v=3      -> the statement XML (poll until ready)
"""
from __future__ import annotations

import argparse
import datetime as dt
import os
import time
import urllib.request
import xml.etree.ElementTree as ET
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "data" / "options_log"
BASE = "https://ndcdyn.interactivebrokers.com/AccountManagement/FlexWebService"

SETUP = __doc__.split("ONE-TIME SETUP", 1)[1]


def _get(url: str, timeout: int = 60) -> bytes:
    req = urllib.request.Request(url, headers={"User-Agent": "myquant-flex/1.0"})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return r.read()


def send_request(token: str, query: str) -> tuple[str, str]:
    """Kick off statement generation. Returns (reference_code, statement_url)."""
    url = f"{BASE}/SendRequest?t={token}&q={query}&v=3"
    root = ET.fromstring(_get(url))
    status = (root.findtext("Status") or "").strip()
    if status != "Success":
        code = root.findtext("ErrorCode") or "?"
        msg = root.findtext("ErrorMessage") or "unknown"
        raise RuntimeError(f"Flex SendRequest {status}: [{code}] {msg}")
    return root.findtext("ReferenceCode").strip(), root.findtext("Url").strip()


def get_statement(url: str, token: str, ref: str, tries: int = 12, wait: float = 5) -> bytes:
    """Poll for the generated statement (IB returns a 'in progress' warning until ready)."""
    stmt_url = f"{url}?t={token}&q={ref}&v=3"
    for i in range(tries):
        body = _get(stmt_url)
        head = body[:200].decode("utf-8", "replace")
        # while generating, IB returns a FlexStatementResponse with Warn/1019
        if "<FlexStatementResponse" in head and "Success" not in head:
            if "1019" in head or "generation in progress" in head.lower():
                time.sleep(wait)
                continue
            raise RuntimeError(f"Flex statement error: {head}")
        return body                                    # the actual statement XML
    raise RuntimeError("Flex statement not ready after polling — try again shortly")


def parse_executions(xml_bytes: bytes) -> list[dict]:
    """Pull execution-level rows. Handles TradeConfirm (confirm flex) and Trade (activity)."""
    root = ET.fromstring(xml_bytes)
    rows = []
    for tag in ("TradeConfirm", "Trade"):
        for el in root.iter(tag):
            a = el.attrib
            # only executions (activity flex mixes in lots/summary rows)
            if tag == "Trade" and a.get("levelOfDetail") not in (None, "", "EXECUTION"):
                continue
            rows.append({
                "ib_exec_time": a.get("dateTime") or f"{a.get('tradeDate','')} {a.get('tradeTime','')}".strip(),
                "trade_id": a.get("tradeID", ""),
                "order_id": a.get("orderID", ""),
                "exec_id": a.get("execID") or a.get("ibExecID", ""),
                "underlying": a.get("underlyingSymbol", ""),
                "symbol": a.get("symbol", ""),
                "expiry": a.get("expiry", ""),
                "strike": a.get("strike", ""),
                "put_call": a.get("putCall", ""),
                "side": a.get("buySell", ""),
                "quantity": a.get("quantity", ""),
                "price": a.get("price", ""),
                # Trade Confirmation Flex uses `commission`/`commissionCurrency`;
                # Activity Flex uses `ibCommission`/`currency` — accept either.
                "commission": a.get("commission") or a.get("ibCommission", ""),
                "currency": a.get("commissionCurrency") or a.get("currency", ""),
                "exchange": a.get("exchange", ""),
                "level": a.get("levelOfDetail", ""),
            })
    return rows


def main() -> int:
    ap = argparse.ArgumentParser(description="Recover IB real exec times (Flex Web Service or a saved file)")
    ap.add_argument("--token", default=os.environ.get("IBKR_FLEX_TOKEN"))
    ap.add_argument("--query", default=os.environ.get("IBKR_FLEX_QUERY"))
    ap.add_argument("--file", help="parse a Flex report you downloaded (XML) instead of the Web Service")
    args = ap.parse_args()

    if args.file:                                        # manual route: no token needed
        p = Path(args.file)
        if not p.exists():
            print(f"no such file: {p}")
            return 1
        print(f"parsing downloaded Flex report: {p}")
        rows = parse_executions(p.read_bytes())
    elif args.token and args.query:                      # automated Web Service route
        print("Flex: requesting statement...")
        ref, url = send_request(args.token, args.query)
        print(f"  reference {ref} — polling for the statement...")
        rows = parse_executions(get_statement(url, args.token, ref))
    else:
        print("!! Provide --file <downloaded.xml>, OR a paper-account Flex token + query ID "
              "(env IBKR_FLEX_TOKEN / IBKR_FLEX_QUERY — never in the repo).")
        print(SETUP)
        return 2
    print(f"  parsed {len(rows)} execution row(s).")
    if not rows:
        print("  (no executions in the statement — check the query's date range + Executions field)")
        return 1

    import csv
    stamp = dt.datetime.now().strftime("%Y%m%d")
    out = OUT / f"ib_flex_executions_{stamp}.csv"
    with open(out, "w", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, fieldnames=list(rows[0].keys()))
        w.writeheader()
        w.writerows(rows)
    dates = sorted({r["ib_exec_time"][:8] for r in rows if r["ib_exec_time"]})
    print(f"saved -> {out.relative_to(ROOT)}  ({len(rows)} rows, dates {dates[:1]}..{dates[-1:]})")
    print("next: join to orders.csv on order_id to get the true fill time per leg; "
          "catalog the new data/options_log family.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
