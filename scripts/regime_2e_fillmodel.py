"""FILL-MODEL spread on the COMMITTED SPEC — touch vs strict trade-through.

Same book (adr.30 x retest6 x gap-filter x EOD x h09-13, $5 RT + 1t exit slip):
  strict : a tick BEYOND the limit required (the spec's assumption)
  touch  : a tick AT the limit fills (optimistic bound)
The spread measures how much edge lives in the last tick of entry precision.

Output: data/regime/fillmodel_20260724.csv + table + PNG.
  python scripts/regime_2e_fillmodel.py [--limit N]
"""
import sys, gc, time
from pathlib import Path
from bisect import bisect_right
import numpy as np
import pandas as pd
import matplotlib; matplotlib.use("Agg")
import matplotlib.pyplot as plt

TICK = 0.25; PT = 50.0; COMM = 5.0; SLIP = 12.5
WT_ROOT = Path(__file__).resolve().parent.parent
DATA = Path(r"C:/Users/Admin/myquant/data")
sys.path.insert(0, str(WT_ROOT / "scripts"))
from regime_second_entry_study import phase_transitions, load_day   # noqa: E402
from regime_2e_causal_check import detect_entries_causal            # noqa: E402

OUT = WT_ROOT / "data" / "regime" / "fillmodel_20260724.csv"
GOOD_HOURS = {"09", "10", "11", "12", "13"}
TRAIN_END = "2023-12-31"
FLOOR = 8 * TICK


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
    gmap = dly.set_index("Date")[["gap", "adr10"]]
    days = sorted(b["Date"].unique())
    if limit:
        days = days[:limit]

    rows = []; t0 = time.time()
    for di, dstr in enumerate(days):
        if dstr not in gmap.index:
            continue
        gapv, adr = gmap.loc[dstr, "gap"], gmap.loc[dstr, "adr10"]
        if not np.isfinite(adr) or gapv > 0.54:
            continue
        g, tP, tbar = load_day(b, dstr)
        if g is None:
            continue
        O, H, L, C = (g[c].values for c in ["Open", "High", "Low", "Close"])
        n = len(g)
        try:
            transitions = phase_transitions(H, L, n, tP, tbar)
            entries = detect_entries_causal(g, tP, tbar)
        except Exception as e:
            print(dstr, "ERR", repr(e), flush=True)
            continue
        tr_ix = [t for (t, _) in transitions]; tr_md = [m for (_, m) in transitions]
        g_dt = g["DateTime"].values
        sdist = max(round(0.30 * adr / TICK) * TICK, FLOOR)
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
            want = "BEAR" if short else "BULL"
            if tr_md[bisect_right(tr_ix, jf) - 1] != want:
                continue
            lim = trig + 6 * TICK if short else trig - 6 * TICK
            seg0 = tP[jf:]
            for model, w in (("strict", np.nonzero(seg0 > lim)[0] if short else np.nonzero(seg0 < lim)[0]),
                             ("touch", np.nonzero(seg0 >= lim)[0] if short else np.nonzero(seg0 <= lim)[0])):
                if not len(w):
                    continue
                jfl = jf + int(w[0])
                fb2 = int(tbar[jfl])
                hh_ = pd.Timestamp(g_dt[min(fb2, n - 1)]).strftime("%H")
                if hh_ not in GOOD_HOURS:
                    continue
                stop = lim + sdist if short else lim - sdist
                seg = tP[jfl:]
                js_ = np.nonzero(seg >= stop)[0] if short else np.nonzero(seg <= stop)[0]
                ex = stop if len(js_) else seg[-1]
                pnl = ((lim - ex) if short else (ex - lim)) * PT - COMM - SLIP
                rows.append((dstr, dr, model, round(pnl, 1)))
        del tP, tbar; gc.collect()
        if (di + 1) % 200 == 0:
            print(f"[{di+1}/{len(days)}] rows={len(rows)} ({time.time()-t0:.0f}s)", flush=True)

    df = pd.DataFrame(rows, columns=["Date", "dir", "model", "net"])
    df.to_csv(OUT, index=False)
    df["is_tr"] = df.Date <= TRAIN_END

    def pf(s):
        gp = s[s > 0].sum(); gl = -s[s < 0].sum()
        return round(gp / gl, 2) if gl > 0 else float("inf")

    print(f"\nDONE {time.time()-t0:.0f}s -> {OUT}")
    for m in ("strict", "touch"):
        x = df[df.model == m]
        trn, tst = x[x.is_tr], x[~x.is_tr]
        print(f"{m:6s}: n={len(x):4d}  net {x.net.sum():+9,.0f}  $/tr {x.net.mean():+7.1f}  "
              f"PF {pf(x.net)}  train {pf(trn.net)} | test {pf(tst.net)}")
    st = df[df.model == "strict"]; to = df[df.model == "touch"]
    extra = len(to) - len(st)
    print(f"touch-only trades: {extra}  |  net spread: {to.net.sum()-st.net.sum():+,.0f} "
          f"({(to.net.sum()/st.net.sum()-1)*100:+.0f}%)")

    fig, ax = plt.subplots(figsize=(12, 5.5), dpi=115)
    for m, c in (("strict", "#2a78d6"), ("touch", "#eb6834")):
        x = df[df.model == m].sort_values("Date")
        ax.plot(range(len(x)), x.net.cumsum().values, lw=2, color=c,
                label=f"{m}: n={len(x)}  {x.net.sum():+,.0f}$  PF {pf(x.net)}")
    ax.axhline(0, color="#c3c2b7", lw=1); ax.legend(frameon=False)
    ax.grid(axis="y", color="#eceeed", lw=0.7)
    for s_ in ("top", "right"): ax.spines[s_].set_visible(False)
    ax.set_title("Fill-model spread on the committed spec — strict trade-through vs touch",
                 fontweight="bold")
    fig.tight_layout()
    p = WT_ROOT / "docs" / "living" / "fillmodel_20260724.png"
    fig.savefig(p, facecolor="white")
    print("saved", p)


if __name__ == "__main__":
    main()
