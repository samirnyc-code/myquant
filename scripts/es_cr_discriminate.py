"""What separates WINNING CR-fades from LOSERS? (S73, user: 'compare W vs L location,
get creative'). For the 18 neg-GEX-morning CR fades, compute a rich feature set from
the 5M bars + our data, then rank features by how well they split wins from losses.

Goal: find a conditioning filter that lifts the 55% base win-rate — turn a marginal
edge into a real one.

Run: .venv/Scripts/python.exe scripts/es_cr_discriminate.py
"""
import json
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
STOP, TGT, FRIC, CUTOFF = 5.0, 10.0, 1.25, "10:30"


def load():
    lv = pd.read_csv(ROOT / "data" / "menthorq" / "levels_history.csv")
    lv = lv[lv.symbol == "ES"].copy(); lv["date"] = lv.date.astype(str)
    b = pd.read_parquet(ROOT / "data" / "bars" / "_continuous_unadj.parquet")
    b["DateTime"] = pd.to_datetime(b["DateTime"]); b["date"] = b.DateTime.dt.strftime("%Y-%m-%d")
    b["hm"] = b.DateTime.dt.strftime("%H:%M")
    gi = pd.read_csv(ROOT / "data" / "menthorq" / "gex_insights_ES1.csv").sort_values("date")
    gi["date"] = gi.date.astype(str)
    qs = pd.read_csv(ROOT / "data" / "menthorq" / "qscore_ES1.csv")
    qs["date"] = qs.date.astype(str)
    qs = {r.date: r for r in qs.itertuples()}
    return lv, b, gi, qs


def features_and_outcome(day, cr, ps, hvl, gex, qrow, prev_close):
    npre = int((day.hm <= CUTOFF).sum())
    H, L, O, Cl = day.High.values, day.Low.values, day.Open.values, day.Close.values
    ti = next((i for i in range(npre) if L[i] - 1.0 <= cr <= H[i] + 1.0), None)
    if ti is None:
        return None
    # outcome (short fade)
    stop_px, tgt_px = cr + STOP, cr - TGT
    reason = "close"; xi = len(day) - 1
    for j in range(ti + 1, len(day)):
        if H[j] >= stop_px:
            reason = "stop"; xi = j; break
        if L[j] <= tgt_px:
            reason = "target"; xi = j; break
    pnl = (cr - {"stop": stop_px, "target": tgt_px, "close": Cl[xi]}[reason]) - FRIC
    win = 1 if pnl > 0 else 0
    o0 = O[0]
    atr = np.mean(H[:max(ti, 1)] - L[:max(ti, 1)])          # morning avg range to touch
    # approach momentum: how much price climbed in the 6 bars before the touch
    k = max(0, ti - 6)
    approach = cr - L[k:ti + 1].min() if ti > 0 else 0
    up_bars = int(np.sum(Cl[k:ti] > O[k:ti])) if ti > k else 0
    feats = {
        "gex_M": round(gex / 1e6, 1),
        "cr_minus_open": round(cr - o0, 1),
        "cr_minus_open_atr": round((cr - o0) / atr, 2) if atr else 0,
        "cr_minus_hvl": round(cr - hvl, 1) if np.isfinite(hvl) else np.nan,
        "cr_minus_prevclose": round(cr - prev_close, 1) if prev_close else np.nan,
        "gap": round(o0 - prev_close, 1) if prev_close else np.nan,
        "touch_bar": ti,
        "touch_min": ti * 5,
        "morning_atr": round(atr, 2),
        "approach_pts": round(approach, 1),
        "approach_bars_up": up_bars,
        "q_momentum": getattr(qrow, "momentum", np.nan) if qrow is not None else np.nan,
        "q_volatility": getattr(qrow, "volatility", np.nan) if qrow is not None else np.nan,
        "q_option": getattr(qrow, "option", np.nan) if qrow is not None else np.nan,
        "open_above_hvl": int(o0 > hvl) if np.isfinite(hvl) else np.nan,
    }
    return feats, win, pnl, reason


def main():
    lv, bars, gi, qs = load()
    levels = {r.date: r for r in lv.itertuples()}
    days = sorted(d for d in set(bars.date) if d in levels)
    rows = []
    prev_close = None
    for d in days:
        day = bars[bars.date == d].reset_index(drop=True)
        pc = prev_close
        prev_close = day.Close.values[-1]
        if len(day) < 10 or not np.isfinite(levels[d].cr):
            continue
        p = gi[gi.date < d]
        if p.empty or p.iloc[-1].gex >= 0:      # neg-GEX only
            continue
        res = features_and_outcome(day, levels[d].cr, levels[d].ps, levels[d].hvl,
                                   p.iloc[-1].gex, qs.get(d), pc)
        if res:
            f, win, pnl, reason = res
            rows.append({"date": d, "win": win, "pnl_usd": round(pnl * 50), "exit": reason, **f})
    df = pd.DataFrame(rows)
    df.to_csv(ROOT / "data" / "options_sim" / "cr_fade_features.csv", index=False)
    W, L = df[df.win == 1], df[df.win == 0]
    print(f"{len(df)} neg-GEX fades: {len(W)} wins / {len(L)} losses  "
          f"(total ${df.pnl_usd.sum():+,})\n")

    feat_cols = [c for c in df.columns if c not in ("date", "win", "pnl_usd", "exit")]
    print(f"{'feature':20s} {'WIN avg':>9s} {'LOSS avg':>9s} {'separation':>11s}")
    ranked = []
    for c in feat_cols:
        w, l = W[c].dropna(), L[c].dropna()
        if len(w) < 3 or len(l) < 3:
            continue
        pooled = df[c].std()
        sep = (w.mean() - l.mean()) / pooled if pooled else 0
        ranked.append((abs(sep), c, w.mean(), l.mean(), sep))
    for _, c, wm, lm, sep in sorted(ranked, reverse=True):
        flag = "  <== strong" if abs(sep) > 0.7 else ("  <= " if abs(sep) > 0.45 else "")
        print(f"{c:20s} {wm:9.2f} {lm:9.2f} {sep:+11.2f}{flag}")

    # test the top discriminator as a filter
    print("\n--- candidate refined filters ---")
    for c, op, thr in [("cr_minus_open_atr", ">", None), ("approach_pts", ">", None),
                       ("touch_min", "<", None), ("cr_minus_hvl", ">", None)]:
        med = df[c].median()
        hi = df[df[c] > med]
        lo = df[df[c] <= med]
        if len(hi) >= 4 and len(lo) >= 4:
            print(f"  {c} > {med:.1f}:  n{len(hi)} win {hi.win.mean()*100:.0f}% ${hi.pnl_usd.sum():+,}"
                  f"   | <= : n{len(lo)} win {lo.win.mean()*100:.0f}% ${lo.pnl_usd.sum():+,}")


if __name__ == "__main__":
    main()
