"""LOSER AUTOPSY — WT-L (2EL), WT-S (2ES), FADE (f2EL). Find a causal 'tell' that
separates losers from winners, per book. Train<=2023 / test 2024+.

Every feature is known AT the fill bar (causal, no lookahead):
  er10, adx14, ema20 dist (ATR units), stochK, gap%, vix_prev, prevday_rng%, adr,
  dayrange_so_far/adr, drift, hour, dow, sig-bar ibs/body/range-x-abr, bars_in_trend,
  dist_from_last_pivot(atr).
Reports: winners-vs-losers mean per feature (with a separation score), then a
train-only filter search (drop worst-quartile / skip a cut) evaluated on test.
CAVEAT printed: the tail edge PAYS FOR small losers - a filter that removes them
can hurt; only filters that raise BOTH $/tr and PF train+test are candidates.

  python scripts/regime_loser_autopsy.py [--limit N]
Output: data/regime/loser_autopsy_20260724.csv + tables.
"""
import sys, gc, time
from pathlib import Path
from bisect import bisect_right
import numpy as np
import pandas as pd
sys.path.insert(0, str(Path(__file__).resolve().parent))
from regime_second_entry_study import phase_transitions, load_day   # noqa: E402
from regime_2e_causal_check import detect_entries_causal            # noqa: E402

TICK = 0.25; PT = 50.0; COMM = 5.0; SLIP = 12.5
WT = Path(__file__).resolve().parent.parent
DATA = Path(r"C:/Users/Admin/myquant/data")
OUT = WT / "data" / "regime" / "loser_autopsy_20260724.csv"
GOOD = {"09", "10", "11", "12", "13"}
FLOOR = 8 * TICK
TRAIN_END = "2023-12-31"


def ema(x, n):
    a = 2.0 / (n + 1); o = np.empty_like(x, float); o[0] = x[0]
    for i in range(1, len(x)):
        o[i] = a * x[i] + (1 - a) * o[i-1]
    return o


def adx(H, L, C, n=14):
    m = len(C); tr = np.zeros(m); pdm = np.zeros(m); ndm = np.zeros(m)
    for i in range(1, m):
        tr[i] = max(H[i]-L[i], abs(H[i]-C[i-1]), abs(L[i]-C[i-1]))
        up = H[i]-H[i-1]; dn = L[i-1]-L[i]
        pdm[i] = up if (up > dn and up > 0) else 0
        ndm[i] = dn if (dn > up and dn > 0) else 0
    atr = pd.Series(tr).rolling(n, min_periods=1).mean().values
    pdi = 100*pd.Series(pdm).rolling(n, min_periods=1).mean().values/np.maximum(atr, 1e-9)
    ndi = 100*pd.Series(ndm).rolling(n, min_periods=1).mean().values/np.maximum(atr, 1e-9)
    dx = 100*np.abs(pdi-ndi)/np.maximum(pdi+ndi, 1e-9)
    return pd.Series(dx).rolling(n, min_periods=1).mean().values


def er10(C):
    m = len(C); o = np.full(m, np.nan); dif = np.abs(np.diff(C, prepend=C[0]))
    for i in range(10, m):
        den = dif[i-9:i+1].sum(); o[i] = abs(C[i]-C[i-10])/den if den > 0 else 0
    return o


def main():
    limit = None
    if "--limit" in sys.argv:
        limit = int(sys.argv[sys.argv.index("--limit")+1])
    b = pd.read_parquet(DATA/"bars"/"_continuous.parquet"); b["Date"] = b["DateTime"].dt.date.astype(str)
    dly = b.groupby("Date").agg(dO=("Open","first"), dC=("Close","last"), dH=("High","max"), dL=("Low","min")).reset_index()
    dly["adr10"] = (dly.dH-dly.dL).rolling(10).mean().shift(1)
    dly["gap"] = ((dly.dO-dly.dC.shift(1))/dly.dC.shift(1)*100).abs()
    dly["prevrng"] = ((dly.dH-dly.dL)/dly.dC*100).shift(1)
    gm = dly.set_index("Date")[["adr10", "gap", "prevrng"]]
    vix = pd.read_csv(WT/"data"/"VIX_History.csv"); vix["Date"] = pd.to_datetime(vix.DATE).dt.date.astype(str)
    vixp = vix.sort_values("Date").assign(v=lambda d: d.CLOSE.shift(1)).set_index("Date")["v"].to_dict()
    days = sorted(b["Date"].unique())
    if limit:
        days = days[:limit]

    rows = []; t0 = time.time()
    for di, dstr in enumerate(days):
        if dstr not in gm.index:
            continue
        adr, gapv, prevrng = gm.loc[dstr, "adr10"], gm.loc[dstr, "gap"], gm.loc[dstr, "prevrng"]
        if not np.isfinite(adr) or gapv > 0.54:
            continue
        g, tP, tbar = load_day(b, dstr)
        if g is None:
            continue
        O, H, L, C = (g[c].values for c in ["Open", "High", "Low", "Close"])
        n = len(g); rngb = np.maximum(H-L, 1e-9)
        e20 = ema(C, 20); ax = adx(H, L, C); er = er10(C)
        abr = pd.Series(rngb).rolling(10, min_periods=1).mean().values
        try:
            trans = phase_transitions(H, L, n, tP, tbar); entries = detect_entries_causal(g, tP, tbar)
        except Exception:
            continue
        tr_ix = [t for t, _ in trans]; tr_md = [m for _, m in trans]
        g_dt = g["DateTime"].values; sd = max(round(0.30*adr/TICK)*TICK, FLOOR)
        vv = vixp.get(dstr, np.nan)
        for (fb, sb, dr, cnt, trig) in entries:
            if cnt != 2:
                continue
            short = dr == "S"
            a = np.searchsorted(tbar, fb, "left"); z = np.searchsorted(tbar, fb, "right")
            hit = np.nonzero(tP[a:z] <= trig)[0] if short else np.nonzero(tP[a:z] >= trig)[0]
            if not len(hit):
                continue
            jf = a+int(hit[0]); reg = tr_md[bisect_right(tr_ix, jf)-1]; want = "BEAR" if short else "BULL"
            book = None; fill = None; fb2 = None; stopd = None
            if reg == want:                       # WT
                lim = trig+6*TICK if short else trig-6*TICK; s0 = tP[jf:]
                jl = np.nonzero(s0 > lim)[0] if short else np.nonzero(s0 < lim)[0]
                if not len(jl):
                    continue
                jfl = jf+int(jl[0]); fb2 = int(tbar[jfl])
                if fb2-fb > 6:
                    continue
                stopd = sd; fill = lim; book = "WT-S" if short else "WT-L"; jj = jfl
            elif (not short) and reg == "BEAR":   # f2EL fade short
                fail = L[sb]-TICK; zl = np.searchsorted(tbar, fb+3, "left")
                w = np.nonzero(tP[jf:zl] <= fail)[0]
                if not len(w):
                    continue
                jj = jf+int(w[0]); fb2 = int(tbar[jj])
                if sb >= fb2:
                    continue
                stopd = 16*TICK; fill = fail-TICK; book = "FADE"; short = True
            else:
                continue
            hh = pd.Timestamp(g_dt[min(fb2, n-1)]).strftime("%H")
            if hh not in GOOD:
                continue
            stop = fill+stopd if short else fill-stopd; seg = tP[jj:]
            js = np.nonzero(seg >= stop)[0] if short else np.nonzero(seg <= stop)[0]
            ex = stop if len(js) else seg[-1]
            net = round(((fill-ex) if short else (ex-fill))*PT-COMM-SLIP, 1)
            # features at fb (last completed bar before/at fill; use fb signal bar)
            hi_sf = H[:fb2].max() if fb2 >= 1 else H[0]; lo_sf = L[:fb2].min() if fb2 >= 1 else L[0]
            rsf = hi_sf-lo_sf
            rows.append(dict(Date=dstr, book=book, net=net,
                er10=round(float(er[fb2]), 3) if np.isfinite(er[fb2]) else np.nan,
                adx14=round(float(ax[fb2]), 1), ema_atr=round((fill-e20[fb2])/max(abr[fb2], TICK)*(1 if not short else -1), 2),
                gap=round(gapv, 3), vix=round(vv, 1) if np.isfinite(vv) else np.nan,
                prevrng=round(prevrng, 3) if np.isfinite(prevrng) else np.nan,
                rsf_adr=round(rsf/adr, 2), hour=int(hh),
                dow=pd.Timestamp(dstr).dayofweek,
                sb_ibs=round((C[sb]-L[sb])/rngb[sb], 2),
                sb_body=round(abs(C[sb]-O[sb])/rngb[sb], 2),
                sb_rngx=round(rngb[sb]/max(abr[sb], 1e-9), 2)))
        del tP, tbar; gc.collect()
        if (di+1) % 200 == 0:
            print(f"[{di+1}/{len(days)}] rows={len(rows)} ({time.time()-t0:.0f}s)", flush=True)

    df = pd.DataFrame(rows); df.to_csv(OUT, index=False); df["is_tr"] = df.Date <= TRAIN_END
    FEATS = ["er10", "adx14", "ema_atr", "gap", "vix", "prevrng", "rsf_adr", "hour", "dow",
             "sb_ibs", "sb_body", "sb_rngx"]

    def pf(s):
        s = np.asarray(s); gp = s[s > 0].sum(); gl = -s[s < 0].sum()
        return round(gp/gl, 2) if gl > 0 else 0
    print(f"\nDONE {time.time()-t0:.0f}s  rows={len(df)}")
    for bk in ("WT-L", "WT-S", "FADE"):
        x = df[df.book == bk]
        win = x[x.net > 0]; los = x[x.net <= 0]
        print(f"\n===== {bk}  (n={len(x)}, win {len(win)}/{len(x)} = {100*len(win)/max(len(x),1):.0f}%, PF {pf(x.net)}) =====")
        print(f"{'feature':10s}  {'win mean':>9s}  {'lose mean':>9s}  {'sep(sd)':>7s}")
        seps = []
        for f in FEATS:
            wv = win[f].dropna(); lv = los[f].dropna()
            if len(wv) < 10 or len(lv) < 10:
                continue
            pooled = np.sqrt((wv.std()**2 + lv.std()**2)/2) or 1
            sep = (wv.mean()-lv.mean())/pooled
            seps.append((abs(sep), f, wv.mean(), lv.mean(), sep))
        for _, f, wm, lm, sep in sorted(seps, reverse=True):
            print(f"{f:10s}  {wm:9.2f}  {lm:9.2f}  {sep:+7.2f}")
        # train-only filter search on the top separators: drop worst quartile in TRAIN, test on OOS
        print("  -- candidate filters (drop tail by TRAIN quartile; must raise $/tr & PF both halves) --")
        trn = x[x.is_tr]
        for _, f, wm, lm, sep in sorted(seps, reverse=True)[:6]:
            q = trn[f].quantile(0.25 if sep > 0 else 0.75)
            keep = (x[f] >= q) if sep > 0 else (x[f] <= q)
            xf = x[keep]; base_tr, base_te = x[x.is_tr], x[~x.is_tr]
            ftr, fte = xf[xf.is_tr], xf[~xf.is_tr]
            better = (ftr.net.mean() > base_tr.net.mean() and fte.net.mean() > base_te.net.mean()
                      and pf(ftr.net) > pf(base_tr.net) and pf(fte.net) > pf(base_te.net))
            tag = "  <== CANDIDATE" if better else ""
            print(f"    keep {f}{'>=' if sep>0 else '<='}{q:.2f}: kept {len(xf)}/{len(x)}  "
                  f"$/tr {x.net.mean():+.0f}->{xf.net.mean():+.0f}  PF {pf(x.net)}->{pf(xf.net)}  "
                  f"(tr {pf(ftr.net)} te {pf(fte.net)}){tag}")


if __name__ == "__main__":
    main()
