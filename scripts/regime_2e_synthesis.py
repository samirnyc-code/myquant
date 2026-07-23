"""P5 SYNTHESIS — the combined 2E strategy candidates, tick-simmed, train/test.

Stack under test (from P0-P4 evidence):
  entry  : RETEST limit (4t back from the S61 trigger; unfilled = skip)  [P3]
  stops  : fx4p (fixed 4pt from fill)  |  sb1 (signal bar +1t, reference)  [P0]
  target : 8pt fixed (~2R on fx4p)  |  EOD hold  (both with the stop)      [P0]
  TOD    : fills only in machine-hours 09-13 (h08, h14, h15 excluded)     [P0/P4]
  filters (causal at signal, thresholds fit on TRAIN only):
    F0 none | F1 with-trend (phase machine) | F2 WT+ER10 top-half
    F3 Brooks cell (WT + SB strong + EMA side) | F4 WT+ADX top-half
    F5 WT + ER10 top-half + ADX top-half

Split: train <= 2023-12-31, test 2024-01-01..2026-07. Report train/test
n, net$, PF for every combo + per-year net for the best test-side combo.
$5 RT, 1 ES. Output: data/regime/synthesis_20260723.csv (+ stdout tables).

  python scripts/regime_2e_synthesis.py [--limit N]
"""
import sys, gc, time
from pathlib import Path
from bisect import bisect_right
import numpy as np
import pandas as pd

TICK = 0.25; PT = 50.0; COMM = 5.0
WT_ROOT = Path(__file__).resolve().parent.parent
DATA = Path(r"C:/Users/Admin/myquant/data")
sys.path.insert(0, str(WT_ROOT / "scripts"))
from regime_second_entry_study import phase_transitions, load_day  # noqa: E402
from regime_2e_sweeps import detect_entries  # noqa: E402

OUT = WT_ROOT / "data" / "regime" / "synthesis_20260723.csv"
TRAIN_END = "2023-12-31"
GOOD_HOURS = {"09", "10", "11", "12", "13"}


def main():
    limit = None
    if "--limit" in sys.argv:
        limit = int(sys.argv[sys.argv.index("--limit") + 1])

    b = pd.read_parquet(DATA / "bars" / "_continuous.parquet")
    b["Date"] = b["DateTime"].dt.date.astype(str)
    days = sorted(b["Date"].unique())
    if limit:
        days = days[:limit]

    # features for filters
    ft = pd.read_csv(WT_ROOT / "data" / "regime" / "second_entries_features_20260723.csv")
    ft = ft[ft["count"] == 2].set_index("entry_id")
    bk = pd.read_csv(WT_ROOT / "data" / "regime" / "brooks_filters_2e_20260723.csv")
    bk["entry_id"] = bk.Date + "_" + bk.fire_bar.astype(str) + bk["dir"] + "2"
    bk = bk[bk.book == "T2"].drop_duplicates("entry_id").set_index("entry_id")

    trades = []   # per 2E: date, dir, hour, regime, er, adx, sb-ok, ema-ok, and sim outcomes
    t0 = time.time()
    for di, dstr in enumerate(days):
        g, tP, tbar = load_day(b, dstr)
        if g is None:
            continue
        O, H, L, C = (g[c].values for c in ["Open", "High", "Low", "Close"])
        n = len(g)
        try:
            transitions = phase_transitions(H, L, n, tP, tbar)
            entries = detect_entries(g, tP, tbar)
        except Exception as e:
            print(dstr, "ERR", repr(e), flush=True)
            continue
        tr_ix = [t for (t, _) in transitions]; tr_md = [m for (_, m) in transitions]
        g_dt = g["DateTime"].values
        for (fb, sb, dr, cnt, trig) in entries:
            if cnt != 2:
                continue
            short = dr == "S"
            a = np.searchsorted(tbar, fb, "left"); z = np.searchsorted(tbar, fb, "right")
            s = tP[a:z]
            hit = np.nonzero(s <= trig)[0] if short else np.nonzero(s >= trig)[0]
            if not len(hit):
                continue
            jf = a + int(hit[0])
            regime = tr_md[bisect_right(tr_ix, jf) - 1]
            # retest fill
            lim = trig + 4 * TICK if short else trig - 4 * TICK
            seg0 = tP[jf:]
            jl_ = np.nonzero(seg0 >= lim)[0] if short else np.nonzero(seg0 <= lim)[0]
            if not len(jl_):
                continue
            jfl = jf + int(jl_[0])
            fill = lim
            fill_bar = int(tbar[jfl])
            hour = pd.Timestamp(g_dt[min(fill_bar, n - 1)]).strftime("%H")
            seg = tP[jfl:]
            res = {}
            for stop_id in ("fx4p", "sb1"):
                stop = (fill + 16 * TICK if short else fill - 16 * TICK) if stop_id == "fx4p" \
                    else (H[sb] + TICK if short else L[sb] - TICK)
                R = (stop - fill) if short else (fill - stop)
                if R <= 0:
                    continue
                js_ = np.nonzero(seg >= stop)[0] if short else np.nonzero(seg <= stop)[0]
                js = js_[0] if len(js_) else np.inf
                for tgt_id, dist in (("t8p", 32 * TICK), ("eod", None)):
                    if dist is None:
                        ex = stop if np.isfinite(js) else seg[-1]
                    else:
                        tgt = fill - dist if short else fill + dist
                        jt_ = np.nonzero(seg <= tgt)[0] if short else np.nonzero(seg >= tgt)[0]
                        jt = jt_[0] if len(jt_) else np.inf
                        ex = stop if js <= jt else (tgt if np.isfinite(jt) else seg[-1])
                    pnl = (fill - ex) if short else (ex - fill)
                    res[f"{stop_id}_{tgt_id}"] = pnl * PT - COMM
            eid = f"{dstr}_{fb+1}{dr}2"
            trades.append(dict(entry_id=eid, Date=dstr, dir=dr, regime=regime,
                               hour=hour, **res))
        del tP, tbar; gc.collect()
        if (di + 1) % 100 == 0:
            print(f"[{di+1}/{len(days)}] trades={len(trades)} ({time.time()-t0:.0f}s)", flush=True)

    df = pd.DataFrame(trades).set_index("entry_id")
    df = df.join(ft[["er10", "adx14"]], how="left")
    df = df.join(bk[["sb_ibs_o", "sb_dirok", "sb_rngx", "ema_side_ok", "warm"]], how="left")
    df.reset_index().to_csv(OUT.with_suffix(".trades.csv"), index=False)

    df["is_tr"] = df.Date <= TRAIN_END
    wt = ((df.regime == "BULL") & (df.dir == "L")) | ((df.regime == "BEAR") & (df.dir == "S"))
    tod = df.hour.isin(GOOD_HOURS)
    er_med = df[df.is_tr].er10.median()
    adx_med = df[df.is_tr].adx14.median()
    print(f"\ntrain medians: ER10 {er_med:.3f}  ADX {adx_med:.1f}")
    brooks = wt & (df.sb_ibs_o >= 0.7) & df.sb_dirok.fillna(False) & \
        (df.sb_rngx >= 1.0) & df.ema_side_ok.fillna(False) & df.warm.fillna(False)
    FILTERS = [
        ("F0 none", pd.Series(True, df.index)),
        ("F1 WT", wt),
        ("F2 WT+ER", wt & (df.er10 >= er_med)),
        ("F3 Brooks", brooks),
        ("F4 WT+ADX", wt & (df.adx14 >= adx_med)),
        ("F5 WT+ER+ADX", wt & (df.er10 >= er_med) & (df.adx14 >= adx_med)),
    ]

    def pf(s):
        gp = s[s > 0].sum(); gl = -s[s < 0].sum()
        return gp / gl if gl > 0 else float("inf")

    out = []
    for (fname, fmask) in FILTERS:
        for todname, tmask in (("all-hours", pd.Series(True, df.index)), ("h09-13", tod)):
            for col in ("fx4p_t8p", "fx4p_eod", "sb1_t8p", "sb1_eod"):
                if col not in df.columns:
                    continue
                x = df[fmask & tmask].dropna(subset=[col])
                trn = x[x.is_tr]; tst = x[~x.is_tr]
                if len(trn) < 30 or len(tst) < 15:
                    continue
                out.append((fname, todname, col, len(trn), round(trn[col].sum()),
                            round(pf(trn[col]), 3), len(tst), round(tst[col].sum()),
                            round(pf(tst[col]), 3)))
    res = pd.DataFrame(out, columns=["filter", "tod", "geom", "n_tr", "net_tr", "PF_tr",
                                     "n_te", "net_te", "PF_te"])
    res.to_csv(OUT, index=False)
    print("\n================= SYNTHESIS GRID (train | test) =================")
    print(res.to_string(index=False))
    ok = res[(res.PF_tr > 1) & (res.PF_te > 1)]
    print("\n== combos green in BOTH train and test ==")
    print(ok.to_string(index=False) if len(ok) else "  NONE")
    if len(ok):
        best = ok.sort_values("net_te", ascending=False).iloc[0]
        fmask = dict(FILTERS)[best["filter"]]
        tmask = tod if best.tod == "h09-13" else pd.Series(True, df.index)
        x = df[fmask & tmask].dropna(subset=[best.geom]).copy()
        x["yr"] = x.Date.str[:4]
        t = x.groupby("yr")[best.geom].agg(n="size", net="sum",
                                           pf=lambda s: round(pf(s), 2)).round(0)
        print(f"\n== per-year: {best['filter']} | {best.tod} | {best.geom} ==")
        print(t.to_string())


if __name__ == "__main__":
    main()
