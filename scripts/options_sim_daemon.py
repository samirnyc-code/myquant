"""OPRA forward-sim daemon — the causal 15:59 BPS rule, live (S70 plan, built S73).

THE RULE (mirrors scripts/mr_bps_causal_1559.py, the only honest backtest):
  * at 15:59:00 ET read SPX spot; compute stoch %K8 (session H/L through 15:59
    included) and SMA100/SMA5 on daily closes with today = the 15:59 spot.
  * ENTRY:  K8 < 15 AND spot > SMA100  ->  sell ~30-delta SPXW put, buy the put
    50 pts lower, ~14 DTE (bps_stmr in docs/living/options_playbook.md).
  * EXIT:   first day spot(15:59) > SMA5 -> buy the spread back; else cash
    settlement at expiry (SPXW PM-settled).
  * FILL:   the REAL 16:00-16:15 OPRA NBBO. Executed at the first valid quote
    >= 16:00:00 ET, sell-at-bid / buy-at-ask, $1.30/contract. Every quote in
    the window is logged to CSV -> this measures the fill-drift the EOD
    backtests could not.

UNDERLYING = SPX, NOT ES (S73 decision, flagged to user): Massive died
2026-07-14 (ES daily pipeline frozen), IB ES/SPX index realtime not subscribed
(15-min delay breaks 15:59 causality). Realtime SPX spot comes from OPRA option
modelGreeks.undPrice (covered by the OPRA sub); daily history from Stooq.
Same math as the validated ES signal, but a VARIANT of it — every decision is
logged so the two can be compared later.

Outputs (all under data/options_sim/, gitignore the quotes/underlying files):
  spx_daily_stooq.csv          refreshed daily history
  decisions.csv                one row per run: spot, K8, SMAs, fire/exit, note
  underlying_YYYYMMDD.csv      1-min undPrice samples (session H/L evidence)
  quotes_YYYYMMDD_<id>.csv     the 16:00-16:15 NBBO tape per trade event
  ../options_log/trades.parquet  unified trade log (scripts/options_trade_log.py)

Run (start any time before 15:59 ET; earlier = better session H/L):
  .venv/Scripts/python.exe scripts/options_sim_daemon.py           # wait for 15:59, paper 4002
  .venv/Scripts/python.exe scripts/options_sim_daemon.py --smoke   # entitlement check, no writes
  .venv/Scripts/python.exe scripts/options_sim_daemon.py --now     # decide immediately, dry-run
"""
import argparse
import csv
import datetime as dt
import json
import sys
import urllib.request
from pathlib import Path
from zoneinfo import ZoneInfo

import numpy as np
import pandas as pd
from ib_async import Index, Option

sys.path.insert(0, str(Path(__file__).resolve().parent))
import ib_conn
import options_trade_log as tlog

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "data" / "options_sim"
ET = ZoneInfo("America/New_York")

STRATEGY = "bps_stmr"
DTE, WIDTH, SHORT_D, FEE = 14, 50, 0.30, 1.30
DECIDE_T = dt.time(15, 59, 0)
FILL_END = dt.time(16, 15, 0)


def now_et():
    return dt.datetime.now(ET)


# ---------- daily history / signal ----------

def refresh_spx_daily():
    """Yahoo ^GSPC daily OHLC -> spx_daily_yahoo.csv (cache on failure).
    Today's PARTIAL bar (if the market is open) is dropped — the signal supplies
    today from the live 15:59 state. (Stooq is behind a JS challenge as of S73.)"""
    f = OUT / "spx_daily_yahoo.csv"
    try:
        req = urllib.request.Request(
            "https://query1.finance.yahoo.com/v8/finance/chart/%5EGSPC?range=2y&interval=1d",
            headers={"User-Agent": "Mozilla/5.0"})
        r = json.loads(urllib.request.urlopen(req, timeout=30).read())["chart"]["result"][0]
        q = r["indicators"]["quote"][0]
        df = pd.DataFrame({
            "Date": [dt.datetime.fromtimestamp(t, ET).date().isoformat() for t in r["timestamp"]],
            "High": q["high"], "Low": q["low"], "Close": q["close"]}).dropna()
        df = df[df.Date < now_et().date().isoformat()]
        assert len(df) > 200
        OUT.mkdir(parents=True, exist_ok=True)
        df.to_csv(f, index=False)
        print(f"SPX daily refreshed from Yahoo: {len(df)} rows, last {df.Date.iloc[-1]}")
    except Exception as e:
        if not f.exists():
            raise SystemExit(f"Yahoo SPX fetch failed and no cache: {e!r}")
        print(f"! Yahoo SPX fetch failed ({e!r}) — using cached {f.name}")
        df = pd.read_csv(f)
    return df


def signal_1559(daily, spot, sess_h, sess_l, today):
    """Causal STMR read: history through YESTERDAY + today's 15:59 state."""
    d = daily[daily.Date < today].tail(150)
    C = np.append(d.Close.values, spot)
    H = np.append(d.High.values, max(sess_h, spot))
    L = np.append(d.Low.values, min(sess_l, spot))
    sma100 = C[-100:].mean()
    sma5 = C[-5:].mean()
    ll8, hh8 = L[-8:].min(), H[-8:].max()
    k8 = 100 * (spot - ll8) / (hh8 - ll8 if hh8 > ll8 else 1)
    return {"spot": spot, "sma100": round(sma100, 2), "sma5": round(sma5, 2),
            "k8": round(k8, 2), "fire": bool(k8 < 15 and spot > sma100),
            "exit_sig": bool(spot > sma5)}


def regime_tags(daily, spot, today):
    vixf = ROOT / "data" / "vix_daily.csv"
    vix = vix_rank = None
    if vixf.exists():
        v = pd.read_csv(vixf)
        vc = v.iloc[:, -1].astype(float)  # close = last col
        vix = float(vc.iloc[-1])
        vix_rank = float((vc.tail(252) <= vix).mean())
    d = daily[daily.Date < today].tail(11)
    C = np.append(d.Close.values, spot)[-11:]
    er10 = abs(C[-1] - C[0]) / max(np.abs(np.diff(C)).sum(), 1e-9)
    return {"vix": vix, "vix_rank": round(vix_rank, 3) if vix_rank is not None else None,
            "er10": round(float(er10), 3), "dow": now_et().strftime("%a")}


# ---------- IB market data ----------

def rough_spot(ib):
    """Delayed SPX index quote — bootstrap only (no RT index sub)."""
    ib.reqMarketDataType(4)
    spx = Index("SPX", "CBOE", "USD")
    ib.qualifyContracts(spx)
    t = ib.reqMktData(spx, "", snapshot=False)
    ib.sleep(4)
    ib.cancelMktData(spx)
    px = next((x for x in (t.last, t.close) if x == x and x), None)
    if not px:
        raise SystemExit("No delayed SPX quote — check Gateway login / entitlements.")
    return spx, float(px)


def get_chain(ib, spx):
    chains = ib.reqSecDefOptParams(spx.symbol, "", spx.secType, spx.conId)
    chain = next((c for c in chains if c.tradingClass == "SPXW" and c.exchange == "SMART"),
                 next((c for c in chains if c.tradingClass == "SPXW"), chains[0]))
    return chain


def pick_expiry(chain, target_dte=DTE):
    today = now_et().date()
    exps = sorted(chain.expirations)
    return min(exps, key=lambda e: abs((dt.datetime.strptime(e, "%Y%m%d").date() - today).days - target_dte))


def open_put_ladder(ib, chain, expiry, spot):
    """Stream RT data on puts from ~spot down to spot-7%. Returns {strike: ticker}."""
    ib.reqMarketDataType(1)  # OPRA realtime
    ks = sorted([k for k in chain.strikes if spot * 0.93 <= k <= spot], reverse=True)
    while len(ks) > 40:
        ks = ks[::2]
    opts = [Option("SPX", expiry, k, "P", "SMART", tradingClass=chain.tradingClass) for k in ks]
    # chain.strikes is the union across expiries — nonexistent ones qualify to None
    opts = [o for o in ib.qualifyContracts(*opts) if o is not None and o.conId]
    tickers = {o.strike: (o, ib.reqMktData(o, "", snapshot=False)) for o in opts}
    return tickers


class SpotRig:
    """Realtime SPX spot via put-call parity on 0DTE ATM pairs (S73).

    modelGreeks.undPrice is None on the paper feed (no SPX index sub), but the
    OPRA NBBO is realtime — so spot = Cmid − Pmid + K on the nearest expiry
    (rate/carry error < 1pt at 0DTE; verified 5-cent agreement across strikes).
    Re-centers its strike pairs if spot drifts > 20 pts.
    """

    def __init__(self, ib, chain, rough_spot):
        self.ib, self.chain = ib, chain
        today = now_et().strftime("%Y%m%d")
        self.exp0 = min(e for e in chain.expirations if e >= today)
        self.pairs, self.center = {}, None
        self._build(rough_spot)

    def _build(self, spot):
        for c, _ in self.pairs.values():
            self.ib.cancelMktData(c)
        self.pairs = {}
        ks = sorted(self.chain.strikes, key=lambda s: abs(s - spot))[:3]
        opts = [Option("SPX", self.exp0, k, r, "SMART", tradingClass=self.chain.tradingClass)
                for k in ks for r in "CP"]
        for o in self.ib.qualifyContracts(*opts):
            if o is not None and o.conId:
                self.pairs[(o.strike, o.right)] = (o, self.ib.reqMktData(o, "", snapshot=False))
        self.center = spot
        self.ib.sleep(5)

    def spot(self, _depth=0):
        vals = []
        for k in {k for k, _ in self.pairs}:
            if (k, "C") in self.pairs and (k, "P") in self.pairs:
                cq, pq = self.pairs[(k, "C")][1], self.pairs[(k, "P")][1]
                if all(x == x and x > 0 for x in (cq.bid, cq.ask, pq.bid, pq.ask)):
                    vals.append((cq.bid + cq.ask) / 2 - (pq.bid + pq.ask) / 2 + k)
        if not vals:
            return None
        s = float(np.median(vals))
        if abs(s - self.center) > 20 and _depth < 2:
            self._build(s)
            return self.spot(_depth + 1)
        return s


def pick_legs(ib, chain, tickers, expiry):
    """short = |delta| nearest SHORT_D with a live quote; long = strike <= short-WIDTH."""
    cand = []
    for k, (o, t) in tickers.items():
        d = t.modelGreeks.delta if t.modelGreeks else None
        if d and d == d and t.bid == t.bid and t.ask == t.ask and t.ask > 0:
            cand.append((k, o, abs(d)))
    if not cand:
        return None, None
    ks, ko, _ = min(cand, key=lambda x: abs(x[2] - SHORT_D))
    lows = [(k, o) for k, o, _ in cand if k <= ks - WIDTH]
    if lows:
        kl, lo = max(lows, key=lambda x: x[0])
    else:  # long strike below the streamed ladder — qualify it directly
        target = ks - WIDTH
        kl = max((k for k in chain.strikes if k <= target), default=None)
        if kl is None:
            return None, None
        lo = ib.qualifyContracts(Option("SPX", expiry, kl, "P", "SMART",
                                        tradingClass=chain.tradingClass))[0]
        tickers[kl] = (lo, ib.reqMktData(lo, "", snapshot=False))
        ib.sleep(3)
    return ks, kl


def log_fill_window(ib, tickers, legs, tag, until=FILL_END, dryrun_secs=None):
    """Stream legs' NBBO to CSV until `until` ET; return the executed fill.

    legs = [(strike, side)] with side 'sell'|'buy' (what WE do at this event).
    Executed at the FIRST timestamp >= start where every leg has a valid quote:
    sell at bid, buy at ask. Also records the mid at that same timestamp.
    """
    OUT.mkdir(parents=True, exist_ok=True)
    f = OUT / f"quotes_{now_et():%Y%m%d}_{tag}.csv"
    end = now_et().replace(hour=until.hour, minute=until.minute, second=0, microsecond=0)
    if dryrun_secs:
        end = now_et() + dt.timedelta(seconds=dryrun_secs)
    fill = mid = None
    # fills are only valid from 16:00:00 ET (the causal rule: decide 15:59, fill 16:00+);
    # quotes before that are logged but never executed on. (S73 bug fix — the first
    # live day executed at 15:59:08.)
    fill_from = now_et().replace(hour=16, minute=0, second=0, microsecond=0)
    if dryrun_secs:
        fill_from = now_et()
    with open(f, "a", newline="") as fh:
        w = csv.writer(fh)
        if fh.tell() == 0:
            w.writerow(["ts_et", "strike", "side", "bid", "ask"])
        while now_et() < end:
            ib.sleep(5)
            ts = now_et().strftime("%H:%M:%S")
            quotes = {}
            for k, side in legs:
                t = tickers[k][1]
                b, a = t.bid, t.ask
                w.writerow([ts, k, side, b, a])
                if b == b and a == a and a > 0 and b > 0:
                    quotes[k] = (b, a, side)
            fh.flush()
            if fill is None and len(quotes) == len(legs) and now_et() >= fill_from:
                fill = sum((b if s == "sell" else -a) for b, a, s in quotes.values())
                mid = sum(((b + a) / 2 if s == "sell" else -(b + a) / 2) for b, a, s in quotes.values())
                print(f"  EXECUTED {tag} @ {ts}: net {fill:+.2f} (mid {mid:+.2f})")
    return fill, mid, f.name


def append_decision(row):
    f = OUT / "decisions.csv"
    OUT.mkdir(parents=True, exist_ok=True)
    new = not f.exists()
    with open(f, "a", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=list(row.keys()))
        if new:
            w.writeheader()
        w.writerow(row)


# ---------- settlement of expired open trades ----------

def settle_expired(daily, today, dry):
    for _, tr in tlog.open_trades(STRATEGY).iterrows():
        legs = json.loads(tr.legs)
        exp = dt.datetime.strptime(legs[0]["expiry"], "%Y%m%d").date().isoformat()
        if exp >= today:
            continue
        row = daily[daily.Date == exp]
        if row.empty:
            print(f"! {tr.trade_id} expired {exp} but no SPX close for that date yet")
            continue
        S = float(row.Close.iloc[0])
        cost = sum((1 if l["side"] == "sell" else -1) * max(0.0, l["strike"] - S) for l in legs)
        print(f"SETTLING {tr.trade_id}: expired {exp}, SPX close {S:.2f}, intrinsic cost {cost:.2f}")
        if not dry:
            r = tlog.update_exit(tr.trade_id, exp, cost, 0.0, fill_model="settlement")
            print(f"  closed: pnl ${r['pnl']:+,.0f}")


# ---------- main ----------

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--smoke", action="store_true", help="entitlement check only, no waiting/writes")
    ap.add_argument("--now", action="store_true", help="decide immediately (dry-run, no trade-log writes)")
    ap.add_argument("--port", type=int, default=None, help="override IB port (default env/4002 paper)")
    a = ap.parse_args()
    dry = a.smoke or a.now

    today = now_et().date().isoformat()
    daily = refresh_spx_daily()
    ib = ib_conn.connect(port=a.port)
    try:
        spx, rspot = rough_spot(ib)
        print(f"delayed SPX ~ {rspot:.2f}")
        chain = get_chain(ib, spx)
        expiry = pick_expiry(chain)
        print(f"chain {chain.tradingClass}@{chain.exchange}, expiry {expiry} "
              f"({(dt.datetime.strptime(expiry, '%Y%m%d').date() - now_et().date()).days} DTE)")
        tickers = open_put_ladder(ib, chain, expiry, rspot)
        rig = SpotRig(ib, chain, rspot)
        print(f"streaming {len(tickers)} puts + spot rig (0DTE {rig.exp0}), waiting for OPRA...")
        ib.sleep(10)
        spot = rig.spot()
        live = [t for _, t in tickers.values() if t.bid == t.bid and t.ask == t.ask and t.ask > 0]
        print(f"OPRA check: {len(live)}/{len(tickers)} strikes quoting, parity spot = {spot}")
        if a.smoke:
            ks, kl = pick_legs(ib, chain, tickers, expiry)
            t = tickers.get(ks, (None, None))[1] if ks else None
            print(f"SMOKE VERDICT: quotes {'YES' if live else 'NO'}, undPrice {'YES' if spot else 'NO'}"
                  + (f", legs {ks}/{kl} P short bid/ask {t.bid}/{t.ask}" if ks else ", legs: NONE"))
            return
        if spot is None:
            raise SystemExit("No realtime undPrice from OPRA — cannot run the causal rule. "
                             "Check the paper account's market-data sharing (S69 warning).")

        # --- sample undPrice each minute until 15:59, tracking session H/L ---
        uf = OUT / f"underlying_{now_et():%Y%m%d}.csv"
        sess_h = sess_l = spot
        if not a.now:
            decide_at = now_et().replace(hour=DECIDE_T.hour, minute=DECIDE_T.minute,
                                         second=0, microsecond=0)
            if now_et() >= decide_at + dt.timedelta(minutes=1):
                raise SystemExit(f"Past {DECIDE_T} ET — too late to decide causally today.")
            print(f"sampling until {decide_at:%H:%M} ET ({(decide_at - now_et()).seconds // 60} min)...")
            with open(uf, "a", newline="") as fh:
                w = csv.writer(fh)
                if fh.tell() == 0:
                    w.writerow(["ts_et", "und"])
                while now_et() < decide_at:
                    ib.sleep(min(60, max(1, (decide_at - now_et()).total_seconds())))
                    s = rig.spot()
                    if s:
                        spot = s
                        sess_h, sess_l = max(sess_h, s), min(sess_l, s)
                        w.writerow([now_et().strftime("%H:%M:%S"), f"{s:.2f}"])
                        fh.flush()

        # --- 15:59 decision ---
        sig = signal_1559(daily, spot, sess_h, sess_l, today)
        tags = regime_tags(daily, spot, today)
        opens = tlog.open_trades(STRATEGY)
        note = "dryrun" if dry else ""
        print(f"\n=== {today} 15:59 ET DECISION ===\n"
              f"spot {sig['spot']:.2f}  K8 {sig['k8']}  SMA100 {sig['sma100']}  SMA5 {sig['sma5']}\n"
              f"ENTRY fire: {sig['fire']}   EXIT signal: {sig['exit_sig']}   open trades: {len(opens)}\n"
              f"tags: {tags}")
        append_decision({"date": today, "ts": now_et().strftime("%H:%M:%S"), **sig,
                         "sess_h": round(sess_h, 2), "sess_l": round(sess_l, 2),
                         "open_trades": len(opens), "sampled_from": now_et().strftime("%H:%M") if a.now else "",
                         "note": note})

        settle_expired(daily, today, dry)

        # --- exits first (frees collateral), then entry ---
        if sig["exit_sig"] and len(opens):
            for _, tr in opens.iterrows():
                legs = json.loads(tr.legs)
                for l in legs:
                    if l["strike"] not in tickers:
                        o = ib.qualifyContracts(Option("SPX", l["expiry"], l["strike"], "P",
                                                       "SMART", tradingClass=chain.tradingClass))[0]
                        tickers[l["strike"]] = (o, ib.reqMktData(o, "", snapshot=False))
                ib.sleep(3)
                ev = [(l["strike"], "buy" if l["side"] == "sell" else "sell") for l in legs]
                cost, mid, qf = log_fill_window(ib, tickers, ev, f"exit_{tr.trade_id}",
                                                dryrun_secs=30 if dry else None)
                if cost is None:
                    print(f"! no valid exit quotes for {tr.trade_id} — left open")
                    continue
                cost = -cost  # we PAID to close
                if dry:
                    print(f"DRYRUN exit {tr.trade_id}: cost {cost:.2f} (not written)")
                else:
                    r = tlog.update_exit(tr.trade_id, today, cost, 4 * FEE,
                                         fill_model="opra_nbbo_1600", slippage=(cost - (-mid)) * 100)
                    print(f"CLOSED {tr.trade_id}: pnl ${r['pnl']:+,.0f}")

        if sig["fire"]:
            ks, kl = pick_legs(ib, chain, tickers, expiry)
            if ks is None:
                raise SystemExit("Signal fired but no quotable legs — investigate.")
            print(f"legs: sell {ks:.0f}P / buy {kl:.0f}P  {expiry}")
            tid = f"{STRATEGY}_{today}"
            cr, mid, qf = log_fill_window(ib, tickers, [(ks, "sell"), (kl, "buy")],
                                          f"entry_{tid}", dryrun_secs=30 if dry else None)
            if cr is None:
                print("! no valid entry quotes in the window — NO TRADE recorded")
            elif cr <= 0:
                print(f"! non-positive credit {cr:.2f} — NO TRADE recorded")
            elif dry:
                print(f"DRYRUN entry {tid}: credit {cr:.2f} (mid {mid:.2f}) — not written")
            else:
                tlog.append_entry({
                    "trade_id": tid, "strategy_id": STRATEGY, "source": "sim",
                    "symbol": "SPXW", "entry_dt": today,
                    "dte": (dt.datetime.strptime(expiry, "%Y%m%d").date() - now_et().date()).days,
                    "structure": f"BPS {WIDTH}pt", "fill_model": "opra_nbbo_1600",
                    "legs": [{"side": "sell", "right": "P", "strike": ks, "expiry": expiry},
                             {"side": "buy", "right": "P", "strike": kl, "expiry": expiry}],
                    "credit": cr, "slippage": (mid - cr) * 100,
                    "collateral": (ks - kl - cr) * 100, **tags,
                })
                print(f"ENTERED {tid}: credit {cr:.2f}, collateral ${(ks - kl - cr) * 100:,.0f}, tape {qf}")
        print("\n" + tlog.summary(STRATEGY))
        import options_sim_report
        options_sim_report.main()
    finally:
        ib.disconnect()


if __name__ == "__main__":
    main()
