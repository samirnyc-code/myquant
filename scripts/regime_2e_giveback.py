"""MFE GIVE-BACK diagnostic + exit-rule variants — S83.

Three books, each on its own geometry:
  2EL long BULL, 2ES short BEAR   -> wide 0.30xADR10 stop
  f2EL fade short BEAR            -> tight 4pt stop
All: gap<=0.54 skip, retest6 (WT) / fail-entry (fade), h09-13, $5 RT + 1t exit slip.

Per trade, from the FILL tick, record the whole path: MFE (best favorable, R and pts),
MAE, bar of peak, terminal EOD/stop PnL. DIAGNOSTIC: how much of reached MFE is given
back; how many trades reach >=1R/>=2R MFE then close <=0.

EXIT VARIANTS (vs EOD baseline), each per book + combined, train/test:
  eod        : hold to close / stop            (baseline)
  gb25/gb50  : after +1R, exit if price gives back 25%/50% of MFE-peak-from-fill
  peakK      : after +1R, exit K pts below MFE peak (K = 0.5xstop)
  t1r        : hard +1R target                 (reference - known bad)
  d1         : MenthorQ D1max (short)/D1min (long) as target, else EOD

Output: data/regime/giveback_20260724.csv + tables + PNG.
  python scripts/regime_2e_giveback.py [--limit N]
"""
import sys, gc, time
from pathlib import Path
from bisect import bisect_right
import numpy as np
import pandas as pd
import matplotlib; matplotlib.use("Agg")
import matplotlib.pyplot as plt

TICK = 0.25; PT = 50.0; COMM = 5.0; SLIP = 12.5
WT = Path(__file__).resolve().parent.parent
DATA = Path(r"C:/Users/Admin/myquant/data")
sys.path.insert(0, str(WT / "scripts"))
from regime_second_entry_study import phase_transitions, load_day   # noqa: E402
from regime_2e_causal_check import detect_entries_causal            # noqa: E402

OUT = WT / "data" / "regime" / "giveback_20260724.csv"
GOOD = {"09", "10", "11", "12", "13"}
TRAIN_END = "2023-12-31"
FLOOR = 8 * TICK


def exits(seg, fill, stop, short, R, d1):
    """Return dict variant->exit price. seg = tick path from fill (incl)."""
    n = len(seg)
    # running MFE index/level and stop-hit index
    if short:
        adv = np.nonzero(seg >= stop)[0]
        fav = fill - seg                       # favorable = how far below fill
    else:
        adv = np.nonzero(seg <= stop)[0]
        fav = seg - fill
    jstop = adv[0] if len(adv) else np.inf
    # running peak favorable
    peak = np.maximum.accumulate(fav)
    out = {}
    # eod baseline
    out["eod"] = stop if np.isfinite(jstop) else seg[-1]
    # +1R hard target
    tgt1 = fill - R if short else fill + R
    jt1 = np.nonzero(seg <= tgt1)[0] if short else np.nonzero(seg >= tgt1)[0]
    jt1 = jt1[0] if len(jt1) else np.inf
    out["t1r"] = (stop if jstop <= jt1 else (tgt1 if np.isfinite(jt1) else seg[-1]))
    # give-back variants: only arm after +1R favorable reached
    j1r = np.nonzero(fav >= R)[0]
    j1r = j1r[0] if len(j1r) else np.inf
    for gid, frac in (("gb25", 0.25), ("gb50", 0.50)):
        if not np.isfinite(j1r):
            out[gid] = out["eod"]; continue
        ex = None
        for i in range(int(j1r), n):
            if np.isfinite(jstop) and i >= jstop:
                ex = stop; break
            if fav[i] <= peak[i] * (1 - frac) and peak[i] >= R:
                ex = (fill - fav[i]) if short else (fill + fav[i]); break
        out[gid] = ex if ex is not None else seg[-1]
    # peakK: after +1R, exit K=0.5*stop_pts below the running peak
    Kpk = 0.5 * abs(fill - stop)
    if np.isfinite(j1r):
        ex = None
        for i in range(int(j1r), n):
            if np.isfinite(jstop) and i >= jstop:
                ex = stop; break
            if fav[i] <= peak[i] - Kpk and peak[i] >= R:
                ex = (fill - fav[i]) if short else (fill + fav[i]); break
        out["peakK"] = ex if ex is not None else seg[-1]
    else:
        out["peakK"] = out["eod"]
    # D1 target
    if d1 is not None and np.isfinite(d1):
        jd = np.nonzero(seg <= d1)[0] if short else np.nonzero(seg >= d1)[0]
        jd = jd[0] if len(jd) else np.inf
        out["d1"] = stop if jstop <= jd else (d1 if np.isfinite(jd) else seg[-1])
    else:
        out["d1"] = out["eod"]
    mfe_pts = float(peak[-1]); mfe_r = mfe_pts / R if R > 0 else 0
    peak_bar = int(np.argmax(fav))
    return out, mfe_pts, mfe_r, peak_bar, np.isfinite(jstop)


def main():
    limit = None
    if "--limit" in sys.argv:
        limit = int(sys.argv[sys.argv.index("--limit") + 1])
    b = pd.read_parquet(DATA / "bars" / "_continuous.parquet")
    b["Date"] = b["DateTime"].dt.date.astype(str)
    dly = b.groupby("Date").agg(dO=("Open", "first"), dC=("Close", "last"),
                                dH=("High", "max"), dL=("Low", "min")).reset_index()
    dly["adr10"] = (dly.dH - dly.dL).rolling(10).mean().shift(1)
    dly["gap"] = ((dly.dO - dly.dC.shift(1)) / dly.dC.shift(1) * 100).abs()
    gmap = dly.set_index("Date")[["adr10", "gap"]]
    # MenthorQ D1 levels
    try:
        mq = pd.read_csv(DATA / "menthorq" / "ES1!_mq_levels_history.csv")
        mq["session_date"] = mq.session_date.astype(str)
        d1map = mq.set_index("session_date")[["d1_min", "d1_max"]].to_dict("index")
    except Exception:
        d1map = {}
    days = sorted(b["Date"].unique())
    if limit:
        days = days[:limit]

    VARIANTS = ["eod", "gb25", "gb50", "peakK", "t1r", "d1"]
    rows = []; t0 = time.time()
    for di, dstr in enumerate(days):
        if dstr not in gmap.index:
            continue
        adr, gapv = gmap.loc[dstr, "adr10"], gmap.loc[dstr, "gap"]
        if not np.isfinite(adr) or gapv > 0.54:
            continue
        g, tP, tbar = load_day(b, dstr)
        if g is None:
            continue
        O, H, L, C = (g[c].values for c in ["Open", "High", "Low", "Close"])
        n = len(g)
        try:
            trans = phase_transitions(H, L, n, tP, tbar)
            entries = detect_entries_causal(g, tP, tbar)
        except Exception as e:
            print(dstr, "ERR", repr(e), flush=True); continue
        tr_ix = [t for (t, _) in trans]; tr_md = [m for (_, m) in trans]
        g_dt = g["DateTime"].values
        wide = max(round(0.30 * adr / TICK) * TICK, FLOOR)
        tight = 16 * TICK
        d1 = d1map.get(dstr, {})
        d1min = d1.get("d1_min", np.nan); d1max = d1.get("d1_max", np.nan)

        def emit(book, short, jfl, fill, sdist):
            fb2 = int(tbar[min(jfl, len(tbar) - 1)])
            hh = pd.Timestamp(g_dt[min(fb2, n - 1)]).strftime("%H")
            if hh not in GOOD:
                return
            stop = fill + sdist if short else fill - sdist
            R = abs(fill - stop)
            seg = tP[jfl:]
            d1t = (d1max if short else d1min)
            ex, mfe_pts, mfe_r, pkb, stopped = exits(seg, fill, stop, short, R, d1t)
            for v in VARIANTS:
                pnl = ((fill - ex[v]) if short else (ex[v] - fill)) * PT - COMM - SLIP
                rows.append((dstr, book, "S" if short else "L", v, round(pnl, 1),
                             round(mfe_r, 2), round(mfe_pts, 2)))

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
            reg = tr_md[bisect_right(tr_ix, jf) - 1]
            want = "BEAR" if short else "BULL"
            if reg == want:
                lim = trig + 6 * TICK if short else trig - 6 * TICK
                seg0 = tP[jf:]
                jl = np.nonzero(seg0 > lim)[0] if short else np.nonzero(seg0 < lim)[0]
                if len(jl):
                    jfl = jf + int(jl[0])
                    if int(tbar[jfl]) - fb <= 6:
                        emit("WT", short, jfl, lim, wide)
            else:
                fade_short = not short
                need = "BEAR" if fade_short else "BULL"
                if reg != need or not fade_short:      # only f2EL (fade short); f2ES dead
                    continue
                sb_ext = L[sb]
                fail_px = sb_ext - TICK
                zlim = np.searchsorted(tbar, fb + 3, "left")
                segf = tP[jf:zlim]
                w = np.nonzero(segf <= fail_px)[0]
                if len(w):
                    jx = jf + int(w[0])
                    emit("FADE", True, jx, fail_px - TICK, tight)
        del tP, tbar; gc.collect()
        if (di + 1) % 200 == 0:
            print(f"[{di+1}/{len(days)}] rows={len(rows)} ({time.time()-t0:.0f}s)", flush=True)

    df = pd.DataFrame(rows, columns=["Date", "book", "dir", "variant", "net", "mfe_r", "mfe_pts"])
    df.to_csv(OUT, index=False)
    df["is_tr"] = df.Date <= TRAIN_END

    def pf(s):
        gp = s[s > 0].sum(); gl = -s[s < 0].sum()
        return round(gp / gl, 2) if gl > 0 else 0

    def mdd(x):
        e = x.sort_values("Date").net.cumsum(); return float((e - e.cummax()).min())

    # DIAGNOSTIC on the EOD baseline
    base = df[df.variant == "eod"]
    print(f"\nDONE {time.time()-t0:.0f}s  trades/variant={len(base)}")
    print("\n=== GIVE-BACK DIAGNOSTIC (EOD baseline) ===")
    for bk in ("WT", "FADE"):
        x = base[base.book == bk]
        rich = x[x.mfe_r >= 1.0]; rich2 = x[x.mfe_r >= 2.0]
        roundtrip = x[(x.mfe_r >= 1.0) & (x.net <= 0)]
        gaveback = rich[rich.net > 0]
        print(f"{bk}: n={len(x)}  reached>=1R MFE {len(rich)} ({100*len(rich)/len(x):.0f}%)  "
              f">=2R {len(rich2)} ({100*len(rich2)/len(x):.0f}%)  "
              f"ROUND-TRIP (>=1R then <=0): {len(roundtrip)} ({100*len(roundtrip)/max(len(rich),1):.0f}% of rich)")
        if len(rich):
            avg_mfe = rich.mfe_r.mean()
            print(f"     among >=1R winners: avg MFE {avg_mfe:.2f}R, avg captured "
                  f"{gaveback.net.mean()/ (rich.mfe_pts.mean()*PT):.0%} of MFE$ (rough)")

    print("\n=== EXIT VARIANTS ($/tr, PF, maxDD, train|test) ===")
    for bk in ("WT", "FADE", "ALL"):
        print(f"\n-- book: {bk} --")
        for v in VARIANTS:
            x = df[(df.variant == v) & ((df.book == bk) if bk != "ALL" else True)]
            if not len(x):
                continue
            trn, tst = x[x.is_tr], x[~x.is_tr]
            star = "  <= baseline" if v == "eod" else ""
            print(f"  {v:6s} n={len(x):4d}  net {x.net.sum():+8,.0f}  $/tr {x.net.mean():+6.1f}  "
                  f"PF {pf(x.net):4.2f}  maxDD {mdd(x):+8,.0f}  {pf(trn.net):4.2f}|{pf(tst.net):4.2f}{star}")

    # chart: combined equity per variant
    fig, ax = plt.subplots(figsize=(12, 6), dpi=115)
    for v in VARIANTS:
        x = df[df.variant == v].sort_values("Date")
        ax.plot(range(len(x)), x.net.cumsum().values, lw=2 if v == "eod" else 1.4,
                label=f"{v}: {x.net.sum():+,.0f}$ PF {pf(x.net)}")
    ax.axhline(0, color="#c3c2b7", lw=1); ax.legend(frameon=False, fontsize=9)
    ax.grid(axis="y", color="#eceeed", lw=0.7)
    for s_ in ("top", "right"): ax.spines[s_].set_visible(False)
    ax.set_title("Exit-rule variants (all 3 books combined) vs EOD baseline", fontweight="bold")
    fig.tight_layout()
    p = WT / "docs" / "living" / "giveback_20260724.png"
    fig.savefig(p, facecolor="white"); print("\nsaved", p)


if __name__ == "__main__":
    main()
