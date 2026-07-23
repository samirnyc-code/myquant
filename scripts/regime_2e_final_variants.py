"""FINAL VARIANTS — the untested combinations, all on the WINNING execution.

Execution held fixed (the audited headline mechanics): S61 trigger -> retest limit
4t back, STRICT through-fill, fixed 4pt stop, fills only h09-13 machine-tz,
directional gate evaluated at the trigger touch. $5 RT, 1 ES.

Grid:
  entries : 2E (base) | 1E | 1E+2E
  gate    : WT-base   (mode == trade dir, base machine)
            WT-sticky (last non-NEUTRAL mode == trade dir — neutral inherits trend)
            WT-closec (close-through machine: transitions need a bar CLOSE beyond)
  exit    : EOD (base) | term (first flip AWAY from trade dir -> out at that tick)
            | oppo (exit only when the OPPOSITE trend starts; neutral doesn't kill)
            | t4p (1:1 target) | t8p (2:1 target)      [all still with the 4pt stop]
For the closec gate, term/oppo exits use the closec machine's own transitions.

Output: data/regime/final_variants_20260723.csv  (+ train/test grid on stdout)
  python scripts/regime_2e_final_variants.py [--limit N]
"""
import sys, gc, time
from pathlib import Path
from bisect import bisect_right
import numpy as np
import pandas as pd

TICK = 0.25; PT = 50.0; COMM = 5.0
WT_ROOT = Path(__file__).resolve().parent.parent
DATA = Path(r"C:/Users/Admin/myquant/data")
sys.path.insert(0, str(WT_ROOT / "scripts"))
from regime_second_entry_study import phase_transitions, load_day          # noqa: E402
from regime_2e_causal_check import detect_entries_causal                    # noqa: E402
from regime_2e_sweeps import phase_transitions_closec                       # noqa: E402

OUT = WT_ROOT / "data" / "regime" / "final_variants_20260723.csv"
GOOD_HOURS = {"09", "10", "11", "12", "13"}
TRAIN_END = "2023-12-31"


def main():
    limit = None
    if "--limit" in sys.argv:
        limit = int(sys.argv[sys.argv.index("--limit") + 1])
    b = pd.read_parquet(DATA / "bars" / "_continuous.parquet")
    b["Date"] = b["DateTime"].dt.date.astype(str)
    days = sorted(b["Date"].unique())
    if limit:
        days = days[:limit]

    rows = []; t0 = time.time()
    for di, dstr in enumerate(days):
        g, tP, tbar = load_day(b, dstr)
        if g is None:
            continue
        O, H, L, C = (g[c].values for c in ["Open", "High", "Low", "Close"])
        n = len(g)
        try:
            trans_b = phase_transitions(H, L, n, tP, tbar)
            trans_c = phase_transitions_closec(H, L, C, n, tP, tbar)
            entries = detect_entries_causal(g, tP, tbar)
        except Exception as e:
            print(dstr, "ERR", repr(e), flush=True)
            continue
        g_dt = g["DateTime"].values

        def mode_at(trans, j):
            ix = [t for (t, _) in trans]
            return trans[bisect_right(ix, j) - 1][1]

        def sticky_at(j):
            ix = [t for (t, _) in trans_b]
            k = bisect_right(ix, j) - 1
            for q in range(k, -1, -1):
                if trans_b[q][1] != "NEUTRAL":
                    return trans_b[q][1]
            return "NEUTRAL"

        def next_flip(trans, j, want, oppo_only):
            """First tick index > j where mode leaves `want` (term) or equals the
            opposite of want (oppo). Returns np.inf if none."""
            opp = "BEAR" if want == "BULL" else "BULL"
            for (tix, md) in trans:
                if tix <= j:
                    continue
                if oppo_only:
                    if md == opp:
                        return tix
                else:
                    if md != want:
                        return tix
            return np.inf

        for (fb, sb, dr, cnt, trig) in entries:
            if cnt > 2:
                continue
            short = dr == "S"
            a = np.searchsorted(tbar, fb, "left"); z = np.searchsorted(tbar, fb, "right")
            s = tP[a:z]
            hit = np.nonzero(s <= trig)[0] if short else np.nonzero(s >= trig)[0]
            if not len(hit):
                continue
            jf = a + int(hit[0])
            want = "BEAR" if short else "BULL"
            gates = dict(
                base=(mode_at(trans_b, jf) == want),
                sticky=(sticky_at(jf) == want),
                closec=(mode_at(trans_c, jf) == want))
            if not any(gates.values()):
                continue
            # retest through-fill
            lim = trig + 4 * TICK if short else trig - 4 * TICK
            seg0 = tP[jf:]
            jl_ = np.nonzero(seg0 > lim)[0] if short else np.nonzero(seg0 < lim)[0]
            if not len(jl_):
                continue
            jfl = jf + int(jl_[0])
            fill = lim; fill_bar = int(tbar[jfl])
            hh_ = pd.Timestamp(g_dt[min(fill_bar, n - 1)]).strftime("%H")
            if hh_ not in GOOD_HOURS:
                continue
            stop = fill + 16 * TICK if short else fill - 16 * TICK
            seg = tP[jfl:]
            js_ = np.nonzero(seg >= stop)[0] if short else np.nonzero(seg <= stop)[0]
            js = js_[0] if len(js_) else np.inf

            def book(exit_id, trans_for_flips):
                if exit_id in ("t4p", "t8p"):
                    dist = (16 if exit_id == "t4p" else 32) * TICK
                    tgt = fill - dist if short else fill + dist
                    jt_ = np.nonzero(seg <= tgt)[0] if short else np.nonzero(seg >= tgt)[0]
                    jt = jt_[0] if len(jt_) else np.inf
                    if js <= jt:
                        ex = stop
                    elif np.isfinite(jt):
                        ex = tgt
                    else:
                        ex = seg[-1]
                elif exit_id == "eod":
                    ex = stop if np.isfinite(js) else seg[-1]
                else:                        # term / oppo
                    jx = next_flip(trans_for_flips, jfl, want, exit_id == "oppo")
                    jrel = jx - jfl if np.isfinite(jx) else np.inf
                    if js <= jrel:
                        ex = stop
                    elif np.isfinite(jrel) and int(jrel) < len(seg):
                        ex = seg[int(jrel)]
                    else:
                        ex = seg[-1]
                pnl = (fill - ex) if short else (ex - fill)
                return pnl * PT - COMM

            for gname, ok in gates.items():
                if not ok:
                    continue
                tfl = trans_c if gname == "closec" else trans_b
                for exit_id in ("eod", "term", "oppo", "t4p", "t8p"):
                    rows.append((dstr, dr, cnt, gname, exit_id, book(exit_id, tfl)))
        del tP, tbar; gc.collect()
        if (di + 1) % 150 == 0:
            print(f"[{di+1}/{len(days)}] rows={len(rows)} ({time.time()-t0:.0f}s)", flush=True)

    df = pd.DataFrame(rows, columns=["Date", "dir", "count", "gate", "exit", "net"])
    df.to_csv(OUT, index=False)
    df["is_tr"] = df.Date <= TRAIN_END

    def pf(s):
        gp = s[s > 0].sum(); gl = -s[s < 0].sum()
        return gp / gl if gl > 0 else float("inf")

    print(f"\nDONE {time.time()-t0:.0f}s rows={len(df)} -> {OUT}")
    for ent_name, ent_mask in (("2E only", df["count"] == 2), ("1E only", df["count"] == 1),
                               ("1E+2E", pd.Series(True, df.index))):
        print("\n" + "=" * 96)
        print(f"ENTRIES: {ent_name}   (train | test)")
        print("=" * 96)
        out = []
        for gname in ("base", "sticky", "closec"):
            for exit_id in ("eod", "term", "oppo", "t4p", "t8p"):
                x = df[ent_mask & (df.gate == gname) & (df["exit"] == exit_id)]
                trn = x[x.is_tr]; tst = x[~x.is_tr]
                if len(trn) < 30 or len(tst) < 15:
                    continue
                out.append((gname, exit_id, len(trn), round(trn.net.sum()),
                            round(pf(trn.net), 2), len(tst), round(tst.net.sum()),
                            round(pf(tst.net), 2)))
        print(pd.DataFrame(out, columns=["gate", "exit", "n_tr", "net_tr", "PF_tr",
                                         "n_te", "net_te", "PF_te"]).to_string(index=False))


if __name__ == "__main__":
    main()
