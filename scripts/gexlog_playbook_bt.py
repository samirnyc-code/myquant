"""Backtest: trade ONLY what the GexLog morning playbook says, mechanically.

User request (S116): "read the playbooks, all of them, and sim based on just
that." Uses playbook_rules_<stamp>.csv from gexlog_playbook_parse.py (327/327
scenarios parsed, 2026-04-06..09-10) + the S114-validated TD infrastructure
(1-min parity SPX feed, 1-min NBBO quotes, official-close settlement).

MECHANICAL SPEC (the playbook text is advisory prose; these are the literal
rules used — every interpretive choice is listed):
- Days: parsed playbook days 2026-04-06 .. 2026-09-09 (today excluded).
- Price path: 1-min parity-SPX at round5(prior close), 09:31-16:00 ET.
  Playbook levels are SPX-scale (walls/pivots ARE SPX strikes).
- Triggers (entries allowed 09:31-15:00 ET):
    above:    S >= level      below: S <= level
    reject_at: |S - level| <= 1.5 (touch of the fade level)
    between (neutral IC): enter at 11:00 ET IF no breakout fired yet
  Three variants per day, same quotes:
    touch   = first minute the condition is true
    hold15  = condition true 15 consecutive minutes, enter at minute 15
              (mirrors the text's "clears and holds"; reject_at same as touch)
    cross15 = condition must TRANSITION false->true intraday, then hold 15
              (audit: touch/hold15 fire at the open when the level is already
              exceeded -> deep-ITM debit spreads the text never meant)
  One breakout per day (first of primary/alternative; primary wins ties).
  Neutral IC held even if a breakout fires later (defined risk, no exits).
- Structures (5-pt grid, wings 25 like the desk book):
    bull_call_debit: long rnd5(level), short rnd5(target1|r2|emUpper)
    bear_put_debit:  long rnd5(level), short rnd5(target1|s2|emLower)
    iron_condor:     short P rnd5(lo)/-25 wing, short C rnd5(hi)/+25 wing
    put_credit/call_credit: short rnd5(level), 25-wide
    debit_spread_generic -> call debit if 'above' else put debit; iron_fly skip
- Entry at the trigger minute's NBBO touch: credit = bid(short)-ask(long),
  debit = ask(long)-bid(short). No entry if quotes missing at that minute (+3m
  grace) or net <= 0 for credit / <= 0.05 for debit.
- Exit: NONE intraday ("manage actively" is not quantifiable) — hold to expiry,
  cash-settle at the official close (yahoo_spx cache). $1.63/contract/exec on
  entry legs only (expiry = cash settlement, desk convention).
- Checkpointed: appends to backtest_full/playbook_bt_rows.csv, resume skips
  finished days. Single TD job; ~6-8 quote requests/day.

Outputs: data/options_sim/backtest_full/playbook_bt_rows.csv (both variants)
         + printed summary (by variant / scenario / structure / month).
"""
from __future__ import annotations

import datetime as dt
import sys
import time
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent))
from backtest_full_em_2022 import FEE, OUT, parity_feed, quotes_1m, round5, yahoo_spx

RULES = Path(r"c:\Users\Admin\myquant\data\options_sim\playbook_rules_20260910.csv")
ROWS = OUT / "playbook_bt_rows.csv"
LAST_DAY = "2026-09-09"
ENTRY_CUTOFF = "15:00:00"
NEUTRAL_ET = "11:00:00"


def clamp(x, lo, hi):
    return max(lo, min(hi, x))


class DayQuotes:
    """lazy 1-min NBBO per (strike, right) for one expiry day."""

    def __init__(self, dc):
        self.dc, self.q = dc, {}

    def at(self, strike, right, et):
        key = (strike, right)
        if key not in self.q:
            self.q[key] = quotes_1m(self.dc, strike, right)
            time.sleep(0.15)
        d = self.q[key]
        if d is None:
            return None
        lim = (dt.datetime.strptime(et, "%H:%M:%S") + dt.timedelta(minutes=3)).strftime("%H:%M:%S")
        w = d[(d["t"] >= et) & (d["t"] <= lim)]
        if not len(w):
            return None
        r = w.iloc[0]
        return float(r["bid"]), float(r["ask"])


def _v(x):
    """NaN-safe scalar: pandas NaN is truthy, so `nan or fallback` picks NaN."""
    return None if x is None or pd.isna(x) else float(x)


def legs_for(sc, base):
    """scenario row -> (kind, legs) with legs=[(role,right,long_k,short_k),..].
    kind in {credit, debit}; iron_condor returns two credit verticals."""
    st, tk = sc["structure"], sc["trig_kind"]
    lvl = _v(sc.get("trig_level"))
    t1 = _v(sc.get("target1"))
    if st == "debit_spread_generic":
        st = "bull_call_debit" if tk == "above" else "bear_put_debit"
    if st == "bull_call_debit":
        lo = round5(lvl)
        hi = round5(t1 or _v(base.get("r2")) or _v(base.get("emUpper")) or lvl + 25)
        if hi <= lo:
            hi = lo + 25
        return [("debit", "C", lo, hi)]
    if st == "bear_put_debit":
        hi = round5(lvl)
        lo = round5(t1 or _v(base.get("s2")) or _v(base.get("emLower")) or lvl - 25)
        if lo >= hi:
            lo = hi - 25
        return [("debit", "P", hi, lo)]
    if st == "iron_condor":
        lo = round5(_v(sc.get("trig_lo")) or _v(base.get("putWall")) or 0)
        hi = round5(_v(sc.get("trig_hi")) or _v(base.get("callWall")) or 0)
        if not lo or not hi:
            return []
        return [("credit", "P", lo - 25, lo), ("credit", "C", hi + 25, hi)]
    if st == "put_credit":
        k = round5(lvl or _v(sc.get("trig_lo")) or 0)
        return [("credit", "P", k - 25, k)] if k else []
    if st == "call_credit":
        k = round5(lvl or _v(sc.get("trig_hi")) or 0)
        return [("credit", "C", k + 25, k)] if k else []
    return []  # iron_fly (1 case) etc.


def trigger_minute(feed, sc, variant):
    tk = sc["trig_kind"]
    f = feed[feed["t"] <= ENTRY_CUTOFF]
    if tk == "between":
        return NEUTRAL_ET
    lvl = _v(sc.get("trig_level"))
    if lvl is None:
        return None
    if tk == "reject_at":
        hit = f[(f["S"] - lvl).abs() <= 1.5]
        return hit["t"].iloc[0] if len(hit) else None
    cond = (f["S"] >= lvl) if tk == "above" else (f["S"] <= lvl)
    if variant == "touch":
        hit = f[cond]
        return hit["t"].iloc[0] if len(hit) else None
    run, seen_false = 0, False
    for t, b in zip(f["t"].tolist(), cond.tolist()):
        if not b:
            seen_false = True
        run = run + 1 if b else 0
        if run >= 15 and (variant == "hold15" or seen_false):
            return t
    return None


def price_entry(dq, kind, right, long_k, short_k, et):
    lq = dq.at(long_k, right, et)
    sq = dq.at(short_k, right, et)
    if lq is None or sq is None:
        return None
    if kind == "credit":
        return round(sq[0] - lq[1], 2)
    return round(lq[1] - sq[0], 2)


def settle(kind, right, long_k, short_k, close):
    w = abs(short_k - long_k)
    if kind == "credit":  # short vertical liability
        itm = max(0.0, short_k - close) if right == "P" else max(0.0, close - short_k)
        return clamp(itm, 0.0, w)
    itm = max(0.0, long_k - close) if right == "P" else max(0.0, close - long_k)
    return clamp(itm, 0.0, w)  # long vertical payoff


def run_day(d, rules, spx, variants=("touch", "hold15", "cross15")):
    dc = d.replace("-", "")
    if d not in spx.index:
        return [dict(date=d, note="no spx close")]
    close = spx.loc[d, "close"]
    day = rules[rules["date"] == d]
    base = day.iloc[0].to_dict()
    cur = _v(base.get("current"))
    feed, _ = parity_feed(dc, round5(cur)) if cur else (None, None)
    if feed is None or not len(feed):
        return [dict(date=d, note="no parity feed")]
    dq = DayQuotes(dc)
    out = []
    for variant in variants:
        fired_breakout = None
        entries = []  # (scenario, minute)
        scen_rows = {r["scenario"]: r for _, r in day.iterrows()}
        for name in ("primary", "alternative"):
            sc = scen_rows.get(name)
            if sc is None or sc["trig_kind"] == "between":
                continue
            t = trigger_minute(feed, sc, variant)
            if t and (fired_breakout is None or t < fired_breakout[1]):
                fired_breakout = (name, t)
        if fired_breakout:
            entries.append(fired_breakout)
        neu = next((r for r in scen_rows.values() if r["trig_kind"] == "between"), None)
        if neu is not None and (fired_breakout is None or fired_breakout[1] > NEUTRAL_ET):
            entries.append((neu["scenario"], NEUTRAL_ET))
        for name, et in entries:
            sc = scen_rows[name]
            for kind, right, long_k, short_k in legs_for(sc, base):
                net = price_entry(dq, kind, right, long_k, short_k, et)
                rec = dict(date=d, variant=variant, scenario=name,
                           structure=sc["structure"], trig_kind=sc["trig_kind"],
                           entry_et=et, right=right, long_k=long_k, short_k=short_k,
                           net=net, close=round(close, 2), note="")
                if net is None:
                    rec["note"] = "no quote"
                elif (kind == "credit" and net <= 0) or (kind == "debit" and net <= 0.05):
                    rec["note"] = f"unquotable net {net}"
                else:
                    sv = settle(kind, right, long_k, short_k, close)
                    pnl = (net - sv) * 100 if kind == "credit" else (sv - net) * 100
                    rec.update(exit_val=round(sv, 2), pnl=round(pnl - 2 * FEE, 2))
                out.append(rec)
        if not entries:
            out.append(dict(date=d, variant=variant, note="no trigger fired"))
    return out


def main():
    rules = pd.read_csv(RULES)
    rules = rules[(rules["scenario"] != "NONE") & (rules["date"] <= LAST_DAY)]
    days = sorted(rules["date"].unique())
    all_v = ("touch", "hold15", "cross15")
    done = {}
    if ROWS.exists():
        prev = pd.read_csv(ROWS)
        done = {d: set(g["variant"].dropna()) for d, g in prev.groupby("date")}
    todo = [(d, tuple(v for v in all_v if v not in done.get(d, set())))
            for d in days]
    todo = [(d, vs) for d, vs in todo if vs]
    if len(sys.argv) > 1:                      # optional day cap for smoke tests
        todo = todo[: int(sys.argv[1])]
    print(f"playbook bt: {len(days)} days, {len(todo)} day-runs pending")
    spx = yahoo_spx(start="2026-03-25")
    for i, (d, vs) in enumerate(todo):
        rows = run_day(d, rules, spx, vs)
        pd.DataFrame(rows).to_csv(ROWS, mode="a", header=not ROWS.exists(), index=False)
        got = [r for r in rows if r.get("pnl") is not None]
        print(f"  [{i + 1}/{len(todo)}] {d}: {len(got)} legs "
              f"{sum(r['pnl'] for r in got):+.0f}", flush=True)
    # ---- summary ----
    r = pd.read_csv(ROWS)
    r = r[r["pnl"].notna()]
    print(f"\n=== PLAYBOOK-ONLY BACKTEST ({r['date'].min()}..{r['date'].max()}) ===")
    for v, g in r.groupby("variant"):
        gd = g.groupby("date")["pnl"].sum()
        print(f"\nvariant {v}: days {gd.size}  total {gd.sum():+,.0f}  "
              f"avg/day {gd.mean():+,.0f}  win% {100 * (gd > 0).mean():.0f}  "
              f"worst {gd.min():+,.0f}")
        print(g.groupby("scenario")["pnl"].agg(["count", "sum"]).to_string())
        print(g.groupby("structure")["pnl"].agg(["count", "sum"]).to_string())
        print(gd.groupby(gd.index.str[:7]).sum().to_string())


if __name__ == "__main__":
    main()
