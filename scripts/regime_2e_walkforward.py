"""STRESS TEST #1 — rolling WALK-FORWARD + reusable stress dataset.

Tick pass (NO gap filter) captures per three-book trade: Date, book, dir, gap%,
gross$ (ES, pre-cost), and net$ at stop-multiples {0.20,0.30,0.40}xADR (WT) /
fixed 4pt (fade). This dataset also feeds the parameter-neighborhood & cost tests.

WALK-FORWARD: rolling 12-mo IS / 3-mo OOS, slide 3mo. Per window:
  - re-derive gap threshold = IS 75th-pctile of |gap| (self-adjusting, not fitted)
  - pick best stop-mult in IS (by net); apply to the next 3-mo OOS
Compare CONCATENATED OOS: walk-forward-optimized vs FIXED (0.54 gap, 0.30 stop).
The honest test: does optimizing beat leaving it alone? (expect: fixed ties/wins.)

  python scripts/regime_2e_walkforward.py [--limit N]
Output: data/regime/wf_dataset_20260725.csv + WF tables + PNG.
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

DS = WT / "data" / "regime" / "wf_dataset_20260725.csv"
GOOD = {"09", "10", "11", "12", "13"}
FLOOR = 8 * TICK
STOP_MULTS = [0.20, 0.30, 0.40]


def build_dataset(days, gm, b):
    rows = []; t0 = time.time()
    for di, dstr in enumerate(days):
        if dstr not in gm.index:
            continue
        adr, gapv = gm.loc[dstr, "adr10"], gm.loc[dstr, "gap"]
        if not np.isfinite(adr):
            continue
        g, tP, tbar = load_day(b, dstr)
        if g is None:
            continue
        O, H, L, C = (g[c].values for c in ["Open", "High", "Low", "Close"])
        n = len(g)
        try:
            trans = phase_transitions(H, L, n, tP, tbar); entries = detect_entries_causal(g, tP, tbar)
        except Exception:
            continue
        tr_ix = [t for (t, _) in trans]; tr_md = [m for (_, m) in trans]
        g_dt = g["DateTime"].values

        def net_at(jj, fill, short, sdist):
            stop = fill + sdist if short else fill - sdist
            seg = tP[jj:]
            js = np.nonzero(seg >= stop)[0] if short else np.nonzero(seg <= stop)[0]
            ex = stop if len(js) else seg[-1]
            gross = ((fill - ex) if short else (ex - fill)) * PT
            return round(gross, 1), round(gross - COMM - SLIP, 1)

        for (fb, sb, dr, cnt, trig) in entries:
            if cnt != 2:
                continue
            short = dr == "S"
            a = np.searchsorted(tbar, fb, "left"); z = np.searchsorted(tbar, fb, "right")
            hit = np.nonzero(tP[a:z] <= trig)[0] if short else np.nonzero(tP[a:z] >= trig)[0]
            if not len(hit):
                continue
            jf = a + int(hit[0]); reg = tr_md[bisect_right(tr_ix, jf) - 1]
            want = "BEAR" if short else "BULL"
            if reg == want:
                lim = trig + 6 * TICK if short else trig - 6 * TICK; s0 = tP[jf:]
                jl = np.nonzero(s0 > lim)[0] if short else np.nonzero(s0 < lim)[0]
                if not len(jl):
                    continue
                jfl = jf + int(jl[0]); fb2 = int(tbar[jfl])
                if fb2 - fb > 6:
                    continue
                hh = pd.Timestamp(g_dt[min(fb2, n - 1)]).strftime("%H")
                if hh not in GOOD:
                    continue
                rec = dict(Date=dstr, book="WT", dir=dr, gap=round(gapv, 3))
                for mlt in STOP_MULTS:
                    sd = max(round(mlt * adr / TICK) * TICK, FLOOR)
                    gr, nt = net_at(jfl, lim, short, sd)
                    rec[f"gross_{int(mlt*100)}"] = gr; rec[f"net_{int(mlt*100)}"] = nt
                rows.append(rec)
            elif (not short) and reg == "BEAR":
                fail = L[sb] - TICK; zl = np.searchsorted(tbar, fb + 3, "left")
                w = np.nonzero(tP[jf:zl] <= fail)[0]
                if not len(w):
                    continue
                jx = jf + int(w[0]); fb2 = int(tbar[jx])
                if sb >= fb2:
                    continue
                hh = pd.Timestamp(g_dt[min(fb2, n - 1)]).strftime("%H")
                if hh not in GOOD:
                    continue
                gr, nt = net_at(jx, fail - TICK, True, 16 * TICK)
                rec = dict(Date=dstr, book="FADE", dir="S", gap=round(gapv, 3))
                for mlt in STOP_MULTS:      # fade stop fixed; same across mults
                    rec[f"gross_{int(mlt*100)}"] = gr; rec[f"net_{int(mlt*100)}"] = nt
                rows.append(rec)
        del tP, tbar; gc.collect()
        if (di + 1) % 200 == 0:
            print(f"[{di+1}/{len(days)}] rows={len(rows)} ({time.time()-t0:.0f}s)", flush=True)
    df = pd.DataFrame(rows); df.to_csv(DS, index=False)
    print(f"dataset -> {DS}  ({len(df)} rows, all days incl gap)")
    return df


def pf(s):
    s = np.asarray(s); gp = s[s > 0].sum(); gl = -s[s < 0].sum()
    return round(gp / gl, 2) if gl > 0 else 0


def main():
    limit = None
    if "--limit" in sys.argv:
        limit = int(sys.argv[sys.argv.index("--limit") + 1])
    b = pd.read_parquet(DATA / "bars" / "_continuous.parquet"); b["Date"] = b["DateTime"].dt.date.astype(str)
    dly = b.groupby("Date").agg(dO=("Open", "first"), dC=("Close", "last"), dH=("High", "max"), dL=("Low", "min")).reset_index()
    dly["adr10"] = (dly.dH - dly.dL).rolling(10).mean().shift(1)
    dly["gap"] = ((dly.dO - dly.dC.shift(1)) / dly.dC.shift(1) * 100).abs()
    gm = dly.set_index("Date")[["adr10", "gap"]]
    days = sorted(b["Date"].unique())
    if limit:
        days = days[:limit]
    if DS.exists() and "--reuse" in sys.argv:
        df = pd.read_csv(DS)
    else:
        df = build_dataset(days, gm, b)
    df["dt"] = pd.to_datetime(df.Date)

    # ---- WALK-FORWARD ----
    starts = pd.date_range("2022-06-01", "2026-04-01", freq="3MS")
    wf_oos = []; fix_oos = []; thresholds = []
    for oos_start in starts:
        is_lo = oos_start - pd.DateOffset(months=12); is_hi = oos_start
        oos_hi = oos_start + pd.DateOffset(months=3)
        IS = df[(df.dt >= is_lo) & (df.dt < is_hi)]
        OOS = df[(df.dt >= oos_start) & (df.dt < oos_hi)]
        if len(IS) < 40 or not len(OOS):
            continue
        thr = np.percentile(IS["gap"], 75); thresholds.append(thr)
        # pick best stop-mult in IS (WT only; fade fixed) by net on gap<=thr days
        best_m, best_net = 30, -1e9
        for mlt in STOP_MULTS:
            isf = IS[IS.gap <= thr]
            nm = isf[f"net_{int(mlt*100)}"].sum()
            if nm > best_net:
                best_net = nm; best_m = int(mlt*100)
        # OOS with WF-chosen threshold+stop
        of = OOS[OOS.gap <= thr]
        wf_oos.append(of[f"net_{best_m}"])
        # OOS with FIXED (0.54 gap, 0.30 stop)
        ff = OOS[OOS.gap <= 0.54]
        fix_oos.append(ff["net_30"])
    wf = pd.concat(wf_oos) if wf_oos else pd.Series(dtype=float)
    fx = pd.concat(fix_oos) if fix_oos else pd.Series(dtype=float)
    print("\n=== WALK-FORWARD (concatenated OOS, ~16 quarters) ===")
    print(f"gap threshold re-derived per window: mean {np.mean(thresholds):.3f}%  "
          f"range {min(thresholds):.3f}-{max(thresholds):.3f}  (adopted const = 0.54)")
    print(f"WF-OPTIMIZED OOS (per-window best stop+threshold): n={len(wf)}  net {wf.sum():+,.0f}  PF {pf(wf)}")
    print(f"FIXED OOS       (0.54 gap, 0.30 stop, no optimizing): n={len(fx)}  net {fx.sum():+,.0f}  PF {pf(fx)}")
    print(f"-> optimizing {'BEAT' if wf.sum()>fx.sum() else 'did NOT beat'} fixed "
          f"({wf.sum()-fx.sum():+,.0f}); if fixed wins, the knobs should stay fixed.")
    # quarterly OOS distribution (fixed)
    fdf = df[df.gap <= 0.54].copy(); fdf["q"] = fdf.dt.dt.to_period("Q")
    fdf = fdf[fdf.dt >= "2022-06-01"]
    q = fdf.groupby("q").net_30.agg(n="size", net="sum")
    q["PF"] = fdf.groupby("q").net_30.apply(pf)
    print(f"\nquarterly OOS (fixed params): {len(q)} quarters, "
          f"{int((q.net>0).sum())} green ({100*(q.net>0).mean():.0f}%), "
          f"worst {q.net.min():+,.0f}, median {q.net.median():+,.0f}")
    print(q.to_string())

    fig, ax = plt.subplots(figsize=(12, 5.5), dpi=115)
    qq = q.reset_index(); qq["qs"] = qq["q"].astype(str)
    cols = ["#1f7a3d" if v >= 0 else "#b23a2e" for v in qq.net]
    ax.bar(range(len(qq)), qq.net.values, color=cols)
    ax.set_xticks(range(len(qq))); ax.set_xticklabels(qq.qs, rotation=45, ha="right", fontsize=8)
    ax.axhline(0, color="#c3c2b7", lw=1); ax.grid(axis="y", color="#eceeed", lw=0.7)
    for s_ in ("top", "right"): ax.spines[s_].set_visible(False)
    ax.set_title(f"Walk-forward: quarterly OOS net (fixed params)  ·  "
                 f"{int((q.net>0).sum())}/{len(q)} quarters green", fontweight="bold")
    fig.tight_layout()
    fig.savefig(WT / "docs" / "living" / "walkforward_20260725.png", facecolor="white")
    print("\nsaved docs/living/walkforward_20260725.png")


if __name__ == "__main__":
    main()
