"""PER-TRADE EMITTER — every filled 2E entry 2010-2026 on the Databento 1-min proxy, with
metadata attached, so all downstream cuts (gate on/off, vol-conditioning, side, era,
walk-forward) are free in-memory. This is the workhorse behind the OOS deep-dive.

For each filled second-entry (both directions, regardless of gate):
  date, yr, dir(L/S), regime@fill(BULL/BEAR/NEUTRAL), with_trend(regime==want),
  net(0.30xADR stop, EOD hold, $5 RT + 1t slip), adr10, vix_prev(causal prior-day close),
  hold_bars.

Bars = _db_es_5m_rth; pseudo-ticks from _db_es_1m_rth. Same fill logic as the frozen book.

  python scripts/regime_2e_oos_pertrade.py [--limit N]
Output: data/regime/oos_pertrade_20260725.csv
"""
import sys, gc, time
from pathlib import Path
from bisect import bisect_right
import numpy as np
import pandas as pd

TICK = 0.25; PT = 50.0; COMM = 5.0; SLIP = 12.5
WT = Path(__file__).resolve().parent.parent
DATA = Path(r"C:/Users/Admin/myquant/data")
sys.path.insert(0, str(WT / "scripts"))
from regime_second_entry_study import phase_transitions as pt_old   # noqa: E402
from regime_2e_causal_check import detect_entries_causal            # noqa: E402
from regime_2e_tickproxy_fidelity import proxy_ticks                # noqa: E402

OUT = WT / "data" / "regime" / "oos_pertrade_20260725.csv"
M5 = DATA / "bars" / "_db_es_5m_rth.parquet"
M1 = DATA / "bars" / "_db_es_1m_rth.parquet"
GOOD = {"09", "10", "11", "12", "13"}
FLOOR = 8 * TICK


def emit_day(g, tP, tbar, adr):
    O, H, L, C = (g[c].values for c in ["Open", "High", "Low", "Close"])
    n = len(g)
    trans = pt_old(H, L, n, tP, tbar)
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
        # MAE (worst adverse excursion, pts) + EOD move (signed favorable, pts) let ANY stop
        # mult / window / side be re-derived exactly in-memory: net(S) = -S if mae>=S else eod_move.
        mae_pts = float(lim - seg.min()) if not short else float(seg.max() - lim)
        eod_move = float(seg[-1] - lim) if not short else float(lim - seg[-1])
        fill_hour = pd.Timestamp(g_dt[min(fb2, n - 1)]).strftime("%H")
        rows.append({"dir": dr, "regime": reg, "with_trend": reg == want,
                     "net": net, "adr": round(float(adr), 2), "hold": hold_bars,
                     "wide": round(float(wide), 2), "mae_pts": round(mae_pts, 2),
                     "eod_move": round(eod_move, 2), "fill_hour": fill_hour})
    return rows


def main():
    limit = None
    if "--limit" in sys.argv:
        limit = int(sys.argv[sys.argv.index("--limit") + 1])
    b = pd.read_parquet(M5); b["DateTime"] = pd.to_datetime(b["DateTime"]); b["Date"] = b["DateTime"].dt.date.astype(str)
    m1 = pd.read_parquet(M1); m1["DateTime"] = pd.to_datetime(m1["DateTime"]); m1["Date"] = m1["DateTime"].dt.date.astype(str)
    m1g = {d: x.sort_values("DateTime").reset_index(drop=True) for d, x in m1.groupby("Date")}
    vix = pd.read_csv(DATA / "vix_daily.csv"); vix["date"] = vix["date"].astype(str)
    vix_prev = vix.set_index("date")["close"].shift(1)  # NOTE: shift on row order = prior row; rebuild properly below
    vixc = vix.sort_values("date").set_index("date")["close"]
    vix_prev = vixc.shift(1)
    dly = b.groupby("Date").agg(dO=("Open", "first"), dC=("Close", "last"), dH=("High", "max"), dL=("Low", "min")).reset_index()
    dly["adr10"] = (dly.dH - dly.dL).rolling(10).mean().shift(1)
    dly["gap"] = ((dly.dO - dly.dC.shift(1)) / dly.dC.shift(1) * 100).abs()
    gm = dly.set_index("Date")[["adr10", "gap"]]
    days = sorted(b["Date"].unique())
    if limit:
        days = days[:limit]
    rows = []; t0 = time.time()
    for di, dstr in enumerate(days):
        if dstr not in gm.index or dstr not in m1g:
            continue
        adr, gapv = gm.loc[dstr, "adr10"], gm.loc[dstr, "gap"]
        if not np.isfinite(adr) or gapv > 0.54:
            continue
        g = b[b.Date == dstr].sort_values("DateTime").reset_index(drop=True)
        if len(g) < 30:
            continue
        m1day = m1g[dstr]; m1day = m1day[m1day.DateTime >= g["DateTime"].values[0]]
        if len(m1day) < 30:
            continue
        try:
            tP, tbar = proxy_ticks(g, m1day)
            vp = float(vix_prev.get(dstr, np.nan))
            for r in emit_day(g, tP, tbar, adr):
                r.update({"Date": dstr, "yr": int(dstr[:4]), "gap": round(float(gapv), 3), "vix_prev": vp})
                rows.append(r)
        except Exception as e:
            print(dstr, "ERR", repr(e), flush=True)
        del g, m1day; gc.collect()
        if (di + 1) % 500 == 0:
            print(f"[{di+1}/{len(days)}] rows={len(rows)} ({time.time()-t0:.0f}s)", flush=True)
    df = pd.DataFrame(rows)
    df.to_csv(OUT, index=False)
    print(f"\nDONE {time.time()-t0:.0f}s  -> {OUT}  ({len(df):,} filled 2E entries)")
    print("with_trend rows:", int(df.with_trend.sum()), "| counter-trend rows:", int((~df.with_trend).sum()))
    print("vix_prev coverage:", f"{df.vix_prev.notna().mean()*100:.0f}%")


if __name__ == "__main__":
    main()
