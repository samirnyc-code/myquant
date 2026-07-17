"""Mark open paper/sim positions to market — running PnL + live VIX (S73).

Quotes every leg of every OPEN trade in the unified log, values the position at
mid, and appends one row per trade to data/options_sim/marks.csv:

  ts_et, trade_id, mark_value(net mid/contract), unreal_pnl($), spot, vix

unreal_pnl = (entry net credit − current net cost-to-close at mid) × 100 × qty-adjusted.
Also refreshes data/vix_daily.csv from Yahoo ^VIX (through yesterday) once per run.

Run once:            .venv/Scripts/python.exe scripts/options_mark.py
Loop until close:    .venv/Scripts/python.exe scripts/options_mark.py --watch 300
"""
import csv
import datetime as dt
import json
import sys
import urllib.request
from pathlib import Path
from zoneinfo import ZoneInfo

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent))
import ib_conn
import options_metrics as omx
import options_trade_log as tlog
from options_manual_trade import qualify

ET = ZoneInfo("America/New_York")
CT = ZoneInfo("America/Chicago")
ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "data" / "options_sim" / "marks.csv"
MET = ROOT / "data" / "options_sim" / "trade_metrics.csv"   # richer live time series


def live_spot():
    """Realtime option-parity SPX from the feed (data/options_sim/live.json)."""
    f = ROOT / "data" / "options_sim" / "live.json"
    try:
        return float(json.loads(f.read_text()).get("spx"))
    except Exception:
        return None


def spx_close_on(date_iso):
    """SPX (^GSPC) close for a past calendar date, from the daily cache. None if absent."""
    try:
        d = pd.read_csv(ROOT / "data" / "options_sim" / "spx_daily_yahoo.csv")
        row = d[d.Date == date_iso]
        return float(row.Close.iloc[0]) if len(row) else None
    except Exception:
        return None


def now():
    return dt.datetime.now(ET)


def refresh_vix_daily():
    """Append missing days to data/vix_daily.csv from Yahoo ^VIX (drop today's partial)."""
    f = ROOT / "data" / "vix_daily.csv"
    try:
        req = urllib.request.Request(
            "https://query1.finance.yahoo.com/v8/finance/chart/%5EVIX?range=3mo&interval=1d",
            headers={"User-Agent": "Mozilla/5.0"})
        r = json.loads(urllib.request.urlopen(req, timeout=30).read())["chart"]["result"][0]
        q = r["indicators"]["quote"][0]
        y = pd.DataFrame({"DATE": [dt.datetime.fromtimestamp(t, ET).date().isoformat()
                                   for t in r["timestamp"]],
                          "OPEN": q["open"], "HIGH": q["high"], "LOW": q["low"],
                          "CLOSE": q["close"]}).dropna()
        y = y[y.DATE < now().date().isoformat()]
        old = pd.read_csv(f)
        dcol = old.columns[0]
        add = y[~y.DATE.isin(old[dcol].astype(str))]
        if len(add):
            add.columns = old.columns[:5]
            pd.concat([old, add[old.columns[:5]]], ignore_index=True).to_csv(f, index=False)
            print(f"vix_daily.csv +{len(add)} rows (through {add.iloc[-1, 0]})")
    except Exception as e:
        print(f"! VIX refresh failed ({e!r}) — csv unchanged")


def account_snapshot(ib, vix):
    """Append NetLiq / margin / available funds -> data/options_sim/account.csv."""
    acct = ib.managedAccounts()[0]
    tags = {r.tag: r.value for r in ib.accountSummary(acct)
            if r.tag in ("NetLiquidation", "FullInitMarginReq", "FullMaintMarginReq",
                         "AvailableFunds", "BuyingPower")}
    f = OUT.parent / "account.csv"
    new = not f.exists()
    with open(f, "a", newline="") as fh:
        w = csv.writer(fh)
        if new:
            w.writerow(["ts_et", "net_liq", "init_margin", "maint_margin", "available", "buying_power", "vix"])
        w.writerow([now().strftime("%Y-%m-%d %H:%M:%S"),
                    tags.get("NetLiquidation"), tags.get("FullInitMarginReq"),
                    tags.get("FullMaintMarginReq"), tags.get("AvailableFunds"),
                    tags.get("BuyingPower"), round(vix, 2) if vix else ""])
    print(f"  account: NetLiq {tags.get('NetLiquidation')}  initMargin {tags.get('FullInitMarginReq')}  "
          f"maintMargin {tags.get('FullMaintMarginReq')}  avail {tags.get('AvailableFunds')}")


def live_vix(ib):
    from ib_async import Index
    ib.reqMarketDataType(4)
    vix = Index("VIX", "CBOE", "USD")
    ib.qualifyContracts(vix)
    t = ib.reqMktData(vix, "", snapshot=False)
    ib.sleep(4)
    ib.cancelMktData(vix)
    return next((x for x in (t.last, t.close) if x == x and x), None)


def mark_once(ib, vix):
    opens = tlog.open_trades()
    if not len(opens):
        print("no open trades")
        return
    ib.reqMarketDataType(1)
    today = now().strftime("%Y%m%d")
    tickers = {}
    settled = {}                               # expired legs -> settled intrinsic value
    for _, tr in opens.iterrows():
        for l in json.loads(tr.legs):
            key = (l["expiry"], l["strike"], l["right"])
            if key in tickers or key in settled:
                continue
            if l["expiry"] < today:            # expired leg — settle at expiry-date SPX close
                exp_iso = dt.datetime.strptime(l["expiry"], "%Y%m%d").date().isoformat()
                S = spx_close_on(exp_iso)
                if S is None:                  # no close on file — fall back to skip-the-leg
                    tickers[key] = None
                else:                          # intrinsic; a partial-expiry calendar keeps marking
                    settled[key] = max(0.0, (l["strike"] - S) if l["right"] == "P"
                                       else (S - l["strike"]))
                continue
            try:
                c = qualify(ib, *key)
                if c is None or not getattr(c, "conId", None):
                    tickers[key] = None
                    continue
                tickers[key] = ib.reqMktData(c, "", snapshot=False)
            except Exception as e:              # never let one bad leg kill the whole mark
                print(f"  qualify failed {key}: {type(e).__name__}")
                tickers[key] = None
    ib.sleep(8)
    OUT.parent.mkdir(parents=True, exist_ok=True)
    spot = live_spot()
    now_ct = dt.datetime.now(CT)
    date = now_ct.strftime("%Y%m%d")
    new = not OUT.exists()
    mnew = not MET.exists()
    ts = now().strftime("%Y-%m-%d %H:%M:%S")
    with open(OUT, "a", newline="") as fh, open(MET, "a", newline="") as mfh:
        w = csv.writer(fh)
        mw = csv.writer(mfh)
        if new:
            w.writerow(["ts_et", "trade_id", "mark_value", "unreal_pnl", "vix"])
        if mnew:
            mw.writerow(["ts_et", "trade_id", "spot", "net_mid", "net_spread", "unreal_pnl",
                         "pop", "ev", "p_maxloss", "sigma", "max_gain", "max_loss"])
        total = 0.0
        for _, tr in opens.iterrows():
            cost = 0.0
            spread = 0.0
            ok = True
            legs = json.loads(tr.legs)
            for l in legs:
                key = (l["expiry"], l["strike"], l["right"])
                if key in settled:             # already-expired leg: fixed intrinsic, no spread
                    mid = settled[key]
                    cost += l["qty"] * (mid if l["side"] == "sell" else -mid)
                    continue
                t = tickers[key]
                if t is None or not (t.bid == t.bid and t.ask == t.ask and t.ask > 0):
                    ok = False
                    break
                mid = (t.bid + t.ask) / 2
                cost += l["qty"] * (mid if l["side"] == "sell" else -mid)  # cost to close
                spread += l["qty"] * (t.ask - t.bid)
            if not ok:
                print(f"  {tr.trade_id}: incomplete quotes, skipped")
                continue
            unreal = (float(tr.credit) - cost) * 100
            total += unreal
            w.writerow([ts, tr.trade_id, round(-cost, 2), round(unreal, 2),
                        round(vix, 2) if vix else ""])
            # live probabilities/EV at current spot + time-to-expiry
            m = omx.live_metrics(legs, tr.credit, spot, date, now_ct) if spot else None
            if m:
                mw.writerow([ts, tr.trade_id, round(spot, 2), round(-cost, 2), round(spread, 2),
                             round(unreal, 2), round(m["pop"], 4), round(m["ev"]), round(m["p_maxloss"], 4),
                             m["sigma"], m["max_gain"], m["max_loss"]])
            pop_s = f" POP {m['pop']*100:4.0f}%  EV ${m['ev']:+6,.0f}" if m else ""
            print(f"  {tr.trade_id:34s} unreal ${unreal:+8,.0f}{pop_s}")
        print(f"  {'TOTAL':34s} unreal ${total:+8,.0f}   VIX {vix}")


def main():
    watch = int(sys.argv[sys.argv.index("--watch") + 1]) if "--watch" in sys.argv else 0
    refresh_vix_daily()
    ib = ib_conn.connect()
    try:
        while True:
            vix = live_vix(ib)
            print(f"\n=== marks @ {now():%H:%M:%S} ET ===")
            account_snapshot(ib, vix)
            mark_once(ib, vix)
            if not watch or now().time() > dt.time(16, 20):
                break
            ib.sleep(watch)
    finally:
        ib.disconnect()


if __name__ == "__main__":
    main()
