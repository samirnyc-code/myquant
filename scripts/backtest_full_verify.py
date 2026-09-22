"""Adversarial audit of the 3-EM backtest rows (answering: 'prove -23k is real').

1. Integrity: duplicate rows, credits sane, stop debits vs width, settle caps.
2. Loss tail: worst 15 vix252 days -> do they align with REAL market events?
3. P&L decomposition: credit collected vs losses given back.
4. Settlement input check: Yahoo close vs parity-reconstructed close (independent
   TD-derived) on sampled days across 2022-2024 where TD index history is blocked.
5. Full hand-trace of the 2 worst days: every ingredient printed with RAW TD
   NBBO quotes (both legs, entry + exit) so the arithmetic can be checked by hand.
"""
import sys
import urllib.request
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent))
from backtest_full_em_2022 import parity_feed, round5, yahoo_spx

ROOT = Path(__file__).resolve().parents[1]
BASE = "http://127.0.0.1:25503/v3"


def raw_quote(day_c, k, right, et):
    u = (f"{BASE}/option/at_time/quote?symbol=SPXW&expiration={day_c}&strike={k:.3f}"
         f"&right={'call' if right=='C' else 'put'}&start_date={day_c}&end_date={day_c}"
         f"&time_of_day={et}&format=csv")
    try:
        body = urllib.request.urlopen(u, timeout=20).read().decode()
        lines = [l for l in body.splitlines() if l.strip()]
        h = [x.strip().strip('"') for x in lines[0].split(",")]
        d = dict(zip(h, [x.strip().strip('"') for x in lines[-1].split(",")]))
        return f"bid {d['bid']} / ask {d['ask']}  @ {d['timestamp'][11:23]}"
    except Exception as e:
        return f"ERR {e}"


def main():
    d = pd.read_csv(ROOT / "data/options_sim/backtest_full/rows.csv")
    d = d[d.pnl.notna()].copy()

    print("=" * 70)
    print("1. INTEGRITY")
    dup = d.duplicated(subset=["date", "strat", "method"]).sum()
    print(f"   duplicate (date,strat,method) rows: {dup}")
    neg_cr = (d.credit < -0.5).sum()
    print(f"   credits < -0.50 (nonsense entries): {neg_cr}")
    stop_rows = d[d.exit_kind == "stop"]
    wide = (stop_rows.exit_val > 26).sum()
    print(f"   stop exit debit > width+1 (blown-out fills): {wide} of {len(stop_rows)} stops")
    big_debit = stop_rows.exit_val.max()
    print(f"   max stop debit: {big_debit}  (width=25)")
    setl = d[d.exit_kind.str.startswith("settle")]
    print(f"   settle values >25 (cap breach): {(setl.exit_val > 25.0001).sum()}")

    print("\n" + "=" * 70)
    print("2. WORST 15 DAYS (vix252 daily book) — check vs real market events")
    v = d[d.method == "vix252"]
    daily = v.groupby("date").pnl.sum().sort_values()
    spx = yahoo_spx()
    for dt_, p in daily.head(15).items():
        chg = ""
        if dt_ in spx.index:
            i = spx.index.get_loc(dt_)
            if i > 0:
                pc = spx.iloc[i - 1]["close"]
                chg = f"SPX {100*(spx.loc[dt_,'close']-pc)/pc:+.1f}%  range {100*(spx.loc[dt_,'high']-spx.loc[dt_,'low'])/pc:.1f}%"
        print(f"   {dt_}  {p:>9,.0f}   {chg}")

    print("\n" + "=" * 70)
    print("3. P&L DECOMPOSITION (vix252)")
    print(f"   trades: {len(v)}   credit collected: {(v.credit*100).sum():+,.0f}")
    print(f"   given back on exits:  {(v.exit_val*100).sum():-,.0f}")
    fees = len(v[v.exit_kind == 'stop']) * 4 * 1.63 + len(v[v.exit_kind != 'stop']) * 2 * 1.63
    print(f"   fees: {fees:,.0f}   net: {(v.credit*100).sum() - (v.exit_val*100).sum() - fees:+,.0f}  (file says {v.pnl.sum():+,.0f})")
    full_loss = v[(v.exit_val >= 24)]
    print(f"   max-loss (settle>=24) events: {len(full_loss)} of {len(v)} = {100*len(full_loss)/len(v):.1f}%")

    print("\n" + "=" * 70)
    print("4. SETTLEMENT INPUT: Yahoo close vs TD-parity close (independent), 8 sampled days")
    import random
    random.seed(7)
    days = sorted(random.sample(sorted(set(v.date[(v.date >= '2022-06-01') & (v.date <= '2024-12-31')])), 8))
    for dt_ in days:
        dc = dt_.replace("-", "")
        o = spx.loc[dt_, "open"]
        feed, _ = parity_feed(dc, round5(o))
        if feed is None or not len(feed):
            print(f"   {dt_}  parity feed unavailable")
            continue
        late = feed[feed.t >= "15:55:00"]
        pclose = late.S.iloc[-1] if len(late) else feed.S.iloc[-1]
        yc = spx.loc[dt_, "close"]
        print(f"   {dt_}  yahoo {yc:>8.2f}   parity@{late.t.iloc[-1] if len(late) else feed.t.iloc[-1]} {pclose:>8.2f}   diff {yc-pclose:+.2f}")

    print("\n" + "=" * 70)
    print("5. HAND-TRACE: 2 worst vix252 days, raw TD quotes")
    for dt_ in daily.head(2).index:
        dc = dt_.replace("-", "")
        print(f"\n   ---- {dt_} ----")
        i = spx.index.get_loc(dt_)
        pc = spx.iloc[i - 1]["close"]
        print(f"   prior close {pc}   open {spx.loc[dt_,'open']}   close {spx.loc[dt_,'close']}")
        g = v[v.date == dt_]
        for _, r in g.iterrows():
            right = "P" if r.strat.endswith("_p") else "C"
            et = "09:31:00" if r.strat.startswith("eod") else "10:05:00"
            print(f"   {r.strat:9} short {r.short_k:.0f} long {r.long_k:.0f}  em {r.em}  credit {r.credit}  "
                  f"exit[{r.exit_kind}] {r.exit_val}  pnl {r.pnl:+,.0f}")
            print(f"      entry raw: short {raw_quote(dc, r.short_k, right, et)}")
            print(f"                 long  {raw_quote(dc, r.long_k, right, et)}")


if __name__ == "__main__":
    main()
