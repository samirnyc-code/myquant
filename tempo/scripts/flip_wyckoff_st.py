"""flip_wyckoff_st.py — Wyckoff Secondary Test (ST) confirmation on the climax-flip.

Wyckoff (scraped reports/wyckoff_scrape/, Event 4): after the climax, price returns
to test the extreme. A VALID test shows three things simultaneously:
  (1) narrower range than the climax, (2) LOWER volume than the climax, (3) holds.
"No Supply / No Demand" (VSA) = the first post-entry bar being quiet confirms the
reversal; a loud (high-volume, wide) bar against you = supply/demand still active.

We test the FIRST post-entry bar (bar i+1, i = SB entry bar). Two things:
  A) DIAGNOSTIC: does a quiet ST bar predict a better final outcome? Tercile split
     on st_vol_rel = vol[i+1]/vol[SB], train/test, pre-registered LOW = better.
  B) ACTIONABLE: "ST-scratch" rule = if the first post-entry bar is LOUD (high vol)
     AND closes against the position, exit at that bar's close (decision made at its
     close, no peeking). Compare book vs baseline, train/test, per year.

Frozen base mechanics = IBS + RR2 + skipH8b, stop 1t beyond box, one position,
conservative both-in-bar->stop, session-end close. NO SAR/EB (isolate ST).

    python tempo/scripts/flip_wyckoff_st.py
"""
from __future__ import annotations
import datetime as dt
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
ENG = ROOT / "tempo" / "outputs" / "tempo_engine_bars.parquet"
OUT = ROOT / "tempo" / "outputs"
TICK = 0.25
PT_USD = 50.0
RR = 2
TRAIN_MAX_YEAR = 2022


def prep_days(df):
    days = []
    for d, g in df.groupby("date"):
        g = g.reset_index(drop=True)
        h = g["high"].to_numpy(); l = g["low"].to_numpy()
        o = g["open"].to_numpy(); c = g["close"].to_numpy()
        rg = h - l
        ibs = np.where(rg > TICK / 2, (c - l) / np.where(rg == 0, 1, rg), 0.5)
        d_ibs = np.where(ibs >= 0.55, 1, np.where(ibs <= 0.45, -1, 0))
        days.append({"date": d, "year": int(d[:4]), "h": h, "l": l, "c": c,
                     "cx": g["climax"].to_numpy(), "d_ibs": d_ibs,
                     "vol": g["vol"].to_numpy(dtype=float),
                     "range": g["range"].to_numpy(dtype=float),
                     "hr": pd.to_datetime(g["start"]).dt.hour.to_numpy(), "n": len(g)})
    return days


def sim_day(day, st_scratch=False, st_cut=None):
    """base config; if st_scratch, apply the ST-scratch exit on bar i+1."""
    h, l, c, cx = day["h"], day["l"], day["c"], day["cx"]
    vol, rng, dd = day["vol"], day["range"], day["d_ibs"]
    hr = day["hr"]; n = day["n"]
    out = []
    pos = None      # [short, en, st, tg, rk, i, feat_dict]
    for i in range(1, n):
        if pos is not None:
            sh, en, st, tg, rk, ei, ft = pos
            sgn = -1 if sh else 1
            # ST-scratch: first post-entry bar loud + closes against us -> exit @close
            if st_scratch and i == ei + 1:
                loud = vol[ei] > 0 and (vol[i] / vol[ei] > st_cut)
                against = (c[i] > en) if sh else (c[i] < en)
                # only scratch if not already stopped/targeted this bar
                stopped = (h[i] >= st) if sh else (l[i] <= st)
                hit_tg = (l[i] <= tg) if sh else (h[i] >= tg)
                if loud and against and not stopped and not hit_tg:
                    ft.update(pnl=(c[i] - en) * sgn, res="st_scr")
                    out.append(ft); pos = None
                    continue
            if (h[i] >= st) if sh else (l[i] <= st):
                ft.update(pnl=-rk, res="stop"); out.append(ft); pos = None
            elif (l[i] <= tg) if sh else (h[i] >= tg):
                ft.update(pnl=RR * rk, res="target"); out.append(ft); pos = None
        if pos is not None:
            continue
        if not (cx[i] and cx[i - 1]):
            continue
        d1, d2 = dd[i - 1], dd[i]
        if d1 == 0 or d2 == 0 or d1 == d2:
            continue
        sig_short = d1 == 1
        if hr[i] == 8:
            continue
        hi2, lo2 = max(h[i - 1], h[i]), min(l[i - 1], l[i])
        en = c[i]
        st = hi2 + TICK if sig_short else lo2 - TICK
        rk = abs(en - st)
        if rk < TICK:
            continue
        sgn = -1 if sig_short else 1
        # first post-entry bar features (known only after it closes; diagnostic use)
        stv = vol[i + 1] / vol[i] if (i + 1 < n and vol[i] > 0) else np.nan
        str_ = rng[i + 1] / rng[i] if (i + 1 < n and rng[i] > 0) else np.nan
        ft = {"date": day["date"], "year": day["year"], "i": i, "short": sig_short,
              "rk": rk, "st_vol_rel": stv, "st_range_rel": str_,
              "pnl": np.nan, "res": "open"}
        pos = [sig_short, en, st, en + sgn * RR * rk, rk, i, ft]
    if pos is not None:
        sh, en, ft = pos[0], pos[1], pos[6]
        ft.update(pnl=(c[n - 1] - en) * (-1 if sh else 1), res="open_close")
        out.append(ft)
    return out


def pf(p):
    p = np.asarray(p, float); gp = p[p > 0].sum(); gl = -p[p < 0].sum()
    return (gp / gl) if gl > 0 else np.inf


def block(df, label):
    p = df["pnl"].to_numpy(float)
    if len(p) == 0:
        return {"split": label, "n": 0, "win%": np.nan, "PF": np.nan,
                "$/tr": np.nan, "tot_$": 0.0}
    return {"split": label, "n": len(p), "win%": round(100 * (p > 0).mean(), 1),
            "PF": round(pf(p), 2), "$/tr": round(p.mean() * PT_USD, 1),
            "tot_$": round(p.sum() * PT_USD, 0)}


def main():
    today = dt.date.today().isoformat()
    df = pd.read_parquet(ENG)
    df = df[df["state"] >= 0].sort_values(["date", "bar"]).reset_index(drop=True)
    days = prep_days(df)

    # ---- A) DIAGNOSTIC: baseline trades, tercile on st_vol_rel ---------------
    tr = pd.DataFrame([t for d in days for t in sim_day(d)])
    tr.to_csv(OUT / f"flip_wyckoff_st_trades_{today}.csv", index=False)
    print(f"base climax-flip: {len(tr)} trades {tr.year.min()}-{tr.year.max()}")

    feat = "st_vol_rel"
    train = tr[tr.year <= TRAIN_MAX_YEAR].dropna(subset=[feat])
    test = tr[tr.year > TRAIN_MAX_YEAR].dropna(subset=[feat])
    q1, q2 = train[feat].quantile([1 / 3, 2 / 3]).to_numpy()
    print(f"\n=== A) DIAGNOSTIC: first post-entry bar volume (st_vol_rel = vol[i+1]/vol[SB])")
    print(f"    pre-registered LOW=better (Wyckoff No-Demand/No-Supply); cuts@{q1:.3f},{q2:.3f} ===")
    diag = []
    for name, sub in (("TRAIN", train), ("TEST", test)):
        for tag, m in (("T1(quiet)", sub[feat] <= q1),
                       ("T2(mid)", (sub[feat] > q1) & (sub[feat] <= q2)),
                       ("T3(loud)", sub[feat] > q2)):
            diag.append(block(sub[m], f"{name} {tag}"))
    ddf = pd.DataFrame(diag); print(ddf.to_string(index=False))
    ddf.to_csv(OUT / f"flip_wyckoff_st_diag_{today}.csv", index=False)

    # ---- B) ACTIONABLE: ST-scratch rule, threshold from TRAIN top tercile ----
    st_cut = float(q2)
    tr2 = pd.DataFrame([t for d in days for t in sim_day(d, st_scratch=True, st_cut=st_cut)])
    print(f"\n=== B) ACTIONABLE: ST-scratch (exit if first post-entry bar vol > {st_cut:.2f}x SB "
          f"AND closes against) ===")
    cmp = pd.DataFrame([
        block(tr, "baseline ALL"), block(tr2, "ST-scratch ALL"),
        block(tr[tr.year <= TRAIN_MAX_YEAR], "baseline TRAIN"),
        block(tr2[tr2.year <= TRAIN_MAX_YEAR], "ST-scratch TRAIN"),
        block(tr[tr.year > TRAIN_MAX_YEAR], "baseline TEST"),
        block(tr2[tr2.year > TRAIN_MAX_YEAR], "ST-scratch TEST")])
    print(cmp.to_string(index=False))
    cmp.to_csv(OUT / f"flip_wyckoff_st_rule_{today}.csv", index=False)
    n_scr = int((tr2.res == "st_scr").sum())
    print(f"  ST-scratch fired on {n_scr} trades ({100*n_scr/len(tr2):.1f}%)")
    print("\n  per-year (baseline -> ST-scratch $/tr):")
    py = []
    for y in sorted(tr.year.unique()):
        b = tr[tr.year == y]["pnl"].mean() * PT_USD
        s = tr2[tr2.year == y]["pnl"].mean() * PT_USD
        py.append({"year": y, "baseline_$tr": round(b, 1), "st_scratch_$tr": round(s, 1)})
        print(f"   {y}: {b:+6.1f}  ->  {s:+6.1f}")
    pd.DataFrame(py).to_csv(OUT / f"flip_wyckoff_st_peryear_{today}.csv", index=False)


if __name__ == "__main__":
    main()
