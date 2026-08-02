#!/usr/bin/env python
"""mm50_tick_verify.py — S92-EA: verify the 50% MM trades against the actual TICK TAPE.

The 15M engine resolves same-bar stop/target ambiguity by assuming STOP FIRST. That could be
too pessimistic (or a fill could be unrealistic). This replays the real tick tape
(data/ticks_continuous/<day>.parquet, sub-ms) for each trade to get:
  - tick-accurate FILL (first tick that reaches the 50% limit after leg confirmation; if the
    61.8% stop is hit before the 50% is ever touched, the leg failed -> NO trade, like DH)
  - tick-accurate FIRST-TOUCH outcome (stop vs 123% target, exact order)
and compares to the 15M-bar outcome. Also renders one trade's actual tick path.

Usage: python scripts/mm50_tick_verify.py [YYYY-MM=2026-06] [N=3]
"""
from __future__ import annotations

import sys
from pathlib import Path
import glob as _glob

import numpy as np
import pandas as pd
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

ROOT = Path(__file__).resolve().parent.parent
MASTER_DIR = ROOT / "data" / "nt_internals" / "master"
TICKS = ROOT / "data" / "ticks_continuous"
FIG_DIR = ROOT / "eminiaddict" / "figures" / "mm50_audit"
sys.path.insert(0, str(ROOT / "scripts"))
from halsey_mm50_engine import build_15m  # noqa: E402


def tick_outcome(px, ts, conf_t, side, e50, stop, tgt):
    """Replay ticks from conf_t. Returns (why, R, fill_t, exit_t) or (None,..) if no fill."""
    m = ts >= np.datetime64(conf_t)
    px = px[m]; ts = ts[m]
    if len(px) == 0:
        return None, None, None, None
    rr = (tgt - e50) / (e50 - stop) if side == 1 else (e50 - tgt) / (stop - e50)
    # 1) fill: first tick reaching the 50% limit; but if stop hit first -> leg failed, no trade
    if side == 1:
        hit_fill = px <= e50
        hit_stop_pre = px <= stop
    else:
        hit_fill = px >= e50
        hit_stop_pre = px >= stop
    i_fill = hit_fill.argmax() if hit_fill.any() else -1
    i_spre = hit_stop_pre.argmax() if hit_stop_pre.any() else -1
    if i_fill < 0:
        return None, None, None, None
    if i_spre >= 0 and i_spre < i_fill:
        return None, None, None, None  # 61.8% broke before the 50% pullback filled
    fill_t = ts[i_fill]
    px2 = px[i_fill:]; ts2 = ts[i_fill:]
    if side == 1:
        stp = px2 <= stop; tp = px2 >= tgt
    else:
        stp = px2 >= stop; tp = px2 <= tgt
    i_st = stp.argmax() if stp.any() else 10**9
    i_tg = tp.argmax() if tp.any() else 10**9
    if i_st == 10**9 and i_tg == 10**9:
        R = side * (px2[-1] - e50) / abs(e50 - stop)
        return "mtm", R, fill_t, ts2[-1]
    if i_st <= i_tg:
        return "stop", -1.0, fill_t, ts2[i_st]
    return "target", rr, fill_t, ts2[i_tg]


def main():
    month = sys.argv[1] if len(sys.argv) > 1 else "2026-06"
    N = int(sys.argv[2]) if len(sys.argv) > 2 else 3
    g = build_15m(); dt = g["dt"]
    tr = pd.read_csv(sorted(_glob.glob(str(MASTER_DIR / "mm50_trades_*.csv")))[-1])
    tr = tr[tr.N == N].copy(); tr["dt"] = pd.to_datetime(tr["dt"])
    tr = tr[tr["dt"].dt.strftime("%Y-%m") == month].reset_index(drop=True)
    if tr.empty:
        print(f"! no N={N} trades in {month}"); return

    tick_cache = {}
    rows = []
    for _, t in tr.iterrows():
        conf_t = dt.iloc[int(t["conf"])]
        d = conf_t.date().isoformat()
        if d not in tick_cache:
            fp = TICKS / f"{d}.parquet"
            tick_cache[d] = pd.read_parquet(fp) if fp.exists() else None
        tk = tick_cache[d]
        base = {"dt": t["dt"], "side": "L" if t.side == 1 else "S", "why15": t.why,
                "R15": round(t.R, 2), "risk_tk": round(t.risk_pts * 4, 1),
                "e50": round(t.e50, 2), "stop": round(t.stop, 2), "tgt": round(t.tgt, 2)}
        if tk is None:
            rows.append({**base, "tick_why": "NO_TICKS", "tick_R": np.nan}); continue
        px = tk["Price"].to_numpy(); ts = tk["DateTime"].to_numpy()
        why, R, ft, xt = tick_outcome(px, ts, conf_t, int(t.side), t.e50, t.stop, t.tgt)
        rows.append({**base, "tick_why": (why if why is not None else "no_fill"),
                     "tick_R": round(R, 2) if R is not None else np.nan})
    c = pd.DataFrame(rows)
    filled = c[~c["tick_why"].isin(["NO_TICKS", "no_fill"])]
    print(f"=== TICK-ACCURATE VERIFICATION — {month}, N={N} ({len(c)} 15M trades) ===")
    with pd.option_context("display.max_columns", None, "display.width", 200):
        print(c.to_string(index=False))
    nofill = (c["tick_why"] == "no_fill").sum()
    agree = (filled["why15"] == filled["tick_why"]).sum()
    flips = filled[filled["why15"] != filled["tick_why"]]
    # honest expectancy: tick-accurate, no_fill trades = not taken (R contributes 0)
    tick_R_all = c["tick_R"].fillna(0.0)
    print(f"\nfilled at tick level: {len(filled)}/{len(c)}  | no-fill (61.8% broke before 50%): "
          f"{nofill}")
    print(f"outcome agreement (filled trades): {agree}/{len(filled)}  | flips: {len(flips)}")
    if len(flips):
        print("  FLIPPED trades (15M -> tick):")
        for _, f in flips.iterrows():
            print(f"    {pd.Timestamp(f['dt'])}  {f['side']}  {f['why15']}({f['R15']:+.1f}R) "
                  f"-> {f['tick_why']}({f['tick_R']:+.1f}R)  risk {f['risk_tk']}tk")
    print(f"\nMEAN R over all {len(c)} 15M signals:")
    print(f"  15M-bar backtest : {c['R15'].mean():+.3f}R")
    print(f"  TICK-accurate    : {tick_R_all.mean():+.3f}R   "
          f"(no-fill counted as 0 = trade not taken)")
    print("  If tick << 15M, the 15M backtest is OPTIMISTIC (intrabar path / phantom targets).")

    # render actual tick path for the first tick-target winner (or first filled trade)
    show = filled[filled["tick_why"] == "target"]
    show = show if len(show) else filled
    if len(show):
        t = show.iloc[0]
        d = pd.Timestamp(t["dt"]).date().isoformat()
        tk = tick_cache[d]
        conf_t = None
        # find matching conf time for chart window
        row = tr[tr["dt"] == t["dt"]].iloc[0]
        conf_t = dt.iloc[int(row.conf)]
        w = tk[(tk["DateTime"] >= conf_t) &
               (tk["DateTime"] <= conf_t + pd.Timedelta(hours=6))]
        fig, ax = plt.subplots(figsize=(15, 7), facecolor="#0b0b0b")
        ax.set_facecolor("#0b0b0b"); ax.tick_params(colors="#aaa")
        for sp in ax.spines.values():
            sp.set_color("#333")
        ax.plot(w["DateTime"], w["Price"], color="#ddd", lw=0.7)
        for lv, col, lab in [(t["e50"], "#ffd400", "50% entry"), (t["stop"], "#e2453c", "61.8% stop"),
                             (t["tgt"], "#22d3ee", "123% target")]:
            ax.axhline(lv, color=col, lw=1.2, ls="--")
            ax.annotate(lab, (w["DateTime"].iloc[0], lv), color=col, fontsize=9, va="bottom")
        ax.set_title(f"ACTUAL TICK PATH — {t['side']} 50% MM {d}  (15M said {t['why15']}, "
                     f"tick says {t['tick_why']} {t['tick_R']:+.1f}R)", color="#eee", loc="left")
        FIG_DIR.mkdir(parents=True, exist_ok=True)
        out = FIG_DIR / f"tickpath_{d}.png"
        fig.tight_layout(); fig.savefig(out, dpi=115, facecolor=fig.get_facecolor()); plt.close(fig)
        print(f"\nwrote tick-path chart {out.relative_to(ROOT)}")
    c.to_csv(FIG_DIR / f"tickverify_{month}_N{N}.csv", index=False)


if __name__ == "__main__":
    main()
