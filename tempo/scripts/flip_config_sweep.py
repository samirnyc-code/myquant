"""flip_config_sweep.py — user-requested config sweep on TICK data (S119, 2026-09-13).

Dimensions (user): entry SE vs CLOSE · SE order life · EB-scratch IBS threshold ·
time-of-day filters (open 30min / lunch / EOD) · always broken out per setup.

Engine: tick-precise via tickdata.load_rth (canonical RTH trove), standard
stop-order fill model for the SE (trigger at first print AT the SE, fill AT the
SE); stops fill at the triggering print (gap-through included); targets at limit.
Base rules = deployed chart: both bars climax, bar1 color non-doji, SB IBS
0.55/0.45 + body >= 4t, SAR, RR2, EB on the bar after the SB (signal-referenced),
one position, session end -> last full bar close.

PERIODS (every table row is labeled): IS 2021-06-18..2022-12-31,
OOS 2023-01-01..2026-09-10, FULL = both.

CONFIG ARMS (20):
  A entry/life : CLOSE · SE life 1 / 2 / 3            (EB 0.45, all hours)
  B EB thr     : {CLOSE, SE1} x EB {off, 0.35, 0.40, 0.50}   (0.45 lives in A)
  C TOD skips  : {CLOSE, SE1} x {open<09:00, lunch 11:30-13:00, EOD>=14:30, all3}
TOD skip = no NEW entry whose SIGNAL bar starts in the window (exits unaffected,
SAR exit happens but no re-entry).

Per-setup breakout in every row: ALL / Basic (from flat) / EB Reversal (SAR
entry) / scratched (res=eb_scr).

    python tempo/scripts/flip_config_sweep.py
"""
from __future__ import annotations
import datetime as dt
import sys
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
import tickdata  # noqa: E402  (canonical tick access)

ENG = ROOT / "tempo" / "outputs" / "tempo_engine_bars.parquet"
OUT = ROOT / "tempo" / "outputs"
TICK = 0.25
SIZE = 2000
RR = 2
MINBODY = 4 * TICK
CUTOFF = "2026-09-11"
IS_END = "2022-12-31"
PT_USD = 50.0
EPS = 1e-9

CONFIGS = []
for name, entry, life, eb, skips in [
    ("A CLOSE",            "CLOSE", 0, 0.45, ()),
    ("A SE life1",         "SE",    1, 0.45, ()),
    ("A SE life2",         "SE",    2, 0.45, ()),
    ("A SE life3",         "SE",    3, 0.45, ()),
    ("B CLOSE ebOFF",      "CLOSE", 0, None, ()),
    ("B CLOSE eb0.35",     "CLOSE", 0, 0.35, ()),
    ("B CLOSE eb0.40",     "CLOSE", 0, 0.40, ()),
    ("B CLOSE eb0.50",     "CLOSE", 0, 0.50, ()),
    ("B SE1 ebOFF",        "SE",    1, None, ()),
    ("B SE1 eb0.35",       "SE",    1, 0.35, ()),
    ("B SE1 eb0.40",       "SE",    1, 0.40, ()),
    ("B SE1 eb0.50",       "SE",    1, 0.50, ()),
    ("C CLOSE skipOpen",   "CLOSE", 0, 0.45, ("open",)),
    ("C CLOSE skipLunch",  "CLOSE", 0, 0.45, ("lunch",)),
    ("C CLOSE skipEOD",    "CLOSE", 0, 0.45, ("eod",)),
    ("C CLOSE skipAll3",   "CLOSE", 0, 0.45, ("open", "lunch", "eod")),
    ("C SE1 skipOpen",     "SE",    1, 0.45, ("open",)),
    ("C SE1 skipLunch",    "SE",    1, 0.45, ("lunch",)),
    ("C SE1 skipEOD",      "SE",    1, 0.45, ("eod",)),
    ("C SE1 skipAll3",     "SE",    1, 0.45, ("open", "lunch", "eod")),
]:
    CONFIGS.append({"name": name, "entry": entry, "life": life, "eb": eb,
                    "skips": frozenset(skips)})

# --combos: second pass over the winning combinations (A/B/C varied one at a time)
CONFIGS_D = [
    {"name": "D CLOSE skipOpen ebOFF",  "entry": "CLOSE", "life": 0, "eb": None, "skips": frozenset(("open",))},
    {"name": "D CLOSE skipOpen eb0.35", "entry": "CLOSE", "life": 0, "eb": 0.35, "skips": frozenset(("open",))},
    {"name": "D SE1 skipOpen ebOFF",    "entry": "SE",    "life": 1, "eb": None, "skips": frozenset(("open",))},
    {"name": "D SE1 skipOpen eb0.35",   "entry": "SE",    "life": 1, "eb": 0.35, "skips": frozenset(("open",))},
]
RUN_TAG = ""
if "--combos" in sys.argv:
    CONFIGS = CONFIGS_D
    RUN_TAG = "_combos"


def ibs(h, l, c, j):
    rg = h[j] - l[j]
    return (c[j] - l[j]) / rg if rg > TICK / 2 else 0.5


def sig_dir(h, l, c, o, cx, j):
    if not (cx[j] and cx[j - 1]):
        return 0
    if abs(c[j - 1] - o[j - 1]) < TICK / 2:
        return 0
    if abs(c[j] - o[j]) < MINBODY - TICK / 2:
        return 0
    d1 = 1 if c[j - 1] >= o[j - 1] else -1
    x = ibs(h, l, c, j)
    d2 = 1 if x >= 0.55 else (-1 if x <= 0.45 else 0)
    if d2 == 0 or d1 == d2:
        return 0
    return 1 if d1 == 1 else 2


def in_window(smin, skips):
    if "open" in skips and smin < 30:
        return True
    if "lunch" in skips and 180 <= smin < 270:
        return True
    if "eod" in skips and smin >= 360:
        return True
    return False


def eb_wrong(h, l, c, cx, j, short, thr):
    if thr is None or cx[j]:
        return False
    x = ibs(h, l, c, j)
    return (x >= 1 - thr) if short else (x <= thr)


def fidx(mask):
    return int(np.argmax(mask)) if mask.any() else -1


def sim_day(g, P, cfg):
    bar = g["bar"].to_numpy(int)
    h = g["high"].to_numpy(); l = g["low"].to_numpy()
    o = g["open"].to_numpy(); c = g["close"].to_numpy()
    cx = g["climax"].to_numpy()
    sm = g["session_min"].to_numpy()
    n = len(g)
    date = g["date"].iloc[0]
    trades = []
    pos = None
    pend = None
    for j in range(1, n):
        B = bar[j]
        T = P[B * SIZE:(B + 1) * SIZE]
        i0 = 0
        while len(T) and i0 < len(T):
            if pos is not None:
                sh = pos["short"]; sgn = -1 if sh else 1
                s_i = fidx((T[i0:] >= pos["st"] - EPS) if sh else (T[i0:] <= pos["st"] + EPS))
                t_i = fidx((T[i0:] <= pos["tg"] + EPS) if sh else (T[i0:] >= pos["tg"] - EPS))
                if s_i < 0 and t_i < 0:
                    break
                if t_i < 0 or (0 <= s_i <= t_i):
                    px = T[i0 + s_i]
                    trades.append({**pos, "res": "stop", "pnl": (px - pos["en"]) * sgn})
                else:
                    trades.append({**pos, "res": "target", "pnl": (pos["tg"] - pos["en"]) * sgn})
                pos = None; break
            elif pend is not None:
                sh = pend["short"]
                tr_i = fidx((T[i0:] <= pend["se"] + EPS) if sh else (T[i0:] >= pend["se"] - EPS))
                iv_i = fidx((T[i0:] >= pend["psl"] - EPS) if sh else (T[i0:] <= pend["psl"] + EPS))
                if tr_i < 0 and iv_i < 0:
                    break
                if tr_i < 0 or (0 <= iv_i < tr_i):
                    trades.append({"date": date, "kind": pend["kind"], "short": sh,
                                   "en": np.nan, "rk": np.nan, "res": "canc", "pnl": 0.0})
                    pend = None; continue
                en = pend["se"]; st = pend["psl"]; rk = abs(en - st)
                sgn = -1 if sh else 1
                pos = {"date": date, "kind": pend["kind"], "short": sh, "en": en, "st": st,
                       "rk": rk, "tg": en + sgn * RR * rk, "sig_j": pend["sig_j"]}
                pend = None
                i0 = i0 + tr_i + 1
                continue
            else:
                break
        # bar close
        if pend is not None and j == pend["sig_j"] + max(1, cfg["life"]):
            wrong = eb_wrong(h, l, c, cx, pend["sig_j"] + 1, pend["short"], cfg["eb"]) \
                if j == pend["sig_j"] + 1 else False
            trades.append({"date": date, "kind": pend["kind"], "short": pend["short"],
                           "en": np.nan, "rk": np.nan,
                           "res": "eb_canc" if wrong else "nofill", "pnl": 0.0})
            pend = None
        elif pend is not None and j == pend["sig_j"] + 1 \
                and eb_wrong(h, l, c, cx, j, pend["short"], cfg["eb"]):
            trades.append({"date": date, "kind": pend["kind"], "short": pend["short"],
                           "en": np.nan, "rk": np.nan, "res": "eb_canc", "pnl": 0.0})
            pend = None
        if pos is not None and j == pos["sig_j"] + 1 \
                and eb_wrong(h, l, c, cx, j, pos["short"], cfg["eb"]):
            sgn = -1 if pos["short"] else 1
            trades.append({**pos, "res": "eb_scr", "pnl": (c[j] - pos["en"]) * sgn})
            pos = None
        s = sig_dir(h, l, c, o, cx, j)
        if s:
            sig_short = s == 1
            kind = "B"
            blocked = False
            if pos is not None:
                if sig_short != pos["short"]:
                    sgn = -1 if pos["short"] else 1
                    trades.append({**pos, "res": "rev", "pnl": (c[j] - pos["en"]) * sgn})
                    pos = None; kind = "R"
                else:
                    blocked = True
            if not blocked and pos is None and not in_window(sm[j], cfg["skips"]):
                if pend is not None:
                    trades.append({"date": date, "kind": pend["kind"], "short": pend["short"],
                                   "en": np.nan, "rk": np.nan, "res": "nofill", "pnl": 0.0})
                    pend = None
                hi2, lo2 = max(h[j - 1], h[j]), min(l[j - 1], l[j])
                psl = hi2 + TICK if sig_short else lo2 - TICK
                if cfg["entry"] == "SE":
                    se = (l[j] - TICK) if sig_short else (h[j] + TICK)
                    if abs(se - psl) >= TICK:
                        pend = {"kind": kind, "short": sig_short, "se": se, "psl": psl, "sig_j": j}
                else:
                    en = c[j]; rk = abs(en - psl)
                    if rk >= TICK:
                        sgn = -1 if sig_short else 1
                        pos = {"date": date, "kind": kind, "short": sig_short, "en": en,
                               "st": psl, "rk": rk, "tg": en + sgn * RR * rk, "sig_j": j}
    if pos is not None:
        sgn = -1 if pos["short"] else 1
        trades.append({**pos, "res": "open", "pnl": (c[n - 1] - pos["en"]) * sgn})
    if pend is not None:
        trades.append({"date": date, "kind": pend["kind"], "short": pend["short"],
                       "en": np.nan, "rk": np.nan, "res": "nofill", "pnl": 0.0})
    return trades


def seg(t):
    f = t[~t["res"].isin(["canc", "nofill", "eb_canc"])]
    if len(f) == 0:
        return {"n": 0, "PF": np.nan, "$/tr": np.nan}
    pnl = f["pnl"]
    gp = pnl[pnl > 0].sum(); gl = -pnl[pnl < 0].sum()
    return {"n": len(f), "PF": round(gp / gl, 2) if gl > 0 else np.inf,
            "$/tr": round(pnl.mean() * PT_USD, 1)}


def main():
    today = dt.date.today().isoformat()
    df = pd.read_parquet(ENG)
    df = df[(df["state"] >= 0) & (df["date"] <= CUTOFF)] \
        .sort_values(["date", "bar"]).reset_index(drop=True)
    byday = {d: g.reset_index(drop=True) for d, g in df.groupby("date")}
    dates = [d for d in sorted(byday) if d in set(tickdata.available("rth"))]
    print(f"days {len(dates)} ({dates[0]}..{dates[-1]})  configs {len(CONFIGS)}")

    res = {cfg["name"]: [] for cfg in CONFIGS}
    for k, d in enumerate(dates):
        g = byday[d]
        h = g["high"].to_numpy(); l = g["low"].to_numpy()
        o = g["open"].to_numpy(); c = g["close"].to_numpy()
        cx = g["climax"].to_numpy()
        if not any(sig_dir(h, l, c, o, cx, j) for j in range(1, len(g))):
            continue
        P = tickdata.load_rth(d)["Price"].to_numpy(np.float64)
        for cfg in CONFIGS:
            res[cfg["name"]] += sim_day(g, P, cfg)
        if (k + 1) % 200 == 0:
            print(f"  {k + 1}/{len(dates)} days", flush=True)

    periods = [("IS 21-06-18..22-12-31", lambda t: t[t["date"] <= IS_END]),
               ("OOS 23-01-01..26-09-10", lambda t: t[t["date"] > IS_END]),
               ("FULL 21-06-18..26-09-10", lambda t: t)]
    rows = []
    alltr = []
    for cfg in CONFIGS:
        t = pd.DataFrame(res[cfg["name"]])
        t["config"] = cfg["name"]
        alltr.append(t)
        f = t[~t["res"].isin(["canc", "nofill", "eb_canc"])]
        for plabel, sel in periods:
            sub = sel(t)
            fsub = sel(f)
            pnl = fsub["pnl"]
            eq = pnl.cumsum()
            dd = (eq - eq.cummax()).min() if len(fsub) else 0.0
            a = seg(sub)
            bas = seg(sub[(sub["kind"] == "B") & (sub["res"] != "eb_scr")])
            rev = seg(sub[(sub["kind"] == "R") & (sub["res"] != "eb_scr")])
            scr = sub[sub["res"] == "eb_scr"]
            rows.append({"config": cfg["name"], "period": plabel,
                         "n": a["n"], "PF": a["PF"], "$/tr": a["$/tr"],
                         "maxDD_$": round(dd * PT_USD, 0),
                         "bas_n": bas["n"], "bas_PF": bas["PF"], "bas_$": bas["$/tr"],
                         "rev_n": rev["n"], "rev_PF": rev["PF"], "rev_$": rev["$/tr"],
                         "scr_n": len(scr),
                         "scr_$": round(scr["pnl"].mean() * PT_USD, 1) if len(scr) else np.nan})
    out = pd.DataFrame(rows)
    out.to_csv(OUT / f"flip_config_sweep{RUN_TAG}_{today}.csv", index=False)
    pd.concat(alltr, ignore_index=True).to_csv(
        OUT / f"flip_config_sweep_trades{RUN_TAG}_{today}.csv", index=False)
    for arm in sorted(set(cfg["name"][0] for cfg in CONFIGS)):
        print(f"\n=== {arm} ===")
        print(out[out["config"].str.startswith(arm)].to_string(index=False))


if __name__ == "__main__":
    main()
