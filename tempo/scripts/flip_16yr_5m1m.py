"""flip_16yr_5m1m.py — climax-flip STRUCTURE across 16 years, 5M signal / 1M entry (S119).

User (2026-09-13): run the setup across the ~16 years of ES minute data on a 5M
chart with 1M granularity for entries. The tempo engine needs ticks (only 2021-06+),
so this is a PROXY of the structure, not the tempo indicator:

  CLIMAX PROXY  no tick tempo pre-2021 -> climax = 5M VOLUME >= 95th percentile of
                that time-of-day slot, self-calibrated on the trailing 60 sessions
                (min 30 prior samples, else warmup=no climax). Volume is the time-bar
                analog of tick pace; faithful to the engine's self-calibration method,
                NOT identical to trades/sec.
  SIGNAL        deployed chart rules: two ADJACENT opposite-direction climax 5M bars;
                bar1 = color only (non-doji); SB = IBS 0.55/0.45 + body >= 4 ticks;
                bull->bear = SHORT, bear->bull = LONG.
  ENTRY (1M)    three REALISTIC models, resolved on the 1M bars of the EB (the 5M bar
                after the SB):
                  MKT  market at SB close -> fill at the NEXT 1M open + 1 tick adverse
                  LIM  limit at the SB close -> fill when a 1M bar trades THROUGH it
                       (long: 1M low <= C-1t), fill AT C; unfilled by EB end -> no trade
                  SE   stop 1t beyond the SB extreme in trade dir -> fill when a 1M bar
                       trades through, at SE (gap-through -> at the 1M open)
  STOP/TGT      protective stop 1t beyond the 2-bar 5M box; target RR2 on actual-fill
                risk. Resolved on 1M bars: stop fills at the stop (or the 1M open if it
                gaps through); target is a limit at the target price. Same-1M-bar
                stop+target -> STOP (conservative).
  EXITS@close   SAR reversal / EB scratch / session end -> NEXT 1M open + 1t adverse.
  MGMT          one position; SAR on opposite signal; EB opposite-IBS scratch (cfg);
                skip-open (cfg) = no new entry with SB in first 30 min; EOD flat.

REALISM: no ideal fills anywhere, ever. Every number below is realistic-fill.
PERIODS: PRE 2010-06..2021-06-17 (never seen by any tuning) / TICK 2021-06-18..2026-07-24
/ FULL. Per-setup breakout (Basic / EB Reversal / scratched). Plus per-year for the
best realistic config.

    python tempo/scripts/flip_16yr_5m1m.py
"""
from __future__ import annotations
import datetime as dt
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
SRC = ROOT / "data" / "bars" / "_db_es_1m_continuous_24h.parquet"
OUT = ROOT / "tempo" / "outputs"
TICK = 0.25
RR = 2
MINBODY = 4 * TICK
ADV = TICK
CLIMAX_PCT = 0.95
CAL_WIN = 60
CAL_MIN = 30
PT_USD = 50.0
TICK_ERA = "2021-06-18"

CONFIGS = [
    {"name": "MKT base",     "entry": "MKT", "sar": True, "eb": 0.45, "skipopen": False},
    {"name": "MKT combo",    "entry": "MKT", "sar": True, "eb": None, "skipopen": True},
    {"name": "LIM base",     "entry": "LIM", "sar": True, "eb": 0.45, "skipopen": False},
    {"name": "LIM combo",    "entry": "LIM", "sar": True, "eb": None, "skipopen": True},
    {"name": "SE base",      "entry": "SE",  "sar": True, "eb": 0.45, "skipopen": False},
    {"name": "SE combo",     "entry": "SE",  "sar": True, "eb": None, "skipopen": True},
]


def build_5m():
    df = pd.read_parquet(SRC)
    df["DateTime"] = pd.to_datetime(df["DateTime"])
    t = df["DateTime"].dt.time
    df = df[(t >= dt.time(8, 30)) & (t < dt.time(15, 15))].copy()
    df["date"] = df["DateTime"].dt.date.astype(str)
    df["smin"] = (df["DateTime"] - df["DateTime"].dt.normalize()
                  - pd.Timedelta(hours=8, minutes=30)).dt.total_seconds() / 60.0
    df["slot"] = (df["smin"] // 5).astype(int)
    df = df.sort_values("DateTime").reset_index(drop=True)
    g = df.groupby(["date", "slot"], sort=False)
    b = g.agg(o=("Open", "first"), h=("High", "max"), lo=("Low", "min"),
              c=("Close", "last"), vol=("Volume", "sum")).reset_index()
    b = b.sort_values(["date", "slot"]).reset_index(drop=True)
    # self-calibrated volume climax per slot (trailing 60 sessions, prior only)
    thr = b.sort_values(["slot", "date"]).groupby("slot")["vol"].transform(
        lambda s: s.shift().rolling(CAL_WIN, min_periods=CAL_MIN).quantile(CLIMAX_PCT))
    b["thr"] = thr
    b["climax"] = b["vol"].to_numpy() >= b["thr"].to_numpy()
    b.loc[b["thr"].isna(), "climax"] = False
    return df, b


def ibs_dir(h, l, c, j):
    rg = h[j] - l[j]
    if rg < TICK / 2:
        return 0
    x = (c[j] - l[j]) / rg
    return 1 if x >= 0.55 else (-1 if x <= 0.45 else 0)


def signal(o, h, l, c, cx, j):
    if not (cx[j] and cx[j - 1]):
        return 0
    if abs(c[j - 1] - o[j - 1]) < TICK / 2:
        return 0
    if abs(c[j] - o[j]) < MINBODY - TICK / 2:
        return 0
    d1 = 1 if c[j - 1] >= o[j - 1] else -1
    d2 = ibs_dir(h, l, c, j)
    if d2 == 0 or d1 == d2:
        return 0
    return 1 if d1 == 1 else 2


def eb_wrong(o, h, l, c, cx, j, short, thr):
    if thr is None or cx[j]:
        return False
    rg = h[j] - l[j]
    if rg < TICK / 2:
        return False
    x = (c[j] - l[j]) / rg
    return (x >= 1 - thr) if short else (x <= thr)


def sim_day(five, mins, cfg, audit):
    """five: DataFrame of 5M bars for one day (o,h,lo,c,climax,slot). mins: 1M
    arrays dict o/h/l/c + slot->list of 1M row indices in [start,end).
    audit: dict accumulating forward-time invariant violations."""
    o = five["o"].to_numpy(); h = five["h"].to_numpy()
    l = five["lo"].to_numpy(); c = five["c"].to_numpy()
    cx = five["climax"].to_numpy(); slot = five["slot"].to_numpy()
    n = len(five)
    mo, mh, ml, mc = mins["o"], mins["h"], mins["l"], mins["c"]
    m_of = mins["by5"]                 # dict: 5M bar-row -> list of 1M idx

    def adj(j):                        # bars j-1,j are TIME-adjacent 5M slots
        return slot[j] == slot[j - 1] + 1

    def sig(j):                        # signal only on time-adjacent bars
        return signal(o, h, l, c, cx, j) if (j >= 1 and adj(j)) else 0
    last1 = len(mo) - 1
    date = five["date"].iloc[0]
    trades = []
    pos = None
    for j in range(1, n):
        mem = m_of.get(j, [])
        # ---- manage open position across this 5M bar's 1M bars ----
        if pos is not None:
            sh = pos["short"]; sgn = -1 if sh else 1
            done = False
            # include the fill bar itself (stop-priority = conservative on the failed
            # breakout that pokes the entry then reverses to the stop same minute),
            # but never a pre-fill 1M bar (lookahead)
            scan = [mi for mi in mem if mi >= pos["fill_mi"]] \
                if j == pos["fill5"] else mem
            for mi in scan:
                # stop (gap-through -> fill at 1M open if it opens beyond)
                if (mh[mi] >= pos["st"]) if sh else (ml[mi] <= pos["st"]):
                    px = pos["st"]
                    if (mo[mi] >= pos["st"]) if sh else (mo[mi] <= pos["st"]):
                        px = mo[mi]
                    trades.append({**pos, "res": "stop", "pnl": (px - pos["en"]) * sgn})
                    pos = None; done = True; break
                if (ml[mi] <= pos["tg"]) if sh else (mh[mi] >= pos["tg"]):
                    trades.append({**pos, "res": "target", "pnl": (pos["tg"] - pos["en"]) * sgn})
                    pos = None; done = True; break
            if not done and pos is not None and j == pos["sig_j"] + 1 \
                    and eb_wrong(o, h, l, c, cx, j, pos["short"], cfg["eb"]):
                sgn = -1 if pos["short"] else 1
                nx = min(mem[-1] + 1 if mem else last1, last1)   # first 1M after this bar
                if nx <= pos["fill_mi"]:
                    audit["scr_le_fill"] += 1
                px = mo[nx] - sgn * ADV
                trades.append({**pos, "res": "eb_scr", "pnl": (px - pos["en"]) * sgn})
                pos = None
        # ---- new signal at this 5M bar (time-adjacent only) ----
        s = sig(j)
        if s:
            sig_short = s == 1
            kind = "B"
            blocked = False
            if pos is not None:
                if cfg["sar"] and sig_short != pos["short"]:
                    sgn = -1 if pos["short"] else 1
                    # exit AFTER the signal bar closes: first 1M of the next bar
                    ebm = m_of.get(j + 1, [])
                    xmi = ebm[0] if ebm else min((mem[-1] if mem else last1) + 1, last1)
                    if xmi <= pos["fill_mi"]:
                        audit["rev_le_fill"] += 1
                    px = mo[xmi] - sgn * ADV
                    trades.append({**pos, "res": "rev", "pnl": (px - pos["en"]) * sgn})
                    pos = None; kind = "R"
                else:
                    blocked = True
            # entry needs a TIME-adjacent EB (next 5M slot) to work the order on
            eb_ok = (j + 1 < n) and (slot[j + 1] == slot[j] + 1)
            if not blocked and pos is None and eb_ok \
                    and not (cfg["skipopen"] and slot[j] < 6):
                hi2 = max(h[j - 1], h[j]); lo2 = min(l[j - 1], l[j])
                psl = hi2 + TICK if sig_short else lo2 - TICK
                sb_last = m_of.get(j, [None])[-1]
                eb = m_of.get(j + 1, [])           # EB = next 5M bar's 1M bars
                fill = None; fill_mi = None
                if cfg["entry"] == "MKT":
                    nx = (m_of.get(j, [None])[-1])
                    nx = (nx + 1) if nx is not None else None
                    if nx is not None and nx <= last1:
                        fill = mo[nx] + (ADV if not sig_short else -ADV); fill_mi = nx
                elif cfg["entry"] == "LIM":
                    lim = c[j]
                    for mi in eb:
                        if (ml[mi] <= lim - TICK) if not sig_short else (mh[mi] >= lim + TICK):
                            fill = lim; fill_mi = mi; break
                else:  # SE
                    se = (h[j] + TICK) if not sig_short else (l[j] - TICK)
                    for mi in eb:
                        if (mh[mi] >= se) if not sig_short else (ml[mi] <= se):
                            fill = mo[mi] if ((mo[mi] >= se) if not sig_short else (mo[mi] <= se)) else se
                            fill_mi = mi; break
                if fill is not None and fill_mi is not None:
                    if sb_last is not None and fill_mi <= sb_last:
                        audit["fill_le_sb"] += 1
                    rk = abs(fill - psl)
                    if rk >= TICK:
                        sgn = -1 if sig_short else 1
                        pos = {"date": date, "kind": kind, "short": sig_short, "en": fill,
                               "st": psl, "rk": rk, "tg": fill + sgn * RR * rk,
                               "sig_j": j + 1, "fill5": j + 1, "fill_mi": fill_mi,
                               "sb_last": sb_last}
    if pos is not None:
        sgn = -1 if pos["short"] else 1
        trades.append({**pos, "res": "open", "pnl": (mc[last1] - sgn * ADV - pos["en"]) * sgn})
    return trades


def seg(t):
    if len(t) == 0:
        return {"n": 0, "PF": np.nan, "$/tr": np.nan}
    pnl = t["pnl"]
    gp = pnl[pnl > 0].sum(); gl = -pnl[pnl < 0].sum()
    r = (pnl / t["rk"]).mean() if "rk" in t.columns and (t["rk"] > 0).all() else np.nan
    return {"n": len(t), "PF": round(gp / gl, 2) if gl > 0 else np.inf,
            "$/tr": round(pnl.mean() * PT_USD, 1)}


def main():
    today = dt.date.today().isoformat()
    print("building 5M bars + volume-climax calibration ...", flush=True)
    m1, b5 = build_5m()
    m1by = {d: g.reset_index(drop=True) for d, g in m1.groupby("date", sort=False)}
    b5by = {d: g.reset_index(drop=True) for d, g in b5.groupby("date", sort=False)}
    dates = sorted(b5by)
    print(f"days {len(dates)} ({dates[0]}..{dates[-1]})", flush=True)

    res = {c["name"]: [] for c in CONFIGS}
    audit = {"fill_le_sb": 0, "rev_le_fill": 0, "scr_le_fill": 0}
    for k, d in enumerate(dates):
        five = b5by[d]
        one = m1by[d]
        oh = one["Open"].to_numpy(); hh = one["High"].to_numpy()
        ll = one["Low"].to_numpy(); cc = one["Close"].to_numpy()
        osmin = one["smin"].to_numpy()
        # map each 5M bar-row -> list of 1M row indices (by slot = smin//5)
        by5 = {}
        oneslot = (osmin // 5).astype(int)
        slot_to_row = {int(s): r for r, s in enumerate(five["slot"].to_numpy())}
        for mi, s in enumerate(oneslot):
            r = slot_to_row.get(int(s))
            if r is not None:
                by5.setdefault(r, []).append(mi)
        mins = {"o": oh, "h": hh, "l": ll, "c": cc, "by5": by5}
        o = five["o"].to_numpy(); h = five["h"].to_numpy()
        l = five["lo"].to_numpy(); c = five["c"].to_numpy(); cx = five["climax"].to_numpy()
        if not any(signal(o, h, l, c, cx, j) for j in range(1, len(five))):
            continue
        for cfg in CONFIGS:
            res[cfg["name"]] += sim_day(five, mins, cfg, audit)
        if (k + 1) % 800 == 0:
            print(f"  {k + 1}/{len(dates)} days", flush=True)
    print("FORWARD-TIME INVARIANTS (must all be 0):", audit, flush=True)

    periods = [("PRE 2010-06..2021-06-17", lambda t: t[t["date"] < TICK_ERA]),
               ("TICK 2021-06-18..2026-07", lambda t: t[t["date"] >= TICK_ERA]),
               ("FULL 2010-06..2026-07", lambda t: t)]
    rows = []
    best_trades = None
    for cfg in CONFIGS:
        t = pd.DataFrame(res[cfg["name"]])
        if cfg["name"] == "LIM combo":
            best_trades = t.copy()
        for plabel, sel in periods:
            sub = sel(t)
            pnl = sub["pnl"] if len(sub) else pd.Series([], dtype=float)
            eq = pnl.cumsum()
            dd = (eq - eq.cummax()).min() if len(sub) else 0.0
            al = seg(sub)
            bas = seg(sub[(sub["kind"] == "B") & (sub["res"] != "eb_scr")]) if len(sub) else seg(sub)
            rev = seg(sub[(sub["kind"] == "R") & (sub["res"] != "eb_scr")]) if len(sub) else seg(sub)
            scr = sub[sub["res"] == "eb_scr"] if len(sub) else sub
            risk_pt = round(sub["rk"].mean(), 1) if len(sub) else np.nan
            r_tr = round((sub["pnl"] / sub["rk"]).mean(), 3) if len(sub) else np.nan
            rows.append({"config": cfg["name"], "period": plabel,
                         "n": al["n"], "PF": al["PF"], "$/tr": al["$/tr"],
                         "risk_pt": risk_pt, "R/tr": r_tr,
                         "maxDD_$": round(dd * PT_USD, 0),
                         "bas_n": bas["n"], "bas_PF": bas["PF"], "bas_$": bas["$/tr"],
                         "rev_n": rev["n"], "rev_PF": rev["PF"], "rev_$": rev["$/tr"],
                         "scr_n": len(scr),
                         "scr_$": round(scr["pnl"].mean() * PT_USD, 1) if len(scr) else np.nan})
    out = pd.DataFrame(rows)
    out.to_csv(OUT / f"flip_16yr_5m1m_{today}.csv", index=False)
    for cfg in CONFIGS:
        print(f"\n=== {cfg['name']} ===")
        print(out[out["config"] == cfg["name"]].to_string(index=False))

    if best_trades is not None and len(best_trades):
        bt = best_trades.copy()
        bt["year"] = bt["date"].str[:4]
        yr = bt.groupby("year").apply(
            lambda g: pd.Series({"n": len(g),
                                 "PF": round(g.loc[g.pnl > 0, "pnl"].sum() /
                                             max(1e-9, -g.loc[g.pnl < 0, "pnl"].sum()), 2),
                                 "$/tr": round(g.pnl.mean() * PT_USD, 1)})).reset_index()
        yr.to_csv(OUT / f"flip_16yr_5m1m_peryear_{today}.csv", index=False)
        print("\n=== per-year: LIM combo (realistic) ===")
        print(yr.to_string(index=False))


if __name__ == "__main__":
    main()
