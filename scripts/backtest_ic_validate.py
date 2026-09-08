"""Step 1a — prove the TD backtest engine on REAL trades.

Takes the desk's actual closed iron-condor verticals (eodic/openic) and reprices
each entirely from ThetaData at its own exact times, then checks the TD P&L
reproduces the sim's booked P&L:
  entry  -> TD NBBO touch at entry time (credit = short_bid - long_ask)
  exit   -> expired: intrinsic vs the FINAL index close (index/history/eod)
            stopped: TD NBBO touch at the exit time (debit = short_ask - long_bid)
  P&L    -> (credit - exit) * 100 - fees

Timestamps in trades.parquet are CT; ThetaData is ET (+1h). This is the confidence
test: if TD P&L tracks the sim's across 70 trades, the pricing + time-stop handling
is proven, and the same engine scales back to 2022.
"""
import datetime as dt
import json
import sys
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent))
from td_shadow_reprice import nbbo_at, ct_to_et  # reuse the exact-time pricer

ROOT = Path(__file__).resolve().parents[1]
BASE = "http://127.0.0.1:25503/v3"
FEE = 1.63
import urllib.request


def index_close(day):
    u = f"{BASE}/index/history/eod?symbol=SPX&start_date={day}&end_date={day}&format=csv"
    try:
        body = urllib.request.urlopen(u, timeout=15).read().decode("utf-8", "replace")
        lines = [l for l in body.splitlines() if l.strip()]
        h = [x.strip().strip('"') for x in lines[0].split(",")]
        r = [x.strip().strip('"') for x in lines[-1].split(",")]
        v = dict(zip(h, r)).get("close")
        return float(v) if v not in (None, "", "0.00", "0") else None
    except Exception as e:
        print(f"  index_close({day}) err: {e}")
        return None


def price_touch(legs, day, et_time, closing=False):
    """credit(open) or debit(close) at the touch; None if any leg unquoted."""
    tot = 0.0
    for lg in legs:
        q = nbbo_at(day, lg["strike"], lg["right"], day, et_time)
        if q is None:
            return None
        b, a, _ = q
        if not closing:
            px = b if lg["side"] == "sell" else a          # open: sell@bid, buy@ask
        else:
            px = a if lg["side"] == "sell" else b          # close: buy short@ask, sell long@bid
        tot += (px if lg["side"] == "sell" else -px) * lg.get("qty", 1)
    return round(tot, 2)


def main():
    df = pd.read_parquet(ROOT / "data/options_log/trades.parquet")
    ic = df[df["strategy_id"].astype(str).str.contains("ic", na=False) & df["pnl"].notna()].copy()
    rows = []
    for _, t in ic.iterrows():
        legs = json.loads(t["legs"]) if isinstance(t["legs"], str) else t["legs"]
        day = str(legs[0]["expiry"]).replace("-", "")
        ent_ct = str(t["entry_dt"]).split(" ")[-1]                  # "09:05"
        et = ct_to_et(ent_ct + ":00" if ent_ct.count(":") == 1 else ent_ct)
        # the 09:30:00 open tick is a stale pre-open quote — the desk's real EOD fills
        # were ~1-3 min after 08:30. Anchor at the first clean post-open quote.
        if et and et <= "09:30:30":
            et = "09:31:00"
        credit = price_touch(legs, day, et)
        expired = str(t["close_reason"]).startswith("expired")
        short = next(l for l in legs if l["side"] == "sell")
        width = abs(short["strike"] - next(l for l in legs if l["side"] == "buy")["strike"])
        if expired:
            sc = index_close(day)
            if sc is None:
                exit_val = None
            else:
                exit_val = min(width, max(0.0, (short["strike"] - sc) if short["right"] == "P"
                                          else (sc - short["strike"])))
            nfee = 2
        else:
            xct = str(t["exit_dt"]).split(" ")[-1]
            xet = ct_to_et(xct + ":00" if xct.count(":") == 1 else xct)
            exit_val = price_touch(legs, day, xet, closing=True)
            nfee = 4
        td_pnl = round((credit - exit_val) * 100 - nfee * FEE, 2) if (credit is not None and exit_val is not None) else None
        rows.append(dict(date=str(t["entry_dt"])[:10], strat=t["strategy_id"],
                         reason="expired" if expired else "stopped",
                         sim_cr=round(float(t["credit"]), 2), td_cr=credit,
                         sim_pnl=round(float(t["pnl"]), 2), td_pnl=td_pnl))

    out = pd.DataFrame(rows)
    out.to_csv(ROOT / "data/options_sim/backtest_ic_validate.csv", index=False)
    ok = out.dropna(subset=["td_pnl"])
    print(f"trades: {len(out)}  priced by TD: {len(ok)}")
    print(f"\n{'date':11}{'strat':10}{'why':9}{'simCr':>7}{'tdCr':>7}{'simPnL':>9}{'tdPnL':>9}{'dPnL':>8}")
    for _, r in out.iterrows():
        d = round(r['sim_pnl'] - r['td_pnl'], 1) if pd.notna(r['td_pnl']) else None
        print(f"  {r['date']:11}{str(r['strat']):10}{r['reason']:9}{r['sim_cr']:>7}"
              f"{str(r['td_cr']):>7}{r['sim_pnl']:>9}{str(r['td_pnl']):>9}{str(d):>8}")
    print(f"\nSim total  P&L: {ok['sim_pnl'].sum():>10,.2f}")
    print(f"TD  total  P&L: {ok['td_pnl'].sum():>10,.2f}")
    print(f"correlation(sim,td): {ok['sim_pnl'].corr(ok['td_pnl']):.4f}")
    print(f"median |sim-td| per trade: {(ok['sim_pnl']-ok['td_pnl']).abs().median():.2f}")
    print(f"-> data/options_sim/backtest_ic_validate.csv")


if __name__ == "__main__":
    main()
