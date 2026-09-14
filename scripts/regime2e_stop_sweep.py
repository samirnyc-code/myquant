"""Stop-multiplier sweep for the 2E book — WITH an out-of-sample check.

One pass over the real-tick trove emits, per gate-passing 2E entry (independent
book, not flip — so the entry set is fixed and the stop can be swept cleanly):
    mae_pts  = worst adverse excursion from entry (heat)   -> did stop S get hit?
    eod_move = favorable move entry->session close          -> P&L if not stopped
    adr10    = that day's ADR (stop = m x ADR10, 8t floor)
Then P&L(S) = -S if mae>=S else eod_move  (stop fills on touch; EOD else).

Sweeps m in a grid, reports net/PF/win/expectancy/maxDD (net of $17.50/tr, 1 ES),
the NEIGHBOURHOOD (is 0.30 a smooth plateau or a lucky spike?), and a
TRAIN(2021-23) / TEST(2024-26) split: pick best m on train, report its test rank.
Overfit tell = the in-sample-best m is NOT near the OOS-best m.

  python scripts/regime2e_stop_sweep.py [--limit N]
Output: reports/regime2e/stop_sweep_entries.csv + stop_sweep.png + stdout.
"""
import sys
from collections import deque
from pathlib import Path

import numpy as np
import pandas as pd
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

TICK = 0.25; MULT = 50.0; COST = 17.5; FLOOR_T = 8
GAP_MAX = 0.54; SMA_N = 20; ADR_N = 10; TREND_MULT = 1.6
GRID = [0.15, 0.20, 0.25, 0.30, 0.35, 0.40, 0.50, 0.60, 0.80, 1.00, 99.0]  # 99 = no stop (EOD)
REPO = Path(__file__).resolve().parent.parent
TICKD = REPO / "data" / "ticks_continuous"
OUTDIR = REPO / "reports" / "regime2e"

sys.path.insert(0, str(REPO / "scripts"))
from regime2e_nt_diff import day_frames                          # noqa: E402
from regime2e_flip_scale_sim import signals_for_day             # noqa: E402


def emit_entries(limit=None):
    dates = sorted(p.stem for p in TICKD.glob("2*.parquet"))
    if limit:
        dates = dates[-limit:]
    ranges = deque(maxlen=ADR_N); closes = deque(maxlen=SMA_N)
    prev_close = prev_range = None
    rows = []
    for d in dates:
        g, tP, tbar = day_frames(d)
        if g is None or len(g) < 30:
            continue
        day_hi, day_lo = float(np.max(tP)), float(np.min(tP))
        day_cl, day_op = float(tP[-1]), float(tP[0])
        adr_prior = np.mean(ranges) if len(ranges) == ADR_N else None
        tdy = (prev_range > TREND_MULT * adr_prior) if (adr_prior is not None and prev_range is not None) else None
        if prev_range is not None:
            ranges.append(prev_range)
        if prev_close is not None:
            closes.append(prev_close)
        sma20 = np.mean(closes) if len(closes) == SMA_N else None
        adr10 = np.mean(ranges) if len(ranges) == ADR_N else None
        if not (adr10 is None or sma20 is None or prev_close is None or tdy is None):
            if abs(day_op - prev_close) / prev_close * 100.0 <= GAP_MAX and not tdy:
                for jfl, dr, lim in signals_for_day(g, tP, tbar, sma20, adr10):
                    seg = tP[jfl:]
                    short = dr == "S"
                    mae = float(lim - seg.min()) if not short else float(seg.max() - lim)
                    eod = float(seg[-1] - lim) if not short else float(lim - seg[-1])
                    rows.append(dict(date=d, yr=int(d[:4]), dir=dr,
                                     mae=round(mae, 2), eod=round(eod, 2), adr10=round(adr10, 3)))
        prev_close, prev_range = day_cl, day_hi - day_lo
    return pd.DataFrame(rows)


def pnl_for(df, m):
    if m >= 99:
        pts = df["eod"].values.copy()                       # no stop
    else:
        S = np.maximum(np.round(m * df["adr10"].values / TICK) * TICK, FLOOR_T * TICK)
        pts = np.where(df["mae"].values >= S, -S, df["eod"].values)
    return pts * MULT - COST


def stats(v):
    w = v[v > 0]; l = v[v <= 0]
    pf = w.sum() / -l.sum() if len(l) and l.sum() < 0 else float("inf")
    return v.sum(), pf, 100 * (v > 0).mean(), v.mean()


def main():
    limit = int(sys.argv[sys.argv.index("--limit") + 1]) if "--limit" in sys.argv else None
    df = emit_entries(limit)
    OUTDIR.mkdir(parents=True, exist_ok=True)
    df.to_csv(OUTDIR / "stop_sweep_entries.csv", index=False)
    print(f"{len(df)} independent 2E entries, {df.yr.min()}-{df.yr.max()}\n")

    print(f"{'stop':>6} {'net$':>9} {'PF':>5} {'win%':>5} {'exp$':>6}  full history")
    res = []
    for m in GRID:
        v = pnl_for(df, m)
        net, pf, win, exp = stats(v)
        eq = np.cumsum(v); mdd = (eq - np.maximum.accumulate(eq)).min()
        res.append((m, net, pf, mdd))
        tag = "no-stop" if m >= 99 else f"{m:.2f}xADR"
        star = "  <- current spec" if abs(m - 0.30) < 1e-6 else ""
        print(f"{tag:>6} {net:>+9,.0f} {pf:>5.2f} {win:>5.0f} {exp:>+6.0f}  maxDD ${mdd:>+8,.0f}{star}")

    # train/test overfit check
    tr = df[df.yr <= 2023]; te = df[df.yr >= 2024]
    grid_real = [m for m in GRID if m < 99]
    tr_best = max(grid_real, key=lambda m: stats(pnl_for(tr, m))[1])   # best PF in-sample
    te_best = max(grid_real, key=lambda m: stats(pnl_for(te, m))[1])
    print("\nOUT-OF-SAMPLE CHECK (train 2021-23, test 2024-26), ranked by PF:")
    print(f"  best stop in TRAIN  = {tr_best:.2f}xADR  (train PF {stats(pnl_for(tr,tr_best))[1]:.2f})")
    print(f"  that stop on TEST   = PF {stats(pnl_for(te,tr_best))[1]:.2f}  net ${stats(pnl_for(te,tr_best))[0]:+,.0f}")
    print(f"  best stop in TEST   = {te_best:.2f}xADR  (would-be hindsight)")
    print(f"  spec 0.30 on TRAIN PF {stats(pnl_for(tr,0.30))[1]:.2f} / TEST PF {stats(pnl_for(te,0.30))[1]:.2f}")
    verdict = ("SMOOTH/robust — train-best ~ 0.30 spec" if abs(tr_best - 0.30) <= 0.10
               else f"train-best {tr_best:.2f} differs from 0.30 -> optimizing risks overfit")
    print(f"  verdict: {verdict}")

    # graphic
    ms = [m if m < 99 else (GRID[-2] + 0.2) for m in GRID]
    fig, ax = plt.subplots(1, 2, figsize=(13, 5))
    ax[0].plot([r[0] if r[0] < 99 else ms[-1] for r in res], [r[1] for r in res], "o-", color="#1565c0")
    ax[0].axvline(0.30, color="#c62828", ls="--", label="0.30 spec")
    ax[0].set_title("PF vs stop multiplier (full history)"); ax[0].set_xlabel("stop x ADR"); ax[0].set_ylabel("PF"); ax[0].legend()
    for lbl, sub, c in [("train 21-23", tr, "#ef6c00"), ("test 24-26", te, "#2e7d32")]:
        ax[1].plot(grid_real, [stats(pnl_for(sub, m))[1] for m in grid_real], "o-", label=lbl, color=c)
    ax[1].axvline(0.30, color="#c62828", ls="--"); ax[1].set_title("PF vs stop — train vs test")
    ax[1].set_xlabel("stop x ADR"); ax[1].set_ylabel("PF"); ax[1].legend()
    fig.tight_layout(); fig.savefig(OUTDIR / "stop_sweep.png", dpi=110)
    print(f"\ngraphic: {OUTDIR / 'stop_sweep.png'}")


if __name__ == "__main__":
    main()
