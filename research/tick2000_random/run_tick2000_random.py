"""
Random stop-entry study on ES 2000-tick RTH charts — variant comparison.

Spec (user, S95 2026-08-05):
- 2000-tick bars built per day from data/ticks_continuous (RTH-only ticks, 08:30-15:15).
- Random signal bars, targeting 2-5 FILLED trades per day (canceled stop orders
  are re-drawn on later random bars until the day's fill target or day end).
- Stop entry placed on signal bar close: long = signal bar high + 1 tick,
  short = signal bar low - 1 tick. Order valid for the NEXT bar only.
- Target +4 ticks (limit, requires 1-tick tick-through to fill at the limit).
- Stop -8 ticks (stop order, fills on touch; gap-through fills at traded price).
- One position at a time. EOD flatten at last tick of day.
- Fee: $4 round-turn per trade, ES big contract ($12.50/tick).

Variants:
  ema    - long above 21EMA / short below (EMA on bar closes, 21-bar warmup)
  random - direction = coin flip, EMA ignored
  long   - always long, EMA ignored
  short  - always short, EMA ignored
(All variants keep the same 21-bar warmup so they trade the same bar universe.)

Outputs (dated):
- trades_tick2000_<variant>_<stamp>.csv  (full trade list per variant)
- summary_tick2000_variants_<stamp>.txt  (comparison table)
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
FEE_RT = 4.0          # $ round-turn per trade
TICK_USD = 12.5       # ES big contract
VARIANTS = ["ema", "random", "long", "short"]


def ema(closes: np.ndarray, n: int) -> np.ndarray:
    return pd.Series(closes).ewm(span=n, adjust=False).mean().to_numpy()


def run_day(prices, times, day, mode, rng):
    n = len(prices)
    nbars = n // BAR
    if nbars < EMA_N + 3:
        return [], 0

    grid = prices[: nbars * BAR].reshape(nbars, BAR)
    highs = grid.max(axis=1)
    lows = grid.min(axis=1)
    closes = grid[:, -1]
    e = ema(closes, EMA_N) if mode == "ema" else None

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

        if mode == "ema":
            c, m = closes[b], e[b]
            if c > m:
                side = 1
            elif c < m:
                side = -1
            else:
                continue
        elif mode == "random":
            side = 1 if rng.random() < 0.5 else -1
        elif mode == "long":
            side = 1
        else:
            side = -1
        stop_lvl = highs[b] + T if side == 1 else lows[b] - T

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
            "date": day,
            "signal_bar": int(b),
            "side": "long" if side == 1 else "short",
            "entry_time": times[fill_i],
            "entry": entry,
            "exit_time": times[exit_i],
            "exit": exit_px,
            "reason": reason,
            "pnl_ticks": pnl_t,
            "pnl_usd_net": pnl_t * TICK_USD - FEE_RT,
        })
    return trades, canceled


def stats_row(name, tdf, canceled, ndays):
    wins = (tdf["pnl_ticks"] > 0).sum()
    gw = tdf.loc[tdf["pnl_ticks"] > 0, "pnl_ticks"].sum()
    gl = -tdf.loc[tdf["pnl_ticks"] < 0, "pnl_ticks"].sum()
    net_t = tdf["pnl_ticks"].sum()
    return {
        "variant": name,
        "trades": len(tdf),
        "per_day": round(len(tdf) / ndays, 2),
        "canceled": canceled,
        "win_pct": round(wins / len(tdf) * 100, 1),
        "tgt": int((tdf["reason"] == "target").sum()),
        "stp": int((tdf["reason"] == "stop").sum()),
        "eod": int((tdf["reason"] == "eod").sum()),
        "net_ticks": int(net_t),
        "t_per_trade": round(net_t / len(tdf), 3),
        "PF": round(gw / gl, 3),
        "gross_usd": round(net_t * TICK_USD),
        "fees_usd": round(FEE_RT * len(tdf)),
        "net_usd": round(net_t * TICK_USD - FEE_RT * len(tdf)),
        "usd_per_trade": round((net_t * TICK_USD - FEE_RT * len(tdf)) / len(tdf), 2),
    }


def main():
    files = sorted(TICK_DIR.glob("*.parquet"))
    rngs = {v: np.random.default_rng(SEED) for v in VARIANTS}
    all_trades = {v: [] for v in VARIANTS}
    all_canceled = {v: 0 for v in VARIANTS}

    for i, f in enumerate(files):
        df = pd.read_parquet(f, columns=["DateTime", "Price"])
        prices = df["Price"].to_numpy()
        times = df["DateTime"].to_numpy()
        for v in VARIANTS:
            tr, canc = run_day(prices, times, f.stem, v, rngs[v])
            all_trades[v].extend(tr)
            all_canceled[v] += canc
        if (i + 1) % 200 == 0:
            print(f"{i+1}/{len(files)} days...", flush=True)

    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    rows = []
    for v in VARIANTS:
        tdf = pd.DataFrame(all_trades[v])
        tdf.to_csv(OUT_DIR / f"trades_tick2000_{v}_{stamp}.csv", index=False)
        rows.append(stats_row(v, tdf, all_canceled[v], tdf["date"].nunique()))

    cmp = pd.DataFrame(rows)
    out = cmp.to_string(index=False)
    print(out)
    (OUT_DIR / f"summary_tick2000_variants_{stamp}.txt").write_text(
        f"fee=${FEE_RT}/RT on ES big (${TICK_USD}/tick), seed={SEED}\n\n" + out + "\n",
        encoding="utf-8")
    cmp.to_csv(OUT_DIR / f"summary_tick2000_variants_{stamp}.csv", index=False)
    print(f"\nsaved: summary_tick2000_variants_{stamp}.txt/.csv + 4 trade CSVs")


if __name__ == "__main__":
    main()
