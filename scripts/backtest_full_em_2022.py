"""FULL 0DTE iron-condor backtest, 2022-05-16 (first daily-0DTE day) -> present,
under 3 expected-move methods side by side. Proven engine from the August control
run (backtest_em_compare_pnl.py: vix252 +804 vs desk booked +792).

Per trading day, all 4 verticals (eodic_p/c centered on prior close @ 09:31 ET,
openic_p/c centered on the open @ 10:05 ET), 25-wide, per EM method:
  A straddle : TD ATM 0DTE straddle mid at 09:31 ET
  B vix252   : prior_close x VIX/100 x sqrt(1/252)   (= gexlog = desk)
  C vix365   : prior_close x VIX/100 x sqrt(1/365)   (TD's IV convention)

Entry  = TD NBBO marketable touch (short@bid - long@ask) at the entry time.
Exit   = desk level-acceptance stop: parity-reconstructed SPX (1-min, from ATM
         call/put quotes: S = C_mid - P_mid + K; validated 0.52pt median vs desk
         feed) holds beyond the short strike >=10 min after entry -> close at TD
         touch at trigger; else SPX settlement intrinsic capped at width.
Data   : SPX daily open/close = Yahoo (TD index history blocked pre-2026 on our
         tier); VIX = data/vix_daily.csv; everything else ThetaData.

Checkpointed to data/options_sim/backtest_full/rows.csv (skips done dates on
restart). Run: python scripts/backtest_full_em_2022.py [--start 20220516] [--end auto]
"""
import argparse
import csv
import datetime as dt
import io
import json
import math
import sys
import urllib.request
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent))
import market_calendar as MC
from td_shadow_reprice import nbbo_at

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "data/options_sim/backtest_full"
OUT.mkdir(parents=True, exist_ok=True)
ROWS = OUT / "rows.csv"
BASE = "http://127.0.0.1:25503/v3"
FEE = 1.63
S252, S365 = math.sqrt(1 / 252.0), math.sqrt(1 / 365.0)
ENTRY_ET = {"eod": "09:31:00", "open": "10:05:00"}
FIELDS = ["date", "strat", "method", "center", "em", "short_k", "long_k",
          "credit", "exit_kind", "exit_val", "pnl", "note"]


def round5(x):
    return round(x / 5.0) * 5.0


def yahoo_spx(start="2022-05-01"):
    """SPX daily OHLC from Yahoo chart API; cached to a dated CSV."""
    cache = OUT / "spx_daily_ohlc.csv"
    if cache.exists():
        d = pd.read_csv(cache)
        if d["date"].iloc[-1] >= (dt.date.today() - dt.timedelta(days=4)).strftime("%Y-%m-%d"):
            return d.set_index("date")
    p1 = int(dt.datetime.strptime(start, "%Y-%m-%d").timestamp())
    p2 = int(dt.datetime.now().timestamp())
    u = (f"https://query1.finance.yahoo.com/v8/finance/chart/%5EGSPC"
         f"?period1={p1}&period2={p2}&interval=1d")
    req = urllib.request.Request(u, headers={"User-Agent": "Mozilla/5.0"})
    j = json.loads(urllib.request.urlopen(req, timeout=30).read())
    res = j["chart"]["result"][0]
    ts = res["timestamp"]
    q = res["indicators"]["quote"][0]
    rows = []
    for i, t in enumerate(ts):
        o, c = q["open"][i], q["close"][i]
        if o is None or c is None:
            continue
        rows.append(dict(date=dt.datetime.fromtimestamp(t).strftime("%Y-%m-%d"),
                         open=round(o, 2), high=round(q["high"][i], 2),
                         low=round(q["low"][i], 2), close=round(c, 2)))
    d = pd.DataFrame(rows)
    d.to_csv(cache, index=False)
    return d.set_index("date")


def quotes_1m(day_c, strike, right):
    """full-day 1-min NBBO for one contract; DataFrame[t, bid, ask] or None."""
    u = (f"{BASE}/option/history/quote?symbol=SPXW&expiration={day_c}&strike={strike:.3f}"
         f"&right={right}&start_date={day_c}&end_date={day_c}&interval=1m&format=csv")
    try:
        body = urllib.request.urlopen(u, timeout=60).read().decode("utf-8", "replace")
        d = pd.read_csv(io.StringIO(body))
        if not len(d):
            return None
        d["t"] = d["timestamp"].str[11:19]
        return d[["t", "bid", "ask"]]
    except Exception:
        return None


def parity_feed(day_c, k):
    """1-min SPX series via put-call parity at strike k. Also returns the 09:31
    straddle mid. -> (DataFrame[t,S] or None, straddle or None)"""
    c = quotes_1m(day_c, k, "call")
    p = quotes_1m(day_c, k, "put")
    if c is None or p is None:
        return None, None
    m = c.merge(p, on="t", suffixes=("_c", "_p"))
    m = m[(m.bid_c > 0) | (m.ask_c > 0)]
    m["S"] = (m.bid_c + m.ask_c) / 2 - (m.bid_p + m.ask_p) / 2 + k
    row = m[m["t"] >= "09:31:00"].head(1)
    strad = None
    if len(row):
        r = row.iloc[0]
        strad = round((r.bid_c + r.ask_c) / 2 + (r.bid_p + r.ask_p) / 2, 2)
    return m[["t", "S"]], strad


def detect_stop(feed, short_k, right, entry_et, hold_min=10):
    """level acceptance: S holds beyond short strike >=hold_min continuous minutes,
    counting only from entry time. Returns ET trigger 'HH:MM:SS' or None."""
    if feed is None:
        return None
    f = feed[feed["t"] >= entry_et]
    beyond = (f["S"] >= short_k) if right == "C" else (f["S"] <= short_k)
    run_start = None
    for t, b in zip(f["t"].tolist(), beyond.tolist()):
        tt = dt.datetime.strptime(t, "%H:%M:%S")
        if b:
            if run_start is None:
                run_start = tt
            elif (tt - run_start).total_seconds() >= hold_min * 60:
                return t
        else:
            run_start = None
    return None


def touch(day_c, short_k, long_k, right, et, closing=False):
    sq = lq = None
    for _ in range(3):                       # retry: terminal drops under load
        sq = sq or nbbo_at(day_c, short_k, right, day_c, et)
        lq = lq or nbbo_at(day_c, long_k, right, day_c, et)
        if sq is not None and lq is not None:
            break
    if sq is None or lq is None:
        return None
    if closing:
        return round(sq[1] - lq[0], 2)      # buy short@ask - sell long@bid
    return round(sq[0] - lq[1], 2)          # sell short@bid - buy long@ask


def settle_vertical(short_k, long_k, right, close):
    w = abs(short_k - long_k)
    itm = max(0.0, short_k - close) if right == "P" else max(0.0, close - short_k)
    return min(w, itm)


def run_day(d, spx, vix):
    """all 12 (4 verticals x 3 methods) rows for date d (YYYY-MM-DD)."""
    dc = d.replace("-", "")
    dd = dt.datetime.strptime(d, "%Y-%m-%d").date()
    prior = MC.prev_trading_day(dd).strftime("%Y-%m-%d")
    if d not in spx.index or prior not in spx.index:
        return [dict(date=d, strat="", method="", note="no spx daily")]
    pc, o_o, close = spx.loc[prior, "close"], spx.loc[d, "open"], spx.loc[d, "close"]
    v = vix.get(prior)
    if v is None:
        return [dict(date=d, strat="", method="", note="no vix")]
    k_atm = round5(o_o)
    feed, strad = parity_feed(dc, k_atm)
    ems = {"vix252": pc * v / 100.0 * S252, "vix365": pc * v / 100.0 * S365}
    if strad and strad > 0:
        ems["straddle"] = strad

    rows = []
    for strat_base, center, ekey in (("eodic", pc, "eod"), ("openic", o_o, "open")):
        et = ENTRY_ET[ekey]
        for right, suff in (("P", "_p"), ("C", "_c")):
            for meth, emv in ems.items():
                short_k = round5(center - emv) if right == "P" else round5(center + emv)
                long_k = short_k - 25 if right == "P" else short_k + 25
                cr = touch(dc, short_k, long_k, right, et)
                rec = dict(date=d, strat=strat_base + suff, method=meth,
                           center=round(center, 2), em=round(emv, 1),
                           short_k=short_k, long_k=long_k, credit=cr,
                           exit_kind="", exit_val=None, pnl=None, note="")
                if cr is None:
                    rec["note"] = "no entry quote"
                    rows.append(rec)
                    continue
                stop_t = detect_stop(feed, short_k, right, et)
                if stop_t:
                    debit = touch(dc, short_k, long_k, right, stop_t, closing=True)
                    if debit is not None:
                        rec["exit_kind"], rec["exit_val"], nfee = "stop", debit, 4
                    else:
                        rec["exit_kind"] = "settle*"
                        rec["exit_val"], nfee = settle_vertical(short_k, long_k, right, close), 2
                else:
                    rec["exit_kind"] = "settle"
                    rec["exit_val"], nfee = settle_vertical(short_k, long_k, right, close), 2
                rec["pnl"] = round((cr - rec["exit_val"]) * 100 - nfee * FEE, 2)
                rows.append(rec)
    return rows


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--start", default="2022-05-16")
    ap.add_argument("--end", default=None)
    ap.add_argument("--workers", type=int, default=4)
    a = ap.parse_args()
    end = a.end or (dt.date.today() - dt.timedelta(days=1)).strftime("%Y-%m-%d")

    spx = yahoo_spx()
    vix = {r["date"]: float(r["close"]) for r in csv.DictReader(open(ROOT / "data/vix_daily.csv"))}

    done = set()
    if ROWS.exists():
        done = set(pd.read_csv(ROWS, usecols=["date"])["date"].unique())
    days = []
    d = dt.datetime.strptime(a.start, "%Y-%m-%d").date()
    e = dt.datetime.strptime(end, "%Y-%m-%d").date()
    while d <= e:
        ds = d.strftime("%Y-%m-%d")
        if MC.is_trading_day(d) and ds not in done:
            days.append(ds)
        d += dt.timedelta(days=1)
    print(f"days to run: {len(days)} (done already: {len(done)})", flush=True)

    new_file = not ROWS.exists()
    fh = open(ROWS, "a", newline="", encoding="utf-8")
    w = csv.DictWriter(fh, fieldnames=FIELDS)
    if new_file:
        w.writeheader()

    with ThreadPoolExecutor(max_workers=a.workers) as ex:
        for i, rows in enumerate(ex.map(lambda dy: run_day(dy, spx, vix), days)):
            for r in rows:
                w.writerow({k: r.get(k) for k in FIELDS})
            fh.flush()
            if (i + 1) % 25 == 0:
                print(f"  {i+1}/{len(days)} days done ({rows[0]['date'] if rows else '?'})", flush=True)
    fh.close()
    print("DONE ->", ROWS, flush=True)


if __name__ == "__main__":
    main()
