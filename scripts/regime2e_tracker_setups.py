"""2E × NEW-REGIME-TRACKER emitter — every filled 2E entry AND every ChoCh-event trade
2010-2026, each tagged with the BOS/ChoCh regime-tracker label (the desk-canonical engine
we reconciled to 100% NT↔Python on 2026-09-24, Lag=1).

WHY: the committed 2E book gates "with-trend" on a *separate* tick phase-machine. This
re-wires the SAME 2E trade universe (identical entry + fill logic, verbatim from
regime_2e_oos_pertrade.emit_day) onto the regime-tracker's Bull/Bear/Range label, and adds
event-driven setups the tracker makes possible (fade / trade-with a ChoCh). One consistent
frame (Databento 5m RTH + 1m pseudo-ticks) and one fill model so every arm is comparable.

CAUSALITY (no lookahead): the tracker commits bar j's label `lag` bars after it closes. So
  - regime@fill uses the last label FINALISED before the fill bar: regime[fb2 - 1 - lag].
  - a ChoCh at bar ci is knowable at bar ci+lag; its trade is eligible from bar ci+lag+1.
Fill realism identical to the frozen book: 2E = limit 6t back, trade-through required, cancel
after 6 bars, 0.30xADR stop on touch, EOD hold, $5 RT + 1t slip. ChoCh = market at the first
tick of the eligible bar (+1t slip), same 0.30xADR stop / EOD / costs (NO limit improvement,
so the event setups get no artificial edge).

  python scripts/regime2e_tracker_setups.py [--limit N]
Outputs (dated): data/regime/tracker_2e_<stamp>.csv, data/regime/tracker_choch_<stamp>.csv
"""
import sys, gc, time
from pathlib import Path
from bisect import bisect_right
import numpy as np
import pandas as pd

TICK = 0.25; PT = 50.0; COMM = 5.0; SLIP = 12.5; FLOOR = 8 * TICK
GOOD = {"09", "10", "11", "12", "13"}
LAG = 1  # canonical (matches the deployed NT8 indicator / desk chart)

REPO = Path(r"C:/Users/Admin/myquant")
DATA = REPO / "data"
WT = Path(r"C:/Users/Admin/myquant-regime")            # 2E engine worktree
sys.path.insert(0, str(WT / "scripts"))
sys.path.insert(0, str(REPO / "regime_tracker"))
from regime_2e_causal_check import detect_entries_causal          # noqa: E402  (verbatim 2E entries)
from regime_2e_tickproxy_fidelity import proxy_ticks              # noqa: E402
from regime_second_entry_study import phase_transitions as pt_old # noqa: E402  (baseline regime, kept for A/B)
from mywedge import compute_mywedge                               # noqa: E402
from regime_tracker import compute_regime                         # noqa: E402

M5 = DATA / "bars" / "_db_es_5m_rth.parquet"
M1 = DATA / "bars" / "_db_es_1m_rth.parquet"


def track_day(O, H, L, C):
    """Run the desk-canonical regime tracker on one RTH session's OHLC.
    Returns (regime[list], events[list of (i,kind,dir,level)], change_idx[sorted list])."""
    n = len(O)
    ins = [i == 0 for i in range(n)]                    # one RTH session -> new-session flag on bar 0
    w = compute_mywedge(list(O), list(H), list(L), list(C), tick_size=TICK, is_new_session=ins,
                        lookback=12, show_w2l=True, wedge_symmetry=4, ol_sensitivity=1,
                        ctsb_ignore=True, ib_ignore=True, show_wedge_sb=True, signal_bar_ibs=66.0,
                        continue_mc=False, continue_on_gap=False, warmup_floor=4, lag=LAG)
    r = compute_regime(w.swing_low_asof, w.swing_high_asof, list(L), list(H), bar_dir=w.bar_dir)
    change_idx = sorted(i for i, _ in r.change_points)
    return r.regime, r.events, change_idx


def causal_regime_at(regime, bar):
    """Last tracker label FINALISED before `bar` (lag-safe, no lookahead)."""
    k = bar - 1 - LAG
    if k < 0:
        return "Range"
    return regime[min(k, len(regime) - 1)]


def trend_age(change_idx, k):
    """Bars since the current trend segment started, as of finalised bar k."""
    start = 0
    for c in change_idx:
        if c <= k:
            start = c
        else:
            break
    return k - start


def emit_2e(g, tP, tbar, adr, regime, events, change_idx):
    """VERBATIM 2E fill logic (from regime_2e_oos_pertrade.emit_day) + tracker tags."""
    O, H, L, C = (g[c].values for c in ["Open", "High", "Low", "Close"])
    n = len(g)
    trans = pt_old(H, L, n, tP, tbar)
    tr_ix = [t for (t, _) in trans]; tr_md = [m for (_, m) in trans]
    entries = detect_entries_causal(g, tP, tbar)
    g_dt = g["DateTime"].values
    wide = max(round(0.30 * adr / TICK) * TICK, FLOOR)
    # ChoCh events knowable strictly before a given fill bar (causal)
    choch_known = [(i, d) for (i, k, d, _lv) in events if k == "ChoCh"]
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
        ex = stop if len(js) else seg[-1]
        net = round(((lim - ex) if short else (ex - lim)) * PT - COMM - SLIP, 1)
        mae_pts = float(lim - seg.min()) if not short else float(seg.max() - lim)
        eod_move = float(seg[-1] - lim) if not short else float(lim - seg[-1])
        # ---- tracker tags (causal) ----
        rk = causal_regime_at(regime, fb2)
        wt_trk = (rk == "Bull" and not short) or (rk == "Bear" and short)
        age = trend_age(change_idx, max(fb2 - 1 - LAG, 0))
        n_choch_before = sum(1 for (i, _) in choch_known if i + LAG < fb2)
        rows.append({"dir": dr, "regime_pm": reg, "with_trend_pm": reg == want,
                     "regime_trk": rk, "with_trend_trk": wt_trk, "trend_age": age,
                     "choch_before": n_choch_before,
                     "net": net, "adr": round(float(adr), 2),
                     "wide": round(float(wide), 2), "mae_pts": round(mae_pts, 2),
                     "eod_move": round(eod_move, 2),
                     "fill_hour": pd.Timestamp(g_dt[min(fb2, n - 1)]).strftime("%H"),
                     "entry_px": round(float(lim), 2)})
    return rows


def emit_choch(g, tP, tbar, adr, events, change_idx):
    """Event-driven trades: one row per ChoCh, both 'fade' (prior-trend dir) and 'with'
    (reversal dir). Market entry at the first tick of the eligible bar (ci+lag+1), +1t slip,
    0.30xADR stop on touch, EOD hold, $5 RT. hours 09-13. Same period/costs as 2E."""
    g_dt = g["DateTime"].values
    n = len(g)
    wide = max(round(0.30 * adr / TICK) * TICK, FLOOR)
    rows = []
    choch = [(i, d, lv) for (i, k, d, lv) in events if k == "ChoCh"]
    first_ci = choch[0][0] if choch else None
    for (ci, cdir, lv) in choch:
        be = ci + LAG + 1                       # first causally-eligible bar
        if be >= n:
            continue
        hr = pd.Timestamp(g_dt[be]).strftime("%H")
        if hr not in GOOD:
            continue
        a = np.searchsorted(tbar, be, "left")
        if a >= len(tP):
            continue
        entry_tick = float(tP[a])
        for mode in ("fade", "with"):
            # ChoCh 'down' ends a Bull (reversal=short); 'up' ends a Bear (reversal=long).
            rev_short = (cdir == "down")
            short = rev_short if mode == "with" else (not rev_short)
            fill = entry_tick + (TICK if short else -TICK)   # 1t slip against (market)
            stop = fill + wide if short else fill - wide
            seg = tP[a:]
            js = np.nonzero(seg >= stop)[0] if short else np.nonzero(seg <= stop)[0]
            ex = stop if len(js) else seg[-1]
            net = round(((fill - ex) if short else (ex - fill)) * PT - COMM - SLIP, 1)
            mae_pts = float(fill - seg.min()) if not short else float(seg.max() - fill)
            eod_move = float(seg[-1] - fill) if not short else float(fill - seg[-1])
            rows.append({"mode": mode, "dir": "S" if short else "L", "choch_dir": cdir,
                         "is_first_of_day": ci == first_ci,
                         "net": net, "adr": round(float(adr), 2), "wide": round(float(wide), 2),
                         "mae_pts": round(mae_pts, 2), "eod_move": round(eod_move, 2),
                         "fill_hour": hr, "entry_px": round(fill, 2), "bar": int(be)})
    return rows


def main():
    limit = int(sys.argv[sys.argv.index("--limit") + 1]) if "--limit" in sys.argv else None
    b = pd.read_parquet(M5); b["DateTime"] = pd.to_datetime(b["DateTime"]); b["Date"] = b["DateTime"].dt.date.astype(str)
    m1 = pd.read_parquet(M1); m1["DateTime"] = pd.to_datetime(m1["DateTime"]); m1["Date"] = m1["DateTime"].dt.date.astype(str)
    m1g = {d: x.sort_values("DateTime").reset_index(drop=True) for d, x in m1.groupby("Date")}
    dly = b.groupby("Date").agg(dH=("High", "max"), dL=("Low", "min")).reset_index()
    dly["adr10"] = (dly.dH - dly.dL).rolling(10).mean().shift(1)
    gm = dly.set_index("Date")["adr10"]
    days = sorted(b["Date"].unique())
    if limit:
        days = days[:limit]
    rows2e = []; rowsch = []; t0 = time.time()
    for di, dstr in enumerate(days):
        if dstr not in gm.index or dstr not in m1g:
            continue
        adr = gm.loc[dstr]
        if not np.isfinite(adr):
            continue
        g = b[b.Date == dstr].sort_values("DateTime").reset_index(drop=True)
        if len(g) < 30:
            continue
        m1day = m1g[dstr]; m1day = m1day[m1day.DateTime >= g["DateTime"].values[0]]
        if len(m1day) < 30:
            continue
        try:
            tP, tbar = proxy_ticks(g, m1day)
            regime, events, change_idx = track_day(g.Open.values, g.High.values, g.Low.values, g.Close.values)
            meta = {"Date": dstr, "yr": int(dstr[:4])}
            for r in emit_2e(g, tP, tbar, adr, regime, events, change_idx):
                r.update(meta); rows2e.append(r)
            for r in emit_choch(g, tP, tbar, adr, events, change_idx):
                r.update(meta); rowsch.append(r)
        except Exception as e:
            print(dstr, "ERR", repr(e), flush=True)
        del g, m1day; gc.collect()
        if (di + 1) % 500 == 0:
            print(f"[{di+1}/{len(days)}] 2e={len(rows2e)} choch={len(rowsch)} ({time.time()-t0:.0f}s)", flush=True)
    stamp = pd.Timestamp("2026-09-24").strftime("%Y%m%d")
    p2 = DATA / "regime" / f"tracker_2e_{stamp}.csv"
    pc = DATA / "regime" / f"tracker_choch_{stamp}.csv"
    pd.DataFrame(rows2e).to_csv(p2, index=False)
    pd.DataFrame(rowsch).to_csv(pc, index=False)
    print(f"\nDONE {time.time()-t0:.0f}s")
    print(f"  2E trades:    {len(rows2e):,} -> {p2}")
    print(f"  ChoCh trades: {len(rowsch):,} -> {pc}")


if __name__ == "__main__":
    main()
