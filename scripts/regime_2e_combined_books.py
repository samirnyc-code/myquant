"""Combined with-trend + fade books on the FINAL geometry — S83.

Final geometry everywhere: 0.30xADR10 stop (floor 8t), EOD exit, gap<=0.54 skip,
h09-13 fills, $5 RT + 1t exit slip.

Four books:
  WT-L  : 2EL with-trend long in BULL      (retest 6t through-fill)
  WT-S  : 2ES with-trend short in BEAR     (retest 6t through-fill)
  FADE-S: f2EL fade short in BEAR  (a 2EL triggers while BEAR then fails 1t through its
          signal-bar low within K=2 bars -> stop-entry short, 1t slip)
  FADE-L: f2ES fade long in BULL   (mirror) -- RE-TEST on final geometry (failed at 4pt)

Reports each book alone, each SIDE combined (WT+FADE), and the OVERLAP subset
(a WT and a FADE trade, same direction, filling within 3 bars same day = "BOTH").
Train<=2023 / test 2024+.

Output: data/regime/combined_books_20260724.csv + tables + PNG.
  python scripts/regime_2e_combined_books.py [--limit N]
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

OUT = WT / "data" / "regime" / "combined_books_20260724.csv"
GOOD = {"09", "10", "11", "12", "13"}
TRAIN_END = "2023-12-31"
FLOOR = 8 * TICK
KFADE = 2


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
        sdist = max(round(0.30 * adr / TICK) * TICK, FLOOR)

        def sim(jfl, fill, short):
            fb2 = int(tbar[min(jfl, len(tbar) - 1)])
            hh = pd.Timestamp(g_dt[min(fb2, n - 1)]).strftime("%H")
            if hh not in GOOD:
                return None, None
            stop = fill + sdist if short else fill - sdist
            seg = tP[jfl:]
            js = np.nonzero(seg >= stop)[0] if short else np.nonzero(seg <= stop)[0]
            ex = stop if len(js) else seg[-1]
            return round(((fill - ex) if short else (ex - fill)) * PT - COMM - SLIP, 1), fb2

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
                # WITH-TREND: retest 6t through-fill
                lim = trig + 6 * TICK if short else trig - 6 * TICK
                seg0 = tP[jf:]
                jl = np.nonzero(seg0 > lim)[0] if short else np.nonzero(seg0 < lim)[0]
                if len(jl):
                    jfl = jf + int(jl[0])
                    if int(tbar[jfl]) - fb <= 6:
                        net, fb2 = sim(jfl, lim, short)
                        if net is not None:
                            rows.append((dstr, "WT-S" if short else "WT-L", "S" if short else "L",
                                         fb2, net))
            else:
                # COUNTER-TREND 2E that may FAIL -> fade with the trend
                fade_short = not short          # 2EL in BEAR -> fade short; 2ES in BULL -> fade long
                sb_ext = L[sb] if fade_short else H[sb]
                fail_px = sb_ext - TICK if fade_short else sb_ext + TICK
                zlim = np.searchsorted(tbar, fb + KFADE + 1, "left")
                segf = tP[jf:zlim]
                w = np.nonzero(segf <= fail_px)[0] if fade_short else np.nonzero(segf >= fail_px)[0]
                if len(w):
                    jx = jf + int(w[0])
                    fill = fail_px - TICK if fade_short else fail_px + TICK
                    net, fb2 = sim(jx, fill, fade_short)
                    if net is not None:
                        rows.append((dstr, "FADE-S" if fade_short else "FADE-L",
                                     "S" if fade_short else "L", fb2, net))
        del tP, tbar; gc.collect()
        if (di + 1) % 150 == 0:
            print(f"[{di+1}/{len(days)}] rows={len(rows)} ({time.time()-t0:.0f}s)", flush=True)

    df = pd.DataFrame(rows, columns=["Date", "book", "dir", "fill_bar", "net"])
    df.to_csv(OUT, index=False)
    df["is_tr"] = df.Date <= TRAIN_END; df["yr"] = df.Date.str[:4]

    def pf(s):
        gp = s[s > 0].sum(); gl = -s[s < 0].sum()
        return round(gp / gl, 2) if gl > 0 else 0

    def line(name, x):
        if not len(x):
            return f"{name:26s}  (none)"
        trn, tst = x[x.is_tr], x[~x.is_tr]
        return (f"{name:26s} n={len(x):4d}  net {x.net.sum():+8,.0f}  $/tr {x.net.mean():+6.1f}  "
                f"PF {pf(x.net):4.2f}  train {pf(trn.net):4.2f} | test {pf(tst.net):4.2f}")

    print(f"\nDONE {time.time()-t0:.0f}s  rows={len(df)}")
    print("\n== individual books ==")
    for bk in ("WT-L", "WT-S", "FADE-S", "FADE-L"):
        print(line(bk, df[df.book == bk]))
    print("\n== SIDES combined ==")
    print(line("BEAR: WT-S + FADE-S", df[df.book.isin(["WT-S", "FADE-S"])]))
    print(line("BULL: WT-L + FADE-L", df[df.book.isin(["WT-L", "FADE-L"])]))
    print(line("FULL: all 4 books", df))

    # OVERLAP: WT and FADE same dir, same day, fills within 3 bars = "BOTH"
    print("\n== OVERLAP (a WT and a FADE trade agree: same dir, <=3 bars apart same day) ==")
    both = []
    for (dt, dr), gg in df.groupby(["Date", "dir"]):
        wt = gg[gg.book.str.startswith("WT")]; fd = gg[gg.book.str.startswith("FADE")]
        for _, wr in wt.iterrows():
            for _, fr in fd.iterrows():
                if abs(wr.fill_bar - fr.fill_bar) <= 3:
                    both.append((dt, dr, wr.fill_bar, fr.fill_bar, wr.net, fr.net))
    if both:
        ob = pd.DataFrame(both, columns=["Date", "dir", "wt_bar", "fd_bar", "wt_net", "fd_net"])
        ob["is_tr"] = ob.Date <= TRAIN_END
        # each overlap = one high-conviction signal; score with the WT leg (representative)
        print(f"overlap events: {len(ob)}  ({ob.dir.value_counts().to_dict()})")
        print(f"  WT-leg of overlaps:   net {ob.wt_net.sum():+,.0f}  PF {pf(ob.wt_net)}  "
              f"win {(ob.wt_net>0).mean()*100:.0f}%")
        print(f"  FADE-leg of overlaps: net {ob.fd_net.sum():+,.0f}  PF {pf(ob.fd_net)}  "
              f"win {(ob.fd_net>0).mean()*100:.0f}%")
        combo = pd.concat([ob.wt_net, ob.fd_net])
        print(f"  BOTH legs taken:      net {combo.sum():+,.0f}  PF {pf(combo)}  "
              f"train {pf(pd.concat([ob[ob.is_tr].wt_net, ob[ob.is_tr].fd_net]))} | "
              f"test {pf(pd.concat([ob[~ob.is_tr].wt_net, ob[~ob.is_tr].fd_net]))}")
        ob.to_csv(WT / "data" / "regime" / "combined_overlaps_20260724.csv", index=False)
    else:
        print("  no overlaps found")

    fig, ax = plt.subplots(figsize=(12, 6), dpi=115)
    for bk, c in (("BEAR WT-S+FADE-S", "#b23a2e"), ("BULL WT-L+FADE-L", "#1f7a3d"),
                  ("FULL 4-book", "#2a78d6")):
        if bk.startswith("BEAR"):
            x = df[df.book.isin(["WT-S", "FADE-S"])]
        elif bk.startswith("BULL"):
            x = df[df.book.isin(["WT-L", "FADE-L"])]
        else:
            x = df
        x = x.sort_values("Date")
        ax.plot(range(len(x)), x.net.cumsum().values, lw=2, color=c,
                label=f"{bk}: {x.net.sum():+,.0f}$ PF {pf(x.net)} n={len(x)}")
    ax.axhline(0, color="#c3c2b7", lw=1); ax.legend(frameon=False)
    ax.grid(axis="y", color="#eceeed", lw=0.7)
    for s_ in ("top", "right"): ax.spines[s_].set_visible(False)
    ax.set_title("Combined with-trend + fade books (final geometry)", fontweight="bold")
    fig.tight_layout()
    p = WT / "docs" / "living" / "combined_books_20260724.png"
    fig.savefig(p, facecolor="white"); print("\nsaved", p)


if __name__ == "__main__":
    main()
