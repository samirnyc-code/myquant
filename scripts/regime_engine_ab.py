"""A/B: OLD engine (S83 study) vs NEW engine (2nd PC: immediate-flip + leg-continuation).

NEW engine logic lifted VERBATIM from scratchpad/regime_phase_machine.py (commit 1760ffd)
into the (H,L,n,tP,tbar)->[(tick,mode)] interface. OLD = regime_second_entry_study.
Per day: compare the tick-level regime state. Then run the COMMITTED-SPEC 2E book
(2EL/2ES with-trend, gap<=0.54 skip, retest6 through, 0.30xADR stop floor8, EOD, h09-13,
$5 RT + 1t slip) under EACH engine's gate and compare PF/net/n + per-year + state-diff.

  python scripts/regime_engine_ab.py [--limit N]
Output: data/regime/engine_ab_20260724.csv + tables + PNG.
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
from regime_second_entry_study import phase_transitions as pt_old, load_day  # noqa: E402
from regime_2e_causal_check import detect_entries_causal                     # noqa: E402

OUT = WT / "data" / "regime" / "engine_ab_20260724.csv"
GOOD = {"09", "10", "11", "12", "13"}
TRAIN_END = "2023-12-31"
FLOOR = 8 * TICK


def pt_new(H, L, n, tP, tbar, trace=None):
    """NEW engine (2nd PC 1760ffd) — verbatim logic, [(tick,mode)] out."""
    piv = []; trend_starts = []; terms = []
    prevH = prevL = 0; first_pivot_done = False
    mode = "NEUTRAL"; standing = None
    run_b = run_px = None
    cand = None
    hi_p = lo_p = lsh = lsl = None
    has_hl = has_lh = False
    struct_hl = struct_lh = None
    d = None; leg_px = None; leg_bar = None

    def add_pivot(bar, side, emit):
        nonlocal prevH, prevL, first_pivot_done, hi_p, lo_p, lsh, lsl
        nonlocal has_hl, has_lh, cand, struct_hl, struct_lh
        if side == "H":
            t = "hh" if H[bar] > H[prevH] else ("lh" if H[bar] < H[prevH] else "dh"); prevH = bar
        else:
            t = "hl" if L[bar] > L[prevL] else ("ll" if L[bar] < L[prevL] else "dl"); prevL = bar
        disp = side if not first_pivot_done else t
        first_pivot_done = True
        p = dict(bar=bar, side=side, tag=t, disp=disp, major=None, majlab=None)
        piv.append(p)
        # structure trackers run in EVERY mode (the 2nd-PC change)
        if side == "H":
            lsh = p
            if hi_p is None or H[bar] > H[hi_p["bar"]]: hi_p = p
            if t == "lh" or len(disp) == 1: has_lh = True; struct_lh = p
        else:
            lsl = p
            if lo_p is None or L[bar] < L[lo_p["bar"]]: lo_p = p
            if t == "hl" or len(disp) == 1: has_hl = True; struct_hl = p
        if mode == "BULL" and side == "L":
            if cand is None or L[bar] < L[cand["p"]["bar"]]: cand = dict(p=p, ref_px=run_px)
        elif mode == "BEAR" and side == "H":
            if cand is None or H[bar] > H[cand["p"]["bar"]]: cand = dict(p=p, ref_px=run_px)
        if mode == "BULL" and side == "H" and bar == run_b:
            p["major"] = emit; p["majlab"] = "HH"
        elif mode == "BEAR" and side == "L" and bar == run_b:
            p["major"] = emit; p["majlab"] = "LL"
        return p

    def start_trend(up, b, px):
        nonlocal mode, standing, run_b, run_px, cand
        nonlocal hi_p, lo_p, lsh, lsl, has_hl, has_lh, struct_hl, struct_lh
        broken = lsh if up else lsl
        partner = struct_hl if up else struct_lh
        broken["major"] = b; broken["majlab"] = "HH" if up else "LL"
        trend_starts.append((b, "bull" if up else "bear", broken["bar"]))
        standing = None
        if partner is not None:
            standing = (partner["bar"], L[partner["bar"]] if up else H[partner["bar"]])
        run_b, run_px = b, px
        mode = "BULL" if up else "BEAR"; cand = None
        hi_p = lo_p = lsh = lsl = None; has_hl = has_lh = False
        struct_hl = struct_lh = None

    def terminate(b, px):
        nonlocal mode, standing, run_b, run_px, cand
        nonlocal hi_p, lo_p, lsh, lsl, has_hl, has_lh, struct_hl, struct_lh
        was_bull = (mode == "BULL")
        terms.append((standing[0], standing[1], b, mode.lower()))
        flip_up = ((not was_bull) and lsh is not None and px > H[lsh["bar"]] and has_hl
                   and struct_hl is not None and struct_hl["bar"] > lsh["bar"])
        flip_dn = (was_bull and lsl is not None and px < L[lsl["bar"]] and has_lh
                   and struct_lh is not None and struct_lh["bar"] > lsl["bar"])
        mode = "NEUTRAL"
        cand = None; standing = None; run_b = run_px = None
        # prevH/prevL untouched; leg NOT reset (the 2nd-PC fix)
        if flip_up or flip_dn:
            start_trend(flip_up, b, px)
        else:
            hi_p = lo_p = lsh = lsl = None; has_hl = has_lh = False
            struct_hl = struct_lh = None

    transitions = [(0, "NEUTRAL")]
    cur_bar = -1; up_done = dn_done = True
    for _t in range(len(tP)):
        b = int(tbar[_t])
        if b < 1 or b >= n:
            continue
        px = tP[_t]
        if b != cur_bar:
            cur_bar = b; up_done = dn_done = False
        if d == 1 and (leg_px is None or px > leg_px): leg_px, leg_bar = px, b
        if d == -1 and (leg_px is None or px < leg_px): leg_px, leg_bar = px, b
        if not up_done and px > H[b - 1]:
            up_done = True
            if d == -1:
                add_pivot(leg_bar, "L", b); d = 1; leg_px, leg_bar = px, b
            elif d is None:
                d = 1; leg_px, leg_bar = px, b
        if not dn_done and px < L[b - 1]:
            dn_done = True
            if d == 1:
                add_pivot(leg_bar, "H", b); d = -1; leg_px, leg_bar = px, b
            elif d is None:
                d = -1; leg_px, leg_bar = px, b
        if mode == "NEUTRAL":
            if lsh is not None and px > H[lsh["bar"]] and has_hl: start_trend(True, b, px)
            elif lsl is not None and px < L[lsl["bar"]] and has_lh: start_trend(False, b, px)
        else:
            if cand is not None and cand["ref_px"] is not None:
                hit = px > cand["ref_px"] if mode == "BULL" else px < cand["ref_px"]
                if hit:
                    q = cand["p"]
                    standing = (q["bar"], L[q["bar"]] if mode == "BULL" else H[q["bar"]])
                    cand = None
            if mode == "BULL" and px > run_px: run_b, run_px = b, px
            if mode == "BEAR" and px < run_px: run_b, run_px = b, px
            if standing is not None:
                if (mode == "BULL" and px < standing[1]) or (mode == "BEAR" and px > standing[1]):
                    terminate(b, px)
        if transitions[-1][1] != mode:
            transitions.append((_t, mode))
    if trace is not None:
        trace["starts"] = trend_starts; trace["terms"] = terms
    return transitions


def book(g, tP, tbar, adr, gapv, pt_fn):
    """Committed-spec 2E book under a given engine. Returns list of (dir, net)."""
    if gapv > 0.54 or not np.isfinite(adr):
        return [], None
    H, L = g["High"].values, g["Low"].values
    O, C = g["Open"].values, g["Close"].values
    n = len(g)
    trans = pt_fn(H, L, n, tP, tbar)
    tr_ix = [t for (t, _) in trans]; tr_md = [m for (_, m) in trans]
    entries = detect_entries_causal(g, tP, tbar)
    g_dt = g["DateTime"].values
    sdist = max(round(0.30 * adr / TICK) * TICK, FLOOR)
    out = []
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
        jl = np.nonzero(seg0 > lim)[0] if short else np.nonzero(seg0 < lim)[0]
        if not len(jl):
            continue
        jfl = jf + int(jl[0]); fb2 = int(tbar[jfl])
        if fb2 - fb > 6:
            continue
        hh = pd.Timestamp(g_dt[min(fb2, n - 1)]).strftime("%H")
        if hh not in GOOD:
            continue
        stop = lim + sdist if short else lim - sdist
        seg = tP[jfl:]
        js = np.nonzero(seg >= stop)[0] if short else np.nonzero(seg <= stop)[0]
        ex = stop if len(js) else seg[-1]
        out.append((dr, round(((lim - ex) if short else (ex - lim)) * PT - COMM - SLIP, 1)))
    return out, tr_md


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

    rows = []; diff_days = 0; tot_days = 0; t0 = time.time()
    for di, dstr in enumerate(days):
        if dstr not in gmap.index:
            continue
        g, tP, tbar = load_day(b, dstr)
        if g is None:
            continue
        adr, gapv = gmap.loc[dstr, "adr10"], gmap.loc[dstr, "gap"]
        try:
            ro, mo = book(g, tP, tbar, adr, gapv, pt_old)
            rn, mn = book(g, tP, tbar, adr, gapv, pt_new)
        except Exception as e:
            print(dstr, "ERR", repr(e), flush=True); continue
        tot_days += 1
        if mo != mn:
            diff_days += 1
        for (dr, net) in ro:
            rows.append((dstr, "OLD", dr, net))
        for (dr, net) in rn:
            rows.append((dstr, "NEW", dr, net))
        del tP, tbar; gc.collect()
        if (di + 1) % 150 == 0:
            print(f"[{di+1}/{len(days)}] statediff {diff_days}/{tot_days} ({time.time()-t0:.0f}s)", flush=True)

    df = pd.DataFrame(rows, columns=["Date", "engine", "dir", "net"])
    df.to_csv(OUT, index=False)
    df["is_tr"] = df.Date <= TRAIN_END; df["yr"] = df.Date.str[:4]

    def pf(s):
        gp = s[s > 0].sum(); gl = -s[s < 0].sum()
        return round(gp / gl, 2) if gl > 0 else float("inf")

    print(f"\nDONE {time.time()-t0:.0f}s  days={tot_days}  "
          f"tick-state differs on {diff_days} days ({100*diff_days/max(tot_days,1):.1f}%)")
    print("\nengine  n    net       $/tr   PF   train      | test        | L_PF  S_PF")
    for e in ("OLD", "NEW"):
        x = df[df.engine == e]; trn = x[x.is_tr]; tst = x[~x.is_tr]
        print(f"{e:5s} {len(x):4d} {x.net.sum():+9,.0f} {x.net.mean():+6.1f} {pf(x.net):5.2f} "
              f"{trn.net.sum():+8.0f}/{pf(trn.net):4.2f} | {tst.net.sum():+8.0f}/{pf(tst.net):4.2f} | "
              f"{pf(x[x.dir=='L'].net):4.2f} {pf(x[x.dir=='S'].net):4.2f}")
    print("\nPF by year:")
    py = df.pivot_table(index="yr", columns="engine", values="net", aggfunc=pf)
    ny = df.pivot_table(index="yr", columns="engine", values="net", aggfunc="size")
    print(pd.concat([py, ny], axis=1, keys=["PF", "n"]).to_string())

    fig, ax = plt.subplots(figsize=(12, 6), dpi=115)
    for e, c in (("OLD", "#8b8f96"), ("NEW", "#2a78d6")):
        x = df[df.engine == e].sort_values("Date")
        ax.plot(range(len(x)), x.net.cumsum().values, lw=2, color=c,
                label=f"{e} engine: {x.net.sum():+,.0f}$  PF {pf(x.net)}  n={len(x)}")
    ax.axhline(0, color="#c3c2b7", lw=1); ax.legend(frameon=False)
    ax.grid(axis="y", color="#eceeed", lw=0.7)
    for s_ in ("top", "right"): ax.spines[s_].set_visible(False)
    ax.set_title(f"Committed-spec book: OLD vs NEW (2nd-PC) engine  ·  "
                 f"state differs {100*diff_days/max(tot_days,1):.0f}% of days", fontweight="bold")
    fig.tight_layout()
    p = WT / "docs" / "living" / "engine_ab_20260724.png"
    fig.savefig(p, facecolor="white"); print("saved", p)


if __name__ == "__main__":
    main()
