"""August 2026 engine rerun v2 — DESK-FAITHFUL emulation, driven by the desk's
own gameplan JSONs. Fixes the three S115 engine defects:

  1. entry anchor: per-day WAIT flag from gameplan (`fire.not_before` 08:30 or
     09:05 CT) + 3-min fire lag, instead of a fixed 10:05 ET
  2. entry gate: credit<=0 -> broken skip; credit<0.10 -> thin_credit skip
     (options_gameplan MIN_CREDIT_ABS), instead of trading everything
  3. strikes: eod* streams use the gameplan's ARMED strikes (kills the
     Yahoo-vs-desk-feed 5pt rounding drift); open* streams struck from the
     parity-SPX at the actual fire minute +/- the gameplan's own offset

Also models the 14:45 CT time-stop the way the desk factually behaves: try a
closing quote at 15:45 ET; close if the debit is quotable and >0.10, else the
position rides to settlement (live "expired" rows = unquotable worthless legs).

Open streams are priced under TWO policies to answer "what if we never waited":
  deskwait — per-day gameplan anchor (the desk's actual behavior)
  nowait   — 08:33 CT (09:33 ET) every day
eod streams are policy-independent (premarket strikes, 09:31 ET entry).

Needs the Theta terminal. ~50 req/day, single job (quota-safe).
Output: august_rerun_v2_<stamp>.csv + stdout summary incl. live comparison.
"""
import datetime as dt
import json
import sys
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent))
from backtest_full_em_2022 import (FEE, OUT, parity_feed, touch, detect_stop,
                                   settle_vertical, yahoo_spx)

ROOT = Path(__file__).resolve().parents[1]
SIM = ROOT / "data" / "options_sim"
STAMP = dt.date.today().strftime("%Y%m%d")
DAYS = [d.strftime("%Y-%m-%d") for d in pd.bdate_range("2026-08-06", "2026-08-31")]
MIN_CREDIT = 0.10
FIRE_LAG_MIN = 3          # daemon poll: triggers fire ~3 min after not_before
TIME_STOP_ET = "15:45:00"  # 14:45 CT
OPEN_STREAMS = ("openic_p", "openic_c", "openfly_p", "openfly_c")
EOD_STREAMS = ("eodic_p", "eodic_c", "eodfly_p", "eodfly_c")


def ct_to_et(hhmm, lag_min=0):
    t = dt.datetime.strptime(hhmm, "%H:%M") + dt.timedelta(hours=1, minutes=lag_min)
    return t.strftime("%H:%M:%S")


def round5(x):
    return round(x / 5.0) * 5.0


def spot_at(feed, et):
    if feed is None:
        return None
    f = feed[feed["t"] >= et].head(1)
    return None if not len(f) else float(f.iloc[0]["S"])


def run_trade(dc, strat, short_k, long_k, right, entry_et, feed, close_px):
    """One vertical under the desk rules. Returns a result dict."""
    rec = dict(strat=strat, short_k=short_k, long_k=long_k, entry_et=entry_et,
               credit=None, exit_kind="", exit_val=None, pnl=None, note="")
    cr = touch(dc, short_k, long_k, right, entry_et)
    rec["credit"] = cr
    if cr is None:
        rec["exit_kind"], rec["note"] = "SKIP", "no entry quote"
        return rec
    if cr <= 0:
        rec["exit_kind"], rec["note"] = "SKIP", f"gate: broken (credit {cr:.2f} <= 0)"
        return rec
    if cr < MIN_CREDIT:
        rec["exit_kind"], rec["note"] = "SKIP", f"gate: thin_credit ({cr:.2f} < {MIN_CREDIT})"
        return rec
    stop_t = detect_stop(feed, short_k, right, entry_et)
    if stop_t:
        debit = touch(dc, short_k, long_k, right, stop_t, closing=True)
        if debit is not None:
            rec.update(exit_kind="stop", exit_val=debit,
                       pnl=round((cr - debit) * 100 - 4 * FEE, 2))
            return rec
        rec["note"] = "stop unquotable -> settle"
    else:
        # 14:45 CT time stop: close only if the closing quote exists and is
        # worth paying (mirrors the desk: worthless legs fail to quote and ride)
        debit = touch(dc, short_k, long_k, right, TIME_STOP_ET, closing=True)
        if debit is not None and debit > 0.10:
            rec.update(exit_kind="time", exit_val=debit,
                       pnl=round((cr - debit) * 100 - 4 * FEE, 2))
            return rec
    sv = settle_vertical(short_k, long_k, right, close_px)
    rec.update(exit_kind=rec["exit_kind"] or "settle", exit_val=sv,
               pnl=round((cr - sv) * 100 - 2 * FEE, 2))
    return rec


def main():
    spx = yahoo_spx()
    rows = []
    for d in DAYS:
        dc = d.replace("-", "")
        gp_path = SIM / f"gameplan_{dc}.json"
        if not gp_path.exists() or d not in spx.index:
            continue
        gp = json.loads(gp_path.read_text(encoding="utf-8"))
        trig = {t["id"]: t for t in gp["triggers"]}
        close_px = float(spx.loc[d, "close"])
        k_atm = round5(float(spx.loc[d, "open"]))
        feed, _ = parity_feed(dc, k_atm)
        if feed is None:
            print(f"{d}: no parity feed — skipped day")
            continue

        # eod streams: armed strikes, 09:31 ET, policy-independent
        for sid in EOD_STREAMS:
            t = trig.get(sid)
            if not t:
                continue
            st = t["structure"]
            r = run_trade(dc, sid, float(st["short"]), float(st["long"]),
                          st["right"], "09:31:00", feed, close_px)
            r.update(date=d, policy="eod", wait_day="")
            rows.append(r)

        # open streams under both policies
        nb = trig["openfly_c"]["fire"].get("not_before", "08:30")
        wait_day = nb >= "09:00"
        for policy, entry_et in (("deskwait", ct_to_et(nb, FIRE_LAG_MIN)),
                                 ("nowait", ct_to_et("08:30", FIRE_LAG_MIN))):
            S = spot_at(feed, entry_et)
            if S is None:
                continue
            for sid in OPEN_STREAMS:
                t = trig.get(sid)
                if not t:
                    continue
                st = t["structure"]
                off = float(st.get("offset") or 0.0)
                short_k = round5(S + off)
                long_k = short_k - 25 if st["right"] == "P" else short_k + 25
                r = run_trade(dc, sid, short_k, long_k, st["right"],
                              entry_et, feed, close_px)
                r.update(date=d, policy=policy, wait_day=wait_day)
                rows.append(r)
        print(f"{d} done (wait_day={wait_day})", flush=True)

    df = pd.DataFrame(rows)
    out = OUT / f"august_rerun_v2_{STAMP}.csv"
    df.to_csv(out, index=False)
    print(f"\nsaved -> {out}")

    tr = df[df["exit_kind"] != "SKIP"]
    print("\n===== totals =====")
    for pol in ("eod", "deskwait", "nowait"):
        g = tr[tr["policy"] == pol]
        print(f"{pol:9s}: pnl {g['pnl'].sum():8.0f}  n {len(g):3d}  "
              f"skips {len(df[(df['policy'] == pol) & (df['exit_kind'] == 'SKIP')])}")
    dw = tr[tr["policy"] == "deskwait"]["pnl"].sum()
    nw = tr[tr["policy"] == "nowait"]["pnl"].sum()
    print(f"\nWAIT delta (deskwait - nowait, open streams): {dw - nw:+.0f}")
    print("\nper-stream by policy:")
    print(tr.pivot_table(index="strat", columns="policy", values="pnl",
                         aggfunc="sum").round(0).to_string())


if __name__ == "__main__":
    main()
