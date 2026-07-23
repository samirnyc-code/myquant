"""ETH regime x 2E study — S83-ETH stage 2. The winning stack on the FULL 24h session.

Session = 17:00 -> 16:00 next day (machine-tz), keyed to its RTH date. The phase
machine and S61 engine run session-scoped (open NEUTRAL at 17:00). Execution is
the audited RTH winner: causal 2E, WT gate at trigger, retest 4t THROUGH-fill,
fixed 4pt stop, flat at session end (16:00), $5 RT, 1 ES.

Slices (fill machine-hour): full session | 17-20 | 20-00 | 00-04 | 04-0830 |
0830-1400 (the RTH morning window analogue) | 1400-16. Train <=2023 / test 2024+.
Also books the f2EL fade (K=2) on the 24h machine.

Output: data/regime_eth/eth_2e_trades_20260724.csv  (+ grids on stdout)
  python scripts/eth_regime_2e_study.py [--limit N]
"""
import sys, gc, time
from pathlib import Path
from bisect import bisect_right
import numpy as np
import pandas as pd

TICK = 0.25; PT = 50.0; COMM = 5.0
WT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(WT_ROOT / "scripts"))
from regime_second_entry_study import phase_transitions        # noqa: E402
from regime_2e_causal_check import detect_entries_causal        # noqa: E402

D = WT_ROOT / "data" / "regime_eth"
OUT = D / "eth_2e_trades_20260724.csv"
TRAIN_END = "2023-12-31"

SLICES = {
    "17-20": lambda h: (h >= 17) & (h < 20),
    "20-00": lambda h: h >= 20,
    "00-04": lambda h: h < 4,
    "04-0830": lambda h: (h >= 4) & (h < 8.5),
    "0830-1400": lambda h: (h >= 8.5) & (h < 14),
    "1400-16": lambda h: h >= 14,
}


def hour_f(ts):
    return ts.hour + ts.minute / 60.0


def main():
    limit = None
    if "--limit" in sys.argv:
        limit = int(sys.argv[sys.argv.index("--limit") + 1])
    bars = pd.read_parquet(D / "_eth_5m.parquet")
    sessions = sorted(bars.Session.unique())
    if limit:
        sessions = sessions[:limit]
    by_sess = {s: g for s, g in bars.groupby("Session")}

    rows = []; t0 = time.time(); nd = 0
    for di, dstr in enumerate(sessions):
        g = by_sess[dstr].sort_values("DateTime").reset_index(drop=True)
        p = D / "ticks" / f"{dstr}.parquet"
        if len(g) < 60 or not p.exists():
            continue
        tk = pd.read_parquet(p)
        if len(tk) < 1000:
            continue
        tP = tk["Price"].values
        tbar = np.searchsorted(g["DateTime"].values, tk["DateTime"].values, side="right") - 1
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
            md = mode_at(jf)
            want = "BEAR" if short else "BULL"
            wt_ok = md == want
            fade = (not short and md == "BEAR") or (short and md == "BULL")
            if wt_ok:
                lim = trig + 4 * TICK if short else trig - 4 * TICK
                seg0 = tP[jf:]
                jl_ = np.nonzero(seg0 > lim)[0] if short else np.nonzero(seg0 < lim)[0]
                if len(jl_):
                    jfl = jf + int(jl_[0])
                    fill = lim
                    fb2 = int(tbar[jfl])
                    hf = hour_f(pd.Timestamp(g_dt[min(fb2, n - 1)]))
                    stop = fill + 16 * TICK if short else fill - 16 * TICK
                    seg = tP[jfl:]
                    js_ = np.nonzero(seg >= stop)[0] if short else np.nonzero(seg <= stop)[0]
                    ex = stop if len(js_) else seg[-1]
                    pnl = (fill - ex) if short else (ex - fill)
                    rows.append((dstr, "2E", dr, round(hf, 2), round(pnl * PT - COMM, 1)))
            elif fade and not short:                      # failed 2EL in BEAR -> fade short
                sb_lo = L[sb]
                fail_px = sb_lo - TICK
                zlim = np.searchsorted(tbar, fb + 3, "left")
                segf = tP[jf:zlim]
                w = np.nonzero(segf <= fail_px)[0]
                if len(w):
                    jx = jf + int(w[0])
                    fill = fail_px - TICK
                    fb2 = int(tbar[jx])
                    hf = hour_f(pd.Timestamp(g_dt[min(fb2, n - 1)]))
                    stop = fill + 16 * TICK
                    seg = tP[jx:]
                    js_ = np.nonzero(seg >= stop)[0]
                    ex = stop if len(js_) else seg[-1]
                    rows.append((dstr, "f2EL", "S", round(hf, 2),
                                 round((fill - ex) * PT - COMM, 1)))
        nd += 1
        del tk, tP, tbar; gc.collect()
        if (di + 1) % 100 == 0:
            print(f"[{di+1}/{len(sessions)}] rows={len(rows)} ({time.time()-t0:.0f}s)", flush=True)

    df = pd.DataFrame(rows, columns=["Session", "setup", "dir", "fill_h", "net"])
    df.to_csv(OUT, index=False)
    df["is_tr"] = df.Session <= TRAIN_END

    def pf(s):
        gp = s[s > 0].sum(); gl = -s[s < 0].sum()
        return gp / gl if gl > 0 else float("inf")

    print(f"\nDONE {time.time()-t0:.0f}s sessions={nd} rows={len(df)} -> {OUT}")
    for setup in ("2E", "f2EL"):
        d1 = df[df.setup == setup]
        print("\n" + "=" * 92)
        print(f"{setup} — 24h session machine   (train | test)")
        print("=" * 92)
        out = []
        segs = [("FULL session", pd.Series(True, d1.index))]
        segs += [(k, fn(d1.fill_h)) for k, fn in SLICES.items()]
        for name, m in segs:
            x = d1[m]; trn = x[x.is_tr]; tst = x[~x.is_tr]
            if len(trn) < 20 or len(tst) < 10:
                continue
            out.append((name, len(trn), round(trn.net.sum()), round(pf(trn.net), 2),
                        len(tst), round(tst.net.sum()), round(pf(tst.net), 2)))
        print(pd.DataFrame(out, columns=["slice", "n_tr", "net_tr", "PF_tr",
                                         "n_te", "net_te", "PF_te"]).to_string(index=False))


if __name__ == "__main__":
    main()
