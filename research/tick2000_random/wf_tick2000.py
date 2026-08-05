"""
Walk-forward + time-of-day analysis for the tick2000 random stop-entry grid.

Same engine as sweep_tick2000_targets.py (random direction, stop entry 1t
beyond signal bar valid next bar only, target needs tick-through, stop on
touch, 2-5 fills/day, shared per-day random schedule across combos).
Fee $3.50 RT, ES big ($12.50/tick).

Produces (dated):
1. trades_grid_<stamp>.parquet          - every trade of every 64 combo (date, hour, pnl)
2. wf_oos_<stamp>.csv                   - 12m IS -> 3m OOS chained combo selection
3. wf_quarters_fixed_<stamp>.csv        - quarterly results for fixed 4/8 and 12/24
4. hourly_<stamp>.csv                   - P&L by entry hour (4/8 and 12/24)
5. late_excl_<stamp>.csv                - all combos, entries before 14:00 only (post-hoc)
6. variants_fee350_<stamp>.csv          - S95 direction-variant table repriced at $3.50
7. wf_summary_<stamp>.txt               - everything printed
"""
import sys
import numpy as np
import pandas as pd
from pathlib import Path
from datetime import datetime

OUT_DIR = Path(__file__).parent
sys.path.insert(0, str(OUT_DIR))
from sweep_tick2000_targets import (TICK_DIR, BAR, T, WARMUP, SEED, GRID,
                                    first_exit, day_schedule)

FEE_RT = 3.5
TICK_USD = 12.5
IS_MONTHS, OOS_MONTHS = 12, 3
LATE_CUTOFF_H = 14.0   # file-time hours; entries at/after this excluded in the late-excl view
FOCUS = [(4, 8), (12, 24)]


def run_day_combo(prices, times, n_target, bars, sides, tgt_t, stp_t):
    fills = 0
    out = []
    busy_until = -1
    for b, side in zip(bars, sides):
        if fills >= n_target:
            break
        win_lo, win_hi = (b + 1) * BAR, (b + 2) * BAR
        if win_lo < busy_until:
            continue
        # signal bar high/low from the tick slice (bars precomputed by caller)
        stop_lvl = out_hl[b][0] + T if side == 1 else out_hl[b][1] - T
        seg = prices[win_lo:win_hi]
        hit = np.nonzero(seg >= stop_lvl)[0] if side == 1 else np.nonzero(seg <= stop_lvl)[0]
        if len(hit) == 0:
            continue
        fill_i = win_lo + hit[0]
        entry = seg[hit[0]]
        target = entry + side * tgt_t * T
        stoploss = entry - side * stp_t * T
        exit_i, exit_px, _ = first_exit(prices, fill_i + 1, side, target, stoploss)
        busy_until = exit_i + 1
        fills += 1
        ts = pd.Timestamp(times[fill_i])
        out.append((ts.hour + ts.minute / 60.0, round(side * (exit_px - entry) / T)))
    return out


def stats(p, label_extra=None):
    n = len(p)
    if n == 0:
        return {"trades": 0}
    gw = p[p > 0].sum()
    gl = -p[p < 0].sum()
    net = p.sum()
    d = {
        "trades": n,
        "win_pct": round((p > 0).mean() * 100, 1),
        "net_ticks": int(net),
        "t_per_trade": round(net / n, 3),
        "PF": round(gw / gl, 3) if gl else np.inf,
        "net_usd_fee": round(net * TICK_USD - FEE_RT * n),
        "usd_per_trade": round((net * TICK_USD - FEE_RT * n) / n, 2),
    }
    if label_extra:
        d.update(label_extra)
    return d


def main():
    global out_hl
    files = sorted(TICK_DIR.glob("*.parquet"))
    rng = np.random.default_rng(SEED)
    combos = [(t, s) for t in GRID for s in GRID]
    recs = []   # combo_t, combo_s, date, hour, pnl

    for i, f in enumerate(files):
        df = pd.read_parquet(f, columns=["DateTime", "Price"])
        prices = df["Price"].to_numpy()
        times = df["DateTime"].to_numpy()
        nbars = len(prices) // BAR
        if nbars < WARMUP + 3:
            continue
        grid_p = prices[: nbars * BAR].reshape(nbars, BAR)
        out_hl = list(zip(grid_p.max(axis=1), grid_p.min(axis=1)))
        n_target, bars, sides = day_schedule(nbars, rng)
        for c in combos:
            for hour, pnl in run_day_combo(prices, times, n_target, bars, sides, c[0], c[1]):
                recs.append((c[0], c[1], f.stem, hour, pnl))
        if (i + 1) % 200 == 0:
            print(f"{i+1}/{len(files)} days...", flush=True)

    tr = pd.DataFrame(recs, columns=["tgt", "stp", "date", "hour", "pnl"])
    tr["dt"] = pd.to_datetime(tr["date"])
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    tr.to_parquet(OUT_DIR / f"trades_grid_{stamp}.parquet", index=False)
    lines = []

    def w(s=""):
        lines.append(str(s))
        print(s)

    # ---- 1. walk-forward 12m/3m -------------------------------------------
    start, end = tr["dt"].min(), tr["dt"].max()
    oos_starts = pd.date_range((start + pd.DateOffset(months=IS_MONTHS)).normalize().replace(day=1)
                               + pd.offsets.MonthBegin(0), end, freq="3MS")
    wf_rows = []
    for os_ in oos_starts:
        is_lo, is_hi = os_ - pd.DateOffset(months=IS_MONTHS), os_
        oos_hi = os_ + pd.DateOffset(months=OOS_MONTHS)
        is_tr = tr[(tr.dt >= is_lo) & (tr.dt < is_hi)]
        oos_tr = tr[(tr.dt >= os_) & (tr.dt < oos_hi)]
        if len(oos_tr) == 0:
            continue
        is_stats = is_tr.groupby(["tgt", "stp"])["pnl"].agg(["sum", "count"])
        is_stats["tpt"] = is_stats["sum"] / is_stats["count"]
        best = is_stats["tpt"].idxmax()
        o = oos_tr[(oos_tr.tgt == best[0]) & (oos_tr.stp == best[1])]["pnl"].to_numpy()
        row = stats(o, {"oos_start": os_.date().isoformat(),
                        "picked": f"{best[0]}/{best[1]}",
                        "is_tpt": round(is_stats.loc[best, "tpt"], 3)})
        wf_rows.append(row)
    wf = pd.DataFrame(wf_rows)
    cols = ["oos_start", "picked", "is_tpt", "trades", "win_pct", "t_per_trade", "PF", "net_usd_fee"]
    wf = wf[cols]
    wf.to_csv(OUT_DIR / f"wf_oos_{stamp}.csv", index=False)
    w("=== WALK-FORWARD 12m IS -> 3m OOS (pick best t/trade combo in IS) ===")
    w(wf.to_string(index=False))
    tot_usd = wf["net_usd_fee"].sum()
    w(f"chained OOS total: {wf['trades'].sum()} trades, net ${tot_usd:+,.0f} @$3.50RT")
    w()

    # ---- 2. quarterly volatility of fixed combos ---------------------------
    w("=== FIXED-COMBO QUARTERLY RESULTS (volatility view) ===")
    q_rows = []
    for (t_, s_) in FOCUS:
        sub = tr[(tr.tgt == t_) & (tr.stp == s_)].copy()
        sub["q"] = sub["dt"].dt.to_period("Q").astype(str)
        for q, g in sub.groupby("q"):
            q_rows.append(stats(g["pnl"].to_numpy(), {"combo": f"{t_}/{s_}", "quarter": q}))
        qdf = pd.DataFrame([r for r in q_rows if r["combo"] == f"{t_}/{s_}"])
        w(f"combo {t_}/{s_}: mean quarterly net ${qdf['net_usd_fee'].mean():+,.0f}, "
          f"std ${qdf['net_usd_fee'].std():,.0f}, best ${qdf['net_usd_fee'].max():+,.0f}, "
          f"worst ${qdf['net_usd_fee'].min():+,.0f}, positive {int((qdf['net_usd_fee']>0).sum())}/{len(qdf)} quarters")
    qall = pd.DataFrame(q_rows)[["combo", "quarter", "trades", "win_pct", "t_per_trade", "PF", "net_usd_fee"]]
    qall.to_csv(OUT_DIR / f"wf_quarters_fixed_{stamp}.csv", index=False)
    w()
    w(qall.to_string(index=False))
    w()

    # ---- 3. hour-of-day ----------------------------------------------------
    w("=== P&L BY ENTRY HOUR (file-time) ===")
    h_rows = []
    for (t_, s_) in FOCUS:
        sub = tr[(tr.tgt == t_) & (tr.stp == s_)].copy()
        sub["h"] = sub["hour"].astype(int)
        for h, g in sub.groupby("h"):
            h_rows.append(stats(g["pnl"].to_numpy(), {"combo": f"{t_}/{s_}", "hour": h}))
    hdf = pd.DataFrame(h_rows)[["combo", "hour", "trades", "win_pct", "t_per_trade", "PF", "usd_per_trade"]]
    hdf.to_csv(OUT_DIR / f"hourly_{stamp}.csv", index=False)
    w(hdf.to_string(index=False))
    w()

    # ---- 4. late-trade exclusion (entries < 14:00 only, post-hoc) ----------
    w(f"=== ENTRIES BEFORE {LATE_CUTOFF_H:.0f}:00 ONLY (post-hoc filter) ===")
    early = tr[tr.hour < LATE_CUTOFF_H]
    le_rows = []
    for (t_, s_), g in early.groupby(["tgt", "stp"]):
        le_rows.append(stats(g["pnl"].to_numpy(), {"tgt": t_, "stp": s_}))
    le = pd.DataFrame(le_rows).sort_values("usd_per_trade", ascending=False)
    le = le[["tgt", "stp", "trades", "win_pct", "t_per_trade", "PF", "net_usd_fee", "usd_per_trade"]]
    le.to_csv(OUT_DIR / f"late_excl_{stamp}.csv", index=False)
    w("top 10:")
    w(le.head(10).to_string(index=False))
    w()

    # ---- 5. reprice the S95 direction-variant table at $3.50 ---------------
    w("=== DIRECTION VARIANTS REPRICED @ $3.50 RT ===")
    v_rows = []
    for v in ["ema", "random", "long", "short"]:
        p = pd.read_csv(OUT_DIR / f"trades_tick2000_{v}_20260805_224511.csv")["pnl_ticks"].to_numpy()
        v_rows.append(stats(p, {"variant": v}))
    vdf = pd.DataFrame(v_rows)[["variant", "trades", "win_pct", "t_per_trade", "PF", "net_usd_fee", "usd_per_trade"]]
    vdf.to_csv(OUT_DIR / f"variants_fee350_{stamp}.csv", index=False)
    w(vdf.to_string(index=False))

    (OUT_DIR / f"wf_summary_{stamp}.txt").write_text("\n".join(lines), encoding="utf-8")
    print(f"\nsaved: wf_summary_{stamp}.txt + 6 CSV/parquet outputs")


if __name__ == "__main__":
    main()
