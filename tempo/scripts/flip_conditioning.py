"""flip_conditioning.py — flushing out the climax-flip: filters + management (S117-tempo).

Base = flip_backtest.py spec (adjacent opposite climax bars, entry close of bar 2,
stop 1 tick beyond the 2-bar box, one trade at a time, both-in-bar -> stop).

=== ARM 1: MANAGEMENT variants (no information added, pure mechanics) ===
  RR2      target 2R
  RR3      target 3R (baseline)
  RR2_BE1  target 2R, stop moved to ENTRY once 1R touches (BE fill assumed)
  RR3_BE1  target 3R, same break-even rule
  RR3_P1   half off at 1R, rest to 3R w/ BE stop after 1R  (avg of the two legs)

=== ARM 2: CONDITION sweep on RR3, train 2021-2024 / test 2025-2026 ===
Per-trade features (all computable at entry): pair max tpct >=99; risk <= median;
risk/ADR <= 0.10; hour of session; first flip of day; WITH vs COUNTER the 10-bar
trend (eff10 sign at bar 2 vs trade side); prior state EXPAND-run vs other;
within 0.15xADR of PDH/PDL (levels_by_day.json); gap day (|gap| >= 0.3xADR).
Keep any single condition with train n>=100 AND train win > breakeven+1pp;
report its TEST performance. Everything else is listed as failed - no cherry-picks.

    python tempo/scripts/flip_conditioning.py
"""
from __future__ import annotations
import datetime as dt
import json
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
ENG = ROOT / "tempo" / "outputs" / "tempo_engine_bars.parquet"
LV = ROOT / "tempo" / "outputs" / "levels_by_day.json"
OUT = ROOT / "tempo" / "outputs"
TICK = 0.25
ADR_LB = 8


def walk(h, l, i, n, short, en, st, tgt, be_after=None):
    """Bar walk. be_after = price that, once touched, moves stop to entry.
    Returns (result 0 open/1 stop/2 target/3 BE-out, exit_bar). Conservative: stop first."""
    stop = st
    armed = False
    for j in range(i + 1, n):
        hs = h[j] >= stop if short else l[j] <= stop
        if hs:
            return (3 if armed and abs(stop - en) < TICK / 2 else 1), j
        if be_after is not None and not armed:
            if (l[j] <= be_after if short else h[j] >= be_after):
                armed = True
                stop = en
        if (l[j] <= tgt if short else h[j] >= tgt):
            return 2, j
    return 0, n - 1


def main():
    today = dt.date.today().isoformat()
    df = pd.read_parquet(ENG)
    df = df[df["state"] >= 0].sort_values(["date", "bar"]).reset_index(drop=True)
    levels = json.loads(LV.read_text(encoding="utf-8")) if LV.exists() else {}
    day = df.groupby("date").agg(hi=("high", "max"), lo=("low", "min"))
    day["adr"] = (day["hi"] - day["lo"]).shift(1).rolling(ADR_LB).mean()

    trades = []
    for date, g in df.groupby("date"):
        g = g.reset_index(drop=True)
        adr = day.loc[date, "adr"]
        lv = levels.get(date, {})
        h = g["high"].to_numpy(); l = g["low"].to_numpy()
        o = g["open"].to_numpy(); c = g["close"].to_numpy()
        cx = g["climax"].to_numpy(); e10 = g["eff10"].to_numpy(); t10 = g["t10"].to_numpy()
        n = len(g)
        busy = -1
        first = True
        for i in range(1, n):
            if i <= busy or not (cx[i] and cx[i - 1]):
                continue
            u1, u2 = c[i - 1] >= o[i - 1], c[i] >= o[i]
            if u1 == u2:
                continue
            short = u1 and not u2
            hi2, lo2 = max(h[i - 1], h[i]), min(l[i - 1], l[i])
            en = c[i]
            st = hi2 + TICK if short else lo2 - TICK
            rk = abs(en - st)
            if rk < TICK:
                continue
            sgn = -1 if short else 1
            r1 = en + sgn * rk
            res = {}
            exits = {}
            for name, tgt_mult, be in [("RR2", 2, None), ("RR3", 3, None),
                                       ("RR2_BE1", 2, r1), ("RR3_BE1", 3, r1)]:
                r, j = walk(h, l, i, n, short, en, st, en + sgn * tgt_mult * rk, be)
                res[name] = r; exits[name] = j
            busy = n if res["RR3"] == 0 else exits["RR3"]

            net10 = None
            trend_with = None
            if not np.isnan(e10[i]):
                trend_with = (e10[i] >= 0.30) and ((g["dir"].iloc[i] > 0) != short)
            near_lvl = None
            if "hoy" in lv and np.isfinite(adr) and adr > 0:
                dmin = min(abs(en - lv["hoy"]), abs(en - lv["loy"]))
                near_lvl = dmin <= 0.15 * adr
            gap_day = None
            if "coy" in lv and "ood" in lv and np.isfinite(adr) and adr > 0:
                gap_day = abs(lv["ood"] - lv["coy"]) >= 0.30 * adr
            prior_expand = bool((g["state"].iloc[max(0, i - 5):i - 1] == 1).any())
            trades.append({
                "date": date, "year": int(date[:4]), "short": short, "risk": rk,
                "risk_adr": rk / adr if np.isfinite(adr) and adr > 0 else np.nan,
                "tpct_max": float(np.nanmax([g["tpct"].iloc[i - 1], g["tpct"].iloc[i]])),
                "hour": int(g["session_min"].iloc[i] // 60), "first": first,
                "with_trend": trend_with, "near_pdhl": near_lvl, "gap_day": gap_day,
                "prior_expand": prior_expand,
                "RR2": res["RR2"], "RR3": res["RR3"],
                "RR2_BE1": res["RR2_BE1"], "RR3_BE1": res["RR3_BE1"],
            })
            first = False
    t = pd.DataFrame(trades)
    t.to_csv(OUT / f"flip_conditioning_trades_{today}.csv", index=False)
    lines = [f"trades: {len(t)} over {t['date'].nunique()} sessions"]

    def ev(sub, col, tgt_mult):
        # R-based EV: stop -1, target +tgt, BE 0, open 0 (excluded)
        m = sub[sub[col] != 0]
        if len(m) == 0:
            return 0, 0, 0
        w = (m[col] == 2).mean()
        be = (m[col] == 3).mean()
        evr = w * tgt_mult - (1 - w - be) * 1.0
        return len(m), w, evr

    lines.append("\n=== ARM 1: management variants (full history, R per trade) ===")
    for col, tm in [("RR2", 2), ("RR3", 3), ("RR2_BE1", 2), ("RR3_BE1", 3)]:
        nn, w, evr = ev(t, col, tm)
        lines.append(f"  {col:>8}: n={nn}  win={w:.1%}  EV={evr:+.3f} R/trade")
    m = t[(t["RR3_BE1"] != 0)]
    w3 = (m["RR3_BE1"] == 2).mean(); be3 = (m["RR3_BE1"] == 3).mean()
    r1m = t[t["RR2_BE1"] != 0]
    w1 = ((r1m["RR2_BE1"] == 2) | (r1m["RR2_BE1"] == 3)).mean()   # touched 1R proxy
    ev_p1 = 0.5 * (w1 * 1 - (1 - w1) * 1) + 0.5 * (w3 * 3 + be3 * 0 - (1 - w3 - be3) * 1)
    lines.append(f"  RR3_P1 (half @1R + BE, half to 3R): approx EV={ev_p1:+.3f} R/trade")

    lines.append("\n=== ARM 2: RR3 condition sweep — train 2021-24, test 2025-26 (breakeven 25%) ===")
    tr = t[t["year"] <= 2024]; te = t[t["year"] >= 2025]
    conds = [
        ("tpct>=99 both-ish", lambda d: d["tpct_max"] >= 99),
        ("risk<=median", lambda d: d["risk"] <= t["risk"].median()),
        ("risk/ADR<=0.10", lambda d: d["risk_adr"] <= 0.10),
        ("first flip of day", lambda d: d["first"] == True),           # noqa: E712
        ("hour 5 (13:30CT)", lambda d: d["hour"] == 5),
        ("COUNTER-trend flip", lambda d: d["with_trend"] == False),    # noqa: E712
        ("WITH-trend flip", lambda d: d["with_trend"] == True),        # noqa: E712
        ("near PDH/PDL", lambda d: d["near_pdhl"] == True),            # noqa: E712
        ("away from PDH/PDL", lambda d: d["near_pdhl"] == False),      # noqa: E712
        ("gap day", lambda d: d["gap_day"] == True),                   # noqa: E712
        ("prior EXPAND run", lambda d: d["prior_expand"] == True),     # noqa: E712
        ("shorts only", lambda d: d["short"] == True),                 # noqa: E712
        ("longs only", lambda d: d["short"] == False),                 # noqa: E712
    ]
    for name, f in conds:
        trn = tr[f(tr)]; tst = te[f(te)]
        ntr, wtr, evtr = ev(trn, "RR3", 3)
        nte, wte, evte = ev(tst, "RR3", 3)
        flag = "PASS->" if ntr >= 100 and wtr >= 0.26 else "      "
        lines.append(f"  {flag}{name:<22} train n={ntr:>4} win={wtr:.1%} EV={evtr:+.3f} | "
                     f"test n={nte:>4} win={wte:.1%} EV={evte:+.3f}")
    txt = "\n".join(lines)
    (OUT / f"flip_conditioning_{today}.txt").write_text(txt, encoding="utf-8")
    print(txt)


if __name__ == "__main__":
    main()
