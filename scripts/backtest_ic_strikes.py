"""Step 1b — the backtest CHOOSES the iron-condor strikes from ThetaData inputs,
and we check they match what the desk actually traded (proving it runs WITHOUT
the desk's record).

Desk formula (options_gameplan.py):
  move = prior_close * (VIX/100) / sqrt(252)
  EOD  condor: short put = round5(prior_close - move), short call = round5(prior_close + move)
  OPEN condor: short put = round5(open_spot   - move), short call = round5(open_spot   + move)

Inputs, all historical / TD-available:
  prior_close  -> TD SPX index eod close on the PRIOR trading day
  VIX          -> vix_daily.csv close on the prior trading day (the desk's own source, back to 1990)
  open_spot    -> TD SPX index eod `open` (the 09:30 print) on the trade day
"""
import csv
import datetime as dt
import json
import math
import sys
import urllib.request
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(Path(__file__).resolve().parent))
import market_calendar as MC

BASE = "http://127.0.0.1:25503/v3"


def round5(x):
    return round(x / 5.0) * 5.0


def index_ohlc(day):
    """(open, close) for SPX index on `day` (YYYYMMDD)."""
    u = f"{BASE}/index/history/eod?symbol=SPX&start_date={day}&end_date={day}&format=csv"
    try:
        body = urllib.request.urlopen(u, timeout=15).read().decode("utf-8", "replace")
        lines = [l for l in body.splitlines() if l.strip()]
        h = [x.strip().strip('"') for x in lines[0].split(",")]
        r = [x.strip().strip('"') for x in lines[-1].split(",")]
        d = dict(zip(h, r))
        return float(d["open"]), float(d["close"])
    except Exception:
        return None, None


VIX = {r["date"]: float(r["close"]) for r in csv.DictReader(open(ROOT / "data/vix_daily.csv"))}


def main():
    df = pd.read_parquet(ROOT / "data/options_log/trades.parquet")
    ic = df[df["strategy_id"].astype(str).str.contains("ic", na=False) & df["pnl"].notna()].copy()
    ic["date"] = ic["entry_dt"].astype(str).str[:10]

    # actual short strike per (date, strategy)
    actual = {}
    for _, t in ic.iterrows():
        legs = json.loads(t["legs"]) if isinstance(t["legs"], str) else t["legs"]
        short = next(l for l in legs if l["side"] == "sell")
        actual[(t["date"], t["strategy_id"])] = short["strike"]

    dates = sorted(ic["date"].unique())
    rows, hits, tot = [], 0, 0
    for d in dates:
        pd_ = MC.prev_trading_day(dt.datetime.strptime(d, "%Y-%m-%d").date())
        pc_o, pc_c = index_ohlc(pd_.strftime("%Y%m%d"))          # prior close
        o_o, o_c = index_ohlc(d.replace("-", ""))                # today's open
        vix = VIX.get(pd_.strftime("%Y-%m-%d"))
        if pc_c is None or vix is None or o_o is None:
            print(f"  {d}: missing input (prior_close={pc_c} vix={vix} open={o_o}) — skip")
            continue
        move = pc_c * (vix / 100.0) / math.sqrt(252.0)
        mine = {
            "eodic_p": round5(pc_c - move), "eodic_c": round5(pc_c + move),
            "openic_p": round5(o_o - move), "openic_c": round5(o_o + move),
        }
        for strat, k in mine.items():
            a = actual.get((d, strat))
            if a is None:
                continue
            tot += 1
            match = abs(k - a) < 1e-6
            hits += match
            rows.append(dict(date=d, strat=strat, prior_close=round(pc_c, 1), vix=vix,
                             open=round(o_o, 1), move=round(move, 1),
                             mine=k, desk=a, diff=round(k - a, 0), match=match))

    out = pd.DataFrame(rows)
    out.to_csv(ROOT / "data/options_sim/backtest_ic_strikes.csv", index=False)
    print(f"\n{'date':11}{'strat':10}{'priorC':>8}{'vix':>6}{'open':>8}{'move':>6}{'mine':>7}{'desk':>7}{'diff':>6}")
    for _, r in out.iterrows():
        flag = "" if r["match"] else "  <-- MISS"
        print(f"  {r['date']:11}{r['strat']:10}{r['prior_close']:>8}{r['vix']:>6.1f}"
              f"{r['open']:>8}{r['move']:>6.0f}{r['mine']:>7.0f}{r['desk']:>7.0f}{r['diff']:>6.0f}{flag}")
    print(f"\nExact strike match: {hits}/{tot} = {100*hits/tot:.0f}%")
    within5 = sum(1 for _, r in out.iterrows() if abs(r["diff"]) <= 5)
    print(f"Within 5pt (one strike): {within5}/{tot} = {100*within5/tot:.0f}%")
    print(f"-> data/options_sim/backtest_ic_strikes.csv")


if __name__ == "__main__":
    main()
