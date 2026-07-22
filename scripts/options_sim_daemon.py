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
import options_metrics as omx

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "data" / "options_sim"
ET = ZoneInfo("America/New_York")
CT = ZoneInfo("America/Chicago")


def entry_extras(legs, credit, spot, width, qty, date_ymd, sig):
    """Full card metrics at entry so no STMR card is ever blank again (S79):
    grade, POP@entry, bounded max-gain/max-loss ($), and the thesis. max-gain/loss
    are structural (credit / collateral); POP needs the day's gameplan sigma."""
    ex = {"grade": "A/B",
          "max_gain": round(credit * 100 * qty),
          "max_loss": -round((width - credit) * 100 * qty),
          "commentary": (f"STMR 15:59: K8 {sig['k8']} < 15 (oversold) with spot "
                         f"{sig['spot']:.0f} > SMA100 {sig['sma100']:.0f} — the validated edge.")}
    try:
        m = omx.live_metrics(legs, credit, spot, date_ymd, dt.datetime.now(CT))
        if m:
            ex["pop"] = round(m["pop"], 4)
    except Exception as e:
        print(f"  (entry POP unavailable: {e})")
    return ex

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
    """Rough SPX seed for centering ATM strikes — bootstrap only (no RT index sub).
    Prefers the delayed index quote, but that intermittently 322s on the paper
    feed; when it does, fall back to today's underlying tape so the daemon (and
    the 15:59 BPS decision) never dies on a missing seed. Real spot comes from
    OPRA put-call parity either way."""
    spx = Index("SPX", "CBOE", "USD")
    ib.qualifyContracts(spx)
    ib.reqMarketDataType(4)
    t = ib.reqMktData(spx, "", snapshot=False)
    ib.sleep(4)
    ib.cancelMktData(spx)
    px = next((x for x in (t.last, t.close) if x == x and x), None)
    if px:
        return spx, float(px)
    import csv
    import glob as _glob
    sim = Path(__file__).resolve().parents[1] / "data" / "options_sim"
    for f in reversed(sorted(_glob.glob(str(sim / "underlying_*.csv")))):
        with open(f, newline="") as fh:
            rows = list(csv.DictReader(fh))
        if rows:
            seed = float(rows[-1]["und"])
            print(f"rough_spot: delayed index unavailable — seeding {seed:.1f} "
                  f"from {Path(f).name}")
            return spx, seed
    raise SystemExit("No delayed SPX quote AND no underlying tape — check Gateway login.")


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


# ---------- REAL paper-order execution (S79) ----------
# The sim above measures fill-drift off the NBBO; this places the ACTUAL order on
# IB paper the SAME DAY at 16:00 ET so the edge is really on. qty fixed at 1
# (user-approved). Disable with --no-live. Every real fill is logged as a SEPARATE
# ledger row (source real_paper, trade_id ..._REAL_...) so sim vs real stay comparable.
QTY = 1


def _mkt_leg(ib, contract, action, ref_price, qty, buf=0.30):
    """Place one marketable-limit leg; retry once wider if it cancels; return
    (status, filled, avg_price). outsideRth=True is REQUIRED — the 16:00-16:15 ET
    fill window is after the cash close, so RTH-only orders get cancelled there."""
    from ib_async import LimitOrder
    tr = None
    for attempt, b in enumerate((buf, buf * 4)):
        px = ref_price + (b if action == "BUY" else -b)
        lmt = max(round(round(px / 0.05) * 0.05, 2), 0.05)
        o = LimitOrder(action, qty, lmt)
        o.tif = "DAY"            # pin TIF so the account preset can't reject it (err 10349)
        o.outsideRth = True      # allow the 16:00-16:15 ET post-close fills
        tr = ib.placeOrder(contract, o)
        for _ in range(24):
            ib.sleep(0.5)
            if tr.orderStatus.status in ("Filled", "Cancelled", "ApiCancelled", "Inactive"):
                break
        if tr.orderStatus.status == "Filled":
            return tr.orderStatus.status, tr.orderStatus.filled, tr.orderStatus.avgFillPrice
        print(f"    leg attempt {attempt + 1}: {action} @ {lmt} -> {tr.orderStatus.status}")
    return tr.orderStatus.status, tr.orderStatus.filled, tr.orderStatus.avgFillPrice


def place_real_entry(ib, so, st, lo, lt, qty=QTY):
    """REAL bull put spread on IB paper. Protective LONG bought FIRST (never naked
    short), then short sold. Guards: complete quotes, width==WIDTH, max-loss cap.
    Returns fill dict or None (no/partial order)."""
    if not (st.bid == st.bid and lt.ask == lt.ask and st.bid > 0 and lt.ask > 0):
        print("! REAL entry: incomplete quotes — NO order placed"); return None
    width = so.strike - lo.strike            # actual width pick_legs chose (~WIDTH, varies)
    est = st.bid - lt.ask
    if not (0 < width <= 120) or not (0 < est < width) or (width - est) * 100 * qty > 6000 * qty:
        print(f"! REAL entry guard fail (width {width}, est credit {est:.2f}, "
              f"max-loss ${(width - est) * 100 * qty:,.0f}) — NO order"); return None
    ls, lf, la = _mkt_leg(ib, lo, "BUY", lt.ask, qty)
    print(f"  REAL long  {lo.strike:.0f}P: {ls} {lf}@{la}")
    if ls != "Filled":
        print("! REAL long not filled — aborting entry (never naked short)"); return None
    ss, sf, sa = _mkt_leg(ib, so, "SELL", st.bid, qty)
    print(f"  REAL short {so.strike:.0f}P: {ss} {sf}@{sa}")
    return {"short": so.strike, "long": lo.strike, "width": width, "sfill": sa, "lfill": la,
            "credit": round((sa or 0) - (la or 0), 2), "qty": qty, "short_status": ss}


def place_real_exit(ib, so, st, lo, lt, qty=QTY):
    """Buy-to-close: buy back the SHORT first (risk-reducing), then sell the long."""
    ss, sf, sa = _mkt_leg(ib, so, "BUY", st.ask, qty)
    print(f"  REAL close-short {so.strike:.0f}P: {ss} {sf}@{sa}")
    ls, lf, la = _mkt_leg(ib, lo, "SELL", lt.bid, qty)
    print(f"  REAL close-long  {lo.strike:.0f}P: {ls} {lf}@{la}")
    return {"cost": round((sa or 0) - (la or 0), 2), "qty": qty, "close_status": ss}


def reconcile_real(ib, extra_alerts=None):
    """Diff the ledger's open REAL rows vs actual IB positions; write a status file
    and shout on divergence. This is the guard against a silent no-fill ever again."""
    held = set()
    for p in ib.positions():
        c = p.contract
        if c.secType == "OPT" and p.position:
            held.add((round(float(c.strike)), c.right, p.position > 0))
    alerts = list(extra_alerts or [])
    for _, tr in tlog.open_trades(STRATEGY).iterrows():
        if "REAL" not in str(tr.trade_id):
            continue
        for l in json.loads(tr.legs):
            key = (round(float(l["strike"])), "P", l["side"] == "buy")
            if key not in held:
                alerts.append(f"{tr.trade_id}: {l['side']} {l['strike']:.0f}P NOT held in IB")
    ok = not alerts
    (OUT / "reconcile_status.json").write_text(json.dumps(
        {"ts": now_et().isoformat(), "ok": ok, "alerts": alerts}, indent=2))
    print("RECONCILE: " + ("OK — real ledger matches IB" if ok else
                           "!! DIVERGENCE\n  " + "\n  ".join(alerts)))
    return ok


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
    ap.add_argument("--no-live", action="store_true",
                    help="sim only — do NOT place the real IB order (default: place it)")
    a = ap.parse_args()
    dry = a.smoke or a.now
    place_real = not a.no_live and not dry  # real order only on a genuine live run
    if not dry:
        # single-instance lock: two live daemons would double-log sim trades. Holding a
        # bound socket for the process lifetime is the same pattern as status_light
        # (49731) / telegram_bot (49732). Makes relaunch (task retry, self-heal) safe.
        import socket as _sock
        _lock = _sock.socket()
        try:
            _lock.bind(("127.0.0.1", 49733))
        except OSError:
            print("another sim daemon already holds the lock (port 49733) - exiting")
            return

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
        # S79 restart-safety: a mid-session restart must NOT lose the morning range
        # (the stochastic K8 uses the full 09:30-15:59 H/L). spot_feed writes this
        # same tape ~1/min, so reconstruct H/L from it on startup.
        if uf.exists():
            try:
                import csv as _csv
                vals = [float(r["und"]) for r in _csv.DictReader(open(uf, newline="")) if r.get("und")]
                if vals:
                    sess_h, sess_l = max(sess_h, *vals), min(sess_l, *vals)
                    print(f"session H/L seeded from tape: {sess_l:.2f}..{sess_h:.2f} ({len(vals)} samples)")
            except Exception as e:
                print(f"! tape H/L reconstruct failed ({e}) — seeding from spot only")
        if not a.now:
            decide_at = now_et().replace(hour=DECIDE_T.hour, minute=DECIDE_T.minute,
                                         second=0, microsecond=0)
            if now_et() >= decide_at + dt.timedelta(minutes=1):
                raise SystemExit(f"Past {DECIDE_T} ET — too late to decide causally today.")
            print(f"sampling until {decide_at:%H:%M} ET ({(decide_at - now_et()).seconds // 60} min)...")
            # S75M stall guard: on 7/17 the IB connection died mid-session and this
            # loop hung silently until past decide_at — the decision was missed.
            # A parity spot frozen to the tick for 5 min = dead tickers, not a
            # quiet tape; reconnect and rebuild the rig instead of waiting.
            last_change = now_et()
            with open(uf, "a", newline="") as fh:
                w = csv.writer(fh)
                if fh.tell() == 0:
                    w.writerow(["ts_et", "und"])
                while now_et() < decide_at:
                    ib.sleep(min(60, max(1, (decide_at - now_et()).total_seconds())))
                    s = rig.spot()
                    if s and s != spot:
                        last_change = now_et()
                    if s:
                        spot = s
                        sess_h, sess_l = max(sess_h, s), min(sess_l, s)
                        w.writerow([now_et().strftime("%H:%M:%S"), f"{s:.2f}"])
                        fh.flush()
                    if (now_et() - last_change).total_seconds() > 300 or not ib.isConnected():
                        print(f"! sampler stalled (connected={ib.isConnected()}) — reconnecting IB")
                        try:
                            ib.disconnect()
                        except Exception:
                            pass
                        ib = ib_conn.connect(port=a.port)
                        tickers = open_put_ladder(ib, chain, expiry, spot)
                        rig = SpotRig(ib, chain, spot)
                        last_change = now_et()

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
                # S79: REAL rows get a real buy-to-close; never sim-close a real position
                if "REAL" in str(tr.trade_id):
                    if not place_real:
                        print(f"skip closing REAL {tr.trade_id} (--no-live)")
                        continue
                    sl = next(l for l in legs if l["side"] == "sell")
                    ll = next(l for l in legs if l["side"] == "buy")
                    ex = place_real_exit(ib, tickers[sl["strike"]][0], tickers[sl["strike"]][1],
                                         tickers[ll["strike"]][0], tickers[ll["strike"]][1],
                                         qty=int(sl.get("qty", 1)))
                    tlog.update_exit(tr.trade_id, today, ex["cost"], 4 * FEE,
                                     fill_model="real_paper_ib_marketable")
                    print(f"REAL CLOSED {tr.trade_id}: paid {ex['cost']:.2f}")
                    reconcile_real(ib)
                    continue
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
                sim_legs = [{"side": "sell", "right": "P", "strike": ks, "expiry": expiry, "qty": 1},
                            {"side": "buy", "right": "P", "strike": kl, "expiry": expiry, "qty": 1}]
                tlog.append_entry({
                    "trade_id": tid, "strategy_id": STRATEGY, "source": "sim",
                    "symbol": "SPXW", "entry_dt": today,
                    "dte": (dt.datetime.strptime(expiry, "%Y%m%d").date() - now_et().date()).days,
                    "structure": f"BPS {ks - kl:.0f}pt", "fill_model": "opra_nbbo_1600",
                    "legs": sim_legs,
                    "credit": cr, "slippage": (mid - cr) * 100,
                    "collateral": (ks - kl - cr) * 100,
                    **entry_extras(sim_legs, cr, spot, ks - kl, 1, now_et().strftime("%Y%m%d"), sig),
                    **tags,
                })
                print(f"ENTERED {tid}: credit {cr:.2f}, collateral ${(ks - kl - cr) * 100:,.0f}, tape {qf}")

                # S79: place the REAL IB paper order same-day (separate ledger row)
                if place_real:
                    real = place_real_entry(ib, tickers[ks][0], tickers[ks][1],
                                            tickers[kl][0], tickers[kl][1], qty=QTY)
                    if real and real["short_status"] == "Filled":
                        rtid = f"{STRATEGY}_REAL_{today.replace('-', '')}"
                        real_legs = [{"side": "sell", "right": "P", "strike": ks, "expiry": expiry, "qty": QTY, "fill": real["sfill"]},
                                     {"side": "buy", "right": "P", "strike": kl, "expiry": expiry, "qty": QTY, "fill": real["lfill"]}]
                        tlog.append_entry({
                            "trade_id": rtid, "strategy_id": STRATEGY, "source": "real_paper",
                            "symbol": "SPXW", "entry_dt": today,
                            "dte": (dt.datetime.strptime(expiry, "%Y%m%d").date() - now_et().date()).days,
                            "structure": f"BPS {real['width']:.0f}pt", "fill_model": "real_paper_ib_marketable",
                            "legs": real_legs,
                            "credit": real["credit"], "collateral": (real["width"] - real["credit"]) * 100 * QTY,
                            **entry_extras(real_legs, real["credit"], spot, real["width"], QTY, now_et().strftime("%Y%m%d"), sig),
                            **tags,
                        })
                        print(f"REAL ENTERED {rtid}: credit {real['credit']:.2f} x{QTY}")
                        reconcile_real(ib)
                    else:
                        reconcile_real(ib, extra_alerts=[
                            f"{tid}: signal FIRED but REAL order NOT placed/filled "
                            "— sim logged, NO IB position (INVESTIGATE)"])
        print("\n" + tlog.summary(STRATEGY))
        import options_sim_report
        options_sim_report.main()
        # S79: re-render today's playbook AFTER the 16:00 fills/exits so it reflects the
        # EXECUTED trades (the 08:28 CT morning render froze the pre-market state). Detached.
        if not dry:
            try:
                import subprocess
                subprocess.Popen([sys.executable, str(ROOT / "scripts" / "gameplan_charts.py"),
                                  "--date", today.replace("-", ""), "--no-open"],
                                 cwd=str(ROOT), creationflags=0x08000008,
                                 stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
                print("re-rendered playbook with executed trades")
            except Exception as e:
                print(f"  (playbook re-render not started: {type(e).__name__})")
    finally:
        ib.disconnect()


if __name__ == "__main__":
    main()
