"""TWO-SLEEVE architecture — S83. With-trend (wide vol stop) + Fade (tight stop),
each on ITS OWN geometry, run as parallel books and combined into one equity path.

Sleeve A (WITH-TREND): 2EL long BULL + 2ES short BEAR. Retest 6t through-fill,
  stop 0.30xADR10 (floor 8t), EOD. [the committed book]
Sleeve B (FADE): f2EL fade short BEAR + f2ES fade long BULL. Failed counter-trend 2E
  (fails 1t through signal-bar extreme within K=2 bars) -> stop-entry +1t slip,
  stop = FADESTOP_TICKS fixed (default 16t = 4pt, the fade's own best), EOD.
All: gap<=0.54 skip, h09-13, $5 RT + 1t exit slip. Train<=2023 / test 2024+.

Full breakdown: per-book, per-sleeve, combined; per-year PF; L/S split; expectancy;
maxDD (closed) per sleeve and combined; Monte-Carlo DD (combined); correlation of
sleeve daily PnL. + equity/underwater PNG.

  python scripts/regime_2e_two_sleeves.py [--limit N] [--fadestop 16]
Output: data/regime/two_sleeves_20260724.csv + tables + PNG.
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

OUT = WT / "data" / "regime" / "two_sleeves_20260724.csv"
GOOD = {"09", "10", "11", "12", "13"}
TRAIN_END = "2023-12-31"
FLOOR = 8 * TICK
KFADE = 2
rng = np.random.default_rng(83)


def main():
    limit = None
    fadestop = 16
    if "--limit" in sys.argv:
        limit = int(sys.argv[sys.argv.index("--limit") + 1])
    if "--fadestop" in sys.argv:
        fadestop = int(sys.argv[sys.argv.index("--fadestop") + 1])
    b = pd.read_parquet(DATA / "bars" / "_continuous.parquet")
    b["Date"] = b["DateTime"].dt.date.astype(str)
    dly = b.groupby("Date").agg(dO=("Open", "first"), dC=("Close", "last"),
                                dH=("High", "max"), dL=("Low", "min")).reset_index()
    dly["adr10"] = (dly.dH - dly.dL).rolling(10).mean().shift(1)
    dly["gap"] = ((dly.dO - dly.dC.shift(1)) / dly.dC.shift(1) * 100).abs()
    gmap = dly.set_index("Date")[["adr10", "gap"]]
    days = sorted(b["Date"].unique())
    if limit:
        days = days[:limit]

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
        tight = fadestop * TICK

        def sim(jfl, fill, short, sdist):
            fb2 = int(tbar[min(jfl, len(tbar) - 1)])
            hh = pd.Timestamp(g_dt[min(fb2, n - 1)]).strftime("%H")
            if hh not in GOOD:
                return None
            stop = fill + sdist if short else fill - sdist
            seg = tP[jfl:]
            js = np.nonzero(seg >= stop)[0] if short else np.nonzero(seg <= stop)[0]
            ex = stop if len(js) else seg[-1]
            return round(((fill - ex) if short else (ex - fill)) * PT - COMM - SLIP, 1)

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
                        net = sim(jfl, lim, short, wide)
                        if net is not None:
                            rows.append((dstr, "WT", "S" if short else "L", net))
            else:
                fade_short = not short
                sb_ext = L[sb] if fade_short else H[sb]
                fail_px = sb_ext - TICK if fade_short else sb_ext + TICK
                zlim = np.searchsorted(tbar, fb + KFADE + 1, "left")
                segf = tP[jf:zlim]
                w = np.nonzero(segf <= fail_px)[0] if fade_short else np.nonzero(segf >= fail_px)[0]
                if len(w):
                    jx = jf + int(w[0])
                    fill = fail_px - TICK if fade_short else fail_px + TICK
                    net = sim(jx, fill, fade_short, tight)
                    if net is not None:
                        rows.append((dstr, "FADE", "S" if fade_short else "L", net))
        del tP, tbar; gc.collect()
        if (di + 1) % 200 == 0:
            print(f"[{di+1}/{len(days)}] rows={len(rows)} ({time.time()-t0:.0f}s)", flush=True)

    df = pd.DataFrame(rows, columns=["Date", "sleeve", "dir", "net"])
    df.to_csv(OUT, index=False)
    df["is_tr"] = df.Date <= TRAIN_END; df["yr"] = df.Date.str[:4]

    def pf(s):
        gp = s[s > 0].sum(); gl = -s[s < 0].sum()
        return round(gp / gl, 2) if gl > 0 else 0

    def maxdd(x):
        e = x.sort_values("Date").net.cumsum(); return float((e - e.cummax()).min())

    def block(name, x):
        if not len(x):
            print(f"{name:30s} (none)"); return
        trn, tst = x[x.is_tr], x[~x.is_tr]
        w = x[x.net > 0]; l = x[x.net <= 0]
        print(f"{name:30s} n={len(x):4d}  net {x.net.sum():+8,.0f}  $/tr {x.net.mean():+6.1f}  "
              f"PF {pf(x.net):4.2f}  win {(x.net>0).mean()*100:4.1f}%  "
              f"avgW {w.net.mean():+6.0f} avgL {l.net.mean():+6.0f}  maxDD {maxdd(x):+8,.0f}  "
              f"tr {pf(trn.net):4.2f}|te {pf(tst.net):4.2f}")

    print(f"\nDONE {time.time()-t0:.0f}s  fadestop={fadestop}t  rows={len(df)}")
    print("\n=== PER BOOK ===")
    for (sl, dr, nm) in [("WT", "L", "WT-L  2EL long bull"), ("WT", "S", "WT-S  2ES short bear"),
                         ("FADE", "S", "FADE-S f2EL fade short"), ("FADE", "L", "FADE-L f2ES fade long")]:
        block(nm, df[(df.sleeve == sl) & (df.dir == dr)])
    print("\n=== PER SLEEVE ===")
    block("SLEEVE A  with-trend (wide)", df[df.sleeve == "WT"])
    block("SLEEVE B  fade (tight)", df[df.sleeve == "FADE"])
    print("\n=== COMBINED (both sleeves, one book) ===")
    block("COMBINED", df)

    print("\n=== PF BY YEAR ===")
    py = df.pivot_table(index="yr", columns="sleeve", values="net", aggfunc=pf)
    py["COMBINED"] = df.groupby("yr").net.apply(pf)
    ny = df.pivot_table(index="yr", columns="sleeve", values="net", aggfunc="size")
    print(pd.concat([py, ny.add_suffix("_n")], axis=1).to_string())

    # sleeve daily-PnL correlation
    daily = df.pivot_table(index="Date", columns="sleeve", values="net", aggfunc="sum").fillna(0)
    corr = daily["WT"].corr(daily["FADE"]) if "FADE" in daily and "WT" in daily else float("nan")
    print(f"\nsleeve daily-PnL correlation (WT vs FADE): {corr:+.3f}")

    # Monte-Carlo DD on combined
    vals = df.sort_values("Date").net.values
    dds = np.empty(4000)
    for i in range(4000):
        e = np.cumsum(rng.permutation(vals)); dds[i] = (e - np.maximum.accumulate(e)).min()
    q = np.percentile(dds, [50, 25, 5, 1])
    print(f"combined maxDD: realized {maxdd(df):+,.0f}  | MC median {q[0]:,.0f} "
          f"worst-5% {q[2]:,.0f} worst-1% {q[3]:,.0f}")
    print(f"combined: {len(df)} trades, {len(df)/5.06:.0f}/yr, "
          f"net/yr {df.net.sum()/5.06:+,.0f}, exp {df.net.mean():+.0f}$/tr")

    # chart: sleeve equities + combined + underwater
    fig, (a1, a2) = plt.subplots(2, 1, figsize=(13, 8), dpi=115, sharex=True,
                                 gridspec_kw=dict(height_ratios=[2.3, 1], hspace=0.1))
    for sl, c in (("WT", "#2a78d6"), ("FADE", "#eb6834")):
        x = df[df.sleeve == sl].sort_values("Date")
        a1.plot(x.Date.values, x.net.cumsum().values, lw=1.7, color=c,
                label=f"Sleeve {'A WT(wide)' if sl=='WT' else 'B FADE(tight)'}: "
                      f"{x.net.sum():+,.0f}$ PF {pf(x.net)}")
    xc = df.sort_values("Date")
    ec = xc.net.cumsum()
    a1.plot(xc.Date.values, ec.values, lw=2.4, color="#111",
            label=f"COMBINED: {df.net.sum():+,.0f}$ PF {pf(df.net)}")
    a2.fill_between(xc.Date.values, (ec - ec.cummax()).values, 0, color="#b23a2e", alpha=0.3)
    for ax in (a1, a2):
        ax.grid(axis="y", color="#eceeed", lw=0.7)
        for s_ in ("top", "right"): ax.spines[s_].set_visible(False)
        ax.set_xticks(ax.get_xticks()[::max(1, len(ax.get_xticks())//8)])
    a1.axhline(0, color="#c3c2b7", lw=1); a1.legend(frameon=False)
    a1.set_ylabel("cumulative $"); a2.set_ylabel("underwater $")
    a1.set_title(f"Two-sleeve: with-trend (wide) + fade (tight {fadestop}t) — final geometry",
                 fontweight="bold")
    for lab in a2.get_xticklabels():
        lab.set_rotation(30); lab.set_ha("right"); lab.set_fontsize(8)
    a1.set_xticklabels([])
    fig.tight_layout()
    p = WT / "docs" / "living" / "two_sleeves_20260724.png"
    fig.savefig(p, facecolor="white"); print("saved", p)


if __name__ == "__main__":
    main()
