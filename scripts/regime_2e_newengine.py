"""STRESS TEST #5 — full three-book REGIME-2E on the NEW (2nd-PC immediate-flip) engine
vs the OLD engine. Only the regime GATE changes (pt_old -> pt_new); entries, stops,
gap filter, retest, EOD all identical. NEW = verbatim lift (regime_engine_ab.pt_new).

Books: 2EL-long BULL (wide 0.30xADR), 2ES-short BEAR (wide), f2EL-fade-short BEAR (tight 4pt).
Reports per book + combined, OLD vs NEW: n, net, PF, train/test, per-year, realized+MC DD.

  python scripts/regime_2e_newengine.py [--limit N]
Output: data/regime/newengine_20260724.csv + tables + PNG.
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
from regime_second_entry_study import phase_transitions as pt_old, load_day  # noqa: E402
from regime_2e_causal_check import detect_entries_causal                     # noqa: E402
from regime_engine_ab import pt_new                                          # noqa: E402

OUT = WT / "data" / "regime" / "newengine_20260724.csv"
GOOD = {"09", "10", "11", "12", "13"}
FLOOR = 8 * TICK
TRAIN_END = "2023-12-31"
rng = np.random.default_rng(83)


def run_books(g, tP, tbar, adr, pt_fn):
    O, H, L, C = (g[c].values for c in ["Open", "High", "Low", "Close"])
    n = len(g)
    trans = pt_fn(H, L, n, tP, tbar)
    tr_ix = [t for (t, _) in trans]; tr_md = [m for (_, m) in trans]
    entries = detect_entries_causal(g, tP, tbar)
    g_dt = g["DateTime"].values
    wide = max(round(0.30 * adr / TICK) * TICK, FLOOR)
    out = []
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
            stop = lim + wide if short else lim - wide; seg = tP[jfl:]
            js = np.nonzero(seg >= stop)[0] if short else np.nonzero(seg <= stop)[0]
            ex = stop if len(js) else seg[-1]
            out.append(("WT-S" if short else "WT-L",
                        round(((lim - ex) if short else (ex - lim)) * PT - COMM - SLIP, 1)))
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
            fill = fail - TICK; stop = fill + 16 * TICK; seg = tP[jx:]
            js = np.nonzero(seg >= stop)[0]; ex = stop if len(js) else seg[-1]
            out.append(("FADE", round((fill - ex) * PT - COMM - SLIP, 1)))
    return out


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
    rows = []; t0 = time.time()
    for di, dstr in enumerate(days):
        if dstr not in gm.index:
            continue
        adr, gapv = gm.loc[dstr, "adr10"], gm.loc[dstr, "gap"]
        if not np.isfinite(adr) or gapv > 0.54:
            continue
        g, tP, tbar = load_day(b, dstr)
        if g is None:
            continue
        try:
            for (bk, net) in run_books(g, tP, tbar, adr, pt_old):
                rows.append((dstr, "OLD", bk, net))
            for (bk, net) in run_books(g, tP, tbar, adr, pt_new):
                rows.append((dstr, "NEW", bk, net))
        except Exception as e:
            print(dstr, "ERR", repr(e), flush=True)
        del tP, tbar; gc.collect()
        if (di + 1) % 150 == 0:
            print(f"[{di+1}/{len(days)}] rows={len(rows)} ({time.time()-t0:.0f}s)", flush=True)
    df = pd.DataFrame(rows, columns=["Date", "engine", "book", "net"]); df.to_csv(OUT, index=False)
    df["is_tr"] = df.Date <= TRAIN_END

    def pf(s):
        s = np.asarray(s); gp = s[s > 0].sum(); gl = -s[s < 0].sum()
        return round(gp / gl, 2) if gl > 0 else 0

    def mdd(x):
        e = x.sort_values("Date").net.cumsum(); return float((e - e.cummax()).min())

    print(f"\nDONE {time.time()-t0:.0f}s")
    # three-book system = WT-L + WT-S + FADE (all)
    for eng in ("OLD", "NEW"):
        print(f"\n===== {eng} engine =====")
        e = df[df.engine == eng]
        for bk in ("WT-L", "WT-S", "FADE"):
            x = e[e.book == bk]; trn, tst = x[x.is_tr], x[~x.is_tr]
            print(f"  {bk:6s} n={len(x):4d}  net {x.net.sum():+8,.0f}  $/tr {x.net.mean():+6.1f}  "
                  f"PF {pf(x.net):4.2f}  (tr {pf(trn.net)} te {pf(tst.net)})")
        trn, tst = e[e.is_tr], e[~e.is_tr]
        v = e.sort_values("Date").net.values
        dds = np.array([(lambda c: (c - np.maximum.accumulate(c)).min())(np.cumsum(rng.permutation(v))) for _ in range(3000)])
        print(f"  SYSTEM n={len(e):4d}  net {e.net.sum():+8,.0f}  PF {pf(e.net):4.2f}  "
              f"(tr {pf(trn.net)} te {pf(tst.net)})  maxDD {mdd(e):+,.0f}  MC-1% {np.percentile(dds,1):+,.0f}")
    print("\nPF by year (system):")
    py = df.pivot_table(index=df.Date.str[:4], columns="engine", values="net", aggfunc=pf)
    print(py.to_string())

    fig, ax = plt.subplots(figsize=(12, 6), dpi=115)
    for eng, c in (("OLD", "#8b8f96"), ("NEW", "#2a78d6")):
        x = df[df.engine == eng].sort_values("Date")
        ax.plot(range(len(x)), x.net.cumsum().values, lw=2, color=c,
                label=f"{eng} engine: {x.net.sum():+,.0f}$  PF {pf(x.net)}  n={len(x)}")
    ax.axhline(0, color="#c3c2b7", lw=1); ax.legend(frameon=False)
    ax.grid(axis="y", color="#eceeed", lw=0.7)
    for s_ in ("top", "right"): ax.spines[s_].set_visible(False)
    ax.set_title("STRESS TEST #5 — three-book REGIME-2E: OLD vs NEW (immediate-flip) engine",
                 fontweight="bold")
    fig.tight_layout()
    p = WT / "docs" / "living" / "newengine_20260724.png"
    fig.savefig(p, facecolor="white"); print("\nsaved", p)


if __name__ == "__main__":
    main()
