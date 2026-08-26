"""wedge_exit_sweep.py — single-contract exit policies on the MyWedge signals.

Same entry/stop/alignment/fill model as wedge_structure_pnl.py, but 1 CONTRACT
and it compares several exit policies head to head, each with its OWN
one-at-a-time filtering (so trade counts differ — a 4t target frees up for the
next signal sooner than a trailer):

  fixed targets : exit the single lot at +T ticks (T = 4,5,6,7,8), stop = SB
  trail         : no target; stop -> BE at +BETrig, then 1t beyond each closed
                  2000t bar

Fee: 1 contract RT (default $4). RTH-only (trove), LookBack=20 (correct value),
no slippage (optimistic). NT8 Strategy Analyzer is ground truth.

    python research/wedge/wedge_exit_sweep.py [--fee 4] [--betrig 5] [--trail 1]
"""
from __future__ import annotations
import argparse
from pathlib import Path
from datetime import datetime
import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
TROVE = ROOT / "data" / "ticks_continuous"
TICK = 0.25
TICK_USD = 12.5
BAR = 2000
INF = 1 << 60


def eval_fixed(T):
    def f(u, entryU, stopU):
        m = len(u)
        s = np.nonzero(u <= stopU)[0]; si = s[0] if s.size else INF
        th = np.nonzero(u >= entryU + T * TICK)[0]; ti = th[0] if th.size else INF
        if si == INF and ti == INF:
            return (u[-1] - entryU) / TICK, m - 1
        if si <= ti:
            return (stopU - entryU) / TICK, int(si)
        return float(T), int(ti)
    return f


def eval_trail(betrig, trail):
    def f(u, entryU, stopU):
        t = TICK; m = len(u)
        s = np.nonzero(u <= stopU)[0]; si = s[0] if s.size else INF
        be = np.nonzero(u >= entryU + betrig * t)[0]; bi = be[0] if be.size else INF
        if si < bi:
            return (stopU - entryU) / t, int(si)
        if bi == INF:
            return (u[-1] - entryU) / t, m - 1
        run_stop = max(stopU, entryU); i = int(bi); ri = None
        while i < m:
            bar_end = ((i // BAR) + 1) * BAR
            blk = u[i:min(bar_end, m)]
            h = np.nonzero(blk <= run_stop)[0]
            if h.size:
                ri = i + int(h[0]); break
            if bar_end <= m:
                bstart = max(bar_end - BAR, 0)
                run_stop = max(run_stop, u[bstart:bar_end].min() - trail * t)
            i = bar_end
        if ri is None:
            return (u[-1] - entryU) / t, m - 1
        return (run_stop - entryU) / t, ri
    return f


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--csv", default=str(ROOT / "data" / "wedge" / "wedge_signals_ES_2000t_6mo.csv"))
    ap.add_argument("--off", type=int, default=1)
    ap.add_argument("--fee", type=float, default=4.0, help="$ RT per contract")
    ap.add_argument("--betrig", type=int, default=5)
    ap.add_argument("--trail", type=int, default=1)
    a = ap.parse_args()

    policies = {f"fix{T}t": eval_fixed(T) for T in (4, 5, 6, 7, 8)}
    policies["trail"] = eval_trail(a.betrig, a.trail)
    res = {k: [] for k in policies}

    sig = pd.read_csv(a.csv)
    sig["SignalTime"] = pd.to_datetime(sig["SignalTime"])
    off = a.off * TICK

    for date, g in sig.groupby("Date"):
        f = TROVE / f"{date}.parquet"
        if not f.exists():
            continue
        tv = pd.read_parquet(f, columns=["DateTime", "Price"])
        ttimes = pd.to_datetime(tv["DateTime"]).values.astype("datetime64[ns]")
        price = tv["Price"].to_numpy(dtype=float)
        n = len(price)
        if n < BAR:
            continue
        gg = g.sort_values("SignalTime")
        st = gg["SignalTime"].values.astype("datetime64[ns]")
        i0s = np.searchsorted(ttimes, st, side="left")
        inwin = (i0s < n) & (i0s >= 0)
        if inwin.sum() == 0:
            continue
        med_off = float(np.median(gg["Close"].to_numpy()[inwin] - price[np.clip(i0s[inwin], 0, n - 1)]))

        sides = np.where(gg["Signal"].to_numpy() == "BL", 1, -1)
        highs = gg["High"].to_numpy(); lows = gg["Low"].to_numpy()
        entries = np.where(sides == 1, highs + off, lows - off) - med_off
        stops = np.where(sides == 1, lows - off, highs + off) - med_off

        for name, fn in policies.items():
            busy = -1
            for k in range(len(gg)):
                i0 = int(i0s[k])
                if i0 >= n or i0 <= busy:
                    continue
                side = int(sides[k]); entry = entries[k]; stop0 = stops[k]
                w = price[i0:min(i0 + BAR, n)]
                reach = np.nonzero((side * w) >= (side * entry))[0]
                if reach.size == 0:
                    continue
                fill = i0 + int(reach[0])
                u = side * price[fill:n]
                ticks, life = fn(u, side * entry, side * stop0)
                busy = fill + life
                res[name].append(ticks)

    rows = []
    for name, arr in res.items():
        x = np.array(arr, dtype=float)
        if x.size == 0:
            continue
        net = x * TICK_USD - a.fee
        gw = net[net > 0].sum(); gl = -net[net < 0].sum()
        rows.append({
            "policy": name, "trades": x.size,
            "win%": round((x > 0).mean() * 100, 1),
            "avg_t": round(x.mean(), 3),
            "net_$": round(net.sum()),
            "$/trade": round(net.mean(), 2),
            "PF": round(gw / gl, 3) if gl else np.inf,
        })
    out = pd.DataFrame(rows)
    print(f"Single-contract exit sweep — RTH tick-sim, fee ${a.fee}/RT, no slippage")
    print(f"(entry 1t beyond SB, stop 1t beyond SB; trail = BE@+{a.betrig}t then {a.trail}t/bar)\n")
    print(out.to_string(index=False))

    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    p = ROOT / "research" / "wedge" / f"wedge_exit_sweep_{stamp}"
    out.to_csv(f"{p}.csv", index=False)
    Path(f"{p}.txt").write_text(out.to_string(index=False), encoding="utf-8")
    print(f"\nsaved: {p.relative_to(ROOT)}.csv/.txt")


if __name__ == "__main__":
    main()
