"""FAILED SECOND ENTRY fade (f2E) — Samir's spec, S83.

In a BEAR trend, a counter-trend 2EL that TRIGGERS (1 tick above its signal bar)
and then FAILS (ticks 1 tick below that signal bar's low within K bars) traps the
longs -> SHORT at the failure tick. Mirror: f2ES in a BULL -> LONG. This is the
codex trap rule (#12/#45: "a triggered-then-failed L2 ... usually two legs").

Mechanics kept consistent with the audited stack: machine regime at the 2E
trigger tick must be OPPOSITE the 2E (that's what makes it counter-trend), the
failure entry is a stop-entry at SBlow-1t / SBhigh+1t (fill +1t slip — traps get
chased, so chase cost applies here by design; a retest variant is also booked),
fixed 4pt stop, exits EOD | term (regime leaves trade dir), fills h09-13, $5 RT.
K (bars allowed between trigger and failure) swept: 2 / 3 / 5.

Output: data/regime/failed2e_20260723.csv  (+ train/test grid)
  python scripts/regime_2e_failed2e.py [--limit N]
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
from regime_second_entry_study import phase_transitions, load_day   # noqa: E402
from regime_2e_causal_check import detect_entries_causal            # noqa: E402

OUT = WT_ROOT / "data" / "regime" / "failed2e_20260723.csv"
GOOD_HOURS = {"09", "10", "11", "12", "13"}
TRAIN_END = "2023-12-31"
KS = [2, 3, 5]


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
            transitions = phase_transitions(H, L, n, tP, tbar)
            entries = detect_entries_causal(g, tP, tbar)
        except Exception as e:
            print(dstr, "ERR", repr(e), flush=True)
            continue
        tr_ix = [t for (t, _) in transitions]; tr_md = [m for (_, m) in transitions]
        g_dt = g["DateTime"].values

        def mode_at(j):
            return tr_md[bisect_right(tr_ix, j) - 1]

        def next_flip_away(j, want):
            for (tix, md) in transitions:
                if tix > j and md != want:
                    return tix
            return np.inf

        for (fb, sb, dr, cnt, trig) in entries:
            if cnt != 2:
                continue
            ce_short = dr == "S"                       # the counter-trend 2E's own dir
            a = np.searchsorted(tbar, fb, "left"); z = np.searchsorted(tbar, fb, "right")
            s = tP[a:z]
            hit = np.nonzero(s <= trig)[0] if ce_short else np.nonzero(s >= trig)[0]
            if not len(hit):
                continue
            jf = a + int(hit[0])
            md = mode_at(jf)
            # counter-trend only: 2EL while BEAR -> f2EL short; 2ES while BULL -> f2ES long
            if ce_short and md != "BULL":
                continue
            if not ce_short and md != "BEAR":
                continue
            fade_short = not ce_short                  # we fade the failed 2E
            sb_hi = H[sb]; sb_lo = L[sb]
            fail_px = sb_lo - TICK if fade_short else sb_hi + TICK
            for K in KS:
                # failure must print within K bars after the trigger bar
                zlim = np.searchsorted(tbar, fb + K + 1, "left")
                segf = tP[jf:zlim]
                w = np.nonzero(segf <= fail_px)[0] if fade_short else np.nonzero(segf >= fail_px)[0]
                if not len(w):
                    continue
                jx = jf + int(w[0])
                fill = fail_px - TICK if fade_short else fail_px + TICK   # 1t slip chase
                fill_bar = int(tbar[jx])
                hh_ = pd.Timestamp(g_dt[min(fill_bar, n - 1)]).strftime("%H")
                if hh_ not in GOOD_HOURS:
                    continue
                stop = fill + 16 * TICK if fade_short else fill - 16 * TICK
                seg = tP[jx:]
                js_ = np.nonzero(seg >= stop)[0] if fade_short else np.nonzero(seg <= stop)[0]
                js = js_[0] if len(js_) else np.inf
                want = "BEAR" if fade_short else "BULL"
                for exit_id in ("eod", "term"):
                    if exit_id == "eod":
                        ex = stop if np.isfinite(js) else seg[-1]
                    else:
                        jfl2 = next_flip_away(jx, want)
                        jrel = jfl2 - jx if np.isfinite(jfl2) else np.inf
                        if js <= jrel:
                            ex = stop
                        elif np.isfinite(jrel) and int(jrel) < len(seg):
                            ex = seg[int(jrel)]
                        else:
                            ex = seg[-1]
                    pnl = (fill - ex) if fade_short else (ex - fill)
                    rows.append((dstr, "S" if fade_short else "L", K, exit_id,
                                 round(pnl * PT - COMM, 1)))
        del tP, tbar; gc.collect()
        if (di + 1) % 200 == 0:
            print(f"[{di+1}/{len(days)}] rows={len(rows)} ({time.time()-t0:.0f}s)", flush=True)

    df = pd.DataFrame(rows, columns=["Date", "dir", "K", "exit", "net"])
    df.to_csv(OUT, index=False)
    df["is_tr"] = df.Date <= TRAIN_END

    def pf(s):
        gp = s[s > 0].sum(); gl = -s[s < 0].sum()
        return gp / gl if gl > 0 else float("inf")

    print(f"\nDONE {time.time()-t0:.0f}s rows={len(df)} -> {OUT}")
    out = []
    for K in KS:
        for exit_id in ("eod", "term"):
            for dsel, dn in (("both", None), ("S", "S"), ("L", "L")):
                x = df[(df.K == K) & (df["exit"] == exit_id)]
                if dn:
                    x = x[x["dir"] == dn]
                trn = x[x.is_tr]; tst = x[~x.is_tr]
                if len(trn) < 25 or len(tst) < 12:
                    continue
                out.append((K, exit_id, dsel, len(trn), round(trn.net.sum()),
                            round(pf(trn.net), 2), len(tst), round(tst.net.sum()),
                            round(pf(tst.net), 2)))
    print(pd.DataFrame(out, columns=["K", "exit", "dir", "n_tr", "net_tr", "PF_tr",
                                     "n_te", "net_te", "PF_te"]).to_string(index=False))


if __name__ == "__main__":
    main()
