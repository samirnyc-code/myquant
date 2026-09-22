"""flip_limit_entry_test.py — LIMIT at the SB close, tick-through fill on the EB (S119, user).

User idea: instead of a market order at the climax SB close (which pays next-print
+ spread) or an SE beyond the SB (which pays trigger slippage), rest a LIMIT at the
SB CLOSE price and let the EB (bar after SB) tick THROUGH it.

Spec (frozen):
  entry   limit at SB close C, working ONLY during the EB; fill requires a print
          STRICTLY through it (long: <= C - 1t; short: >= C + 1t); fill AT C.
          Unfilled at EB close -> no trade. Newer signal replaces a pending limit.
  stop    1t beyond the 2-bar box; fills at the triggering print (gap-through).
          The fill print itself is checked for stop/target (sweep-through case).
  target  RR2 limit on |C - stop|, fills at the target price.
  EB rule (when on): filled during EB and EB closes wrong-IBS non-climax -> scratch.
  REALISM: every at-close exit (rev / eb_scr / session end) fills at the NEXT print
  + 1 tick adverse — identical to flip_close_fill_test NEXT+1t.
Arms: base (eb0.45, all hours) · skipOpen+eb0.45 · skipOpen+ebOFF.
Periods IS 2021-06-18..2022-12-31 / OOS 2023-01-01..2026-09-10 / FULL; per-setup.

    python tempo/scripts/flip_limit_entry_test.py
"""
from __future__ import annotations
import datetime as dt
import sys
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "tempo" / "scripts"))
import tickdata  # noqa: E402
from flip_config_sweep import (CUTOFF, ENG, EPS, IS_END, OUT, PT_USD, RR, SIZE,  # noqa: E402
                               TICK, eb_wrong, fidx, in_window, sig_dir)

ADV = TICK  # 1 tick adverse on every at-close market exit
CONFIGS = [{"name": "LIM base eb0.45", "eb": 0.45, "skips": frozenset()},
           {"name": "LIM skipOpen eb0.45", "eb": 0.45, "skips": frozenset(("open",))},
           {"name": "LIM skipOpen ebOFF", "eb": None, "skips": frozenset(("open",))}]


def next_print(P, B, sgn_exit):
    """realistic at-close exit price for a position with direction sign sgn
    (long=+1): next print after bar B closes, 1 tick adverse."""
    idx = min((B + 1) * SIZE, len(P) - 1)
    return P[idx] - sgn_exit * ADV


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
    pend = None          # limit: {kind short lim psl sig_j}
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
            elif pend is not None and j == pend["sig_j"] + 1:
                sh = pend["short"]
                f_i = fidx((T[i0:] >= pend["lim"] + TICK - EPS) if sh
                           else (T[i0:] <= pend["lim"] - TICK + EPS))
                if f_i < 0:
                    break
                en = pend["lim"]; st = pend["psl"]; rk = abs(en - st)
                sgn = -1 if sh else 1
                pos = {"date": date, "kind": pend["kind"], "short": sh, "en": en, "st": st,
                       "rk": rk, "tg": en + sgn * RR * rk, "sig_j": pend["sig_j"]}
                pend = None
                i0 = i0 + f_i        # fill print INCLUSIVE for stop/target (sweep case)
                continue
            else:
                break
        # bar close
        if pend is not None and j == pend["sig_j"] + 1:
            trades.append({"date": date, "kind": pend["kind"], "short": pend["short"],
                           "en": np.nan, "rk": np.nan, "res": "nofill", "pnl": 0.0})
            pend = None
        if pos is not None and j == pos["sig_j"] + 1 \
                and eb_wrong(h, l, c, cx, j, pos["short"], cfg["eb"]):
            sgn = -1 if pos["short"] else 1
            px = next_print(P, B, sgn)
            trades.append({**pos, "res": "eb_scr", "pnl": (px - pos["en"]) * sgn})
            pos = None
        s = sig_dir(h, l, c, o, cx, j)
        if s:
            sig_short = s == 1
            kind = "B"
            blocked = False
            if pos is not None:
                if sig_short != pos["short"]:
                    sgn = -1 if pos["short"] else 1
                    px = next_print(P, B, sgn)
                    trades.append({**pos, "res": "rev", "pnl": (px - pos["en"]) * sgn})
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
                lim = c[j]
                if abs(lim - psl) >= TICK:
                    pend = {"kind": kind, "short": sig_short, "lim": lim, "psl": psl, "sig_j": j}
    if pos is not None:
        sgn = -1 if pos["short"] else 1
        trades.append({**pos, "res": "open", "pnl": (P[-1] - sgn * ADV - pos["en"]) * sgn})
    if pend is not None:
        trades.append({"date": date, "kind": pend["kind"], "short": pend["short"],
                       "en": np.nan, "rk": np.nan, "res": "nofill", "pnl": 0.0})
    return trades


def seg(t):
    f = t[t["res"] != "nofill"]
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
    print(f"days {len(dates)}  configs {len(CONFIGS)}")

    res = {c["name"]: [] for c in CONFIGS}
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
        if (k + 1) % 300 == 0:
            print(f"  {k + 1}/{len(dates)} days", flush=True)

    periods = [("IS 21-06-18..22-12-31", lambda t: t[t["date"] <= IS_END]),
               ("OOS 23-01-01..26-09-10", lambda t: t[t["date"] > IS_END]),
               ("FULL 21-06-18..26-09-10", lambda t: t)]
    rows = []
    for cname, tr in res.items():
        t = pd.DataFrame(tr)
        t.to_csv(OUT / f"flip_limit_trades_{cname.replace(' ', '_')}_{today}.csv", index=False)
        for plabel, sel in periods:
            sub = sel(t)
            filled = sub[sub["res"] != "nofill"]
            nf = len(sub) - len(filled)
            pnl = filled["pnl"]
            eq = pnl.cumsum()
            dd = (eq - eq.cummax()).min() if len(filled) else 0.0
            al = seg(sub)
            bas = seg(sub[(sub["kind"] == "B") & (sub["res"] != "eb_scr")])
            rev = seg(sub[(sub["kind"] == "R") & (sub["res"] != "eb_scr")])
            scr = sub[sub["res"] == "eb_scr"]
            rows.append({"config": cname, "period": plabel,
                         "n": al["n"], "nofill": nf, "PF": al["PF"], "$/tr": al["$/tr"],
                         "maxDD_$": round(dd * PT_USD, 0),
                         "bas_n": bas["n"], "bas_PF": bas["PF"], "bas_$": bas["$/tr"],
                         "rev_n": rev["n"], "rev_PF": rev["PF"], "rev_$": rev["$/tr"],
                         "scr_n": len(scr),
                         "scr_$": round(scr["pnl"].mean() * PT_USD, 1) if len(scr) else np.nan})
    out = pd.DataFrame(rows)
    out.to_csv(OUT / f"flip_limit_entry_{today}.csv", index=False)
    print(out.to_string(index=False))


if __name__ == "__main__":
    main()
