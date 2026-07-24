"""MANAGEMENT SWEEP on the adr.30 book — S83 '+10%' program, lever 1.

Base: causal 2E, WT gate at trigger, retest 4t THROUGH-fill, stop 0.30xADR10
(nearest-tick, floor 8t), EOD hold, fills h09-13, $5 RT + 1t exit slip, 1 ES.

Variants (all keep the initial stop until modified):
  base      : hold to EOD (reference)
  be1.0     : stop -> entry after +1.0x stop-distance trades
  be0.5     : stop -> entry after +0.5x stop-distance trades
  tight6    : after 6 bars (30m), stop tightens to 1.0xABR10 behind extreme-so-far
  scale2x   : exit HALF at +2x stop-distance, rest to EOD (halved contract = /2 PnL,
              full commission per unit modeled: 2 units of 0.5 each, $5 RT total)
  retest2/6 : base management, retest depth 2t / 6t instead of 4t

Output: data/regime/mgmt_sweep_20260724.csv + tables + PNG (equity per variant).
  python scripts/regime_2e_mgmt_sweep.py [--limit N]
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

OUT = WT_ROOT / "data" / "regime" / "mgmt_sweep_20260724.csv"
GOOD_HOURS = {"09", "10", "11", "12", "13"}
TRAIN_END = "2023-12-31"
FLOOR = 8 * TICK


def first_hit(seg, px, short, adverse):
    if short:
        w = np.nonzero(seg >= px)[0] if adverse else np.nonzero(seg <= px)[0]
    else:
        w = np.nonzero(seg <= px)[0] if adverse else np.nonzero(seg >= px)[0]
    return int(w[0]) if len(w) else -1


def main():
    limit = None
    if "--limit" in sys.argv:
        limit = int(sys.argv[sys.argv.index("--limit") + 1])
    b = pd.read_parquet(DATA / "bars" / "_continuous.parquet")
    b["Date"] = b["DateTime"].dt.date.astype(str)
    dly = b.groupby("Date").agg(dH=("High", "max"), dL=("Low", "min")).reset_index()
    dly["adr10"] = (dly.dH - dly.dL).rolling(10).mean().shift(1)
    adr_map = dly.set_index("Date")["adr10"].to_dict()
    days = sorted(b["Date"].unique())
    if limit:
        days = days[:limit]

    rows = []; t0 = time.time()
    for di, dstr in enumerate(days):
        g, tP, tbar = load_day(b, dstr)
        if g is None:
            continue
        adr = adr_map.get(dstr, np.nan)
        if not np.isfinite(adr):
            continue
        O, H, L, C = (g[c].values for c in ["Open", "High", "Low", "Close"])
        n = len(g)
        rng_ = np.maximum(H - L, 1e-9)
        abr10 = pd.Series(rng_).rolling(10, min_periods=1).mean().values
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
            for rt_id, rt in (("base", 4), ("retest2", 2), ("retest6", 6)):
                lim = trig + rt * TICK if short else trig - rt * TICK
                seg0 = tP[jf:]
                jl_ = np.nonzero(seg0 > lim)[0] if short else np.nonzero(seg0 < lim)[0]
                if not len(jl_):
                    continue
                jfl = jf + int(jl_[0])
                fb2 = int(tbar[jfl])
                hh_ = pd.Timestamp(g_dt[min(fb2, n - 1)]).strftime("%H")
                if hh_ not in GOOD_HOURS:
                    continue
                fill = lim
                seg = tP[jfl:]
                segbars = tbar[jfl:]
                stop0 = fill + sdist if short else fill - sdist
                js = first_hit(seg, stop0, short, True)
                jsv = js if js >= 0 else len(seg)
                eod_px = seg[-1]

                def base_pnl():
                    ex = stop0 if js >= 0 else eod_px
                    return ((fill - ex) if short else (ex - fill)) * PT - COMM - SLIP

                if rt_id != "base":
                    rows.append((dstr, dr, rt_id, round(base_pnl(), 1)))
                    continue
                rows.append((dstr, dr, "base", round(base_pnl(), 1)))
                # BE moves
                for beid, k in (("be1.0", 1.0), ("be0.5", 0.5)):
                    bpx = fill - k * sdist if short else fill + k * sdist
                    jb = first_hit(seg, bpx, short, False)
                    if jb >= 0 and jb < jsv:
                        seg2 = seg[jb:]
                        js2 = first_hit(seg2, fill, short, True)
                        ex = fill if js2 >= 0 else eod_px
                    else:
                        ex = stop0 if js >= 0 else eod_px
                    pnl = ((fill - ex) if short else (ex - fill)) * PT - COMM - SLIP
                    rows.append((dstr, dr, beid, round(pnl, 1)))
                # tighten after 6 bars: stop -> extreme-so-far -/+ 1xABR10(fb)
                cut = np.searchsorted(segbars, fb2 + 6, "left")
                if jsv <= cut:
                    ex = stop0
                else:
                    ext = seg[:cut].min() if short else seg[:cut].max()
                    tst = ext + abr10[fb2] if short else ext - abr10[fb2]
                    # tightened stop only if tighter than original
                    tst = min(tst, stop0) if short else max(tst, stop0)
                    seg2 = seg[cut:]
                    js2 = first_hit(seg2, tst, short, True)
                    ex = tst if js2 >= 0 else eod_px
                pnl = ((fill - ex) if short else (ex - fill)) * PT - COMM - SLIP
                rows.append((dstr, dr, "tight6", round(pnl, 1)))
                # scale-out half at 2x stop distance
                tpx = fill - 2 * sdist if short else fill + 2 * sdist
                jt = first_hit(seg, tpx, short, False)
                if jt >= 0 and jt < jsv:
                    p1 = 2 * sdist * PT * 0.5
                    ex2 = stop0 if js >= 0 else eod_px
                    p2 = ((fill - ex2) if short else (ex2 - fill)) * PT * 0.5
                else:
                    ex = stop0 if js >= 0 else eod_px
                    p1 = ((fill - ex) if short else (ex - fill)) * PT * 0.5
                    p2 = p1
                rows.append((dstr, dr, "scale2x", round(p1 + p2 - COMM - SLIP, 1)))
        del tP, tbar; gc.collect()
        if (di + 1) % 150 == 0:
            print(f"[{di+1}/{len(days)}] rows={len(rows)} ({time.time()-t0:.0f}s)", flush=True)

    df = pd.DataFrame(rows, columns=["Date", "dir", "variant", "net"])
    df.to_csv(OUT, index=False)
    df["is_tr"] = df.Date <= TRAIN_END

    def pf(s):
        gp = s[s > 0].sum(); gl = -s[s < 0].sum()
        return round(gp / gl, 2) if gl > 0 else float("inf")

    print(f"\nDONE {time.time()-t0:.0f}s rows={len(df)} -> {OUT}")
    print("\nvariant   n    $/tr   PF   win%  maxDD    net_tr/PF | net_te/PF")
    order = ["base", "be0.5", "be1.0", "tight6", "scale2x", "retest2", "retest6"]
    for v in order:
        x = df[df.variant == v].sort_values("Date")
        if not len(x):
            continue
        eq = x.net.cumsum(); dd = (eq - eq.cummax()).min()
        trn, tst = x[x.is_tr], x[~x.is_tr]
        print(f"{v:8s} {len(x):4d} {x.net.mean():+7.1f} {pf(x.net):5.2f} "
              f"{(x.net>0).mean()*100:5.1f} {dd:+9.0f}  {trn.net.sum():+8.0f}/{pf(trn.net):4.2f} | "
              f"{tst.net.sum():+8.0f}/{pf(tst.net):4.2f}")

    fig, ax = plt.subplots(figsize=(13, 6), dpi=115)
    for v in order:
        x = df[df.variant == v].sort_values("Date")
        if len(x):
            ax.plot(range(len(x)), x.net.cumsum().values, lw=1.8,
                    label=f"{v} ({x.net.sum():+,.0f}$)")
    ax.axhline(0, color="#c3c2b7", lw=1); ax.legend(frameon=False, fontsize=9)
    ax.grid(axis="y", color="#eceeed", lw=0.7)
    for s_ in ("top", "right"): ax.spines[s_].set_visible(False)
    ax.set_title("Management sweep on the adr.30 book — net of all costs (1 ES)",
                 fontweight="bold")
    fig.tight_layout()
    p1 = WT_ROOT / "docs" / "living" / "mgmt_sweep_20260724.png"
    fig.savefig(p1, facecolor="white"); plt.close(fig)
    print("saved", p1)


if __name__ == "__main__":
    main()
