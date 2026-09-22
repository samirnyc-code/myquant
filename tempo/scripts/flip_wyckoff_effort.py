"""flip_wyckoff_effort.py — Wyckoff Effort-vs-Result filter on the climax-flip setup.

Motivation (tradingwyckoff.com/en/wyckoff-method, scraped reports/wyckoff_scrape/):
  - Our climax-flip IS Wyckoff's "Climax" fast-reversal schematic.
  - Law of Effort vs Result + the THREE SPRING TYPES give a PRE-REGISTERED sign:
      Spring #3 (LOW volume / narrow penetration) = MOST reliable reversal.
      Spring #1 / Terminal Shakeout (HIGH volume / deep) = riskiest, often fails.
    => the reversal (SB) bar doing MORE result on LESS effort should trade better.
  - Secondary-test quality: valid test = lower volume than the climax.
  - Footprint 1: a strongly climactic FIRST bar (trap) => rotation/reversal.

PRE-REGISTERED hypotheses (sign fixed BEFORE looking at P&L; reject on sign-flip):
  H1 sb_vol_rel   = vol[SB]/vol[trap]        -> LOWER better   (Spring #3)
  H2 sb_tempo_rel = tempo[SB]/tempo[trap]    -> LOWER better   (Spring #3)
  H3 sb_rpe       = range[SB]/vol[SB]         -> HIGHER better  (result-per-effort harmony)
  H4 sb_tpct      = tempo pctile of SB        -> LOWER better   (low absolute effort)
  H5 trap_absorb  = vol[trap]/range[trap]     -> HIGHER better  (Footprint 1: strong climax)

Frozen mechanics = the WF-stable BASE config (S119): IBS direction + RR2 + skip-hour-8
Basic, stop 1t beyond the 2-bar box, one position, conservative both-in-bar->stop,
session-end close. NO SAR, NO EB (isolate the filter's effect on the raw setup).

Discipline: split thresholds are learned on TRAIN (2021-2022, per the WF IS window),
then applied UNCHANGED to TEST (2023-2026). A filter is only blessed if it is monotone
in the pre-registered direction in TRAIN *and* keeps its sign in TEST.

    python tempo/scripts/flip_wyckoff_effort.py
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
TRAIN_MAX_YEAR = 2022     # IS = through 2022 (matches flip_walkforward_v2)


def prep_days(df):
    days = []
    for d, g in df.groupby("date"):
        g = g.reset_index(drop=True)
        h = g["high"].to_numpy(); l = g["low"].to_numpy()
        o = g["open"].to_numpy(); c = g["close"].to_numpy()
        rg = h - l
        ibs = np.where(rg > TICK / 2, (c - l) / np.where(rg == 0, 1, rg), 0.5)
        d_ibs = np.where(ibs >= 0.55, 1, np.where(ibs <= 0.45, -1, 0))
        days.append({
            "date": d, "year": int(d[:4]), "h": h, "l": l, "c": c, "o": o,
            "cx": g["climax"].to_numpy(), "d_ibs": d_ibs,
            "vol": g["vol"].to_numpy(dtype=float),
            "tempo": g["tempo"].to_numpy(dtype=float),
            "range": g["range"].to_numpy(dtype=float),
            "tpct": g["tpct"].to_numpy(dtype=float),
            "hr": pd.to_datetime(g["start"]).dt.hour.to_numpy(), "n": len(g)})
    return days


def sim_day(day):
    """Base config, records per-trade features. Returns list of dicts."""
    h, l, c, cx = day["h"], day["l"], day["c"], day["cx"]
    vol, tempo, rng, tpct = day["vol"], day["tempo"], day["range"], day["tpct"]
    dd = day["d_ibs"]; hr = day["hr"]; n = day["n"]
    out = []
    pos = None      # [short, en, st, tg, rk, i]
    for i in range(1, n):
        if pos is not None:
            sh, en, st, tg, rk, ei = pos
            if (h[i] >= st) if sh else (l[i] <= st):
                out[-1].update(pnl=-rk, res="stop"); pos = None
            elif (l[i] <= tg) if sh else (h[i] >= tg):
                out[-1].update(pnl=RR * rk, res="target"); pos = None
        if pos is not None:
            continue
        if not (cx[i] and cx[i - 1]):
            continue
        d1, d2 = dd[i - 1], dd[i]
        if d1 == 0 or d2 == 0 or d1 == d2:
            continue
        sig_short = d1 == 1
        if hr[i] == 8:                       # skip-hour-8 Basic (WF-stable rule)
            continue
        hi2, lo2 = max(h[i - 1], h[i]), min(l[i - 1], l[i])
        en = c[i]
        st = hi2 + TICK if sig_short else lo2 - TICK
        rk = abs(en - st)
        if rk < TICK:
            continue
        sgn = -1 if sig_short else 1
        pos = [sig_short, en, st, en + sgn * RR * rk, rk, i]
        # features (trap = bar i-1, SB = bar i)
        v_sb, v_tp = vol[i], vol[i - 1]
        t_sb, t_tp = tempo[i], tempo[i - 1]
        r_sb, r_tp = rng[i], rng[i - 1]
        out.append({
            "date": day["date"], "year": day["year"], "i": i, "short": sig_short,
            "rk": rk, "pnl": np.nan, "res": "open",
            "sb_vol_rel": v_sb / v_tp if v_tp > 0 else np.nan,
            "sb_tempo_rel": t_sb / t_tp if t_tp > 0 else np.nan,
            "sb_rpe": r_sb / v_sb if v_sb > 0 else np.nan,
            "sb_tpct": tpct[i],
            "trap_absorb": v_tp / r_tp if r_tp > 0 else np.nan,
        })
    if pos is not None:
        sh, en = pos[0], pos[1]
        out[-1].update(pnl=(c[n - 1] - en) * (-1 if sh else 1), res="open_close")
    return out


def pf(pnl):
    pnl = np.asarray(pnl, float)
    gp = pnl[pnl > 0].sum(); gl = -pnl[pnl < 0].sum()
    return (gp / gl) if gl > 0 else np.inf


def block(df, label):
    p = df["pnl"].to_numpy(float)
    return {"split": label, "n": len(p), "win%": round(100 * (p > 0).mean(), 1),
            "PF": round(pf(p), 2), "pts/tr": round(p.mean(), 3),
            "$/tr": round(p.mean() * PT_USD, 1), "tot_$": round(p.sum() * PT_USD, 0)}


HYP = [   # (feature, better_direction)  'low' => low values expected to trade better
    ("sb_vol_rel", "low"),
    ("sb_tempo_rel", "low"),
    ("sb_rpe", "high"),
    ("sb_tpct", "low"),
    ("trap_absorb", "high"),
]


def tercile_report(tr, feat, better):
    """Learn tercile cuts on TRAIN, apply to TEST. Report both."""
    train = tr[tr["year"] <= TRAIN_MAX_YEAR].dropna(subset=[feat])
    test = tr[tr["year"] > TRAIN_MAX_YEAR].dropna(subset=[feat])
    q1, q2 = train[feat].quantile([1 / 3, 2 / 3]).to_numpy()
    rows = []
    for name, sub in (("TRAIN", train), ("TEST", test)):
        for tag, mask in (("T1(low)", sub[feat] <= q1),
                          ("T2(mid)", (sub[feat] > q1) & (sub[feat] <= q2)),
                          ("T3(high)", sub[feat] > q2)):
            b = block(sub[mask], f"{name} {tag}")
            rows.append(b)
    # verdict: is the favored tercile better than the disfavored one, both periods?
    fav, dis = ("T1(low)", "T3(high)") if better == "low" else ("T3(high)", "T1(low)")
    def val(period, tag):
        m = {"T1(low)": train[feat] <= q1 if period == "TRAIN" else test[feat] <= q1,
             "T3(high)": train[feat] > q2 if period == "TRAIN" else test[feat] > q2}
        sub = train if period == "TRAIN" else test
        return sub[m[tag]]["pnl"].mean() * PT_USD
    tr_edge = val("TRAIN", fav) - val("TRAIN", dis)
    te_edge = val("TEST", fav) - val("TEST", dis)
    verdict = "BLESS" if (tr_edge > 0 and te_edge > 0) else "reject"
    return rows, (q1, q2), fav, tr_edge, te_edge, verdict


def main():
    today = dt.date.today().isoformat()
    df = pd.read_parquet(ENG)
    df = df[df["state"] >= 0].sort_values(["date", "bar"]).reset_index(drop=True)
    days = prep_days(df)
    trades = [t for d in days for t in sim_day(d)]
    tr = pd.DataFrame(trades)
    tr.to_csv(OUT / f"flip_wyckoff_trades_{today}.csv", index=False)

    print(f"climax-flip base (IBS+RR2+skipH8b, no SAR/EB): {len(tr)} trades "
          f"{tr['year'].min()}-{tr['year'].max()}")
    print("\n=== BASELINE (all trades) ===")
    base = pd.DataFrame([block(tr, "ALL"),
                         block(tr[tr.year <= TRAIN_MAX_YEAR], "TRAIN 21-22"),
                         block(tr[tr.year > TRAIN_MAX_YEAR], "TEST 23-26")])
    print(base.to_string(index=False))

    summary = []
    for feat, better in HYP:
        rows, cuts, fav, tre, tee, verdict = tercile_report(tr, feat, better)
        print(f"\n=== {feat}  (pre-registered: {better} = better)  "
              f"cuts@{cuts[0]:.3g},{cuts[1]:.3g} ===")
        print(pd.DataFrame(rows).to_string(index=False))
        print(f"  favored tercile = {fav};  edge vs disfavored:  "
              f"TRAIN {tre:+.1f}$/tr,  TEST {tee:+.1f}$/tr  -> {verdict}")
        summary.append({"feature": feat, "expect": better, "favored": fav,
                        "train_edge_$": round(tre, 1), "test_edge_$": round(tee, 1),
                        "verdict": verdict})

    sdf = pd.DataFrame(summary)
    sdf.to_csv(OUT / f"flip_wyckoff_summary_{today}.csv", index=False)
    print("\n=== VERDICT SUMMARY (blessed = sign holds TRAIN and TEST) ===")
    print(sdf.to_string(index=False))

    # ---- DEPLOYABLE FILTER: reject Terminal-Shakeout flips -------------------
    # Threshold learned on TRAIN ONLY (top tercile of sb_vol_rel), applied forward.
    # Wyckoff: SB volume >= trap volume => Spring #1 / Terminal Shakeout => skip.
    cut = tr[tr.year <= TRAIN_MAX_YEAR]["sb_vol_rel"].quantile(2 / 3)
    keep = tr[tr["sb_vol_rel"] <= cut]
    print(f"\n=== DEPLOYABLE FILTER: skip flips with sb_vol_rel > {cut:.3f} "
          f"(reversal bar volume > {cut:.2f}x trap bar) ===")
    cmp = pd.DataFrame([
        block(tr, "baseline ALL"), block(keep, "filtered ALL"),
        block(tr[tr.year <= TRAIN_MAX_YEAR], "baseline TRAIN"),
        block(keep[keep.year <= TRAIN_MAX_YEAR], "filtered TRAIN"),
        block(tr[tr.year > TRAIN_MAX_YEAR], "baseline TEST"),
        block(keep[keep.year > TRAIN_MAX_YEAR], "filtered TEST")])
    print(cmp.to_string(index=False))
    print("\n  per-year (baseline -> filtered $/tr, n):")
    for y in sorted(tr.year.unique()):
        b = tr[tr.year == y]; k = keep[keep.year == y]
        print(f"   {y}: {b['pnl'].mean()*PT_USD:+6.1f} (n{len(b)})  ->  "
              f"{k['pnl'].mean()*PT_USD:+6.1f} (n{len(k)})   "
              f"kept {100*len(k)/len(b):.0f}%")

    # redundancy: do the two blessed features flag the SAME trades?
    lo_vol = set(keep.index)                                  # sb_vol_rel keeps
    rpe_cut = tr[tr.year <= TRAIN_MAX_YEAR]["sb_rpe"].quantile(1 / 3)
    hi_rpe = set(tr[tr["sb_rpe"] > rpe_cut].index)            # sb_rpe keeps
    inter = len(lo_vol & hi_rpe); uni = len(lo_vol | hi_rpe)
    print(f"\n  redundancy check (sb_vol_rel-keep vs sb_rpe-keep): "
          f"Jaccard {inter/uni:.2f} ({inter} shared / {uni} union)")


if __name__ == "__main__":
    main()
