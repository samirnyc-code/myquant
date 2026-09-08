"""Step 1b — the STRIKE-SELECTION LOGIC proof, shown per day.

Feeds the desk's OWN recorded expected-move band (em_low/em_high from each
gameplan) into my strike formula and checks it reproduces the desk's ACTUAL
short strikes:

  short put  = round5(em_low)
  short call = round5(em_high)

This isolates the LOGIC from the EM-source question. If this is 100%, the only
reason the pure-VIX run (backtest_ic_strikes.py) missed by ~5pt is the EM source
(the recent desk used gexlog's band; gexlog didn't exist before 2026, so the VIX
formula is the correct historical input).
"""
import glob
import json
import os
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]


def round5(x):
    return round(x / 5.0) * 5.0


def norm(d):
    d = str(d).replace("-", "")
    return f"{d[:4]}-{d[4:6]}-{d[6:8]}"


def main():
    df = pd.read_parquet(ROOT / "data/options_log/trades.parquet")
    ic = df[df["strategy_id"].astype(str).str.contains("ic", na=False) & df["pnl"].notna()].copy()
    ic["date"] = ic["entry_dt"].astype(str).str[:10]
    actual = {}
    for _, t in ic.iterrows():
        legs = json.loads(t["legs"]) if isinstance(t["legs"], str) else t["legs"]
        short = next(l for l in legs if l["side"] == "sell")
        actual[(t["date"], t["strategy_id"])] = short["strike"]

    rows, hits, tot = [], 0, 0
    for f in sorted(glob.glob(str(ROOT / "data/options_sim/gameplan_2026*.json"))):
        g = json.load(open(f))
        d = norm(g.get("date") or os.path.basename(f)[9:17])
        lo, hi = g.get("em_low"), g.get("em_high")
        src = g.get("em_source")
        if lo is None or hi is None:
            continue
        for strat, band, k in (("eodic_p", lo, round5(lo)), ("eodic_c", hi, round5(hi))):
            a = actual.get((d, strat))
            if a is None:
                continue
            tot += 1
            ok = abs(k - a) < 1e-6
            hits += ok
            rows.append(dict(date=d, strat=strat, em_source=src, em_band=band,
                             mine=k, desk=a, match=ok))

    out = pd.DataFrame(rows)
    out.to_csv(ROOT / "data/options_sim/backtest_ic_strikes_logic.csv", index=False)
    print(f"{'date':12}{'leg':10}{'EMsource':14}{'EMband':>8}{'round5':>8}{'desk':>7}  match")
    for _, r in out.iterrows():
        print(f"{r['date']:12}{r['strat']:10}{str(r['em_source']):14}{r['em_band']:>8.1f}"
              f"{r['mine']:>8.0f}{r['desk']:>7.0f}  {'YES' if r['match'] else 'NO <--'}")
    print(f"\nEOD condor strikes reproduced from the desk's own EM band: {hits}/{tot} = {100*hits/tot:.0f}%")
    print(f"-> data/options_sim/backtest_ic_strikes_logic.csv")


if __name__ == "__main__":
    main()
