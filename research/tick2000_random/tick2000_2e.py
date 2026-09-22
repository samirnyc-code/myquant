"""
Second-entry (H2/L2) signals on ES 2000-tick RTH charts — same engine as the
random-entry sims (S95):

- 2000-tick bars, 21EMA on closes (21-bar warmup), per-day chart.
- Direction gate: longs only when signal-bar close > EMA21, shorts only below
  (same as the original EMA variant).
- Entry: stop order 1 tick beyond the signal bar (valid NEXT bar only).
- Target limit requires 1-tick tick-through; stop fills on touch (gap = worse);
  one position at a time; EOD flatten; fee $3.50 RT, ES $12.50/tick.
- Difference vs the random sims: entries are SECOND ENTRIES instead of random
  bars, and ALL signals are taken (no 2-5/day sampling).

Second-entry definition (classic Brooks H2/L2, simplified):
- Long side: track the running leg high. While price has not made a new leg
  high, each UPWARD transition of bar highs (high > prior high, after at least
  one bar with high < prior high) increments the count: H1, H2. The H2 bar is
  the signal bar (if close > EMA21). New leg high resets the count; emitting a
  signal resets the count.
- Short side mirrored on lows below the running leg low.

Sweep: same 64 target/stop combos as the random grid; signals computed once
per day, shared by all combos. Baseline deltas vs trades_grid parquet (random).

Outputs (dated): trades_2e_grid_<stamp>.parquet, sweep_2e_grid_<stamp>.csv/.txt
"""
import sys
import numpy as np
import pandas as pd
from pathlib import Path
from datetime import datetime

OUT_DIR = Path(__file__).parent
sys.path.insert(0, str(OUT_DIR))
from sweep_tick2000_targets import (TICK_DIR, BAR, T, WARMUP, GRID, first_exit)

FEE_RT = 3.5
TICK_USD = 12.5
RANDOM_BASELINE = OUT_DIR / "trades_grid_20260805_225717.parquet"
FOCUS = [(4, 8), (12, 24)]


def ema(closes, n=21):
    return pd.Series(closes).ewm(span=n, adjust=False).mean().to_numpy()


def second_entry_signals(highs, lows, closes, e, nbars):
    """Return list of (bar_index, side) H2/L2 signals, EMA-gated."""
    sigs = []
    leg_high, leg_low = highs[0], lows[0]
    h_count, l_count = 0, 0
    h_was_up, l_was_dn = False, False
    h_pb, l_pb = False, False          # pullback started since last leg extreme
    for i in range(1, nbars - 1):
        # ---- long side (H-count on highs) ----
        if highs[i] > leg_high:
            leg_high = highs[i]
            h_count, h_pb, h_was_up = 0, False, False
        else:
            if highs[i] < highs[i - 1]:
                h_pb, h_was_up = True, False
            elif highs[i] > highs[i - 1] and h_pb and not h_was_up:
                h_count += 1
                h_was_up = True
                if h_count == 2:
                    if i >= WARMUP and closes[i] > e[i]:
                        sigs.append((i, 1))
                    h_count, h_pb = 0, False
        # ---- short side (L-count on lows) ----
        if lows[i] < leg_low:
            leg_low = lows[i]
            l_count, l_pb, l_was_dn = 0, False, False
        else:
            if lows[i] > lows[i - 1]:
                l_pb, l_was_dn = True, False
            elif lows[i] < lows[i - 1] and l_pb and not l_was_dn:
                l_count += 1
                l_was_dn = True
                if l_count == 2:
                    if i >= WARMUP and closes[i] < e[i]:
                        sigs.append((i, -1))
                    l_count, l_pb = 0, False
    return sorted(sigs)


def run_day_combo(prices, times, highs, lows, sigs, tgt_t, stp_t):
    out = []
    canceled = 0
    busy_until = -1
    for b, side in sigs:
        win_lo, win_hi = (b + 1) * BAR, (b + 2) * BAR
        if win_lo < busy_until:
            continue
        stop_lvl = highs[b] + T if side == 1 else lows[b] - T
        seg = prices[win_lo:win_hi]
        hit = np.nonzero(seg >= stop_lvl)[0] if side == 1 else np.nonzero(seg <= stop_lvl)[0]
        if len(hit) == 0:
            canceled += 1
            continue
        fill_i = win_lo + hit[0]
        entry = seg[hit[0]]
        target = entry + side * tgt_t * T
        stoploss = entry - side * stp_t * T
        exit_i, exit_px, reason = first_exit(prices, fill_i + 1, side, target, stoploss)
        busy_until = exit_i + 1
        ts = pd.Timestamp(times[fill_i])
        out.append((side, ts.hour + ts.minute / 60.0,
                    round(side * (exit_px - entry) / T), reason))
    return out, canceled


def agg(p):
    n = len(p)
    gw = p[p > 0].sum()
    gl = -p[p < 0].sum()
    net = p.sum()
    return {
        "trades": n,
        "win_pct": round((p > 0).mean() * 100, 1),
        "net_ticks": int(net),
        "t_per_trade": round(net / n, 3),
        "PF": round(gw / gl, 3) if gl else np.inf,
        "net_usd_fee": round(net * TICK_USD - FEE_RT * n),
        "usd_per_trade": round((net * TICK_USD - FEE_RT * n) / n, 2),
    }


def main():
    files = sorted(TICK_DIR.glob("*.parquet"))
    combos = [(t, s) for t in GRID for s in GRID]
    recs = []
    n_signals = 0
    canceled_48 = 0

    for i, f in enumerate(files):
        df = pd.read_parquet(f, columns=["DateTime", "Price"])
        prices = df["Price"].to_numpy()
        times = df["DateTime"].to_numpy()
        nbars = len(prices) // BAR
        if nbars < WARMUP + 3:
            continue
        grid_p = prices[: nbars * BAR].reshape(nbars, BAR)
        highs, lows = grid_p.max(axis=1), grid_p.min(axis=1)
        closes = grid_p[:, -1]
        e = ema(closes)
        sigs = second_entry_signals(highs, lows, closes, e, nbars)
        n_signals += len(sigs)
        for c in combos:
            trades, canc = run_day_combo(prices, times, highs, lows, sigs, c[0], c[1])
            if c == (4, 8):
                canceled_48 += canc
            for side, hour, pnl, reason in trades:
                recs.append((c[0], c[1], f.stem, side, hour, pnl, reason))
        if (i + 1) % 200 == 0:
            print(f"{i+1}/{len(files)} days...", flush=True)

    tr = pd.DataFrame(recs, columns=["tgt", "stp", "date", "side", "hour", "pnl", "reason"])
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    tr.to_parquet(OUT_DIR / f"trades_2e_grid_{stamp}.parquet", index=False)
    lines = []

    def w(s=""):
        lines.append(str(s))
        print(s)

    ndays = tr["date"].nunique()
    rows = []
    for (t_, s_), g in tr.groupby(["tgt", "stp"]):
        rows.append({**agg(g["pnl"].to_numpy()), "tgt": t_, "stp": s_})
    res = pd.DataFrame(rows).sort_values("usd_per_trade", ascending=False)

    base = pd.read_parquet(RANDOM_BASELINE)
    bstat = base.groupby(["tgt", "stp"])["pnl"].agg(["sum", "count"])
    bstat["tpt"] = (bstat["sum"] / bstat["count"]).round(3)

    piv = res.pivot(index="tgt", columns="stp", values="t_per_trade")
    bpiv = bstat["tpt"].unstack()
    w(f"2E signals: {n_signals} total ({n_signals/ndays:.1f}/day), days={ndays}, "
      f"fee=${FEE_RT}RT; canceled entry orders (4/8 combo): {canceled_48}")
    w()
    w("2E net ticks/trade (rows=target, cols=stop):")
    w(piv)
    w()
    w("DELTA vs random baseline (2E minus random, ticks/trade):")
    w((piv - bpiv).round(3))
    w()
    w("top 10 combos by $/trade @$3.50:")
    cols = ["tgt", "stp", "trades", "win_pct", "t_per_trade", "PF", "net_usd_fee", "usd_per_trade"]
    w(res[cols].head(10).to_string(index=False))
    w()
    for (t_, s_) in FOCUS:
        g = tr[(tr.tgt == t_) & (tr.stp == s_)].copy()
        a = agg(g["pnl"].to_numpy())
        w(f"combo {t_}/{s_}: trades={a['trades']} ({a['trades']/ndays:.2f}/day) win%={a['win_pct']} "
          f"t/tr={a['t_per_trade']} PF={a['PF']} net=${a['net_usd_fee']:+,} (${a['usd_per_trade']}/tr)")
        g["year"] = g["date"].str[:4]
        for y, gy in g.groupby("year"):
            ay = agg(gy["pnl"].to_numpy())
            w(f"    {y}: n={ay['trades']:5d} win%={ay['win_pct']:5.1f} t/tr={ay['t_per_trade']:+.3f} "
              f"PF={ay['PF']:.3f} ${ay['net_usd_fee']:+,}")
        for sd, gs in g.groupby("side"):
            asd = agg(gs["pnl"].to_numpy())
            w(f"    {'long' if sd==1 else 'short'}: n={asd['trades']} win%={asd['win_pct']} "
              f"t/tr={asd['t_per_trade']:+.3f} PF={asd['PF']:.3f}")
        w()

    res[cols].to_csv(OUT_DIR / f"sweep_2e_grid_{stamp}.csv", index=False)
    (OUT_DIR / f"sweep_2e_grid_{stamp}.txt").write_text("\n".join(lines), encoding="utf-8")
    print(f"saved: sweep_2e_grid_{stamp}.csv/.txt + trades parquet")


if __name__ == "__main__":
    main()
