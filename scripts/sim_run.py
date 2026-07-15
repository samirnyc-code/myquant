"""Unified level-fade SIM with FULL METRICS, saved to a persistent ledger (S73).

Every run appends rows to data/options_sim/sim_ledger.csv (one row per
market x level x config) AND writes a per-run trades file, so results accumulate
and are comparable across days/configs. Also prints a rich table.

Metrics per setup: n, win%, avg win, avg loss, profit factor, expectancy $/trade,
total $, maxDD $, max consecutive losses, best, worst, Sharpe (per-trade),
36-cell sweep %positive, in-sample vs OOS expectancy, monthly spread, verdict.

Markets: any with repaired/native bars + level history. Levels via
levels_history.csv (majors) + levels0_history.csv (0DTE).

Run: .venv/Scripts/python.exe scripts/sim_run.py [--markets ES,NQ,GC,AAPL] [--tag note]
"""
import datetime as dt
import sys
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
LEDGER = ROOT / "data" / "options_sim" / "sim_ledger.csv"
FRIC_ES = 1.25
STOPS = [3, 4, 5, 6, 8, 10]
TGTS = [6, 8, 10, 12, 15, 20]

BARFILE = {  # market -> parquet (repaired futures continuous / IB stock)
    "ES": "_continuous_unadj.parquet", "NQ": "_continuous_NQ_unadj.parquet",
    "CL": "_continuous_CL_unadj.parquet", "GC": "_continuous_GC_unadj.parquet",
    "YM": "_continuous_YM_unadj.parquet",
    "AAPL": "stocks/AAPL_5m_ib.parquet", "MSFT": "stocks/MSFT_5m_ib.parquet",
    "NVDA": "stocks/NVDA_5m_ib.parquet",
}
POINT = {"ES": 50, "NQ": 20, "CL": 1000, "GC": 100, "YM": 5,
         "AAPL": 100, "MSFT": 100, "NVDA": 100}  # $ per point (stocks: 100 sh)
LEVELS = [("cr", "res"), ("ps", "sup"), ("cr0", "res"), ("ps0", "sup")]


def bars(mkt):
    f = ROOT / "data" / "bars" / BARFILE[mkt]
    if not f.exists():
        return None
    b = pd.read_parquet(f)
    b["DateTime"] = pd.to_datetime(b["DateTime"])
    b["date"] = b.DateTime.dt.strftime("%Y-%m-%d")
    return b


def levels():
    l1 = pd.read_csv(ROOT / "data" / "menthorq" / "levels_history.csv")
    l0 = pd.read_csv(ROOT / "data" / "menthorq" / "levels0_history.csv")
    return l1, l0


def range_scale(es_bars, m_bars):
    if m_bars is es_bars:
        return 1.0
    r_es = es_bars.groupby("date").apply(lambda d: d.High.max() - d.Low.min(), include_groups=False).median()
    r_m = m_bars.groupby("date").apply(lambda d: d.High.max() - d.Low.min(), include_groups=False).median()
    return float(r_m / r_es)


def entries(lv_df, mkt, b, col, kind):
    sub = lv_df[lv_df.symbol == mkt]
    if col not in sub.columns:
        return []
    lm = {str(r.date): getattr(r, col) for r in sub.itertuples()
          if np.isfinite(getattr(r, col, np.nan))}
    out = []
    for d in sorted(set(b.date)):
        if d not in lm:
            continue
        day = b[b.date == d].reset_index(drop=True)
        if len(day) < 10:
            continue
        lvl = lm[d]
        H, L, Cl, O = day.High.values, day.Low.values, day.Close.values, day.Open.values
        # VIRGIN FIRST-TOUCH FROM THE CORRECT SIDE (S73, 2nd user-caught bug):
        #   resistance: session must OPEN BELOW the level AND price must not have
        #     reached it earlier -> first bar with High>=level = genuine rally into it.
        #   support: mirror (open above, first bar Low<=level).
        # Fill AT the level (limit order). No tolerance, no gap-above/re-approach.
        if (kind == "res" and O[0] >= lvl) or (kind == "sup" and O[0] <= lvl):
            continue
        ti = None
        for i in range(1, len(day)):
            reached_before = (np.max(H[:i]) >= lvl) if kind == "res" else (np.min(L[:i]) <= lvl)
            hit = (H[i] >= lvl) if kind == "res" else (L[i] <= lvl)
            if hit and not reached_before:
                ti = i
                break
        if ti is not None:
            out.append((d, day, lvl, ti))
    return out


def pnl(day, lvl, ti, stop, tgt, kind, fric):
    H, L, Cl = day.High.values, day.Low.values, day.Close.values
    for j in range(ti + 1, len(day)):
        if kind == "res":
            if H[j] >= lvl + stop:
                return -stop - fric
            if L[j] <= lvl - tgt:
                return tgt - fric
        else:
            if L[j] <= lvl - stop:
                return -stop - fric
            if H[j] >= lvl + tgt:
                return tgt - fric
    return ((lvl - Cl[-1]) if kind == "res" else (Cl[-1] - lvl)) - fric


def metrics(pts, mult, dates):
    p = np.array(pts) * mult
    n = len(p)
    wins, losses = p[p > 0], p[p < 0]
    eq = np.cumsum(p)
    dd = float((eq - np.maximum.accumulate(eq)).min())
    streak = mx = 0
    for x in p:
        streak = streak + 1 if x < 0 else 0
        mx = max(mx, streak)
    return {
        "n": n, "win_pct": round((p > 0).mean() * 100, 1),
        "avg_win": round(wins.mean()) if len(wins) else 0,
        "avg_loss": round(losses.mean()) if len(losses) else 0,
        "pf": round(wins.sum() / -losses.sum(), 2) if len(losses) else np.inf,
        "expectancy": round(p.mean()), "total": round(p.sum()), "maxdd": round(dd),
        "max_consec_loss": mx, "best": round(p.max()), "worst": round(p.min()),
        "sharpe_tr": round(p.mean() / p.std(), 2) if p.std() else 0,
        "months": len({d[:7] for d in dates}),
    }


def main():
    mkts = (sys.argv[sys.argv.index("--markets") + 1].split(",")
            if "--markets" in sys.argv else ["ES", "NQ", "GC", "CL", "YM"])
    tag = sys.argv[sys.argv.index("--tag") + 1] if "--tag" in sys.argv else ""
    run_ts = dt.datetime.now().strftime("%Y-%m-%d %H:%M")
    l1, l0 = levels()
    es_b = bars("ES")
    rows = []
    hdr = f"{'mkt':4s} {'lvl':4s} {'n':>4s} {'win%':>5s} {'PF':>5s} {'exp$':>6s} {'avgW':>6s} {'avgL':>6s} {'tot$':>9s} {'maxDD':>8s} {'cLoss':>5s} {'shrp':>5s} {'cells':>6s} {'IS$':>6s} {'OOS$':>6s}  verdict"
    print(f"\n=== SIM {run_ts}  stop8/tgt10 ref, range-scaled, {'/'.join(mkts)} ===")
    print(hdr)
    for mkt in mkts:
        b = bars(mkt)
        if b is None:
            print(f"{mkt:4s} — no bars")
            continue
        scale = range_scale(es_b, b)
        fric = FRIC_ES * scale
        mult = POINT[mkt]
        for col, kind in LEVELS:
            lv_df = l1 if col in ("cr", "ps") else l0
            ents = entries(lv_df, mkt, b, col, kind)
            if len(ents) < 10:
                print(f"{mkt:4s} {col:4s} {len(ents):4d}  (too few)")
                continue
            pos = sum(np.mean([pnl(d[1], d[2], d[3], s * scale, t * scale, kind, fric)
                               for d in ents]) > 0 for s in STOPS for t in TGTS)
            ref = [pnl(d[1], d[2], d[3], 8 * scale, 10 * scale, kind, fric) for d in ents]
            dts = [d[0] for d in ents]
            cut = sorted(dts)[int(len(dts) * 0.66)]
            isp = [pnl(d[1], d[2], d[3], 8 * scale, 10 * scale, kind, fric) for d in ents if d[0] <= cut]
            oos = [pnl(d[1], d[2], d[3], 8 * scale, 10 * scale, kind, fric) for d in ents if d[0] > cut]
            M = metrics(ref, mult, dts)
            is_e, oos_e = round(np.mean(isp) * mult), round(np.mean(oos) * mult)
            verdict = ("SURVIVES" if pos >= 31 and oos_e > 0 else
                       "fragile" if pos >= 22 else "REJECT")
            print(f"{mkt:4s} {col:4s} {M['n']:4d} {M['win_pct']:5.1f} {M['pf']:5.2f} "
                  f"{M['expectancy']:+6d} {M['avg_win']:+6d} {M['avg_loss']:+6d} {M['total']:+9,} "
                  f"{M['maxdd']:+8,} {M['max_consec_loss']:5d} {M['sharpe_tr']:5.2f} {pos:3d}/36 "
                  f"{is_e:+6d} {oos_e:+6d}  {verdict}")
            rows.append({"run": run_ts, "tag": tag, "market": mkt, "level": col, "dir": kind,
                         "cells_pos": pos, "is_exp": is_e, "oos_exp": oos_e,
                         "verdict": verdict, **M})
    if rows:
        df = pd.DataFrame(rows)
        LEDGER.parent.mkdir(parents=True, exist_ok=True)
        if LEDGER.exists():
            df = pd.concat([pd.read_csv(LEDGER), df], ignore_index=True)
        df.to_csv(LEDGER, index=False)
        print(f"\n{len(rows)} setups appended to {LEDGER}  (total {len(df)} rows in ledger)")


if __name__ == "__main__":
    main()
