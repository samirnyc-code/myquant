"""Validation demand #5 (tick pass): apply the stage-3/4 filters to the STAGE-0
config (4pt stop, retest 4t) — independent evidence test. Plus retest-8t point
under the adr.30 stop (does the 6t optimum sit on a plateau?).

Variants (all: WT gate, h09-13 fills, EOD, $5 RT + 1t exit slip):
  s0            : 4pt stop, retest4, no lifetime, all days
  s0+gap        : + skip |gap|>0.54
  s0+cxl6       : + limit dies 6 bars after trigger
  s0+both       : both filters
  adr30_rt8     : adr.30 stop, retest 8t, cxl6, gap-filtered (plateau check)

Output: data/regime/validation_tick_20260724.csv + table.
  python scripts/regime_2e_validation_tick.py [--limit N]
"""
import sys, gc, time
from pathlib import Path
from bisect import bisect_right
import numpy as np
import pandas as pd

TICK = 0.25; PT = 50.0; COMM = 5.0; SLIP = 12.5
WT_ROOT = Path(__file__).resolve().parent.parent
DATA = Path(r"C:/Users/Admin/myquant/data")
sys.path.insert(0, str(WT_ROOT / "scripts"))
from regime_second_entry_study import phase_transitions, load_day   # noqa: E402
from regime_2e_causal_check import detect_entries_causal            # noqa: E402

OUT = WT_ROOT / "data" / "regime" / "validation_tick_20260724.csv"
GOOD_HOURS = {"09", "10", "11", "12", "13"}
TRAIN_END = "2023-12-31"
GAP_THR = 0.54
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
    dly["gap_abs"] = ((dly.dO - dly.dC.shift(1)) / dly.dC.shift(1) * 100).abs()
    gmap = dly.set_index("Date")[["gap_abs", "adr10"]]
    days = sorted(b["Date"].unique())
    if limit:
        days = days[:limit]

    rows = []; t0 = time.time()
    for di, dstr in enumerate(days):
        g, tP, tbar = load_day(b, dstr)
        if g is None or dstr not in gmap.index:
            continue
        gapv, adr = gmap.loc[dstr, "gap_abs"], gmap.loc[dstr, "adr10"]
        if not np.isfinite(adr):
            continue
        is_gap = gapv > GAP_THR
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
        sdistA = max(round(0.30 * adr / TICK) * TICK, FLOOR)
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

            def run(rt, sdist, need_cxl, variants):
                lim = trig + rt * TICK if short else trig - rt * TICK
                seg0 = tP[jf:]
                jl_ = np.nonzero(seg0 > lim)[0] if short else np.nonzero(seg0 < lim)[0]
                if not len(jl_):
                    return
                jfl = jf + int(jl_[0])
                fill_bar = int(tbar[jfl])
                hh_ = pd.Timestamp(g_dt[min(fill_bar, n - 1)]).strftime("%H")
                if hh_ not in GOOD_HOURS:
                    return
                late = fill_bar - fb > 6
                stop = lim + sdist if short else lim - sdist
                seg = tP[jfl:]
                js_ = np.nonzero(seg >= stop)[0] if short else np.nonzero(seg <= stop)[0]
                ex = stop if len(js_) else seg[-1]
                pnl = ((lim - ex) if short else (ex - lim)) * PT - COMM - SLIP
                for v, gate_gap, gate_cxl in variants:
                    if gate_gap and is_gap:
                        continue
                    if gate_cxl and late:
                        continue
                    rows.append((dstr, dr, v, round(pnl, 1)))

            run(4, 16 * TICK, True, [("s0", False, False), ("s0+gap", True, False),
                                     ("s0+cxl6", False, True), ("s0+both", True, True)])
            run(8, sdistA, True, [("adr30_rt8", True, True)])
        del tP, tbar; gc.collect()
        if (di + 1) % 200 == 0:
            print(f"[{di+1}/{len(days)}] rows={len(rows)} ({time.time()-t0:.0f}s)", flush=True)

    df = pd.DataFrame(rows, columns=["Date", "dir", "variant", "net"])
    df.to_csv(OUT, index=False)
    df["is_tr"] = df.Date <= TRAIN_END

    def pf(s):
        gp = s[s > 0].sum(); gl = -s[s < 0].sum()
        return round(gp / gl, 2) if gl > 0 else float("inf")

    print(f"\nDONE {time.time()-t0:.0f}s rows={len(df)} -> {OUT}")
    print("variant     n    $/tr   PF    train        | test")
    for v in ["s0", "s0+gap", "s0+cxl6", "s0+both", "adr30_rt8"]:
        x = df[df.variant == v]
        trn, tst = x[x.is_tr], x[~x.is_tr]
        print(f"{v:10s} {len(x):4d} {x.net.mean():+7.1f} {pf(x.net):5.2f} "
              f"{trn.net.sum():+8.0f}/{pf(trn.net):4.2f} | {tst.net.sum():+8.0f}/{pf(tst.net):4.2f}")


if __name__ == "__main__":
    main()
