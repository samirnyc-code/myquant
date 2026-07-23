"""2E ENTRY-TECHNIQUE variants — S83 P3. Same signal, different execution/management.

The base sim buys a stop-entry 1t beyond the break with 1t slip — it pays the
breakout chase every time. These variants test whether the DEFICIT IS THE
EXECUTION rather than the signal (all on the base-study 2E set, 5m, $5 RT):

  base   : stop entry trig, fill trig+1t slip, stop sigbar+-1t, T1/T2 books (reference)
  noslip : same but fill AT the trigger (bounds what slip costs)
  retest : after the trigger fires, LIMIT 4t back from the trigger; only trades
           that pull back fill (no chase); unfilled = skipped
  closec : fire bar must CLOSE beyond the trigger; enter next bar's first tick +1t
  bemove : base entry, stop moves to breakeven once +1R trades (T2 book only)
  tstop12: base entry, flat at market after 12 bars if neither stop nor target hit

Output: data/regime/entry_variants_20260723.csv (per trade x variant x book)
        stdout summary: variant x book (all 2E + with-trend subset)

  python scripts/regime_2e_entry_variants.py [--limit N]
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
from regime_second_entry_study import phase_transitions, load_day  # noqa: E402
from regime_2e_sweeps import detect_entries  # noqa: E402

OUT = WT_ROOT / "data" / "regime" / "entry_variants_20260723.csv"


def first_hit(seg, px, short, side):
    """Index in seg of first tick at/beyond px. side: 'adv' = adverse (stop-ish,
    >= for short), 'fav' = favorable (target-ish, <= for short)."""
    if short:
        w = np.nonzero(seg >= px)[0] if side == "adv" else np.nonzero(seg <= px)[0]
    else:
        w = np.nonzero(seg <= px)[0] if side == "adv" else np.nonzero(seg >= px)[0]
    return w[0] if len(w) else np.inf


def sim_books(seg, fill, stop, short):
    """Return dict book -> net for plain 1R/2R first-hit sim."""
    R = (stop - fill) if short else (fill - stop)
    if R <= 0:
        return None, None
    js = first_hit(seg, stop, short, "adv")
    out = {}
    for k, book in ((1.0, "T1"), (2.0, "T2")):
        tgt = fill - k * R if short else fill + k * R
        jt = first_hit(seg, tgt, short, "fav")
        ex = stop if js <= jt else (tgt if np.isfinite(jt) else seg[-1])
        pnl = (fill - ex) if short else (ex - fill)
        out[book] = pnl * PT - COMM
    return out, R


def main():
    limit = None
    if "--limit" in sys.argv:
        limit = int(sys.argv[sys.argv.index("--limit") + 1])
    b = pd.read_parquet(DATA / "bars" / "_continuous.parquet")
    b["Date"] = b["DateTime"].dt.date.astype(str)
    days = sorted(b["Date"].unique())
    if limit:
        days = days[:limit]

    rows = []; t0 = time.time(); nd = 0
    for di, dstr in enumerate(days):
        g, tP, tbar = load_day(b, dstr)
        if g is None:
            continue
        O, H, L, C = (g[c].values for c in ["Open", "High", "Low", "Close"])
        n = len(g)
        try:
            transitions = phase_transitions(H, L, n, tP, tbar)
            entries = detect_entries(g, tP, tbar)
        except Exception as e:
            print(dstr, "ERR", repr(e), flush=True)
            continue
        tr_ix = [t for (t, _) in transitions]; tr_md = [m for (_, m) in transitions]
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
            regime = tr_md[bisect_right(tr_ix, jf) - 1]
            stop0 = H[sb] + TICK if short else L[sb] - TICK
            base_fill = trig - TICK if short else trig + TICK
            eid = f"{dstr}_{fb+1}{dr}2"

            def emit(var, book, net, R):
                rows.append((eid, dstr, dr, regime, var, book, net, R))

            # base + noslip
            for var, fl in (("base", base_fill), ("noslip", trig)):
                seg = tP[jf:]
                bk, R = sim_books(seg, fl, stop0, short)
                if bk:
                    emit(var, "T1", bk["T1"], R); emit(var, "T2", bk["T2"], R)

            # retest: limit 4t back from trigger, valid to EOD
            lim = trig + 4 * TICK if short else trig - 4 * TICK
            seg0 = tP[jf:]
            jl_ = np.nonzero(seg0 >= lim)[0] if short else np.nonzero(seg0 <= lim)[0]
            jl = jl_[0] if len(jl_) else np.inf
            if np.isfinite(jl):
                jfl = jf + int(jl)
                seg = tP[jfl:]
                bk, R = sim_books(seg, lim, stop0, short)
                if bk:
                    emit("retest", "T1", bk["T1"], R); emit("retest", "T2", bk["T2"], R)

            # closec: fire bar closes beyond trigger -> enter next bar first tick +1t
            ok = (C[fb] <= trig) if short else (C[fb] >= trig)
            if ok and fb + 1 < n:
                a2 = np.searchsorted(tbar, fb + 1, "left")
                if a2 < len(tP):
                    fl = tP[a2] - TICK if short else tP[a2] + TICK   # 1t adverse slip
                    seg = tP[a2:]
                    bk, R = sim_books(seg, fl, stop0, short)
                    if bk:
                        emit("closec", "T1", bk["T1"], R); emit("closec", "T2", bk["T2"], R)

            # bemove (T2 only): stop -> entry after +1R trades
            seg = tP[jf:]
            R0 = (stop0 - base_fill) if short else (base_fill - stop0)
            if R0 > 0:
                js = first_hit(seg, stop0, short, "adv")
                be_px = base_fill - R0 if short else base_fill + R0
                jbe = first_hit(seg, be_px, short, "fav")
                tgt = base_fill - 2 * R0 if short else base_fill + 2 * R0
                jt = first_hit(seg, tgt, short, "fav")
                if jbe < js:                                   # reached +1R first
                    seg2 = seg[int(jbe):]
                    js2_ = first_hit(seg2, base_fill, short, "adv")
                    jt2_ = first_hit(seg2, tgt, short, "fav")
                    if jt2_ <= js2_ and np.isfinite(jt2_):
                        ex = tgt
                    elif np.isfinite(js2_):
                        ex = base_fill
                    else:
                        ex = seg[-1]
                else:
                    ex = stop0 if np.isfinite(js) else (seg[-1] if not np.isfinite(jt) else tgt)
                    if js <= jt:
                        ex = stop0 if np.isfinite(js) else seg[-1]
                    elif np.isfinite(jt):
                        ex = tgt
                pnl = (base_fill - ex) if short else (ex - base_fill)
                emit("bemove", "T2", pnl * PT - COMM, R0)

            # tstop12: exit market after 12 bars if no stop/target (T1+T2)
            zt = np.searchsorted(tbar, fb + 12, "left")
            seg = tP[jf:]
            cut = max(1, zt - jf)
            if R0 > 0:
                js = first_hit(seg, stop0, short, "adv")
                for k, book in ((1.0, "T1"), (2.0, "T2")):
                    tgt = base_fill - k * R0 if short else base_fill + k * R0
                    jt = first_hit(seg, tgt, short, "fav")
                    if min(js, jt) >= cut and cut < len(seg):
                        ex = seg[cut]
                    elif js <= jt:
                        ex = stop0 if np.isfinite(js) else seg[-1]
                    elif np.isfinite(jt):
                        ex = tgt
                    else:
                        ex = seg[-1]
                    pnl = (base_fill - ex) if short else (ex - base_fill)
                    emit("tstop12", book, pnl * PT - COMM, R0)
        nd += 1
        del tP, tbar; gc.collect()
        if (di + 1) % 100 == 0:
            print(f"[{di+1}/{len(days)}] rows={len(rows)} ({time.time()-t0:.0f}s)", flush=True)

    df = pd.DataFrame(rows, columns=["entry_id", "Date", "dir", "regime",
                                     "variant", "book", "net", "R"])
    df.to_csv(OUT, index=False)
    print(f"\nDONE {time.time()-t0:.0f}s days={nd} rows={len(df)} -> {OUT}")

    def pf(s):
        gp = s[s > 0].sum(); gl = -s[s < 0].sum()
        return gp / gl if gl > 0 else float("inf")

    wt = ((df.regime == "BULL") & (df.dir == "L")) | ((df.regime == "BEAR") & (df.dir == "S"))
    for scope, dd in (("ALL 2E", df), ("WITH-TREND", df[wt])):
        print(f"\n== {scope} ==")
        t = dd.groupby(["variant", "book"]).agg(
            n=("net", "size"), win=("net", lambda s: (s > 0).mean() * 100),
            net=("net", "sum"), PF=("net", pf),
            per_tr=("net", "mean")).round(2)
        print(t.to_string())


if __name__ == "__main__":
    main()
