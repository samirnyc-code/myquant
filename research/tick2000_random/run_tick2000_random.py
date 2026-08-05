"""
Random stop-entry study on ES 2000-tick RTH charts.

Spec (user, S95 2026-08-05):
- 2000-tick bars built per day from data/ticks_continuous (RTH-only ticks, 08:30-15:15).
- 21 EMA on bar closes (per-day chart; signals only after 21 bars of warmup).
- Random signal bars, targeting 2-5 FILLED trades per day (canceled stop orders
  are re-drawn on later random bars until the day's fill target or day end).
- Stop entry placed on signal bar close: long = signal bar high + 1 tick (only if
  close > EMA21), short = signal bar low - 1 tick (only if close < EMA21).
  Order valid for the NEXT bar only; canceled if not triggered.
- Target +4 ticks (limit, requires 1-tick tick-through to fill at the limit).
- Stop -8 ticks (stop order, fills on touch; gap-through fills at traded price).
- One position at a time. EOD flatten at last tick of day.

Outputs (dated):
- trades_tick2000_random_<stamp>.csv  (full trade list)
- summary_tick2000_random_<stamp>.txt (aggregate stats)
"""
import numpy as np
import pandas as pd
from pathlib import Path
from datetime import datetime

ROOT = Path(r"c:\Users\Admin\myquant")
TICK_DIR = ROOT / "data" / "ticks_continuous"
OUT_DIR = Path(__file__).parent

BAR = 2000            # ticks per bar
T = 0.25              # tick size
EMA_N = 21
TGT_T = 4             # target ticks
STP_T = 8             # stop ticks
SEED = 42

rng = np.random.default_rng(SEED)


def ema(closes: np.ndarray, n: int) -> np.ndarray:
    return pd.Series(closes).ewm(span=n, adjust=False).mean().to_numpy()


def run_day(path: Path):
    df = pd.read_parquet(path, columns=["DateTime", "Price"])
    prices = df["Price"].to_numpy()
    times = df["DateTime"].to_numpy()
    n = len(prices)
    nbars = n // BAR
    if nbars < EMA_N + 3:
        return [], 0

    grid = prices[: nbars * BAR].reshape(nbars, BAR)
    highs = grid.max(axis=1)
    lows = grid.min(axis=1)
    closes = grid[:, -1]
    e = ema(closes, EMA_N)

    # eligible signal bars: EMA warmed up, and a full next bar exists for the entry window
    n_target = int(rng.integers(2, 6))
    trades = []
    canceled = 0
    busy_until = -1  # tick index; signals whose entry window starts before this are skipped

    b = EMA_N - 1
    while True:
        b += 1
        if b >= nbars - 1 or len(trades) >= n_target:
            break
        win_lo, win_hi = (b + 1) * BAR, (b + 2) * BAR
        if win_lo < busy_until:
            continue
        # sequential uniform sampling: expected picks ≈ trades still needed
        remaining = (nbars - 1) - b
        need = n_target - len(trades)
        if rng.random() >= need / remaining:
            continue
        c, m = closes[b], e[b]
        if c > m:
            side = 1
            stop_lvl = highs[b] + T
        elif c < m:
            side = -1
            stop_lvl = lows[b] - T
        else:
            continue

        seg = prices[win_lo:win_hi]
        hit = np.nonzero(seg >= stop_lvl)[0] if side == 1 else np.nonzero(seg <= stop_lvl)[0]
        if len(hit) == 0:
            canceled += 1
            continue
        fill_i = win_lo + hit[0]
        entry = seg[hit[0]]  # traded price at/through the stop (gap = worse fill)
        target = entry + side * TGT_T * T
        stoploss = entry - side * STP_T * T

        rest = prices[fill_i + 1:]
        if side == 1:
            t_idx = np.nonzero(rest >= target + T)[0]      # tick-through required
            s_idx = np.nonzero(rest <= stoploss)[0]        # stop fills on touch
        else:
            t_idx = np.nonzero(rest <= target - T)[0]
            s_idx = np.nonzero(rest >= stoploss)[0]
        t_first = t_idx[0] if len(t_idx) else np.inf
        s_first = s_idx[0] if len(s_idx) else np.inf

        if t_first < s_first:
            exit_rel, exit_px, reason = t_first, target, "target"
        elif s_first < np.inf:
            px = rest[s_first]
            exit_px = min(px, stoploss) if side == 1 else max(px, stoploss)
            exit_rel, reason = s_first, "stop"
        else:
            exit_rel, exit_px, reason = len(rest) - 1, prices[-1], "eod"
        exit_i = fill_i + 1 + int(exit_rel)
        busy_until = exit_i + 1

        pnl_t = round(side * (exit_px - entry) / T)
        trades.append({
            "date": path.stem,
            "signal_bar": int(b),
            "side": "long" if side == 1 else "short",
            "entry_time": times[fill_i],
            "entry": entry,
            "exit_time": times[exit_i],
            "exit": exit_px,
            "reason": reason,
            "pnl_ticks": pnl_t,
            "bars_in_day": int(nbars),
        })
    return trades, canceled


def main():
    files = sorted(TICK_DIR.glob("*.parquet"))
    all_trades, total_canceled = [], 0
    for i, f in enumerate(files):
        tr, canc = run_day(f)
        all_trades.extend(tr)
        total_canceled += canc
        if (i + 1) % 200 == 0:
            print(f"{i+1}/{len(files)} days...", flush=True)

    tdf = pd.DataFrame(all_trades)
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    trades_path = OUT_DIR / f"trades_tick2000_random_{stamp}.csv"
    tdf.to_csv(trades_path, index=False)

    lines = []
    def w(s=""):
        lines.append(s)
        print(s)

    ndays = tdf["date"].nunique()
    wins = (tdf["pnl_ticks"] > 0).sum()
    losses = (tdf["pnl_ticks"] < 0).sum()
    gross_win = tdf.loc[tdf["pnl_ticks"] > 0, "pnl_ticks"].sum()
    gross_loss = -tdf.loc[tdf["pnl_ticks"] < 0, "pnl_ticks"].sum()
    net_t = tdf["pnl_ticks"].sum()

    w(f"days={ndays}  trades={len(tdf)}  ({len(tdf)/ndays:.2f}/day)  canceled_orders={total_canceled}")
    w(f"win={wins} ({wins/len(tdf)*100:.1f}%)  loss={losses}  eod_exits={(tdf['reason']=='eod').sum()}")
    w(f"target_exits={(tdf['reason']=='target').sum()}  stop_exits={(tdf['reason']=='stop').sum()}")
    w(f"net={net_t:+,} ticks  ({net_t/len(tdf):+.3f} t/trade)")
    w(f"PF={gross_win/gross_loss:.3f}  gross_win={gross_win:,}t gross_loss={gross_loss:,}t")
    w(f"ES $/contract gross: {net_t*12.5:+,.0f}   MES gross: {net_t*1.25:+,.0f}   MES net @$5RT: {net_t*1.25-5*len(tdf):+,.0f}")
    w()
    w("by side:")
    for side, g in tdf.groupby("side"):
        gw = g.loc[g.pnl_ticks > 0, "pnl_ticks"].sum(); gl = -g.loc[g.pnl_ticks < 0, "pnl_ticks"].sum()
        w(f"  {side:5s} n={len(g):5d}  win%={(g.pnl_ticks>0).mean()*100:5.1f}  net={g.pnl_ticks.sum():+8,}t  PF={gw/max(gl,1):.3f}")
    w()
    w("by year:")
    yr = tdf.assign(year=tdf["date"].str[:4])
    for y, g in yr.groupby("year"):
        gw = g.loc[g.pnl_ticks > 0, "pnl_ticks"].sum(); gl = -g.loc[g.pnl_ticks < 0, "pnl_ticks"].sum()
        w(f"  {y} n={len(g):5d}  win%={(g.pnl_ticks>0).mean()*100:5.1f}  net={g.pnl_ticks.sum():+8,}t  PF={gw/max(gl,1):.3f}")

    summary_path = OUT_DIR / f"summary_tick2000_random_{stamp}.txt"
    summary_path.write_text("\n".join(lines), encoding="utf-8")
    print(f"\nsaved: {trades_path.name}, {summary_path.name}")


if __name__ == "__main__":
    main()
