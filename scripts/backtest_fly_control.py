"""Chat-B decisive test: end-to-end stop-rule control on the HARD case — the 79
August fly verticals (short strike AT the pin level; 53/79 desk level-stops).

Same engine as the IC control: desk's ACTUAL legs + entry times, entry = TD touch,
stop = level-acceptance (spot beyond short strike >=10 continuous min, counted
from entry) -> TD touch close at trigger; else settlement intrinsic.

Two stop-feed variants, reported side by side:
  parity : 1-min SPX from put-call parity (what the 2022-> historical engine has)
  desk   : the desk's own decision feed underlying_<d>.csv (what the daemon saw)

Outputs per trade: desk stop? / model stop? / trigger times / P&L vs booked.
Confusion matrix + totals per variant. This is the test Chat B named as decisive
(docs/research_notes/stop_backtest_debate.md Q3.1).
"""
import datetime as dt
import json
import sys
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent))
from td_shadow_reprice import nbbo_at, ct_to_et
from backtest_full_em_2022 import parity_feed, round5, yahoo_spx
from backtest_em_compare_pnl import load_feed  # desk CT feed, cached

ROOT = Path(__file__).resolve().parents[1]
FEE = 1.63


def touch_legs(legs, day_c, et, closing=False):
    tot = 0.0
    for lg in legs:
        q = nbbo_at(day_c, lg["strike"], lg["right"], day_c, et)
        if q is None:
            return None
        b, a = q[0], q[1]
        if closing:
            px = a if lg["side"] == "sell" else b
        else:
            px = b if lg["side"] == "sell" else a
        tot += (px if lg["side"] == "sell" else -px) * lg.get("qty", 1)
    return round(tot, 2)


def settle_legs(legs, close):
    tot = 0.0
    for lg in legs:
        itm = max(0.0, lg["strike"] - close) if lg["right"] == "P" else max(0.0, close - lg["strike"])
        tot += (itm if lg["side"] == "sell" else -itm) * lg.get("qty", 1)
    return round(tot, 2)


def detect(series_t, series_s, short_k, right, entry_t, hold_min=10):
    """series in (time,spot) lists, times 'HH:MM:SS'. Returns trigger time or None."""
    run_start = None
    for t, s in zip(series_t, series_s):
        if t < entry_t:
            continue
        beyond = (s >= short_k) if right == "C" else (s <= short_k)
        tt = dt.datetime.strptime(t, "%H:%M:%S")
        if beyond:
            if run_start is None:
                run_start = tt
            elif (tt - run_start).total_seconds() >= hold_min * 60:
                return t
        else:
            run_start = None
    return None


def main():
    import argparse
    ap = argparse.ArgumentParser()
    ap.add_argument("--month", default="2026-08")
    a = ap.parse_args()
    m0, m1 = a.month + "-01", a.month + "-31"
    spx = yahoo_spx()
    df = pd.read_parquet(ROOT / "data/options_log/trades.parquet")
    df["date"] = df["entry_dt"].astype(str).str[:10]
    fly = df[(df["date"] >= m0) & (df["date"] <= m1)
             & df["pnl"].notna()
             & df["strategy_id"].astype(str).str.contains("fly", na=False)].copy()

    feeds = {}   # date -> dict(parity=(t[],s[]), desk=(t[],s[]))
    def get_feeds(d):
        if d in feeds:
            return feeds[d]
        dc = d.replace("-", "")
        o_o = spx.loc[d, "open"] if d in spx.index else None
        par, _ = parity_feed(dc, round5(o_o)) if o_o else (None, None)
        pf = (par["t"].tolist(), par["S"].tolist()) if par is not None else None
        dk = load_feed(d)
        dkf = None
        if dk is not None and len(dk):
            ts = [(dt.datetime.strptime(t, "%H:%M:%S") + dt.timedelta(hours=1)).strftime("%H:%M:%S")
                  for t in dk["ts_et"]]          # desk feed is CT -> ET
            dkf = (ts, dk["und"].tolist())
        feeds[d] = dict(parity=pf, desk=dkf)
        return feeds[d]

    rows = []
    for _, t in fly.iterrows():
        d = t["date"]
        dc = d.replace("-", "")
        legs = json.loads(t["legs"]) if isinstance(t["legs"], str) else t["legs"]
        short = next(l for l in legs if l["side"] == "sell")
        ect = str(t["entry_dt"]).split(" ")[-1]
        et = ct_to_et(ect + ":00" if ect.count(":") == 1 else ect)
        if et and et <= "09:30:30":
            et = "09:31:00"
        cr = touch_legs(legs, dc, et)
        close = spx.loc[d, "close"] if d in spx.index else None
        desk_stopped = str(t["close_reason"]).startswith("level")
        rec = dict(date=d, strat=t["strategy_id"], short_k=short["strike"],
                   right=short["right"], entry_et=et, credit=cr,
                   booked_stop=desk_stopped, booked_pnl=round(float(t["pnl"]), 2),
                   desk_exit=str(t["exit_dt"]).split(" ")[-1])
        fd = get_feeds(d)
        for variant in ("parity", "dfeed"):
            f = fd["desk" if variant == "dfeed" else variant]
            trig = detect(f[0], f[1], short["strike"], short["right"], et) if f else None
            rec[f"{variant}_stop"] = trig is not None
            rec[f"{variant}_trig"] = trig
            if cr is None or close is None:
                rec[f"{variant}_pnl"] = None
                continue
            if trig:
                debit = touch_legs(legs, dc, trig, closing=True)
                if debit is None:
                    rec[f"{variant}_pnl"] = None
                    continue
                ncon = sum(l.get("qty", 1) for l in legs)
                rec[f"{variant}_pnl"] = round((cr - debit) * 100 - 2 * ncon * FEE, 2)
            else:
                ncon = sum(l.get("qty", 1) for l in legs)
                rec[f"{variant}_pnl"] = round((cr - settle_legs(legs, close)) * 100 - ncon * FEE, 2)
        rows.append(rec)

    out = pd.DataFrame(rows)
    out.to_csv(ROOT / f"data/options_sim/backtest_fly_control_{a.month}.csv", index=False)

    print(f"August fly verticals: {len(out)}   desk ACTUAL stops: {out.booked_stop.sum()}\n")
    for variant in ("parity", "dfeed"):
        s = out[f"{variant}_stop"]
        tp = ((s) & (out.booked_stop)).sum()
        fp = ((s) & (~out.booked_stop)).sum()
        fn = ((~s) & (out.booked_stop)).sum()
        tn = ((~s) & (~out.booked_stop)).sum()
        pnl = out[f"{variant}_pnl"].dropna()
        print(f"[{variant} feed]  stop-match: {tp+tn}/{len(out)}   "
              f"missed: {fn}  false: {fp}   model P&L: {pnl.sum():+,.2f} (n={len(pnl)})")
    print(f"desk booked P&L (all {len(out)}): {out.booked_pnl.sum():+,.2f}\n")

    mism = out[(out.parity_stop != out.booked_stop) | (out.dfeed_stop != out.booked_stop)]
    if len(mism):
        print("mismatches (parity vs desk-actual):")
        print(mism[["date", "strat", "short_k", "credit", "booked_stop", "parity_stop", "dfeed_stop",
                    "parity_trig", "desk_exit", "booked_pnl", "parity_pnl", "dfeed_pnl"]].to_string(index=False))
    print("-> data/options_sim/backtest_fly_control.csv")


if __name__ == "__main__":
    main()
