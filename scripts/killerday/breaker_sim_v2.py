"""STAGE-2 realized-loss circuit breaker on the v2 full-history book (event-
driven, exact — no minute-level book marking needed).

Mechanic per day per book: book each realized exit at its actual time (stops at
their detected parity-feed trigger time, 14:45CT time-exits at 15:45 ET, settles
at the close). When cumulative realized day P&L hits -X: close EVERY still-open
position at the TD touch at that minute (at_time quotes), skip entries not yet
made, stand down rest of day. This is a breaker the live daemon could implement
verbatim (it keys on booked losses, not marks).

Levels: -1000 / -1500 / -2000 / -3000. Books: ic (4 condor streams), puts_band
(eodic_p+openic_p, credit 0.5-2.5), combined (all 8 incl fly, for reference).
Data: rows_v2.csv (eod + calwait policies) + parity feeds + TD touch at breach.
Fallback when a breach-close quote is missing: settle intrinsic (counted).

Output: breaker_v2_results_<stamp>.csv (per level x book: total/train/test
delta, killer-day table) + breaker_v2_days_<stamp>.csv (per-day deltas).
"""
import datetime as dt
import sys
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from backtest_full_em_2022 import FEE, parity_feed, touch, detect_stop, yahoo_spx

ROOT = Path(__file__).resolve().parents[2]
BT = ROOT / "data" / "options_sim" / "backtest_full"
STAMP = dt.date.today().strftime("%Y%m%d")
LEVELS = [1000, 1500, 2000, 3000]
BOOKS = {
    "ic": lambda e: "ic" in e["strat"],
    "puts_band": lambda e: e["strat"] in ("eodic_p", "openic_p")
                           and 0.5 <= e["credit"] <= 2.5,
    "combined": lambda e: True,
}


def round5(x):
    return round(x / 5.0) * 5.0


def right_of(strat):
    return "P" if strat.endswith("_p") else "C"


def main():
    rows = pd.read_csv(BT / "rows_v2.csv")
    rows = rows[rows["policy"].isin(["eod", "calwait"])
                & rows["exit_kind"].isin(["stop", "settle", "time"])].copy()
    spx = yahoo_spx()

    day_events = {}   # date -> list of event dicts (all 8 streams)
    days = sorted(rows["date"].unique())
    print(f"{len(days)} days", flush=True)

    for i, d in enumerate(days):
        dc = d.replace("-", "")
        if d not in spx.index:
            continue
        feed, _ = parity_feed(dc, round5(float(spx.loc[d, "open"])))
        evs = []
        for _, r in rows[rows["date"] == d].iterrows():
            right = right_of(r["strat"])
            if r["exit_kind"] == "stop":
                t = detect_stop(feed, r["short_k"], right, r["entry_et"]) or "15:45:00"
            elif r["exit_kind"] == "time":
                t = "15:45:00"
            else:
                t = "16:00:00"
            evs.append(dict(strat=r["strat"], entry_et=r["entry_et"],
                            short_k=r["short_k"], long_k=r["long_k"],
                            right=right, credit=r["credit"], exit_t=t,
                            pnl=r["pnl"], dc=dc))
        day_events[d] = sorted(evs, key=lambda e: e["exit_t"])
        if (i + 1) % 100 == 0:
            print(f"  timeline {i+1}/{len(days)}", flush=True)

    close_cache = {}

    def close_cost(e, t):
        key = (e["dc"], e["short_k"], e["long_k"], e["right"], t)
        if key not in close_cache:
            close_cache[key] = touch(e["dc"], e["short_k"], e["long_k"],
                                     e["right"], t, closing=True)
        return close_cache[key]

    out_days, out_sum = [], []
    for book, mask_fn in BOOKS.items():
        for level in LEVELS:
            nonlocal_fb = 0
            for d, evs in day_events.items():
                bevs = [e for e in evs if mask_fn(e)]
                if not bevs:
                    continue
                base = sum(e["pnl"] for e in bevs)
                cum, sim, breached, bt_time = 0.0, 0.0, False, None
                for e in bevs:
                    if breached:
                        if e["entry_et"] >= bt_time:
                            continue          # entry never happened
                        c = close_cost(e, bt_time)
                        if c is None:
                            nonlocal_fb += 1
                            continue
                        sim += (e["credit"] - c) * 100 - 4 * FEE
                        continue
                    cum += e["pnl"]
                    sim += e["pnl"]
                    if cum <= -level and e["exit_t"] < "16:00:00":
                        breached, bt_time = True, e["exit_t"]
                if breached:
                    out_days.append(dict(book=book, level=level, date=d,
                                         base=round(base), sim=round(sim),
                                         delta=round(sim - base),
                                         breach_t=bt_time))
            dd = [x for x in out_days if x["book"] == book and x["level"] == level]
            df = pd.DataFrame(dd) if dd else pd.DataFrame(columns=["date", "delta", "base", "sim"])
            tr = df[df["date"] < "2025-01-01"]["delta"].sum() if len(df) else 0
            te = df[df["date"] >= "2025-01-01"]["delta"].sum() if len(df) else 0
            killers = df[df["base"] <= -1500] if len(df) else df
            out_sum.append(dict(book=book, level=-level, breach_days=len(df),
                                total_delta=round(df["delta"].sum()) if len(df) else 0,
                                train_delta=round(tr), test_delta=round(te),
                                killer_days_hit=len(killers),
                                killer_delta=round(killers["delta"].sum()) if len(killers) else 0,
                                quote_fallbacks=nonlocal_fb))
            print(f"{book} -{level}: done ({len(df)} breach days)", flush=True)

    pd.DataFrame(out_days).to_csv(BT / f"killerday/breaker_v2_days_{STAMP}.csv", index=False)
    s = pd.DataFrame(out_sum)
    s.to_csv(BT / f"killerday/breaker_v2_results_{STAMP}.csv", index=False)
    print(s.to_string(index=False))


if __name__ == "__main__":
    main()
