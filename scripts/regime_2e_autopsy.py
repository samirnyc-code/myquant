"""2E WINNER AUTOPSY — S83 P2. Full per-trade feature matrix + winners-vs-losers.

For every 2E of the base study (5m), compute everything a Brooks trader could see
at the moment of entry (CAUSAL — only bars closed before the fill, plus day
context). Then: univariate edge scans + a 2-condition rule search, train 2021-2023
/ test 2024-2026. Nothing is reported without its out-of-sample row.

Features per 2E (in addition to the sweeps features, joined by entry_id):
  structure : prior-leg size (ATR), pullback depth (% of leg), pullback bars,
              pullback overlap (barbwire proxy), microchannel length before,
              3-push wedge flag in pullback, bars since phase-machine trend start,
              entry # of day (per dir), prior same-dir 1E/2E outcome so far
  location  : position in day range so far, dist from day high/low (ATR),
              vs prior-day close/high/low (PC + RTH), vs open (gap dir)
  day-so-far: range-so-far/ADR10, directional drift |C_now-O_day|/range-so-far,
              first-hour range/ADR, EMA20 slope (10-bar, ATR units)
Output:
  data/regime/autopsy_features_20260723.csv     (per 2E)
  data/regime/autopsy_scan_20260723.csv         (univariate + rule search, train/test)
  stdout: ranked table of survivors

  python scripts/regime_2e_autopsy.py [--limit N]
"""
import sys, gc, time
from pathlib import Path
from bisect import bisect_right
import numpy as np
import pandas as pd

TICK = 0.25
WT_ROOT = Path(__file__).resolve().parent.parent
DATA = Path(r"C:/Users/Admin/myquant/data")
sys.path.insert(0, str(WT_ROOT / "scripts"))
from regime_second_entry_study import phase_transitions, load_day  # noqa: E402

OUT_F = WT_ROOT / "data" / "regime" / "autopsy_features_20260723.csv"
OUT_S = WT_ROOT / "data" / "regime" / "autopsy_scan_20260723.csv"
TRAIN_END = "2023-12-31"


def swing_pivots(H, L, k=2):
    """Simple k-bar fractal swings, causal at bar i+k (returns confirm bar)."""
    n = len(H); out = []
    for i in range(k, n - k):
        if H[i] == max(H[i-k:i+k+1]) and H[i] > H[i-1]:
            out.append((i, i + k, "H", H[i]))
        if L[i] == min(L[i-k:i+k+1]) and L[i] < L[i-1]:
            out.append((i, i + k, "L", L[i]))
    return out


def main():
    limit = None
    if "--limit" in sys.argv:
        limit = int(sys.argv[sys.argv.index("--limit") + 1])

    tr = pd.read_csv(WT_ROOT / "data" / "regime" / "second_entries_regime_20260723.csv")
    tr = tr[(tr["count"] == 2) & (tr.book == "T2")].copy()      # one row per 2E; T2 = payoff row
    t1 = pd.read_csv(WT_ROOT / "data" / "regime" / "second_entries_regime_20260723.csv")
    t1 = t1[(t1["count"] == 2) & (t1.book == "T1")][["Date", "fire_bar", "dir", "net", "R"]]
    t1 = t1.rename(columns={"net": "netT1", "R": "RT1"})
    tr = tr.merge(t1, on=["Date", "fire_bar", "dir"], how="left")
    by_day = {d: g for d, g in tr.groupby("Date")}
    e1 = pd.read_csv(WT_ROOT / "data" / "regime" / "second_entries_regime_20260723.csv")
    e1 = e1[(e1["count"] == 1) & (e1.book == "T1")][["Date", "dir", "fire_bar", "fill"]]
    e1_by_day = {d: g.sort_values("fire_bar") for d, g in e1.groupby("Date")}

    b = pd.read_parquet(DATA / "bars" / "_continuous.parquet")
    b["Date"] = b["DateTime"].dt.date.astype(str)
    eth = pd.read_parquet(DATA / "eth_levels.parquet")
    eth["Date"] = eth["Date"].astype(str)
    eth = eth.set_index("Date")
    dly = b.groupby("Date").agg(dO=("Open", "first"), dH=("High", "max"),
                                dL=("Low", "min"), dC=("Close", "last")).reset_index()
    dly["adr10"] = ((dly.dH - dly.dL)).rolling(10).mean().shift(1)
    dly["pC"] = dly.dC.shift(1); dly["pH"] = dly.dH.shift(1); dly["pL"] = dly.dL.shift(1)
    dly = dly.set_index("Date")

    days = sorted(by_day.keys())
    if limit:
        days = days[:limit]
    rows = []; t0 = time.time()
    for di, dstr in enumerate(days):
        g, tP, tbar = load_day(b, dstr)
        if g is None:
            continue
        O, H, L, C = (g[c].values for c in ["Open", "High", "Low", "Close"])
        n = len(g)
        transitions = phase_transitions(H, L, n, tP, tbar)
        tr_ix = [t for (t, _) in transitions]; tr_md = [m for (_, m) in transitions]
        # trend-start tick indices
        starts = [(ix, md) for (ix, md) in transitions if md != "NEUTRAL"]
        rng = np.maximum(H - L, 1e-9)
        abr10 = pd.Series(rng).rolling(10, min_periods=1).mean().values
        a20 = 2.0 / 21.0
        ema = np.empty(n); ema[0] = C[0]
        for i in range(1, n):
            ema[i] = a20 * C[i] + (1 - a20) * ema[i - 1]
        dd = dly.loc[dstr]
        er = eth.loc[dstr] if dstr in eth.index else None
        piv = swing_pivots(H, L)
        g_dt = g["DateTime"].values

        day_tr = by_day[dstr].sort_values("fire_bar")
        seq = {"L": 0, "S": 0}
        prior_out = {"L": np.nan, "S": np.nan}
        for t in day_tr.itertuples():
            fb = int(t.fire_bar) - 1; sb = int(t.sig_bar) - 1
            short = t.dir == "S"
            fill = t.fill
            atr = max(abr10[fb], TICK)
            # fill tick index -> bars since trend start (phase machine)
            aa = np.searchsorted(tbar, fb, "left"); zz = np.searchsorted(tbar, fb, "right")
            s = tP[aa:zz]
            hit = np.nonzero(s <= fill + TICK/2)[0] if short else np.nonzero(s >= fill - TICK/2)[0]
            jf = aa + int(hit[0]) if len(hit) else aa
            k = bisect_right(tr_ix, jf) - 1
            reg_now = tr_md[k]
            ts_bars = np.nan
            if reg_now != "NEUTRAL":
                ts_tick = tr_ix[k]
                ts_bars = fb - int(tbar[min(ts_tick, len(tbar) - 1)])
            # structure: last confirmed swings before fb
            cps = [(pb, typ, px) for (pb, cf, typ, px) in piv if cf <= fb]
            leg_atr = pb_depth = pb_bars = np.nan
            if short:
                lows = [(pb, px) for (pb, typ, px) in cps if typ == "L"]
                highs = [(pb, px) for (pb, typ, px) in cps if typ == "H"]
                if lows and highs:
                    le_b, le_px = lows[-1]                      # recent extreme low
                    hs = [(pb, px) for (pb, px) in highs if pb < le_b]
                    if hs:
                        st_b, st_px = hs[-1]                    # leg start high
                        leg = st_px - le_px
                        leg_atr = leg / atr
                        pb_hi = H[le_b:fb + 1].max()
                        pb_depth = (pb_hi - le_px) / leg if leg > 0 else np.nan
                        pb_bars = fb - le_b
            else:
                highs = [(pb, px) for (pb, typ, px) in cps if typ == "H"]
                lows = [(pb, px) for (pb, typ, px) in cps if typ == "L"]
                if highs and lows:
                    he_b, he_px = highs[-1]
                    ls = [(pb, px) for (pb, px) in lows if pb < he_b]
                    if ls:
                        st_b, st_px = ls[-1]
                        leg = he_px - st_px
                        leg_atr = leg / atr
                        pb_lo = L[he_b:fb + 1].min()
                        pb_depth = (he_px - pb_lo) / leg if leg > 0 else np.nan
                        pb_bars = fb - he_b
            # pullback overlap (barbwire proxy): avg overlap of last 4 bars before fb
            ov = np.nan
            if fb >= 5:
                o_ = []
                for i in range(fb - 4, fb):
                    inter = min(H[i], H[i+1]) - max(L[i], L[i+1])
                    o_.append(inter / max(rng[i], 1e-9))
                ov = float(np.mean(o_))
            # microchannel before signal: consecutive closed bars with-trend before sb
            mc = 0
            i = sb - 1
            while i >= 1 and ((L[i] >= L[i-1]) if not short else (H[i] <= H[i-1])):
                mc += 1; i -= 1
            # wedge/3-push in pullback: count of local pushes against trend in last pb window
            pushes = np.nan
            w0 = max(1, fb - 10)
            if not short:
                pushes = sum(1 for i in range(w0 + 1, fb)
                             if L[i] < L[i-1] and (i + 1 > fb - 1 or L[i] <= L[i+1]))
            else:
                pushes = sum(1 for i in range(w0 + 1, fb)
                             if H[i] > H[i-1] and (i + 1 > fb - 1 or H[i] >= H[i+1]))
            # ---- Brooks codex gates ----
            # momentum gate: consecutive counter-trend closes into the signal
            cct = 0
            i = sb
            while i >= 1 and ((C[i] < O[i]) if not short else (C[i] > O[i])):
                cct += 1; i -= 1
            # climax lockout: any bar in last 10 with range >= 2x ABR10
            clim = bool((rng[max(0, fb - 10):fb] >= 2 * abr10[max(0, fb - 10):fb]).any())
            # tight-range veto: last-15-bar range vs ADR10
            t15 = ((H[max(0, fb - 15):fb].max() - L[max(0, fb - 15):fb].min()) /
                   dd.adr10) if (fb >= 5 and pd.notna(dd.adr10) and dd.adr10 > 0) else np.nan
            # barbwire: doji fraction of last 4 closed bars
            w4 = slice(max(0, fb - 4), fb)
            doji4 = float(np.mean(np.abs(C[w4] - O[w4]) / rng[w4] < 0.25)) if fb >= 4 else np.nan
            # prior-strength: max with-trend body/range in the prior leg window
            pstr = np.nan
            if np.isfinite(leg_atr):
                lw = slice(st_b, (le_b if short else he_b) + 1)
                bodies = (O[lw] - C[lw]) / rng[lw] if short else (C[lw] - O[lw]) / rng[lw]
                pstr = float(bodies.max()) if len(bodies) else np.nan
            # double-bottom/top pullback: two pushes ~equal (<=3 ticks)
            dbl = np.nan
            if np.isfinite(pb_bars) and pb_bars >= 3:
                w0_ = (le_b if short else he_b)
                half = w0_ + max(1, int(pb_bars // 2))
                if short:
                    a1 = H[w0_:half].max(); a2 = H[half:fb + 1].max()
                else:
                    a1 = L[w0_:half].min(); a2 = L[half:fb + 1].min()
                dbl = bool(abs(a1 - a2) <= 3 * TICK)
            # M2B/M2S: pullback tags the EMA (any pullback bar straddles EMA)
            m2 = False
            if np.isfinite(pb_bars):
                w0_ = (le_b if short else he_b)
                for i in range(w0_, fb + 1):
                    if L[i] <= ema[i] <= H[i]:
                        m2 = True; break
            # better-price trap: 2E fill BETTER than latest prior same-dir 1E fill
            bp = np.nan
            ge1 = e1_by_day.get(dstr)
            if ge1 is not None:
                pri = ge1[(ge1["dir"] == t.dir) & (ge1.fire_bar < t.fire_bar)]
                if len(pri):
                    f1 = pri.fill.iloc[-1]
                    bp = bool(fill > f1) if short else bool(fill < f1)
            # location / day-so-far (bars closed before fb)
            hi_sf = H[:fb].max(); lo_sf = L[:fb].min(); rng_sf = max(hi_sf - lo_sf, 1e-9)
            pos_day = (fill - lo_sf) / rng_sf
            drift = abs(C[fb - 1] - O[0]) / rng_sf if fb >= 1 else np.nan
            fh_rng = (H[:12].max() - L[:12].min()) if n >= 12 else np.nan
            adr = dd.adr10 if pd.notna(dd.adr10) else np.nan
            ema_slope = (ema[fb] - ema[fb - 10]) / atr if fb >= 10 else np.nan
            o_dir = 1 if short else -1  # gap helping?
            gap_pts = (O[0] - dd.pC) if pd.notna(dd.pC) else np.nan
            seq[t.dir] += 1
            rows.append(dict(
                entry_id=f"{dstr}_{fb+1}{t.dir}2", Date=dstr, dir=t.dir,
                netT2=t.net, RmulT2=t.R, netT1=t.netT1, Rpts=t.Rpts,
                regime=reg_now, ts_bars=ts_bars,
                leg_atr=round(leg_atr, 2) if np.isfinite(leg_atr) else np.nan,
                pb_depth=round(pb_depth, 2) if np.isfinite(pb_depth) else np.nan,
                pb_bars=pb_bars, overlap=round(ov, 2) if np.isfinite(ov) else np.nan,
                mchan=mc, pushes=pushes,
                pos_day=round(pos_day, 2), drift=round(drift, 2) if np.isfinite(drift) else np.nan,
                rng_sf_adr=round(rng_sf / adr, 2) if np.isfinite(adr) else np.nan,
                fh_adr=round(fh_rng / adr, 2) if (np.isfinite(adr) and np.isfinite(fh_rng)) else np.nan,
                ema_slope=round(ema_slope, 2) if np.isfinite(ema_slope) else np.nan,
                vs_pC=round((fill - dd.pC) / atr, 1) if pd.notna(dd.pC) else np.nan,
                above_pH=bool(fill > dd.pH) if pd.notna(dd.pH) else np.nan,
                below_pL=bool(fill < dd.pL) if pd.notna(dd.pL) else np.nan,
                gap_atr=round(gap_pts / atr, 2) if np.isfinite(gap_pts) else np.nan,
                nth_2e=seq[t.dir], hour=pd.Timestamp(g_dt[fb]).strftime("%H"),
                prior_out=prior_out[t.dir],
                consec_ct=cct, climax10=clim,
                tight15=round(t15, 2) if np.isfinite(t15) else np.nan,
                doji4=doji4, prior_str=round(pstr, 2) if np.isfinite(pstr) else np.nan,
                dbl_pb=dbl, m2_tag=m2, better_px=bp))
            prior_out[t.dir] = 1.0 if t.net > 0 else 0.0
        del tP, tbar; gc.collect()
        if (di + 1) % 100 == 0:
            print(f"[{di+1}/{len(days)}] ({time.time()-t0:.0f}s)", flush=True)

    f = pd.DataFrame(rows)
    # join sweeps features if present
    sw = WT_ROOT / "data" / "regime" / "second_entries_features_20260723.csv"
    if sw.exists():
        s = pd.read_csv(sw)
        s = s[s["count"] == 2][["entry_id", "ema20_atr", "er10", "adx14", "stochK",
                                "stochD", "zl_osc", "zl_sign", "ib_pos", "va_pos",
                                "eth_pos", "vix", "adr10_pct"]]
        f = f.merge(s, on="entry_id", how="left")
    f.to_csv(OUT_F, index=False)
    print(f"features -> {OUT_F}  n={len(f)}")

    # ================= scans: train/test =================
    def pf(s):
        gp = s[s > 0].sum(); gl = -s[s < 0].sum()
        return gp / gl if gl > 0 else float("inf")

    f["is_tr"] = f.Date <= TRAIN_END
    wt = ((f.regime == "BULL") & (f.dir == "L")) | ((f.regime == "BEAR") & (f.dir == "S"))
    NUMS = ["ts_bars", "leg_atr", "pb_depth", "pb_bars", "overlap", "mchan", "pushes",
            "pos_day", "drift", "rng_sf_adr", "fh_adr", "ema_slope", "vs_pC", "gap_atr",
            "nth_2e", "ema20_atr", "er10", "adx14", "stochK", "zl_osc", "vix", "adr10_pct",
            "consec_ct", "tight15", "doji4", "prior_str"]
    CATS = ["regime", "hour", "ib_pos", "va_pos", "eth_pos", "prior_out",
            "above_pH", "below_pL", "zl_sign",
            "climax10", "dbl_pb", "m2_tag", "better_px"]
    scan = []
    for c in NUMS:
        if c not in f.columns:
            continue
        x = f.dropna(subset=[c])
        if len(x) < 300:
            continue
        try:
            x = x.copy(); x["q"] = pd.qcut(x[c], 4, duplicates="drop")
        except Exception:
            continue
        for qv, gq in x.groupby("q", observed=True):
            trn = gq[gq.is_tr]; tst = gq[~gq.is_tr]
            scan.append(("num", c, str(qv), len(trn), round(pf(trn.netT2), 3),
                         round(trn.netT2.sum()), len(tst), round(pf(tst.netT2), 3),
                         round(tst.netT2.sum())))
    for c in CATS:
        if c not in f.columns:
            continue
        for v, gq in f.groupby(c, dropna=True):
            if len(gq) < 100:
                continue
            trn = gq[gq.is_tr]; tst = gq[~gq.is_tr]
            scan.append(("cat", c, str(v), len(trn), round(pf(trn.netT2), 3),
                         round(trn.netT2.sum()), len(tst), round(pf(tst.netT2), 3),
                         round(tst.netT2.sum())))
    # 2-condition rule search on TRAIN (quartile-extreme x quartile-extreme, plus WT)
    conds = {}
    for c in NUMS:
        if c not in f.columns:
            continue
        x = f[c].dropna()
        if len(x) < 500:
            continue
        lo, hi = x.quantile(0.25), x.quantile(0.75)
        conds[f"{c}<=q1"] = f[c] <= lo
        conds[f"{c}>=q3"] = f[c] >= hi
    conds["WT"] = wt
    conds["hour!=EOD"] = f.hour < f.hour.max()
    names = list(conds)
    for i in range(len(names)):
        for j in range(i + 1, len(names)):
            m = conds[names[i]] & conds[names[j]]
            trn = f[m & f.is_tr]; tst = f[m & ~f.is_tr]
            if len(trn) < 150 or len(tst) < 60:
                continue
            scan.append(("rule2", names[i] + " & " + names[j], "", len(trn),
                         round(pf(trn.netT2), 3), round(trn.netT2.sum()),
                         len(tst), round(pf(tst.netT2), 3), round(tst.netT2.sum())))
    sc = pd.DataFrame(scan, columns=["kind", "feature", "bucket", "n_tr", "PF_tr",
                                     "net_tr", "n_te", "PF_te", "net_te"])
    sc.to_csv(OUT_S, index=False)
    surv = sc[(sc.PF_tr > 1.0) & (sc.PF_te > 1.0)].sort_values("net_te", ascending=False)
    print(f"\nscan -> {OUT_S}  rows={len(sc)}")
    print("\n== SURVIVORS (PF>1 in BOTH train and test) ==")
    print(surv.head(40).to_string(index=False) if len(surv) else "  NONE")
    top_tr = sc.sort_values("net_tr", ascending=False).head(15)
    print("\n== top-15 by TRAIN net (for honesty, with their test cols) ==")
    print(top_tr.to_string(index=False))


if __name__ == "__main__":
    main()
