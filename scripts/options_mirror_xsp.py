"""options_mirror_xsp.py — Phase 2 of the mini mirror.

Mirror every SPX desk execution into XSP (Mini-SPX, 1/10 SPX, same Cboe/OPRA feed) on
the paper account, so we can measure the *exact* same strategy at 1/10 size and see how
much XSP's wider spreads + coarser strikes cost vs SPX. Produces a PARALLEL mini book
(data/options_log/trades_xsp.parquet) the mini dashboard tab renders.

How it mirrors:
  * ENTRY — poll the SPX book (trades.parquet). Each new SPX trade today → map its legs
    (strike/10 rounded to the nearest $1 XSP strike, same right/side/qty/expiry) → place
    the XSP combo on the paper account → log to the xsp book with a link to the SPX parent.
  * EXIT  — when the SPX parent closes, close the XSP mirror the same way.
  * The mapping is the honest mirror you'd actually trade: XSP strikes are $1 apart, so
    an SPX 25-wide (÷10 = 2.5) becomes a 2- or 3-wide — that rounding basis IS part of
    what we're measuring.

Runs alongside the desk during the session (own IB clientId 73). Real paper orders by
default; --dry maps + logs WITHOUT placing anything (for verifying the mapping offline).

    python scripts/options_mirror_xsp.py --until 15:00
    python scripts/options_mirror_xsp.py --dry --date 2026-08-21   # map a past day, no orders
"""
from __future__ import annotations
import argparse
import datetime as dt
import json
import time
from pathlib import Path
from zoneinfo import ZoneInfo

ROOT = Path(__file__).resolve().parents[1]
LOG = ROOT / "data" / "options_log"
SIM = ROOT / "data" / "options_sim"
CT = ZoneInfo("America/Chicago")
SYMBOL, TCLASS, CLIENT_ID = "XSP", "XSP", 73


def now_ct():
    return dt.datetime.now(CT)


# ---------------- the mapping (pure, testable without IB) ----------------

def xsp_strike(spx_strike) -> float:
    """SPX strike -> nearest listed XSP strike ($1 grid). 7635 -> 763.5 -> 764."""
    return float(round(float(spx_strike) / 10.0))


def map_legs(spx_legs):
    """Map SPX legs to XSP legs (strike/10 nearest $1; side/right/qty/expiry preserved)."""
    out = []
    for l in spx_legs:
        out.append({"side": l["side"], "right": l["right"],
                    "strike": xsp_strike(l["strike"]), "expiry": l["expiry"],
                    "qty": int(l.get("qty", 1))})
    return out


def mirror_row(spx, xsp_legs, credit, exit_cost=None, pnl=None, fill_model="paper_fill"):
    """Build an xsp-book row from an SPX parent trade + the executed XSP economics."""
    return {
        "trade_id": f"xsp_{spx['trade_id']}", "strategy_id": spx["strategy_id"],
        "source": "mirror_xsp", "symbol": "XSP", "entry_dt": spx["entry_dt"],
        "exit_dt": spx.get("exit_dt"), "dte": spx.get("dte"),
        "structure": spx.get("structure"), "legs": xsp_legs, "credit": credit,
        "exit_cost": exit_cost, "fill_model": fill_model, "pnl": pnl,
        "max_loss": (spx.get("max_loss") / 10.0) if spx.get("max_loss") == spx.get("max_loss") else None,
        "max_gain": (spx.get("max_gain") / 10.0) if spx.get("max_gain") == spx.get("max_gain") else None,
        "collateral": (spx.get("collateral") / 10.0) if spx.get("collateral") == spx.get("collateral") else None,
        "close_reason": spx.get("close_reason"), "grade": spx.get("grade"),
        "vix": spx.get("vix"), "gex_regime": spx.get("gex_regime"),
        "entry_valid": spx.get("entry_valid"),
        "entry_note": f"mirror of SPX {spx['trade_id']}",
    }


# ---------------- XSP order placement (self-contained; SPX desk untouched) --------------

def _qualify(ib, exp, strike, right):
    from ib_async import Option
    o = ib.qualifyContracts(Option(SYMBOL, exp, strike, right, "SMART", tradingClass=TCLASS))
    if not o or not o[0].conId:
        raise RuntimeError(f"cannot qualify {SYMBOL} {exp} {strike}{right}")
    return o[0]


def _bag(ib, exp, legs):
    """BAG whose BUY == our position. legs=[(right,strike,action)]."""
    from ib_async import Contract, ComboLeg
    bag = Contract(secType="BAG", symbol=SYMBOL, currency="USD", exchange="SMART")
    bag.comboLegs = []
    for right, strike, action in legs:
        c = _qualify(ib, exp, strike, right)
        cl = ComboLeg()
        cl.conId, cl.ratio, cl.action, cl.exchange = c.conId, 1, action, "SMART"
        bag.comboLegs.append(cl)
    return bag


def _quote(ib, bag, wait=6):
    t = ib.reqMktData(bag, "", snapshot=False)
    ib.sleep(wait)
    bid, ask = t.bid, t.ask
    ib.cancelMktData(bag)
    ok = all(x == x and x is not None for x in (bid, ask))
    return (bid, ask) if ok else (None, None)


def open_combo(ib, exp, legs, qty=1):
    """BUY the bag (== our position) marketable at the ask; returns (credit, bag)."""
    from ib_async import LimitOrder
    bag = _bag(ib, exp, legs)
    bid, ask = _quote(ib, bag)
    if bid is None:
        raise RuntimeError("no XSP combo quote")
    o = LimitOrder("BUY", qty, round(ask, 2)); o.tif = "DAY"
    tr = ib.placeOrder(bag, o); ib.sleep(8)
    if tr.orderStatus.status == "Filled":
        return -tr.orderStatus.avgFillPrice, bag     # negative fill = credit
    ib.cancelOrder(tr.order)
    raise RuntimeError("XSP combo did not fill")


def close_combo(ib, bag, qty=1):
    from ib_async import LimitOrder
    bid, ask = _quote(ib, bag)
    if bid is None:
        raise RuntimeError("no XSP combo quote to close")
    o = LimitOrder("SELL", qty, round(bid, 2)); o.tif = "DAY"
    tr = ib.placeOrder(bag, o); ib.sleep(8)
    if tr.orderStatus.status == "Filled":
        return -tr.orderStatus.avgFillPrice
    ib.cancelOrder(tr.order)
    raise RuntimeError("XSP combo close did not fill")


def _open_actions(legs):
    """legs (dicts) -> [(right,strike,'BUY'|'SELL')] BUY-wings-first for a credit spread."""
    ordered = sorted(legs, key=lambda l: 0 if l["side"] == "buy" else 1)
    return [(l["right"], l["strike"], "BUY" if l["side"] == "buy" else "SELL") for l in ordered]


# ---------------- the mirror loop ----------------

def _today_spx(date):
    import options_trade_log as tlog
    tlog.set_book("spx")
    d = tlog.load()
    d["e"] = __import__("pandas").to_datetime(d["entry_dt"], errors="coerce")
    day = __import__("pandas").Timestamp(date)
    return d[(d["e"] >= day) & (d["e"] < day + __import__("pandas").Timedelta("1D"))]


def _xsp_ids(date):
    import options_trade_log as tlog
    tlog.set_book("xsp")
    d = tlog.load()
    return set(d.trade_id), d


def run_dry(date):
    """Map every SPX trade for `date` into the xsp book WITHOUT IB — verifies the mapping
    and gives the mini tab data to render. Fills are ESTIMATED (SPX economics / 10)."""
    import options_trade_log as tlog
    spx = _today_spx(date)
    print(f"[dry] mapping {len(spx)} SPX trades -> XSP mirror for {date}")
    tlog.set_book("xsp")
    have, _ = _xsp_ids(date)
    n = 0
    for _, r in spx.iterrows():
        tid = f"xsp_{r['trade_id']}"
        if tid in have:
            continue
        legs = r["legs"] if isinstance(r["legs"], list) else json.loads(r["legs"])
        xl = map_legs(legs)
        credit = round(float(r["credit"]) / 10.0, 2) if r.get("credit") == r.get("credit") else 0.0
        pnl = round(float(r["pnl"]) / 10.0, 2) if r.get("pnl") == r.get("pnl") else None
        ec = round(float(r["exit_cost"]) / 10.0, 2) if r.get("exit_cost") == r.get("exit_cost") else None
        row = mirror_row(r, xl, credit, exit_cost=ec, pnl=pnl, fill_model="dry_est")
        tlog.append_entry(row)
        n += 1
        print(f"  {r['strategy_id']:>10}: SPX {[int(l['strike']) for l in legs]} "
              f"-> XSP {[l['strike'] for l in xl]}  credit {credit}")
    print(f"[dry] wrote {n} XSP mirror rows -> data/options_log/trades_xsp.parquet")


def run_live(until):
    import options_trade_log as tlog
    import ib_conn, singleton
    singleton.ensure("options_mirror_xsp")
    stop = dt.time(*map(int, until.split(":")))
    ib = ib_conn.connect(client_id=CLIENT_ID)
    ib.reqMarketDataType(1)
    date = now_ct().strftime("%Y-%m-%d")
    bags = {}   # xsp trade_id -> bag (to close later)
    print(f"XSP mirror live until {until} CT (client {CLIENT_ID})")
    while now_ct().time() < stop:
        try:
            spx = _today_spx(date)
            have, xbook = _xsp_ids(date)
            # ENTRIES — mirror any SPX trade we haven't mirrored yet
            for _, r in spx.iterrows():
                tid = f"xsp_{r['trade_id']}"
                if tid in have:
                    continue
                legs = r["legs"] if isinstance(r["legs"], list) else json.loads(r["legs"])
                exp = legs[0]["expiry"]
                xl = map_legs(legs)
                try:
                    credit, bag = open_combo(ib, exp, _open_actions(xl))
                    bags[tid] = bag
                    tlog.set_book("xsp")
                    tlog.append_entry(mirror_row(r, xl, round(credit, 2)))
                    print(f"  mirrored {r['strategy_id']} -> XSP credit {credit:+.2f}")
                except Exception as e:
                    print(f"  ! mirror entry failed {r['trade_id']}: {e}")
            # EXITS — close XSP mirrors whose SPX parent has closed
            tlog.set_book("xsp")
            xopen = tlog.open_trades()
            for _, xr in xopen.iterrows():
                parent = xr["trade_id"].replace("xsp_", "")
                pm = spx[spx.trade_id == parent]
                if len(pm) and pm.iloc[0]["exit_dt"] == pm.iloc[0]["exit_dt"]:  # parent closed
                    bag = bags.get(xr["trade_id"])
                    try:
                        cost = close_combo(ib, bag) if bag is not None else None
                        if cost is not None:
                            tlog.update_exit(xr["trade_id"], now_ct().strftime("%Y-%m-%d %H:%M"),
                                             round(cost, 2), 0.13, close_reason="mirror parent closed")
                            print(f"  closed XSP mirror {xr['trade_id']} cost {cost:+.2f}")
                    except Exception as e:
                        print(f"  ! mirror exit failed {xr['trade_id']}: {e}")
            # MARK open XSP positions -> marks_xsp.csv (so the mini tab shows unrealized)
            _mark_open(ib, bags)
        except Exception as e:
            print(f"  loop error (continuing): {type(e).__name__}: {e}")
        ib.sleep(20)
    ib.disconnect()
    print("XSP mirror done.")


def _mark_open(ib, bags):
    """Quote each open XSP combo -> unrealized -> append to marks_xsp.csv. unreal for a
    bag we BOUGHT (== our position) = (current_mid - entry_price)*100; entry_price = -credit.
    First-cut schema (ts,trade_id,unreal_pnl,mid,vix); aligned with marks.csv when the
    mini tab is built. Positions opened in a prior process run (no bag cached) are skipped
    until the mirror is hardened to rebuild bags from legs."""
    import csv as _csv
    import options_trade_log as tlog
    tlog.set_book("xsp")
    op = tlog.load()
    op = op[op.exit_dt.isna()]
    if not len(op):
        return
    try:
        vix = json.loads((SIM / "live.json").read_text()).get("vix")
    except Exception:
        vix = None
    rows = []
    ts = now_ct().strftime("%Y-%m-%d %H:%M:%S")
    for _, r in op.iterrows():
        bag = bags.get(r["trade_id"])
        if bag is None:
            continue
        bid, ask = _quote(ib, bag, wait=3)
        if bid is None:
            continue
        mid = (bid + ask) / 2
        credit = float(r["credit"]) if r.get("credit") == r.get("credit") else 0.0
        unreal = round((mid + credit) * 100, 2)
        rows.append([ts, r["trade_id"], unreal, round(mid, 3), vix])
    if rows:
        f = LOG / "marks_xsp.csv"
        new = not f.exists()
        with f.open("a", newline="") as fh:
            w = _csv.writer(fh)
            if new:
                w.writerow(["ts", "trade_id", "unreal_pnl", "mid", "vix"])
            w.writerows(rows)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--until", default="15:00", help="stop time CT (live)")
    ap.add_argument("--dry", action="store_true", help="map + log, NO orders")
    ap.add_argument("--date", default=None, help="date for --dry (default: today CT)")
    a = ap.parse_args()
    if a.dry:
        run_dry(a.date or now_ct().strftime("%Y-%m-%d"))
    else:
        run_live(a.until)


if __name__ == "__main__":
    main()
