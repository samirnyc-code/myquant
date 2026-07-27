"""Regime x 2E on VOLUME BARS — the FROZEN book (S85) on 6500-contract bars.

The prior S83 run (4pt fixed stop, no SMA20 gate) was KILLED at test PF 0.94. This
re-runs with the CURRENT frozen book, which was never applied to volume bars:
  with-trend 2E (2EL/2ES) · entry > SMA20 of daily closes · skip day after a trend day
  (prior range > 1.6xADR10) · 09-13 fill window · stop-entry retest <=6t · 0.30xADR10
  stop · EOD flat. P&L re-derived from MAE/EOD, identical to regime_2e_book_metrics.

Bars: constant-volume bars from the REAL RTH tick cache (myquant/data/ticks_continuous)
— a bar closes when cumulative volume crosses SIZE. REAL ticks drive fills (better than
the 1M pseudo-ticks the 5M book uses). Engine (phase_transitions + detect_entries_causal)
is imported UNCHANGED — it is bar-type agnostic (needs only bars + a tick->bar map).

Daily SMA20/ADR10/skip-after come from the tick price series itself (same price base as
the bars), using ALL tick days for the 20-day lookback.

  python scripts/regime_2e_volbars.py                    # 6500V, trailing 12 mo
  python scripts/regime_2e_volbars.py --vol 6500 --months 12
  python scripts/regime_2e_volbars.py --all              # full tick history (2021-06+)
Output: data/regime/volbars_2e_pertrade_<VOL>V_<END>.csv  +  _metrics_<VOL>V_<END>.txt
"""
import sys, glob, os, time
from pathlib import Path
from bisect import bisect_right
import numpy as np
import pandas as pd

TICK = 0.25; PT = 50.0; COMM = 5.0; SLIP = 12.5; FLOOR = 8 * TICK
GOOD = {"09", "10", "11", "12", "13"}
WT = Path(__file__).resolve().parent.parent
MAIN_DATA = Path(r"C:/Users/Admin/myquant/data")
TICK_DIR = MAIN_DATA / "ticks_continuous"
sys.path.insert(0, str(WT / "scripts"))
from regime_second_entry_study import phase_transitions          # noqa: E402
from regime_2e_causal_check import detect_entries_causal         # noqa: E402


def vol_bars(tk, size):
    """OHLC constant-volume bars + per-tick bar index (each whole tick -> one bar)."""
    v = tk["Volume"].values.astype(np.int64)
    cs = np.cumsum(v)
    bar_ix = ((cs - v) // size).astype(np.int64)
    p = tk["Price"].values; dt = tk["DateTime"].values
    df = pd.DataFrame({"b": bar_ix, "p": p, "dt": dt})
    g = df.groupby("b", sort=True)
    bars = pd.DataFrame({
        "DateTime": g["dt"].first(),
        "Open": g["p"].first(), "High": g["p"].max(),
        "Low": g["p"].min(), "Close": g["p"].last()}).reset_index(drop=True)
    return bars, bar_ix, p


def emit_day(g, tP, tbar, adr):
    """EXACT fill logic of regime_2e_oos_pertrade.emit_day (0.30xADR stop, retest 6t,
    6-bar cancel, 09-13 window, EOD; stores mae_pts/eod_move for exact re-derivation)."""
    H, L = g["High"].values, g["Low"].values
    n = len(g)
    trans = phase_transitions(H, L, n, tP, tbar)
    tr_ix = [t for (t, _) in trans]; tr_md = [m for (_, m) in trans]
    entries = detect_entries_causal(g, tP, tbar)
    g_dt = g["DateTime"].values
    wide = max(round(0.30 * adr / TICK) * TICK, FLOOR)
    rows = []
    for (fb, sb, dr, cnt, trig) in entries:
        if cnt != 2:
            continue
        short = dr == "S"; want = "BEAR" if short else "BULL"
        a = np.searchsorted(tbar, fb, "left"); z = np.searchsorted(tbar, fb, "right")
        hit = np.nonzero(tP[a:z] <= trig)[0] if short else np.nonzero(tP[a:z] >= trig)[0]
        if not len(hit):
            continue
        jf = a + int(hit[0]); reg = tr_md[bisect_right(tr_ix, jf) - 1]
        lim = trig + 6 * TICK if short else trig - 6 * TICK; s0 = tP[jf:]
        jl = np.nonzero(s0 > lim)[0] if short else np.nonzero(s0 < lim)[0]
        if not len(jl):
            continue
        jfl = jf + int(jl[0]); fb2 = int(tbar[jfl])
        if fb2 - fb > 6:
            continue
        if pd.Timestamp(g_dt[min(fb2, n - 1)]).strftime("%H") not in GOOD:
            continue
        stop = lim + wide if short else lim - wide; seg = tP[jfl:]
        js = np.nonzero(seg >= stop)[0] if short else np.nonzero(seg <= stop)[0]
        exit_i = int(js[0]) if len(js) else len(seg) - 1
        ex = stop if len(js) else seg[-1]
        net = round(((lim - ex) if short else (ex - lim)) * PT - COMM - SLIP, 1)
        hold_bars = int(tbar[min(jfl + exit_i, len(tbar) - 1)] - fb2)
        mae_pts = float(lim - seg.min()) if not short else float(seg.max() - lim)
        eod_move = float(seg[-1] - lim) if not short else float(lim - seg[-1])
        fill_hour = pd.Timestamp(g_dt[min(fb2, n - 1)]).strftime("%H")
        rows.append({"dir": dr, "regime": reg, "with_trend": reg == want,
                     "net": net, "adr": round(float(adr), 2), "hold": hold_bars,
                     "mae_pts": round(mae_pts, 2), "eod_move": round(eod_move, 2),
                     "fill_hour": fill_hour, "entry_px": round(float(lim), 2)})
    return rows


def daily_stats_from_ticks(all_days):
    recs = []
    for d in all_days:
        p = pd.read_parquet(TICK_DIR / f"{d}.parquet", columns=["Price"])["Price"].to_numpy()
        recs.append((d, p[0], p.max(), p.min(), p[-1]))
    g = pd.DataFrame(recs, columns=["Date", "dO", "dH", "dL", "dC"]).sort_values("Date")
    g["sma20"] = g.dC.rolling(20).mean().shift(1)
    g["adr10"] = (g.dH - g.dL).rolling(10).mean().shift(1)
    g["skip_after"] = ((g.dH - g.dL) > 1.6 * g["adr10"]).shift(1).fillna(False).astype(bool)
    return g.set_index("Date")


def pf(v):
    v = np.asarray(v, float); gp = v[v > 0].sum(); gl = -v[v < 0].sum()
    return gp / gl if gl else float("inf")


def mdd(x):
    e = x.sort_values("Date").net.cumsum().values
    return float((e - np.maximum.accumulate(e)).min())


def main():
    vol = 6500; months = 12; allhist = "--all" in sys.argv
    if "--vol" in sys.argv: vol = int(sys.argv[sys.argv.index("--vol") + 1])
    if "--months" in sys.argv: months = int(sys.argv[sys.argv.index("--months") + 1])

    all_days = [os.path.basename(f)[:10] for f in sorted(glob.glob(str(TICK_DIR / "*.parquet")))]
    if allhist:
        win = all_days
    else:
        end = pd.Timestamp(all_days[-1]); start = end - pd.DateOffset(months=months)
        win = [d for d in all_days if pd.Timestamp(d) >= start]
    print(f"window {win[0]} -> {win[-1]}  ({len(win)} days)  vol/bar={vol:,}", flush=True)

    ds = daily_stats_from_ticks(all_days)

    rows = []; t0 = time.time(); nbars = []
    for i, d in enumerate(win):
        if d not in ds.index: continue
        adr = ds.loc[d, "adr10"]
        if not np.isfinite(adr): continue
        tk = pd.read_parquet(TICK_DIR / f"{d}.parquet").sort_values("DateTime")
        if len(tk) < 1000: continue
        g, tbar, tP = vol_bars(tk, vol)
        if len(g) < 20: continue
        nbars.append(len(g))
        try:
            for r in emit_day(g, tP, tbar, adr):
                r.update({"Date": d, "yr": int(d[:4])})
                rows.append(r)
        except Exception as e:
            print(d, "ERR", repr(e), flush=True)
        if (i + 1) % 50 == 0:
            print(f"[{i+1}/{len(win)}] rows={len(rows)} bars/day~{int(np.median(nbars))} ({time.time()-t0:.0f}s)", flush=True)

    d = pd.DataFrame(rows).merge(ds[["sma20", "skip_after"]], left_on="Date", right_index=True, how="left")
    d = d.dropna(subset=["sma20"])
    S = np.maximum(np.round(0.30 * d.adr.values / TICK) * TICK, FLOOR)
    d["net"] = np.where(d.mae_pts.values >= S, -S, d.eod_move.values) * PT - COMM - SLIP

    all_2e = d[d.fill_hour.astype(int).isin({9, 10, 11, 12, 13})].copy()
    book = all_2e[all_2e.with_trend & (all_2e.entry_px > all_2e.sma20) & (~all_2e.skip_after)].copy()

    end_tag = win[-1]
    (WT / "data" / "regime").mkdir(parents=True, exist_ok=True)
    out_csv = WT / "data" / "regime" / f"volbars_2e_pertrade_{vol}V_{end_tag}.csv"
    d.to_csv(out_csv, index=False)

    yrs = len(win) / 252.0
    lines = []
    def out(s=""): lines.append(s); print(s, flush=True)
    out(f"\n===== 2E FROZEN BOOK on {vol:,}V bars | {win[0]} -> {win[-1]} ({yrs:.2f} yr, {len(nbars)} days, ~{int(np.median(nbars))} bars/day) =====")
    out(f"raw 2E signals (cnt==2): {len(d)}   with-trend+09-13: {len(all_2e)}   BOOK: {len(book)}")
    if len(book):
        v = book.net.values; w = v[v > 0]; l = v[v < 0]
        daily = book.groupby("Date").net.sum()
        sharpe = daily.mean() / daily.std() * np.sqrt(252) if daily.std() > 0 else 0
        out(f"  net            ${v.sum():+,.0f}   (${v.sum()/yrs:+,.0f}/yr, 1 ES)")
        out(f"  PF             {pf(v):.2f}")
        out(f"  win rate       {100*(v>0).mean():.1f}%   ({len(w)}W / {len(l)}L)")
        out(f"  avg win/loss   ${w.mean() if len(w) else 0:+,.0f} / ${l.mean() if len(l) else 0:+,.0f}"
            f"   payoff {abs(w.mean()/l.mean()) if len(l) and len(w) else float('nan'):.2f}")
        out(f"  expectancy     ${v.mean():+,.0f}/trade")
        out(f"  max drawdown   ${mdd(book):+,.0f}")
        out(f"  best / worst   ${v.max():+,.0f} / ${v.min():+,.0f}")
        out(f"  trades/yr      {len(v)/yrs:.0f}    daily Sharpe {sharpe:.2f}")
        L = book[book.dir == "L"]; Sh = book[book.dir == "S"]
        out(f"  by side:  2EL n={len(L)} PF {pf(L.net):.2f} ${L.net.sum():+,.0f}   2ES n={len(Sh)} PF {pf(Sh.net):.2f} ${Sh.net.sum():+,.0f}")
        out("\n  per-year (net | PF | n | win%):")
        for y, x in book.groupby("yr"):
            vv = x.net.values
            out(f"    {int(y)}: ${vv.sum():+8,.0f}  PF {pf(vv):4.2f}  n={len(vv):3d}  win {100*(vv>0).mean():3.0f}%")
    out("\n-- ref: frozen 5M book 2021+ (5.5yr): PF 1.46, +$14,021/yr, win 49.9%, Sharpe 2.18, ~107 tr/yr --")
    out("-- prior 6500V run (OLD 4pt spec) was KILLED at test PF 0.94 --")
    (WT / "data" / "regime" / f"volbars_2e_metrics_{vol}V_{end_tag}.txt").write_text("\n".join(lines), encoding="utf-8")
    print(f"\nsaved: {out_csv}")


if __name__ == "__main__":
    main()
