"""wedge_mgmt_lab.py — creative single-contract management search on MyWedge.

Same entry (stop 1t beyond SB) + alignment/fill model as the other wedge sims.
1 contract. Compares many EXIT-MANAGEMENT schemes head to head, each run with
realistic one-at-a-time filling, then dissects the winner by time-of-day and
signal-bar size. Every policy also gets a 1-tick slippage haircut so we don't
fall in love with a no-slippage mirage.

Schemes:
  pure_dN      structural trail from entry: stop starts at SB, ratchets to
               (bar_low - N t) beyond each closed 2000t bar. No BE step.
  beB_dN       hold SB stop until +B t, jump to breakeven, then trail N t/bar.
  R{k}         fixed target at k x (initial stop distance), SB stop. Target
               scales to the bar's risk instead of a flat tick count.
  capC_*       same but the initial stop is capped to C ticks (tighter stop).

Caveats unchanged: RTH-only trove, LookBack=20 (correct), python approx,
no-slippage base case. NT8 Strategy Analyzer is ground truth.

    python research/wedge/wedge_mgmt_lab.py [--fee 4]
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


def _cap(entryU, stopU, cap):
    return entryU - cap * TICK if cap else stopU   # u-frame: closer to entry = higher


def pure(trail, cap=None):
    def f(u, entryU, stopU):
        stopU = max(stopU, _cap(entryU, stopU, cap))
        m = len(u); run = stopU; i = 0; ri = None
        while i < m:
            be = ((i // BAR) + 1) * BAR
            blk = u[i:min(be, m)]; h = np.nonzero(blk <= run)[0]
            if h.size:
                ri = i + int(h[0]); break
            if be <= m:
                run = max(run, u[max(be - BAR, 0):be].min() - trail * TICK)
            i = be
        if ri is None:
            return (u[-1] - entryU) / TICK, m - 1
        return (run - entryU) / TICK, ri
    return f


def be_then_trail(be_t, trail, cap=None):
    def f(u, entryU, stopU):
        stopU = max(stopU, _cap(entryU, stopU, cap))
        t = TICK; m = len(u)
        s = np.nonzero(u <= stopU)[0]; si = s[0] if s.size else INF
        bh = np.nonzero(u >= entryU + be_t * t)[0]; bi = bh[0] if bh.size else INF
        if si < bi:
            return (stopU - entryU) / t, int(si)
        if bi == INF:
            return (u[-1] - entryU) / t, m - 1
        run = max(stopU, entryU); i = int(bi); ri = None
        while i < m:
            be = ((i // BAR) + 1) * BAR
            blk = u[i:min(be, m)]; h = np.nonzero(blk <= run)[0]
            if h.size:
                ri = i + int(h[0]); break
            if be <= m:
                run = max(run, u[max(be - BAR, 0):be].min() - trail * t)
            i = be
        if ri is None:
            return (u[-1] - entryU) / t, m - 1
        return (run - entryU) / t, ri
    return f


def rtarget(k, cap=None):
    def f(u, entryU, stopU):
        stopU = max(stopU, _cap(entryU, stopU, cap))
        m = len(u); dist = entryU - stopU
        tgt = entryU + k * dist
        s = np.nonzero(u <= stopU)[0]; si = s[0] if s.size else INF
        th = np.nonzero(u >= tgt)[0]; ti = th[0] if th.size else INF
        if si == INF and ti == INF:
            return (u[-1] - entryU) / TICK, m - 1
        if si <= ti:
            return (stopU - entryU) / TICK, int(si)
        return (tgt - entryU) / TICK, int(ti)
    return f


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--csv", default=str(ROOT / "data" / "wedge" / "wedge_signals_ES_2000t_6mo.csv"))
    ap.add_argument("--off", type=int, default=1)
    ap.add_argument("--fee", type=float, default=4.0)
    a = ap.parse_args()

    policies = {
        "pure_d1": pure(1), "pure_d2": pure(2), "pure_d3": pure(3),
        "be3_d1": be_then_trail(3, 1), "be5_d1": be_then_trail(5, 1),
        "be8_d1": be_then_trail(8, 1), "be12_d1": be_then_trail(12, 1),
        "be5_d2": be_then_trail(5, 2), "be5_d3": be_then_trail(5, 3),
        "be8_d2": be_then_trail(8, 2), "be8_d3": be_then_trail(8, 3),
        "R1.0": rtarget(1.0), "R1.5": rtarget(1.5), "R2.0": rtarget(2.0), "R3.0": rtarget(3.0),
        "cap10_be5_d2": be_then_trail(5, 2, cap=10), "cap8_pure_d2": pure(2, cap=8),
        "cap10_R1.5": rtarget(1.5, cap=10),
    }
    res = {k: [] for k in policies}          # each: list of (hour, stop_t, ticks)
    off = a.off * TICK

    for date, g in pd.read_csv(a.csv).assign(
            SignalTime=lambda d: pd.to_datetime(d["SignalTime"])).groupby("Date"):
        f = TROVE / f"{date}.parquet"
        if not f.exists():
            continue
        tv = pd.read_parquet(f, columns=["DateTime", "Price"])
        ttimes = pd.to_datetime(tv["DateTime"]).values.astype("datetime64[ns]")
        price = tv["Price"].to_numpy(dtype=float); n = len(price)
        if n < BAR:
            continue
        gg = g.sort_values("SignalTime")
        st = gg["SignalTime"].values.astype("datetime64[ns]")
        i0s = np.searchsorted(ttimes, st, side="left")
        # only signals whose timestamp is INSIDE the trove session; a pre-open
        # signal would otherwise searchsorted to index 0 and get simulated from
        # the RTH open with a bogus offset (phantom overnight trades).
        valid = (st >= ttimes[0]) & (st <= ttimes[-1]) & (i0s < n)
        if valid.sum() == 0:
            continue
        med_off = float(np.median(gg["Close"].to_numpy()[valid] - price[np.clip(i0s[valid], 0, n - 1)]))
        sides = np.where(gg["Signal"].to_numpy() == "BL", 1, -1)
        highs = gg["High"].to_numpy(); lows = gg["Low"].to_numpy()
        entries = np.where(sides == 1, highs + off, lows - off) - med_off
        stops = np.where(sides == 1, lows - off, highs + off) - med_off
        hours = gg["SignalTime"].dt.hour.to_numpy()
        stopt = np.abs(entries - stops) / TICK

        for name, fn in policies.items():
            busy = -1
            for k in range(len(gg)):
                i0 = int(i0s[k])
                if i0 >= n or i0 <= busy or not valid[k]:
                    continue
                side = int(sides[k])
                w = price[i0:min(i0 + BAR, n)]
                reach = np.nonzero((side * w) >= (side * entries[k]))[0]
                if reach.size == 0:
                    continue
                fill = i0 + int(reach[0])
                u = side * price[fill:n]
                ticks, life = fn(u, side * entries[k], side * stops[k])
                busy = fill + life
                res[name].append((int(hours[k]), float(stopt[k]), float(ticks)))

    rows = []
    for name, lst in res.items():
        if not lst:
            continue
        arr = np.array(lst)
        tk = arr[:, 2]; net = tk * TICK_USD - a.fee
        gw = net[net > 0].sum(); gl = -net[net < 0].sum()
        tval = tk.mean() / (tk.std(ddof=1) / np.sqrt(len(tk))) if tk.std() > 0 else 0
        rows.append({
            "policy": name, "trades": len(tk), "win%": round((tk > 0).mean() * 100, 1),
            "avg_t": round(tk.mean(), 3), "$/tr": round(net.mean(), 2),
            "$/tr@slip1t": round((tk.mean() - 1) * TICK_USD - a.fee, 2),
            "net_$": int(net.sum()), "PF": round(gw / gl, 3) if gl else np.inf,
            "t_stat": round(tval, 2),
        })
    lb = pd.DataFrame(rows).sort_values("$/tr", ascending=False)
    print(f"Single-contract management lab — RTH tick-sim, fee ${a.fee}/RT")
    print("(t_stat = mean/SE of per-trade ticks; |t|>~2 = distinguishable from 0)\n")
    print(lb.to_string(index=False))

    best = lb.iloc[0]["policy"]
    barr = np.array(res[best])
    print(f"\n=== winner '{best}' — by TIME OF DAY (CT) ===")
    for h in sorted(set(barr[:, 0].astype(int))):
        sub = barr[barr[:, 0] == h][:, 2]
        net = sub * TICK_USD - a.fee
        print(f"  {h:02d}:00  n={len(sub):4d}  $/tr {net.mean():+7.2f}  win {(sub>0).mean()*100:4.1f}%")
    print(f"\n=== winner '{best}' — by SIGNAL-BAR STOP SIZE ===")
    for lo, hi, lab in [(0, 10, "<=10t"), (10, 14, "11-14t"), (14, 20, "15-20t"), (20, 999, ">20t")]:
        sub = barr[(barr[:, 1] > lo) & (barr[:, 1] <= hi)][:, 2]
        if len(sub):
            net = sub * TICK_USD - a.fee
            print(f"  {lab:>7}  n={len(sub):4d}  $/tr {net.mean():+7.2f}  win {(sub>0).mean()*100:4.1f}%")

    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    lb.to_csv(ROOT / "research" / "wedge" / f"wedge_mgmt_lab_{stamp}.csv", index=False)
    print(f"\nsaved: research/wedge/wedge_mgmt_lab_{stamp}.csv")


if __name__ == "__main__":
    main()
