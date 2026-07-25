"""STRESS TEST #3 — pessimistic fills, three-book system.
Baseline vs: (a) retest must trade 3 ticks THROUGH (not 1); (b) randomly FAIL X% of
limit fills (queue-position model, X=10/25%); (c) both. Fade entry: require 2t through
its failure level. All else = committed config (gap<=0.54, 0.30 stop, EOD, $5RT+1t slip).

  python scripts/regime_2e_pessfills.py [--limit N]
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
GOOD = {"09", "10", "11", "12", "13"}
FLOOR = 8 * TICK
TRAIN_END = "2023-12-31"
rng = np.random.default_rng(83)


def main():
    limit = None
    if "--limit" in sys.argv:
        limit = int(sys.argv[sys.argv.index("--limit")+1])
    b = pd.read_parquet(DATA/"bars"/"_continuous.parquet"); b["Date"] = b["DateTime"].dt.date.astype(str)
    dly = b.groupby("Date").agg(dO=("Open","first"), dC=("Close","last"), dH=("High","max"), dL=("Low","min")).reset_index()
    dly["adr10"] = (dly.dH-dly.dL).rolling(10).mean().shift(1)
    dly["gap"] = ((dly.dO-dly.dC.shift(1))/dly.dC.shift(1)*100).abs()
    gm = dly.set_index("Date")[["adr10","gap"]]
    days = sorted(b["Date"].unique())
    if limit:
        days = days[:limit]
    # variants: (through_ticks, fail_frac)
    VAR = {"base(1t,0%)": (1, 0.0), "3t-through": (3, 0.0), "fail10%": (1, 0.10),
           "fail25%": (1, 0.25), "3t+fail25%": (3, 0.25)}
    rows = []; t0 = time.time()
    for di, dstr in enumerate(days):
        if dstr not in gm.index:
            continue
        adr, gapv = gm.loc[dstr,"adr10"], gm.loc[dstr,"gap"]
        if not np.isfinite(adr) or gapv > 0.54:
            continue
        g, tP, tbar = load_day(b, dstr)
        if g is None:
            continue
        O, H, L, C = (g[c].values for c in ["Open","High","Low","Close"])
        n = len(g)
        try:
            trans = phase_transitions(H, L, n, tP, tbar); entries = detect_entries_causal(g, tP, tbar)
        except Exception:
            continue
        tr_ix = [t for (t,_) in trans]; tr_md = [m for (_,m) in trans]
        g_dt = g["DateTime"].values; sd = max(round(0.30*adr/TICK)*TICK, FLOOR)
        for (fb, sb, dr, cnt, trig) in entries:
            if cnt != 2:
                continue
            short = dr == "S"
            a = np.searchsorted(tbar, fb, "left"); z = np.searchsorted(tbar, fb, "right")
            hit = np.nonzero(tP[a:z] <= trig)[0] if short else np.nonzero(tP[a:z] >= trig)[0]
            if not len(hit):
                continue
            jf = a+int(hit[0]); reg = tr_md[bisect_right(tr_ix, jf)-1]; want = "BEAR" if short else "BULL"
            is_wt = reg == want; is_fade = (not short) and reg == "BEAR"
            if not (is_wt or is_fade):
                continue
            for vn, (thru, failf) in VAR.items():
                if failf > 0 and rng.random() < failf:      # queue-position fill failure
                    continue
                if is_wt:
                    lim = trig + 6*TICK if short else trig - 6*TICK
                    # trade THROUGH by `thru` ticks: short fills when price rises to lim+(thru-1)t;
                    # long fills when price drops to lim-(thru-1)t (stricter as thru grows).
                    thr_px = lim + (thru-1)*TICK if short else lim - (thru-1)*TICK
                    s0 = tP[jf:]
                    jl = np.nonzero(s0 > thr_px)[0] if short else np.nonzero(s0 < thr_px)[0]
                    if not len(jl):
                        continue
                    jj = jf+int(jl[0]); fb2 = int(tbar[jj])
                    if fb2-fb > 6:
                        continue
                    fill = lim; sdist = sd
                else:
                    fail = L[sb]-TICK; thr_px = fail-(thru-1)*TICK
                    zl = np.searchsorted(tbar, fb+3, "left")
                    w = np.nonzero(tP[jf:zl] <= thr_px)[0]
                    if not len(w):
                        continue
                    jj = jf+int(w[0]); fb2 = int(tbar[jj])
                    if sb >= fb2:
                        continue
                    fill = fail-TICK; sdist = 16*TICK
                hh = pd.Timestamp(g_dt[min(fb2, n-1)]).strftime("%H")
                if hh not in GOOD:
                    continue
                stop = fill+sdist if short else fill-sdist; seg = tP[jj:]
                js = np.nonzero(seg >= stop)[0] if short else np.nonzero(seg <= stop)[0]
                ex = stop if len(js) else seg[-1]
                rows.append((dstr, vn, round(((fill-ex) if short else (ex-fill))*PT-COMM-SLIP, 1)))
        del tP, tbar; gc.collect()
        if (di+1) % 200 == 0:
            print(f"[{di+1}/{len(days)}] rows={len(rows)} ({time.time()-t0:.0f}s)", flush=True)
    df = pd.DataFrame(rows, columns=["Date","variant","net"]); df["is_tr"] = df.Date <= TRAIN_END
    df.to_csv(WT/"data"/"regime"/"pessfills_20260725.csv", index=False)

    def pf(s):
        s = np.asarray(s); gp = s[s>0].sum(); gl = -s[s<0].sum()
        return round(gp/gl, 2) if gl > 0 else 0
    print(f"\nDONE {time.time()-t0:.0f}s")
    print("variant        n     net       $/tr   PF    train|test")
    for vn in VAR:
        x = df[df.variant == vn]
        if not len(x):
            continue
        trn, tst = x[x.is_tr], x[~x.is_tr]
        print(f"{vn:14s} {len(x):4d}  {x.net.sum():+8,.0f}  {x.net.mean():+6.1f}  {pf(x.net):4.2f}  "
              f"{pf(trn.net)}|{pf(tst.net)}")


if __name__ == "__main__":
    main()
