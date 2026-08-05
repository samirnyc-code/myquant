"""
Target/stop grid sweep for the tick2000 random stop-entry engine.

Engine identical to run_tick2000_random.py "random" variant (direction = coin
flip, EMA ignored): 2000-tick RTH bars, stop entry 1 tick beyond signal bar
(valid next bar only), target limit needs 1-tick tick-through, stop fills on
touch, one position at a time, EOD flatten, 2-5 fills/day target.

Sweep: targets x stops in {2,3,4,6,8,12,16,24} ticks (64 combos).
To make combos directly comparable, the random attempt schedule (bars +
directions + daily fill target) is drawn ONCE per day and shared by all combos;
only exit structure differs (position-overlap skips can still differ).

Fee: $4 RT on ES big ($12.50/tick).

Outputs (dated): sweep_tick2000_grid_<stamp>.csv + pivot table in
sweep_tick2000_grid_<stamp>.txt
"""
import numpy as np
import pandas as pd
from pathlib import Path
from datetime import datetime

ROOT = Path(r"c:\Users\Admin\myquant")
TICK_DIR = ROOT / "data" / "ticks_continuous"
OUT_DIR = Path(__file__).parent

BAR = 2000
T = 0.25
WARMUP = 21           # same bar universe as the EMA runs
SEED = 42
FEE_RT = 4.0
TICK_USD = 12.5
GRID = [2, 3, 4, 6, 8, 12, 16, 24]   # ticks, both axes
MAX_CANDIDATES = 14   # candidate bars drawn per day (covers cancels/skips)
CHUNK = 4096


def first_exit(prices, start, side, target, stoploss):
    """Chunked scan from `start`: returns (exit_rel_index, exit_px, reason)."""
    n = len(prices)
    i = start
    while i < n:
        seg = prices[i:i + CHUNK]
        if side == 1:
            t_mask = seg >= target + T          # tick-through
            s_mask = seg <= stoploss            # touch
        else:
            t_mask = seg <= target - T
            s_mask = seg >= stoploss
        t_any, s_any = t_mask.any(), s_mask.any()
        if t_any or s_any:
            t_first = np.argmax(t_mask) if t_any else np.inf
            s_first = np.argmax(s_mask) if s_any else np.inf
            if t_first < s_first:
                return i + int(t_first), target, "target"
            px = seg[int(s_first)]
            exit_px = min(px, stoploss) if side == 1 else max(px, stoploss)
            return i + int(s_first), exit_px, "stop"
        i += CHUNK
    return n - 1, prices[-1], "eod"


def day_schedule(nbars, rng):
    """Shared random schedule: fill target + candidate (bar, side) list."""
    n_target = int(rng.integers(2, 6))
    eligible = np.arange(WARMUP, nbars - 1)
    k = min(MAX_CANDIDATES, len(eligible))
    bars = np.sort(rng.choice(eligible, size=k, replace=False))
    sides = np.where(rng.random(k) < 0.5, 1, -1)
    return n_target, bars, sides


def run_day_combo(prices, highs, lows, n_target, bars, sides, tgt_t, stp_t):
    fills = 0
    pnl_list = []
    reasons = []
    busy_until = -1
    for b, side in zip(bars, sides):
        if fills >= n_target:
            break
        win_lo, win_hi = (b + 1) * BAR, (b + 2) * BAR
        if win_lo < busy_until:
            continue
        stop_lvl = highs[b] + T if side == 1 else lows[b] - T
        seg = prices[win_lo:win_hi]
        hit = np.nonzero(seg >= stop_lvl)[0] if side == 1 else np.nonzero(seg <= stop_lvl)[0]
        if len(hit) == 0:
            continue
        fill_i = win_lo + hit[0]
        entry = seg[hit[0]]
        target = entry + side * tgt_t * T
        stoploss = entry - side * stp_t * T
        exit_i, exit_px, reason = first_exit(prices, fill_i + 1, side, target, stoploss)
        busy_until = exit_i + 1
        fills += 1
        exc = side * (prices[fill_i:exit_i + 1] - entry) / T   # excursion in ticks
        pnl_list.append((round(side * (exit_px - entry) / T),
                         max(0.0, -exc.min()),                  # MAE (ticks)
                         max(0.0, exc.max())))                  # MFE (ticks)
        reasons.append(reason)
    return pnl_list, reasons


def main():
    files = sorted(TICK_DIR.glob("*.parquet"))
    rng = np.random.default_rng(SEED)
    combos = [(t, s) for t in GRID for s in GRID]
    acc = {c: {"pnl": [], "tgt": 0, "stp": 0, "eod": 0} for c in combos}

    for i, f in enumerate(files):
        prices = pd.read_parquet(f, columns=["Price"])["Price"].to_numpy()
        nbars = len(prices) // BAR
        if nbars < WARMUP + 3:
            continue
        grid_p = prices[: nbars * BAR].reshape(nbars, BAR)
        highs = grid_p.max(axis=1)
        lows = grid_p.min(axis=1)
        n_target, bars, sides = day_schedule(nbars, rng)
        for c in combos:
            pnl, reasons = run_day_combo(prices, highs, lows, n_target, bars, sides, c[0], c[1])
            acc[c]["pnl"].extend(pnl)
            for r in reasons:
                acc[c][{"target": "tgt", "stop": "stp", "eod": "eod"}[r]] += 1
        if (i + 1) % 200 == 0:
            print(f"{i+1}/{len(files)} days...", flush=True)

    rows = []
    for (t, s), a in acc.items():
        arr = np.array(a["pnl"])           # columns: pnl, mae, mfe
        p, mae, mfe = arr[:, 0], arr[:, 1], arr[:, 2]
        n = len(p)
        gw = p[p > 0].sum()
        gl = -p[p < 0].sum()
        net = p.sum()
        rows.append({
            "target_t": t, "stop_t": s, "trades": n,
            "win_pct": round((p > 0).mean() * 100, 1),
            "be_win_pct": round(s / (t + s) * 100, 1),
            "tgt": a["tgt"], "stp": a["stp"], "eod": a["eod"],
            "net_ticks": int(net),
            "t_per_trade": round(net / n, 3),
            "PF": round(gw / gl, 3) if gl else np.inf,
            "net_usd_fee": round(net * TICK_USD - FEE_RT * n),
            "usd_per_trade": round((net * TICK_USD - FEE_RT * n) / n, 2),
            "mae_avg": round(mae.mean(), 2), "mae_med": round(np.median(mae), 2),
            "mfe_avg": round(mfe.mean(), 2), "mfe_med": round(np.median(mfe), 2),
        })
    res = pd.DataFrame(rows).sort_values("usd_per_trade", ascending=False)

    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    res.to_csv(OUT_DIR / f"sweep_tick2000_grid_{stamp}.csv", index=False)

    piv_t = res.pivot(index="target_t", columns="stop_t", values="t_per_trade")
    piv_u = res.pivot(index="target_t", columns="stop_t", values="usd_per_trade")
    piv_w = res.pivot(index="target_t", columns="stop_t", values="win_pct")
    txt = (f"fee=${FEE_RT}/RT ES (${TICK_USD}/tick), seed={SEED}, "
           f"random direction, shared per-day schedule\n\n"
           f"net ticks/trade (rows=target, cols=stop):\n{piv_t}\n\n"
           f"net $/trade after fee:\n{piv_u}\n\n"
           f"win %:\n{piv_w}\n\n"
           f"top 10 by $/trade:\n{res.head(10).to_string(index=False)}\n")
    print(txt)
    (OUT_DIR / f"sweep_tick2000_grid_{stamp}.txt").write_text(txt, encoding="utf-8")
    print(f"saved: sweep_tick2000_grid_{stamp}.csv/.txt")


if __name__ == "__main__":
    main()
