"""flip_close_fill_test.py — can you actually GET the close of a climax SB? (S119, 2026-09-13)

User challenge: the tick engine filled CLOSE entries at the SB's LAST print. A real
market order goes out after the bar completes -> you get the NEXT print at best,
plus the spread, in a climactic tape. Same for every exit-at-close (SAR rev,
EB scratch, session end). This tests fill models where EVERY at-close transaction
(entry AND exit) is degraded symmetrically:

  IDEAL      fill at the bar's last print (what was reported so far)
  NEXT       fill at the 1st print after the bar closes, no spread
  NEXT+1t    1st print after close, +1 tick adverse (market order pays the spread)
  NEXT5+1t   5th print after close, +1 tick adverse (latency stress in fast tape)

Configs: base CLOSE (eb0.45, all hours) and the best combo CLOSE+skipOpen+ebOFF.
Engine: tick (tickdata.load_rth), stops at triggering print, targets at limit,
RR2 on actual-fill risk. Periods: IS 2021-06-18..2022-12-31 /
OOS 2023-01-01..2026-09-10 / FULL. Per-setup breakout per reporting standard.

    python tempo/scripts/flip_close_fill_test.py
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

FILLS = [("IDEAL", 0, 0), ("NEXT", 1, 0), ("NEXT+1t", 1, 1), ("NEXT5+1t", 5, 1)]
CONFIGS = [{"name": "CLOSE base", "eb": 0.45, "skips": frozenset()},
           {"name": "CLOSE+skipOpen+ebOFF", "eb": None, "skips": frozenset(("open",))}]


def close_px(P, B, lag):
    """price of a transaction decided at the close of raw bar B: lag=0 -> last print
    of B; lag=k -> k-th print after the close (clamped to day end)."""
    idx = (B + 1) * SIZE - 1 + lag
    return P[min(idx, len(P) - 1)], lag  # offset into next bar = lag


def sim_day(g, P, cfg, lag, adv):
    bar = g["bar"].to_numpy(int)
    h = g["high"].to_numpy(); l = g["low"].to_numpy()
    o = g["open"].to_numpy(); c = g["close"].to_numpy()
    cx = g["climax"].to_numpy()
    sm = g["session_min"].to_numpy()
    n = len(g)
    date = g["date"].iloc[0]
    a = adv * TICK
    trades = []
    pos = None
    for j in range(1, n):
        B = bar[j]
        T = P[B * SIZE:(B + 1) * SIZE]
        i0 = pos.pop("skip", 0) if pos is not None else 0
        if pos is not None and i0 < len(T):
            sh = pos["short"]; sgn = -1 if sh else 1
            s_i = fidx((T[i0:] >= pos["st"] - EPS) if sh else (T[i0:] <= pos["st"] + EPS))
            t_i = fidx((T[i0:] <= pos["tg"] + EPS) if sh else (T[i0:] >= pos["tg"] - EPS))
            if s_i >= 0 and (t_i < 0 or s_i <= t_i):
                px = T[i0 + s_i]
                trades.append({**pos, "res": "stop", "pnl": (px - pos["en"]) * sgn}); pos = None
            elif t_i >= 0:
                trades.append({**pos, "res": "target", "pnl": (pos["tg"] - pos["en"]) * sgn}); pos = None
        # bar close decisions (fills modeled at close_px +/- adverse)
        if pos is not None and j == pos["sig_j"] + 1 \
                and eb_wrong(h, l, c, cx, j, pos["short"], cfg["eb"]):
            sgn = -1 if pos["short"] else 1
            px, _ = close_px(P, B, lag)
            trades.append({**pos, "res": "eb_scr", "pnl": (px - sgn * a - pos["en"]) * sgn})
            pos = None
        s = sig_dir(h, l, c, o, cx, j)
        if s:
            sig_short = s == 1
            kind = "B"
            blocked = False
            if pos is not None:
                if sig_short != pos["short"]:
                    sgn = -1 if pos["short"] else 1
                    px, _ = close_px(P, B, lag)
                    trades.append({**pos, "res": "rev", "pnl": (px - sgn * a - pos["en"]) * sgn})
                    pos = None; kind = "R"
                else:
                    blocked = True
            if not blocked and pos is None and not in_window(sm[j], cfg["skips"]):
                hi2, lo2 = max(h[j - 1], h[j]), min(l[j - 1], l[j])
                psl = hi2 + TICK if sig_short else lo2 - TICK
                sgn = -1 if sig_short else 1
                px, off = close_px(P, B, lag)
                en = px + (a if not sig_short else -a)   # entry pays the spread adversely
                rk = abs(en - psl)
                if rk >= TICK:
                    pos = {"date": date, "kind": kind, "short": sig_short, "en": en,
                           "st": psl, "rk": rk, "tg": en + sgn * RR * rk, "sig_j": j,
                           "skip": off}
    if pos is not None:
        pos.pop("skip", None)
        sgn = -1 if pos["short"] else 1
        px = P[-1]
        trades.append({**pos, "res": "open", "pnl": (px - sgn * a - pos["en"]) * sgn})
    return trades


def seg(t):
    if len(t) == 0:
        return {"n": 0, "PF": np.nan, "$/tr": np.nan}
    pnl = t["pnl"]
    gp = pnl[pnl > 0].sum(); gl = -pnl[pnl < 0].sum()
    return {"n": len(t), "PF": round(gp / gl, 2) if gl > 0 else np.inf,
            "$/tr": round(pnl.mean() * PT_USD, 1)}


def main():
    today = dt.date.today().isoformat()
    df = pd.read_parquet(ENG)
    df = df[(df["state"] >= 0) & (df["date"] <= CUTOFF)] \
        .sort_values(["date", "bar"]).reset_index(drop=True)
    byday = {d: g.reset_index(drop=True) for d, g in df.groupby("date")}
    dates = [d for d in sorted(byday) if d in set(tickdata.available("rth"))]
    print(f"days {len(dates)}  fills {len(FILLS)} x configs {len(CONFIGS)}")

    res = {(c["name"], f[0]): [] for c in CONFIGS for f in FILLS}
    for k, d in enumerate(dates):
        g = byday[d]
        h = g["high"].to_numpy(); l = g["low"].to_numpy()
        o = g["open"].to_numpy(); c = g["close"].to_numpy()
        cx = g["climax"].to_numpy()
        if not any(sig_dir(h, l, c, o, cx, j) for j in range(1, len(g))):
            continue
        P = tickdata.load_rth(d)["Price"].to_numpy(np.float64)
        for cfg in CONFIGS:
            for fname, lag, adv in FILLS:
                res[(cfg["name"], fname)] += sim_day(g, P, cfg, lag, adv)
        if (k + 1) % 300 == 0:
            print(f"  {k + 1}/{len(dates)} days", flush=True)

    periods = [("IS 21-06-18..22-12-31", lambda t: t[t["date"] <= IS_END]),
               ("OOS 23-01-01..26-09-10", lambda t: t[t["date"] > IS_END]),
               ("FULL 21-06-18..26-09-10", lambda t: t)]
    rows = []
    for (cname, fname), tr in res.items():
        t = pd.DataFrame(tr)
        for plabel, sel in periods:
            sub = sel(t)
            pnl = sub["pnl"]
            eq = pnl.cumsum()
            dd = (eq - eq.cummax()).min() if len(sub) else 0.0
            al = seg(sub)
            bas = seg(sub[(sub["kind"] == "B") & (sub["res"] != "eb_scr")])
            rev = seg(sub[(sub["kind"] == "R") & (sub["res"] != "eb_scr")])
            scr = sub[sub["res"] == "eb_scr"]
            rows.append({"config": cname, "fill": fname, "period": plabel,
                         "n": al["n"], "PF": al["PF"], "$/tr": al["$/tr"],
                         "maxDD_$": round(dd * PT_USD, 0),
                         "bas_n": bas["n"], "bas_PF": bas["PF"], "bas_$": bas["$/tr"],
                         "rev_n": rev["n"], "rev_PF": rev["PF"], "rev_$": rev["$/tr"],
                         "scr_n": len(scr),
                         "scr_$": round(scr["pnl"].mean() * PT_USD, 1) if len(scr) else np.nan})
    out = pd.DataFrame(rows)
    out.to_csv(OUT / f"flip_close_fill_{today}.csv", index=False)
    for cname in [c["name"] for c in CONFIGS]:
        print(f"\n=== {cname} ===")
        print(out[out["config"] == cname].to_string(index=False))


if __name__ == "__main__":
    main()
