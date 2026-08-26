"""wedge_entry_edge.py — does the MyWedge signal carry ANY directional edge?

Strips away the breakout mechanic: enter at the signal-bar CLOSE (first tick
after the signal), fixed stop S ticks, symmetric target (R x S). Runs BOTH the
signalled direction and the FADE on the identical in-session signal set (no
one-at-a-time, so with/fade are apples-to-apples). If 'with' wins >~53% the
signal points a direction; ~50% = no edge; fade >~53% = fade it.

RTH-only trove, LookBack=20, no slippage. Reuses the session-bounded alignment.

    python research/wedge/wedge_entry_edge.py [--R 1]
"""
from __future__ import annotations
import argparse
from pathlib import Path
import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
TROVE = ROOT / "data" / "ticks_continuous"
TICK = 0.25
TICK_USD = 12.5
INF = 1 << 60


def outcome(u, entryU, S, R):
    stopU = entryU - S * TICK
    tgt = entryU + R * S * TICK
    s = np.nonzero(u <= stopU)[0]; si = s[0] if s.size else INF
    th = np.nonzero(u >= tgt)[0]; ti = th[0] if th.size else INF
    if si == INF and ti == INF:
        return (u[-1] - entryU) / TICK
    if si <= ti:
        return -float(S)
    return float(R * S)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--csv", default=str(ROOT / "data" / "wedge" / "wedge_signals_ES_2000t_6mo.csv"))
    ap.add_argument("--R", type=float, default=1.0)
    ap.add_argument("--fee", type=float, default=4.0)
    a = ap.parse_args()

    STOPS = [6, 8, 10, 12, 15]
    acc = {(m, S): [] for m in ("with", "fade") for S in STOPS}

    for date, g in pd.read_csv(a.csv).assign(
            SignalTime=lambda d: pd.to_datetime(d["SignalTime"])).groupby("Date"):
        f = TROVE / f"{date}.parquet"
        if not f.exists():
            continue
        tv = pd.read_parquet(f, columns=["DateTime", "Price"])
        ttimes = pd.to_datetime(tv["DateTime"]).values.astype("datetime64[ns]")
        price = tv["Price"].to_numpy(dtype=float); n = len(price)
        if n < 2000:
            continue
        gg = g.sort_values("SignalTime")
        st = gg["SignalTime"].values.astype("datetime64[ns]")
        i0s = np.searchsorted(ttimes, st, side="left")
        valid = (st >= ttimes[0]) & (st <= ttimes[-1]) & (i0s < n)
        sig_side = np.where(gg["Signal"].to_numpy() == "BL", 1, -1)
        for k in range(len(gg)):
            if not valid[k]:
                continue
            i0 = int(i0s[k]); entry = price[i0]
            for m in ("with", "fade"):
                side = sig_side[k] if m == "with" else -sig_side[k]
                u = side * price[i0:n]
                for S in STOPS:
                    acc[(m, S)].append(outcome(u, side * entry, S, a.R))

    print(f"MyWedge directional-edge test — enter at signal close, stop S, target {a.R}xS")
    print(f"RTH, LookBack=20, fee ${a.fee}/RT, no slippage. n per cell shown.\n")
    print(f"{'mode':>5} {'stopS':>6} {'n':>6} {'win%':>6} {'$/tr':>8} {'PF':>6}")
    for m in ("with", "fade"):
        for S in STOPS:
            x = np.array(acc[(m, S)])
            win = (x > 0).mean() * 100
            net = x * TICK_USD - a.fee
            gw = net[net > 0].sum(); gl = -net[net < 0].sum()
            pf = gw / gl if gl else np.inf
            print(f"{m:>5} {S:>6} {len(x):>6} {win:>6.1f} {net.mean():>+8.2f} {pf:>6.3f}")
    print("\nread: 'with' win% ~50 and PF<1 across the board = signal has no "
          "directional edge at entry; fees then guarantee a loss.")


if __name__ == "__main__":
    main()
