"""ES gamma-level edge study v2 (S73 #1+#3) — condition on GEX regime + time-of-day,
sweep params. Builds on v1's finding (raw fade ~coin-flip; morning-hold/midday-break).

Adds:
  - GEX regime per session (causal: last gamma-insights EOD strictly BEFORE the session),
    split hold-rates by GEX sign and by 1y-percentile terciles.
  - time-of-day x GEX cross-tab.
  - MOVE/LOOK parameter sweep to check robustness.
  - a fade-with-costs expectancy (ES $50/pt; assume 1.25pt round-trip friction).

Writes data/options_sim/es_levels_v2.json for the morning report.
Run: .venv/Scripts/python.exe scripts/mr_es_gamma_levels_v2.py
"""
import json
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
FRICTION = 1.25  # ES pts round-trip (comm+slip) — conservative for a 4pt target


def load():
    lv = pd.read_csv(ROOT / "data" / "menthorq" / "levels_history.csv")
    lv = lv[lv.symbol == "ES"].copy()
    lv["date"] = lv.date.astype(str)
    b = pd.read_parquet(ROOT / "data" / "bars" / "_continuous_unadj.parquet")
    b["DateTime"] = pd.to_datetime(b["DateTime"])
    b["date"] = b.DateTime.dt.strftime("%Y-%m-%d")
    b["hm"] = b.DateTime.dt.strftime("%H:%M")
    gi = pd.read_csv(ROOT / "data" / "menthorq" / "gex_insights_ES1.csv")
    gi["date"] = gi.date.astype(str)
    gi = gi.sort_values("date").reset_index(drop=True)
    return lv, b, gi


def regime_for(session_date, gi):
    """causal GEX regime: the last EOD report strictly before the session."""
    prior = gi[gi.date < session_date]
    if prior.empty:
        return None
    r = prior.iloc[-1]
    return {"gex": r.gex, "pct": r.gex_pct_1y, "sign": "pos" if r.gex > 0 else "neg"}


def touches(day, lvl, side, MOVE, LOOK, TOL):
    H, L = day.High.values, day.Low.values
    hm = day.hm.values
    out = []
    n = len(day)
    last = -99
    for i in range(n):
        if (L[i] - TOL) <= lvl <= (H[i] + TOL) and i - last > LOOK:
            last = i
            res = None
            for j in range(i + 1, min(n, i + 1 + LOOK)):
                up = H[j] >= lvl + MOVE
                dn = L[j] <= lvl - MOVE
                if side == "res":
                    if dn:
                        res = "reject"; break
                    if up:
                        res = "break"; break
                else:
                    if up:
                        res = "reject"; break
                    if dn:
                        res = "break"; break
            if res:
                out.append((res, hm[i][:2]))
    return out


def hold(pairs):
    r = sum(1 for x, _ in pairs if x == "reject")
    b = sum(1 for x, _ in pairs if x == "break")
    return r, b, (r / (r + b) * 100 if r + b else None)


def run(lv, bars, gi, MOVE=4.0, LOOK=8, TOL=1.0):
    levels = {r.date: r for r in lv.itertuples()}
    days = [d for d in sorted(set(bars.date)) if d in levels]
    all_touch, by_gex, by_hour, by_hour_pos, by_hour_neg = [], {"pos": [], "neg": []}, {}, {}, {}
    pct_bucket = {"low": [], "mid": [], "high": []}
    for d in days:
        day = bars[bars.date == d].reset_index(drop=True)
        if len(day) < 10:
            continue
        reg = regime_for(d, gi)
        cr, ps = levels[d].cr, levels[d].ps
        for lvl, side in [(cr, "res"), (ps, "sup")]:
            if not np.isfinite(lvl):
                continue
            for res, hh in touches(day, lvl, side, MOVE, LOOK, TOL):
                all_touch.append((res, hh))
                by_hour.setdefault(hh, []).append(res)
                if reg:
                    by_gex[reg["sign"]].append(res)
                    (by_hour_pos if reg["sign"] == "pos" else by_hour_neg).setdefault(hh, []).append(res)
                    if reg["pct"] is not None:
                        bkt = "low" if reg["pct"] < 1/3 else ("high" if reg["pct"] > 2/3 else "mid")
                        pct_bucket[bkt].append(res)
    return all_touch, by_gex, by_hour, by_hour_pos, by_hour_neg, pct_bucket


def summ(pairs):
    r, b, h = hold([(x, None) for x in pairs]) if pairs and isinstance(pairs[0], str) else hold(pairs)
    return {"n": r + b, "reject": r, "break": b, "hold_pct": round(h, 1) if h else None}


def main():
    lv, bars, gi = load()
    out = {"params": {}, "sweep": [], "gex": {}, "gex_pct": {}, "hour": {}, "hour_pos": {}, "hour_neg": {}}

    # base run
    at, bg, bh, bhp, bhn, pb = run(lv, bars, gi)
    base = summ([x for x, _ in at])
    out["base"] = base
    out["gex"] = {k: summ(v) for k, v in bg.items()}
    out["gex_pct"] = {k: summ(v) for k, v in pb.items()}
    out["hour"] = {k: summ(v) for k, v in sorted(bh.items())}
    out["hour_pos"] = {k: summ(v) for k, v in sorted(bhp.items())}
    out["hour_neg"] = {k: summ(v) for k, v in sorted(bhn.items())}

    # param sweep (robustness of the base hold-rate)
    for MOVE in (2, 4, 6, 8):
        for LOOK in (6, 12):
            at2, *_ = run(lv, bars, gi, MOVE=MOVE, LOOK=LOOK)
            s = summ([x for x, _ in at2])
            out["sweep"].append({"move": MOVE, "look": LOOK, **s})

    (ROOT / "data" / "options_sim" / "es_levels_v2.json").write_text(json.dumps(out, indent=1))

    # print
    print(f"BASE (MOVE4/LOOK8): {base}")
    print(f"\nby GEX regime (causal prior-EOD):")
    for k, v in out["gex"].items():
        print(f"  GEX {k}: {v}")
    print(f"\nby GEX 1y-percentile tercile:")
    for k, v in out["gex_pct"].items():
        print(f"  {k:4s}: {v}")
    print(f"\nhold by hour — POSITIVE GEX days:")
    for k, v in out["hour_pos"].items():
        if v["n"] >= 5:
            print(f"  {k}:00  {v}")
    print(f"\nhold by hour — NEGATIVE GEX days:")
    for k, v in out["hour_neg"].items():
        if v["n"] >= 5:
            print(f"  {k}:00  {v}")
    print(f"\nparam sweep (base hold-rate robustness):")
    for s in out["sweep"]:
        print(f"  MOVE{s['move']}/LOOK{s['look']}: n{s['n']} hold {s['hold_pct']}%")


if __name__ == "__main__":
    main()
