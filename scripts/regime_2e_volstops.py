"""VOLATILITY-SCALED stop/target sweep — S83. Replaces the fixed 4pt stop.

On the audited winning execution (causal 2E, WT gate at trigger, retest 4t
THROUGH-fill, fills h09-13, EOD-flat baseline, $5 RT, 1 ES):

  stops   : {1.0, 1.5, 2.0, 3.0, 4.0} x ABR10   (avg 5m bar range, 10 bars, at signal)
            {0.10, 0.15, 0.20, 0.30} x ADR10    (prior 10-day avg daily range)
            fx4p (the incumbent) as reference
            all floored at 8 ticks
  targets : EOD hold  |  2x stop  |  3x stop    (first-hit, stop always active)

Output: data/regime/volstops_20260724.csv + train/test grid on stdout.
  python scripts/regime_2e_volstops.py [--limit N]
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

OUT = WT_ROOT / "data" / "regime" / "volstops_20260724.csv"
GOOD_HOURS = {"09", "10", "11", "12", "13"}
TRAIN_END = "2023-12-31"
STOPS = [("abr1.0", "abr", 1.0), ("abr1.5", "abr", 1.5), ("abr2.0", "abr", 2.0),
         ("abr3.0", "abr", 3.0), ("abr4.0", "abr", 4.0),
         ("adr.10", "adr", 0.10), ("adr.15", "adr", 0.15), ("adr.20", "adr", 0.20),
         ("adr.30", "adr", 0.30), ("fx4p", "fix", 16 * TICK)]
TARGETS = [("eod", None), ("t2x", 2.0), ("t3x", 3.0)]
FLOOR = 8 * TICK


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
        O, H, L, C = (g[c].values for c in ["Open", "High", "Low", "Close"])
        n = len(g)
        rng = np.maximum(H - L, 1e-9)
        abr10 = pd.Series(rng).rolling(10, min_periods=1).mean().values
        adr = adr_map.get(dstr, np.nan)
        try:
            transitions = phase_transitions(H, L, n, tP, tbar)
            entries = detect_entries_causal(g, tP, tbar)
        except Exception as e:
            print(dstr, "ERR", repr(e), flush=True)
            continue
        tr_ix = [t for (t, _) in transitions]; tr_md = [m for (_, m) in transitions]
        g_dt = g["DateTime"].values
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
            lim = trig + 4 * TICK if short else trig - 4 * TICK
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
            for (sid, kind, k) in STOPS:
                if kind == "abr":
                    dist = k * abr10[fb]
                elif kind == "adr":
                    if not np.isfinite(adr):
                        continue
                    dist = k * adr
                else:
                    dist = k
                dist = max(round(dist / TICK) * TICK, FLOOR)
                stop = fill + dist if short else fill - dist
                js_ = np.nonzero(seg >= stop)[0] if short else np.nonzero(seg <= stop)[0]
                js = js_[0] if len(js_) else np.inf
                for (tid, mult) in TARGETS:
                    if mult is None:
                        ex = stop if np.isfinite(js) else seg[-1]
                    else:
                        tgt = fill - mult * dist if short else fill + mult * dist
                        jt_ = np.nonzero(seg <= tgt)[0] if short else np.nonzero(seg >= tgt)[0]
                        jt = jt_[0] if len(jt_) else np.inf
                        ex = stop if js <= jt else (tgt if np.isfinite(jt) else seg[-1])
                    pnl = (fill - ex) if short else (ex - fill)
                    rows.append((dstr, dr, sid, tid, round(dist, 2),
                                 round(pnl * PT - COMM, 1)))
        del tP, tbar; gc.collect()
        if (di + 1) % 150 == 0:
            print(f"[{di+1}/{len(days)}] rows={len(rows)} ({time.time()-t0:.0f}s)", flush=True)

    df = pd.DataFrame(rows, columns=["Date", "dir", "stop", "target", "dist_pts", "net"])
    df.to_csv(OUT, index=False)
    df["is_tr"] = df.Date <= TRAIN_END

    def pf(s):
        gp = s[s > 0].sum(); gl = -s[s < 0].sum()
        return gp / gl if gl > 0 else float("inf")

    print(f"\nDONE {time.time()-t0:.0f}s rows={len(df)} -> {OUT}")
    out = []
    for (sid, _, _) in STOPS:
        for (tid, _) in TARGETS:
            x = df[(df["stop"] == sid) & (df.target == tid)]
            if not len(x):
                continue
            trn = x[x.is_tr]; tst = x[~x.is_tr]
            out.append((sid, tid, len(x), round(x.dist_pts.median(), 1),
                        round(trn.net.sum()), round(pf(trn.net), 2),
                        round(tst.net.sum()), round(pf(tst.net), 2)))
    res = pd.DataFrame(out, columns=["stop", "target", "n", "med_stop_pts",
                                     "net_tr", "PF_tr", "net_te", "PF_te"])
    print(res.to_string(index=False))
    g_ = res[(res.PF_tr > 1) & (res.PF_te > 1)].sort_values("net_te", ascending=False)
    print("\n== green in BOTH halves ==")
    print(g_.to_string(index=False) if len(g_) else "  NONE")


if __name__ == "__main__":
    main()
