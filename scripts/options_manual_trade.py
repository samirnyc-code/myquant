"""Manual PAPER options trades, logged to the unified trade log (S73).

For discretionary / "random intraday" trades: places real orders on the paper
account (per-leg marketable limits — transparent, and fills at the same NBBO
the sim models), then writes the ACTUAL fills to data/options_log/trades.parquet
with source="paper". Close reverses the stored legs and books pnl.

  python scripts/options_manual_trade.py open --exp 20260728 --right P --short 7400 --long 7350
  python scripts/options_manual_trade.py open --exp 20260714 --right C --short 7550 --long 7560 --qty 2
  python scripts/options_manual_trade.py open --exp 20260714 --right P --long 7500        # plain long
  python scripts/options_manual_trade.py close --id paper_20260714_1531
  python scripts/options_manual_trade.py list
"""
import argparse
import datetime as dt
import json
import sys
from pathlib import Path
from zoneinfo import ZoneInfo

from ib_async import Option

sys.path.insert(0, str(Path(__file__).resolve().parent))
import ib_conn
import options_trade_log as tlog
from ib_order_test import marketable

ET = ZoneInfo("America/New_York")
FEE = 1.30  # $/contract, matches the sim/backtests


def now():
    return dt.datetime.now(ET)


def get_quote(ib, opt, wait=6):
    q = ib.reqMktData(opt, "", snapshot=False)
    ib.sleep(wait)
    return q


def qualify(ib, exp, strike, right):
    o = ib.qualifyContracts(Option("SPX", exp, strike, right, "SMART", tradingClass="SPXW"))
    if not o or not o[0].conId:
        o = ib.qualifyContracts(Option("SPX", exp, strike, right, "SMART", tradingClass="SPX"))
    if not o or not o[0].conId:
        raise SystemExit(f"cannot qualify SPX {exp} {strike} {right}")
    return o[0]


def exec_legs(ib, legs, qty):
    """legs: [(contract, 'BUY'|'SELL')]. Returns net price/contract (+=credit received)."""
    net = 0.0
    for c, action in legs:
        q = get_quote(ib, c)
        px = q.ask if action == "BUY" else q.bid
        if not (px == px and px > 0):
            raise SystemExit(f"no live quote on {c.strike}{c.right} — aborting (nothing placed after this leg)")
        tr = marketable(ib, c, action, qty, px)
        if tr.orderStatus.status != "Filled":
            raise SystemExit(f"leg {action} {c.strike}{c.right} did not fill — resolve in TWS/Gateway")
        fill = tr.orderStatus.avgFillPrice
        net += fill if action == "SELL" else -fill
    return net


def cmd_open(a):
    ib = ib_conn.connect()
    try:
        ib.reqMarketDataType(1)
        legs_spec = []
        if a.short:
            legs_spec.append((qualify(ib, a.exp, a.short, a.right), "SELL", "sell", a.short))
        if a.long:
            legs_spec.append((qualify(ib, a.exp, a.long, a.right), "BUY", "buy", a.long))
        if not legs_spec:
            raise SystemExit("give --short and/or --long")
        # BUY wings BEFORE selling shorts (naked-short-first triggers IB margin reject / Inactive)
        legs_spec.sort(key=lambda x: 0 if x[1] == "BUY" else 1)
        net = exec_legs(ib, [(c, act) for c, act, _, _ in legs_spec], a.qty)
        tid = f"paper_{now():%Y%m%d_%H%M}"
        width = abs(a.short - a.long) if (a.short and a.long) else None
        coll = (width - net) * 100 * a.qty if (width and net > 0) else abs(net) * 100 * a.qty
        tlog.append_entry({
            "trade_id": tid, "strategy_id": a.strategy, "source": "paper", "symbol": "SPXW",
            "entry_dt": now().strftime("%Y-%m-%d %H:%M"),
            "dte": (dt.datetime.strptime(a.exp, "%Y%m%d").date() - now().date()).days,
            "structure": f"{a.right}-spread {width:.0f}pt x{a.qty}" if width else f"long {a.right} x{a.qty}",
            "fill_model": "paper_fill",
            "legs": [{"side": s, "right": a.right, "strike": float(k), "expiry": a.exp, "qty": a.qty}
                     for _, _, s, k in legs_spec],
            "credit": net, "collateral": coll, "dow": now().strftime("%a"),
        })
        kind = "credit" if net > 0 else "debit"
        print(f"\nLOGGED {tid}: net {kind} {abs(net):.2f}/contract, collateral ${coll:,.0f}")
        print(tlog.summary())
    finally:
        ib.disconnect()


def cmd_close(a):
    tr = tlog.load()
    m = tr[tr.trade_id == a.id]
    if m.empty:
        raise SystemExit(f"unknown trade_id {a.id}; open: {list(tlog.open_trades().trade_id)}")
    row = m.iloc[0]
    if isinstance(row.exit_dt, str):
        raise SystemExit(f"{a.id} already closed")
    legs = json.loads(row.legs)
    ib = ib_conn.connect()
    try:
        ib.reqMarketDataType(1)
        qty = int(legs[0].get("qty", 1))
        rev = [(qualify(ib, l["expiry"], l["strike"], l["right"]),
                "BUY" if l["side"] == "sell" else "SELL") for l in legs]
        net = exec_legs(ib, rev, qty)  # + = credit received on close
        exit_cost = -net               # what closing COST per contract
        fees = 2 * len(legs) * qty * FEE
        r = tlog.update_exit(a.id, now().strftime("%Y-%m-%d %H:%M"), exit_cost, fees,
                             fill_model="paper_fill")
        print(f"\nCLOSED {a.id}: pnl ${r['pnl']:+,.2f}")
        print(tlog.summary())
    finally:
        ib.disconnect()


def main():
    ap = argparse.ArgumentParser()
    sub = ap.add_subparsers(dest="cmd", required=True)
    o = sub.add_parser("open")
    o.add_argument("--exp", required=True, help="YYYYMMDD")
    o.add_argument("--right", default="P", choices=["P", "C"])
    o.add_argument("--short", type=float, help="strike to SELL")
    o.add_argument("--long", type=float, help="strike to BUY")
    o.add_argument("--qty", type=int, default=1)
    o.add_argument("--strategy", default="manual")
    c = sub.add_parser("close")
    c.add_argument("--id", required=True)
    sub.add_parser("list")
    a = ap.parse_args()
    if a.cmd == "open":
        cmd_open(a)
    elif a.cmd == "close":
        cmd_close(a)
    else:
        ot = tlog.open_trades()
        print(ot[["trade_id", "strategy_id", "entry_dt", "structure", "credit"]].to_string(index=False)
              if len(ot) else "no open trades")
        print(tlog.summary())


if __name__ == "__main__":
    main()
