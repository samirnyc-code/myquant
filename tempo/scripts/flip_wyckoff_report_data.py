"""flip_wyckoff_report_data.py — assemble all Wyckoff-study results into ONE JSON
for the visual report (tempo/outputs/wyckoff_report.json). Reads the dated CSVs
emitted by flip_wyckoff_effort.py / flip_wf_wyckoff.py / flip_wyckoff_st.py.

    python tempo/scripts/flip_wyckoff_report_data.py [YYYY-MM-DD]
"""
from __future__ import annotations
import datetime as dt
import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / "tempo" / "outputs"
PT = 50.0
CUT = 1.0                      # Wyckoff Terminal-Shakeout boundary (SB vol > trap vol)
TRAIN_MAX = 2022


def pf(p):
    p = np.asarray(p, float); gp = p[p > 0].sum(); gl = -p[p < 0].sum()
    return float(gp / gl) if gl > 0 else float("inf")


def maxdd(p):
    eq = np.cumsum(np.asarray(p, float) * PT)
    return float((eq - np.maximum.accumulate(eq)).min()) if len(eq) else 0.0


def stats(p):
    p = np.asarray(p, float)
    if not len(p):
        return dict(n=0, pf=None, dtr=None, tot=0, dd=0, win=None)
    return dict(n=int(len(p)), pf=round(pf(p), 2), dtr=round(p.mean() * PT, 1),
                tot=round(p.sum() * PT, 0), dd=round(maxdd(p), 0),
                win=round(100 * (p > 0).mean(), 1))


def main():
    day = sys.argv[1] if len(sys.argv) > 1 else dt.date.today().isoformat()
    tr = pd.read_csv(OUT / f"flip_wyckoff_trades_{day}.csv")
    tr = tr.sort_values(["date", "i"]).reset_index(drop=True)
    keep = tr[tr["sb_vol_rel"] <= CUT].reset_index(drop=True)

    R = {"as_of": day, "cut": CUT}

    # headline stat blocks (base config, filter @1.0)
    R["headline"] = {
        "base_test": stats(tr[tr.year > TRAIN_MAX]["pnl"]),
        "filt_test": stats(keep[keep.year > TRAIN_MAX]["pnl"]),
        "base_all": stats(tr["pnl"]),
        "filt_all": stats(keep["pnl"]),
    }

    # equity curves (cumulative $), baseline vs filtered — full history
    R["equity"] = {
        "base": np.round(np.cumsum(tr["pnl"].to_numpy() * PT)).astype(int).tolist(),
        "filt": np.round(np.cumsum(keep["pnl"].to_numpy() * PT)).astype(int).tolist(),
        "base_dates": tr["date"].tolist(),
        "filt_dates": keep["date"].tolist(),
    }

    # per-year $/tr and n, baseline vs filtered
    years = sorted(tr.year.unique())
    R["peryear"] = [{
        "year": int(y),
        "base_dtr": round(tr[tr.year == y]["pnl"].mean() * PT, 1),
        "base_n": int((tr.year == y).sum()),
        "filt_dtr": round(keep[keep.year == y]["pnl"].mean() * PT, 1),
        "filt_n": int((keep.year == y).sum()),
    } for y in years]

    # 5 pre-registered filters — tercile $/tr (train cuts), train+test
    feats = [("sb_vol_rel", "low", "vol(reversal)/vol(trap)  · Spring #3"),
             ("sb_rpe", "high", "range/vol of reversal bar · effort⇄result"),
             ("sb_tempo_rel", "low", "tempo(reversal)/tempo(trap)"),
             ("sb_tpct", "low", "reversal-bar tempo percentile"),
             ("trap_absorb", "high", "trap-bar vol/range · Footprint 1")]
    summ = pd.read_csv(OUT / f"flip_wyckoff_summary_{day}.csv")
    vmap = dict(zip(summ.feature, summ.verdict))
    filt_rows = []
    for f, better, desc in feats:
        train = tr[tr.year <= TRAIN_MAX].dropna(subset=[f])
        test = tr[tr.year > TRAIN_MAX].dropna(subset=[f])
        q1, q2 = train[f].quantile([1 / 3, 2 / 3]).to_numpy()
        def terc(sub):
            return [round(sub[sub[f] <= q1]["pnl"].mean() * PT, 1),
                    round(sub[(sub[f] > q1) & (sub[f] <= q2)]["pnl"].mean() * PT, 1),
                    round(sub[sub[f] > q2]["pnl"].mean() * PT, 1)]
        filt_rows.append({"feat": f, "desc": desc, "better": better,
                          "verdict": vmap.get(f, "?"),
                          "train": terc(train), "test": terc(test)})
    R["filters"] = filt_rows

    # WF confirmation
    wf = pd.read_csv(OUT / f"flip_wf_wyckoff_summary_{day}.csv")
    R["wf_summary"] = wf.to_dict(orient="records")
    wfy = pd.read_csv(OUT / f"flip_wf_wyckoff_years_{day}.csv")
    R["wf_years"] = wfy.to_dict(orient="records")

    # #2 Secondary Test — diagnostic terciles + per-year scratch
    diag = pd.read_csv(OUT / f"flip_wyckoff_st_diag_{day}.csv")
    R["st_diag"] = diag.to_dict(orient="records")
    stpy = pd.read_csv(OUT / f"flip_wyckoff_st_peryear_{day}.csv")
    R["st_peryear"] = stpy.to_dict(orient="records")
    strule = pd.read_csv(OUT / f"flip_wyckoff_st_rule_{day}.csv")
    R["st_rule"] = strule.to_dict(orient="records")

    p = OUT / "wyckoff_report.json"
    p.write_text(json.dumps(R, indent=1), encoding="utf-8")
    print("wrote", p, f"({p.stat().st_size} bytes)")
    print("headline base_test:", R["headline"]["base_test"])
    print("headline filt_test:", R["headline"]["filt_test"])


if __name__ == "__main__":
    main()
