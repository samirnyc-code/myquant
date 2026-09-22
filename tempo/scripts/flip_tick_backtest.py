"""flip_tick_backtest.py — TICK-PRECISE flip backtest, RTH trove, through 2026-09-11 (S119).

User: we have the tick data — use it. This replays every trade on the actual RTH
tick stream (data/ticks_continuous/<date>.parquet, Panama-adjusted, the SAME ticks
the 2000t bars are built from; bar b = ticks [b*2000,(b+1)*2000) in file order).

SPEC = the deployed chart config (2026-09-13):
  signals   both bars climax; bar1 = color, non-doji; SB = IBS band 0.55/0.45 AND
            body >= 4 ticks; one position; SAR on opposite signal (exit @ signal
            bar close); session end -> exit @ last full bar close
  SE arm    stop entry 1t beyond SB extreme; pending life = 1 bar (works only
            during the bar after the SB); invalidated if the stop side prints
            first; EB-ON: bar after SB closes wrong-IBS non-climax -> scratch @
            close if filled / order pulled if not
  CLOSE arm reference: enter at SB close; EB scratch on the bar after the SB
  target    RR2 on actual risk (|fill - stop|); protective stop 1t beyond box

FILLS (the tick-precise part):
  SE trigger  = first tick STRICTLY beyond SE; filled AT THAT PRINT (gap slippage in)
  stop        = first tick at/beyond the stop; filled AT THAT PRINT (gap-through in)
  target      = limit: first tick at/beyond target, filled AT the target price
  bar-close exits (EB scratch / SAR / session end) at the bar's last tick
  Tick order resolves every ambiguity the OHLC engine had to call conservatively.

A bar-OHLC twin of the SAME spec (fills at exact SE / stop / touch, both-in-bar ->
stop) runs alongside: the tick-vs-bar delta is the value of the tick data.
Days without a tick file are skipped in BOTH engines (count reported).

    python tempo/scripts/flip_tick_backtest.py
"""
from __future__ import annotations
import datetime as dt
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
ENG = ROOT / "tempo" / "outputs" / "tempo_engine_bars.parquet"
TROVE = ROOT / "data" / "ticks_continuous"
OUT = ROOT / "tempo" / "outputs"
TICK = 0.25
SIZE = 2000
RR = 2
LIFE = 1
MINBODY = 4 * TICK
CUTOFF = "2026-09-11"
PT_USD = 50.0
EPS = 1e-9


def ibs_dir(h, l, c, j):
    rg = h[j] - l[j]
    if rg < TICK / 2:
        return 0
    x = (c[j] - l[j]) / rg
    return 1 if x >= 0.55 else (-1 if x <= 0.45 else 0)


def signal(h, l, o, c, cx, j):
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


def fidx(mask):
    return int(np.argmax(mask)) if mask.any() else -1


def sim_day_tick(g, P, arm, fillmode="thru"):
    """fillmode for the SE arm: 'thru'  = trigger on first print STRICTLY beyond SE,
    fill AT that print (worst case); 'touch' = trigger on first print AT the SE,
    fill AT the SE (standard stop-order model). Slippage vs SE recorded per fill."""
    bar = g["bar"].to_numpy(int)
    h = g["high"].to_numpy(); l = g["low"].to_numpy()
    o = g["open"].to_numpy(); c = g["close"].to_numpy()
    cx = g["climax"].to_numpy()
    n = len(g)
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
                    pos = None; break
                trades.append({**pos, "res": "target", "pnl": (pos["tg"] - pos["en"]) * sgn})
                pos = None; break
            elif pend is not None:
                sh = pend["short"]
                off = TICK if fillmode == "thru" else 0.0
                tr_i = fidx((T[i0:] <= pend["se"] - off + EPS) if sh
                            else (T[i0:] >= pend["se"] + off - EPS))
                iv_i = fidx((T[i0:] >= pend["psl"] - EPS) if sh else (T[i0:] <= pend["psl"] + EPS))
                if tr_i < 0 and iv_i < 0:
                    break
                if tr_i < 0 or (0 <= iv_i < tr_i):
                    trades.append({"date": pend["date"], "short": sh, "en": np.nan, "rk": np.nan,
                                   "res": "canc", "pnl": 0.0, "sig_j": pend["sig_j"]})
                    pend = None; continue
                px = T[i0 + tr_i] if fillmode == "thru" else pend["se"]
                slip = abs(px - pend["se"])
                en = px; st = pend["psl"]; rk = abs(en - st)
                sgn = -1 if sh else 1
                pos = {"date": pend["date"], "short": sh, "en": en, "st": st, "rk": rk,
                       "tg": en + sgn * RR * rk, "sig_j": pend["sig_j"], "slip": slip}
                pend = None
                i0 = i0 + tr_i + 1
                continue
            else:
                break
        # ---- bar close ----
        if pend is not None and j == pend["sig_j"] + LIFE:
            d = ibs_dir(h, l, c, j)
            sh = pend["short"]
            ebw = (not cx[j]) and ((not sh and d == -1) or (sh and d == 1))
            trades.append({"date": pend["date"], "short": sh, "en": np.nan, "rk": np.nan,
                           "res": "eb_canc" if ebw else "nofill", "pnl": 0.0,
                           "sig_j": pend["sig_j"]})
            pend = None
        if pos is not None and j == pos["sig_j"] + 1:
            d = ibs_dir(h, l, c, j)
            sh = pos["short"]
            if (not cx[j]) and ((not sh and d == -1) or (sh and d == 1)):
                sgn = -1 if sh else 1
                trades.append({**pos, "res": "eb_scr", "pnl": (c[j] - pos["en"]) * sgn})
                pos = None
        s = signal(h, l, o, c, cx, j)
        if s:
            sig_short = s == 1
            blocked = False
            if pos is not None:
                if sig_short != pos["short"]:
                    sgn = -1 if pos["short"] else 1
                    trades.append({**pos, "res": "rev", "pnl": (c[j] - pos["en"]) * sgn})
                    pos = None
                else:
                    blocked = True
            if not blocked and pos is None:
                if pend is not None:
                    trades.append({"date": pend["date"], "short": pend["short"], "en": np.nan,
                                   "rk": np.nan, "res": "nofill", "pnl": 0.0,
                                   "sig_j": pend["sig_j"]})
                    pend = None
                hi2, lo2 = max(h[j - 1], h[j]), min(l[j - 1], l[j])
                psl = hi2 + TICK if sig_short else lo2 - TICK
                if arm == "SE":
                    se = (l[j] - TICK) if sig_short else (h[j] + TICK)
                    if abs(se - psl) >= TICK:
                        pend = {"date": g["date"].iloc[0], "short": sig_short, "se": se,
                                "psl": psl, "sig_j": j}
                else:
                    en = c[j]; rk = abs(en - psl)
                    if rk >= TICK:
                        sgn = -1 if sig_short else 1
                        pos = {"date": g["date"].iloc[0], "short": sig_short, "en": en,
                               "st": psl, "rk": rk, "tg": en + sgn * RR * rk, "sig_j": j}
    if pos is not None:
        sgn = -1 if pos["short"] else 1
        trades.append({**pos, "res": "open", "pnl": (c[n - 1] - pos["en"]) * sgn})
    if pend is not None:
        trades.append({"date": pend["date"], "short": pend["short"], "en": np.nan, "rk": np.nan,
                       "res": "nofill", "pnl": 0.0, "sig_j": pend["sig_j"]})
    return trades


def sim_day_ohlc(g, arm):
    """same spec, bar OHLC, conservative (exact-SE/stop fills, touch, both-in-bar -> stop)"""
    bar = g["bar"].to_numpy(int)  # noqa: F841  (kept for parity)
    h = g["high"].to_numpy(); l = g["low"].to_numpy()
    o = g["open"].to_numpy(); c = g["close"].to_numpy()
    cx = g["climax"].to_numpy()
    n = len(g)
    trades = []
    pos = None
    pend = None
    for j in range(1, n):
        if pos is not None:
            sh = pos["short"]; sgn = -1 if sh else 1
            if (h[j] >= pos["st"]) if sh else (l[j] <= pos["st"]):
                trades.append({**pos, "res": "stop", "pnl": -pos["rk"]}); pos = None
            elif (l[j] <= pos["tg"]) if sh else (h[j] >= pos["tg"]):
                trades.append({**pos, "res": "target", "pnl": RR * pos["rk"]}); pos = None
        elif pend is not None:
            sh = pend["short"]
            inval = (h[j] >= pend["psl"]) if sh else (l[j] <= pend["psl"])
            trig = (l[j] <= pend["se"] - TICK) if sh else (h[j] >= pend["se"] + TICK)
            if trig:
                en = pend["se"]; st = pend["psl"]; rk = abs(en - st)
                sgn = -1 if sh else 1
                pos = {"date": pend["date"], "short": sh, "en": en, "st": st, "rk": rk,
                       "tg": en + sgn * RR * rk, "sig_j": pend["sig_j"]}
                pend = None
                if inval:
                    trades.append({**pos, "res": "stop", "pnl": -rk}); pos = None
                elif (l[j] <= pos["tg"]) if sh else (h[j] >= pos["tg"]):
                    trades.append({**pos, "res": "target", "pnl": RR * rk}); pos = None
            elif inval:
                trades.append({"date": pend["date"], "short": sh, "en": np.nan, "rk": np.nan,
                               "res": "canc", "pnl": 0.0, "sig_j": pend["sig_j"]})
                pend = None
        if pend is not None and j == pend["sig_j"] + LIFE:
            d = ibs_dir(h, l, c, j)
            sh = pend["short"]
            ebw = (not cx[j]) and ((not sh and d == -1) or (sh and d == 1))
            trades.append({"date": pend["date"], "short": sh, "en": np.nan, "rk": np.nan,
                           "res": "eb_canc" if ebw else "nofill", "pnl": 0.0,
                           "sig_j": pend["sig_j"]})
            pend = None
        if pos is not None and j == pos["sig_j"] + 1:
            d = ibs_dir(h, l, c, j)
            sh = pos["short"]
            if (not cx[j]) and ((not sh and d == -1) or (sh and d == 1)):
                sgn = -1 if sh else 1
                trades.append({**pos, "res": "eb_scr", "pnl": (c[j] - pos["en"]) * sgn})
                pos = None
        s = signal(h, l, o, c, cx, j)
        if s:
            sig_short = s == 1
            blocked = False
            if pos is not None:
                if sig_short != pos["short"]:
                    sgn = -1 if pos["short"] else 1
                    trades.append({**pos, "res": "rev", "pnl": (c[j] - pos["en"]) * sgn})
                    pos = None
                else:
                    blocked = True
            if not blocked and pos is None:
                if pend is not None:
                    trades.append({"date": pend["date"], "short": pend["short"], "en": np.nan,
                                   "rk": np.nan, "res": "nofill", "pnl": 0.0,
                                   "sig_j": pend["sig_j"]})
                    pend = None
                hi2, lo2 = max(h[j - 1], h[j]), min(l[j - 1], l[j])
                psl = hi2 + TICK if sig_short else lo2 - TICK
                if arm == "SE":
                    se = (l[j] - TICK) if sig_short else (h[j] + TICK)
                    if abs(se - psl) >= TICK:
                        pend = {"date": g["date"].iloc[0], "short": sig_short, "se": se,
                                "psl": psl, "sig_j": j}
                else:
                    en = c[j]; rk = abs(en - psl)
                    if rk >= TICK:
                        sgn = -1 if sig_short else 1
                        pos = {"date": g["date"].iloc[0], "short": sig_short, "en": en,
                               "st": psl, "rk": rk, "tg": en + sgn * RR * rk, "sig_j": j}
    if pos is not None:
        sgn = -1 if pos["short"] else 1
        trades.append({**pos, "res": "open", "pnl": (c[n - 1] - pos["en"]) * sgn})
    if pend is not None:
        trades.append({"date": pend["date"], "short": pend["short"], "en": np.nan, "rk": np.nan,
                       "res": "nofill", "pnl": 0.0, "sig_j": pend["sig_j"]})
    return trades


def stats(t, label):
    f = t[~t["res"].isin(["canc", "nofill", "eb_canc"])]
    unf = len(t) - len(f)
    if len(f) == 0:
        return {"row": label, "fills": 0, "unfilled": unf}
    pnl = f["pnl"]
    eq = pnl.cumsum()
    dd = (eq - eq.cummax()).min()
    gp = pnl[pnl > 0].sum(); gl = -pnl[pnl < 0].sum()
    return {"row": label, "fills": len(f), "unfilled": unf,
            "win%": round(100 * (pnl > 0).mean(), 1),
            "PF": round(gp / gl, 2) if gl > 0 else np.inf,
            "avg_risk": round(f["rk"].mean(), 2),
            "tot_pts": round(pnl.sum(), 1),
            "$/trade": round(pnl.mean() * PT_USD, 1),
            "maxDD_$": round(dd * PT_USD, 0)}


def main():
    today = dt.date.today().isoformat()
    df = pd.read_parquet(ENG)
    df = df[(df["state"] >= 0) & (df["date"] <= CUTOFF)] \
        .sort_values(["date", "bar"]).reset_index(drop=True)
    byday = {d: g.reset_index(drop=True) for d, g in df.groupby("date")}
    dates = sorted(byday)
    missing = [d for d in dates if not (TROVE / f"{d}.parquet").exists()]
    dates = [d for d in dates if d not in set(missing)]
    print(f"days {len(dates)} ({dates[0]}..{dates[-1]})  tick-file missing: {len(missing)}")

    res = {("tick-thru", "SE"): [], ("tick-touch", "SE"): [], ("tick", "CLOSE"): [],
           ("ohlc", "SE"): [], ("ohlc", "CLOSE"): []}
    for k, d in enumerate(dates):
        g = byday[d]
        has_sig = any(signal(g["high"].to_numpy(), g["low"].to_numpy(), g["open"].to_numpy(),
                             g["close"].to_numpy(), g["climax"].to_numpy(), j)
                      for j in range(1, len(g)))
        if not has_sig:
            continue
        P = pd.read_parquet(TROVE / f"{d}.parquet", columns=["Price"])["Price"] \
            .to_numpy(np.float64)
        res[("tick-thru", "SE")] += sim_day_tick(g, P, "SE", "thru")
        res[("tick-touch", "SE")] += sim_day_tick(g, P, "SE", "touch")
        res[("tick", "CLOSE")] += sim_day_tick(g, P, "CLOSE")
        res[("ohlc", "SE")] += sim_day_ohlc(g, "SE")
        res[("ohlc", "CLOSE")] += sim_day_ohlc(g, "CLOSE")
        if (k + 1) % 200 == 0:
            print(f"  {k + 1}/{len(dates)} days", flush=True)

    rows = []
    for (engv, arm), tr in res.items():
        t = pd.DataFrame(tr)
        t["year"] = t["date"].str[:4].astype(int)
        t.to_csv(OUT / f"flip_tick_trades_{engv}_{arm}_{today}.csv", index=False)
        for label, sub in [("21-22", t[t["year"] <= 2022]),
                           ("23-26", t[t["year"] >= 2023]), ("full", t)]:
            rows.append({"engine": engv, "arm": arm, "period": label,
                         **stats(sub, f"{engv} {arm} {label}")})
    out = pd.DataFrame(rows).drop(columns=["row"])
    out.to_csv(OUT / f"flip_tick_backtest_{today}.csv", index=False)
    print(out.to_string(index=False))

    th = pd.DataFrame(res[("tick-thru", "SE")])
    th = th[th["slip"].notna()] if "slip" in th.columns else pd.DataFrame()
    if len(th):
        s = (th["slip"] / TICK).round().astype(int)
        print("\nSE trigger-print gap beyond the SE (worst-case model, ticks): "
              + ", ".join(f"{k}t: {v} ({v / len(s):.0%})"
                          for k, v in s.value_counts().sort_index().items() if k <= 5)
              + f"  |  mean {s.mean():.2f}t")


if __name__ == "__main__":
    main()
