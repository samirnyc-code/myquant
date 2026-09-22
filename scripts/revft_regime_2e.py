"""RevFT x REGIME (phase-machine) x 2E-book exits — rescue study.  2026-07-25 (S85)

Premise. RevFT ("MyReversals") 5M ES swing-reversal is a firm loser at 1:1 (Note 0005:
-$187k/5yr). Note 0005's one durable finding: RevFT is structurally a WITH-TREND
CONTINUATION signal, not a fade — but its only trend proxy was crude VWAP-side, and it
only ever tested fixed 1R/2R/3R targets (never hold-to-EOD). The S83 2E book's actual
edge was the OPPOSITE exit: a wide vol stop + HOLD-TO-EOD, no target (tail-concentrated
runners). This study replaces the VWAP proxy with the real phase-machine regime label
(engine `pt_new`, the "latest regime engine" = 2nd-PC 1760ffd, verbatim) and applies the
2E exit machinery to RevFT.

Books (all causal, real ticks, $5 RT + 1t slip, EOD flat):
  BASE    all RevFT, native 1R (StopPrice = rejected extreme)         [reference loser]
  WT      with-trend gate: Long only in BULL, Short only in BEAR
  CT      counter-trend: Long in BEAR, Short in BULL  (mechanism check — should lose)
  ALIGN   trade the REGIME side at each RevFT bar (flip CT signals)
For WT/CT/ALIGN, three exits: native-1R, native-stop+EOD, wideVol(0.30xADR)+EOD.
Full 2E stack = WT + gap-skip(|gap|>0.54%) + hour-filter(09-13) + wideVol+EOD.

Regime at a signal = phase-machine mode as of the SIGNAL BAR's close (causal; entry is the
first tick of the next bar). Output: data/regime/revft_regime_2e_YYYYMMDD.csv (per-trade)
+ printed book table + year-by-year for the headline book.

    python scripts/revft_regime_2e.py [--limit N]
"""
import sys
from pathlib import Path
from bisect import bisect_right
import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parent.parent
DATA = ROOT / "data"
BARS = DATA / "bars" / "_continuous.parquet"
TICKD = DATA / "ticks_continuous"
SIG = ROOT / "saved_signals" / "ba_signals_revft.parquet"
STAMP = "20260725"
OUT = DATA / "regime" / f"revft_regime_2e_{STAMP}.csv"

TICK = 0.25; PT = 50.0; COMM = 5.0; SLIP = 12.5   # SLIP already in $ (=1 tick) per 2E convention
FLOOR = 8 * TICK
GOOD = {"09", "10", "11", "12", "13"}
GAP_MAX = 0.54


# ============ REGIME ENGINE — pt_new, vendored verbatim from ============
# myquant-regime/scripts/regime_engine_ab.py (branch regime/indep), which is the
# 2nd-PC commit 1760ffd of scratchpad/regime_phase_machine.py lifted to the
# (H,L,n,tP,tbar)->[(tick,mode)] interface. DO NOT edit logic here — keep in lockstep.
def pt_new(H, L, n, tP, tbar, trace=None):
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
# ============ end vendored engine ============


def load_day(b, dstr):
    g = b[b["Date"] == dstr].sort_values("DateTime").reset_index(drop=True)
    p = TICKD / f"{dstr}.parquet"
    if len(g) < 30 or not p.exists():
        return None, None, None
    tk = pd.read_parquet(p).sort_values("DateTime")
    if tk.empty:
        return None, None, None
    tP = tk["Price"].values
    tbar = np.searchsorted(g["DateTime"].values, tk["DateTime"].values, side="right") - 1
    return g, tP, tbar


def sim_exit(seg, entry, long, stop, target):
    """seg = tick prices from entry onward. Returns exit price. target=None -> hold to EOD."""
    if long:
        loss = np.nonzero(seg <= stop)[0]
        win = np.nonzero(seg >= target)[0] if target is not None else np.array([], int)
    else:
        loss = np.nonzero(seg >= stop)[0]
        win = np.nonzero(seg <= target)[0] if target is not None else np.array([], int)
    il = loss[0] if len(loss) else None
    iw = win[0] if len(win) else None
    if il is None and iw is None:
        return seg[-1]                       # EOD flat
    if iw is None:
        return stop
    if il is None:
        return target
    return stop if il <= iw else target      # tie -> stop first (conservative)


def dollars(entry, ex, long):
    return round(((ex - entry) if long else (entry - ex)) * PT - COMM - SLIP, 1)


def main():
    limit = int(sys.argv[sys.argv.index("--limit") + 1]) if "--limit" in sys.argv else None
    b = pd.read_parquet(BARS); b["Date"] = b["DateTime"].dt.date.astype(str)
    dly = b.groupby("Date").agg(dO=("Open", "first"), dC=("Close", "last"),
                                dH=("High", "max"), dL=("Low", "min")).reset_index()
    dly["adr10"] = (dly.dH - dly.dL).rolling(10).mean().shift(1)
    dly["gap"] = ((dly.dO - dly.dC.shift(1)) / dly.dC.shift(1) * 100).abs()
    gm = dly.set_index("Date")[["adr10", "gap"]]

    sig = pd.read_parquet(SIG)
    sig = sig[sig.SignalType != "Sneaky"].copy()          # Sneaky excluded throughout the RevFT notes
    sig["Date"] = sig["Date"].astype(str)
    sig["DateTime"] = pd.to_datetime(sig["DateTime"])
    days = sorted(sig["Date"].unique())
    if limit:
        days = days[:limit]

    rows = []
    for di, dstr in enumerate(days):
        if dstr not in gm.index:
            continue
        adr, gapv = gm.loc[dstr, "adr10"], gm.loc[dstr, "gap"]
        if not np.isfinite(adr):
            continue
        g, tP, tbar = load_day(b, dstr)
        if g is None:
            continue
        trans = pt_new(g["High"].values, g["Low"].values, len(g), tP, tbar)
        tr_ix = [t for (t, _) in trans]; tr_md = [m for (_, m) in trans]
        gdt = g["DateTime"].values
        wide = max(round(0.30 * adr / TICK) * TICK, FLOOR)
        daysig = sig[sig.Date == dstr]
        for _, s in daysig.iterrows():
            sb = np.searchsorted(gdt, np.datetime64(s.DateTime), "right") - 1   # signal bar
            if sb < 1 or sb >= len(g) - 1:
                continue
            # regime as of signal-bar close (last tick with tbar==sb) — causal
            zt = np.searchsorted(tbar, sb, "right") - 1
            if zt < 0:
                continue
            reg = tr_md[bisect_right(tr_ix, zt) - 1]
            # entry = first tick of next bar
            a = np.searchsorted(tbar, sb + 1, "left")
            if a >= len(tP):
                continue
            entry = tP[a]; seg = tP[a:]
            long = (s.Direction == "Long")
            stopx = float(s.StopPrice)                     # rejected extreme = native stop
            R = (entry - stopx) if long else (stopx - entry)
            if R <= 0:
                continue                                    # entry already past native stop
            hh = pd.Timestamp(gdt[sb + 1]).strftime("%H")
            rows.append(dict(
                Date=dstr, year=int(dstr[:4]), dir=("L" if long else "S"),
                stype=s.SignalType, reg=reg, hour=hh, gap=round(gapv, 3), R=round(R, 2),
                # native 1R
                n1r=dollars(entry, sim_exit(seg, entry, long, stopx,
                            entry + R if long else entry - R), long),
                # native stop, hold to EOD
                neod=dollars(entry, sim_exit(seg, entry, long, stopx, None), long),
                # wide vol stop, hold to EOD
                weod=dollars(entry, sim_exit(seg, entry, long,
                            entry - wide if long else entry + wide, None), long),
            ))
        if (di + 1) % 200 == 0:
            print(f"[{di+1}/{len(days)}] rows={len(rows)}", flush=True)

    t = pd.DataFrame(rows)
    t.to_csv(OUT, index=False)
    print(f"\nsaved {OUT}  ({len(t)} trades)\n")

    def stat(df, col):
        if not len(df):
            return "n=0"
        v = df[col].values
        gp = v[v > 0].sum(); gl = -v[v < 0].sum()
        pf = gp / gl if gl > 0 else float("inf")
        return f"n={len(df):5d}  tot=${v.sum():>9,.0f}  $/tr={v.mean():>6.1f}  PF={pf:4.2f}  win={100*(v>0).mean():4.1f}%"

    print("=" * 96)
    print("RevFT x regime x 2E-exit — full sample (Sneaky excluded)")
    print("=" * 96)
    L, S = t.dir == "L", t.dir == "S"
    bull, bear, neu = t.reg == "BULL", t.reg == "BEAR", t.reg == "NEUTRAL"
    WT = (L & bull) | (S & bear)          # with-trend
    CT = (L & bear) | (S & bull)          # counter-trend
    print(f"\nregime mix at signal:  BULL {bull.mean()*100:.0f}%  BEAR {bear.mean()*100:.0f}%  NEUTRAL {neu.mean()*100:.0f}%")
    print(f"of non-neutral signals: with-trend {WT.sum()}  counter-trend {CT.sum()}\n")

    books = [
        ("BASE  all / native-1R      ", t, "n1r"),
        ("WT    with-trend / native-1R", t[WT], "n1r"),
        ("WT    with-trend / stop+EOD ", t[WT], "neod"),
        ("WT    with-trend / wideVol+EOD", t[WT], "weod"),
        ("CT    counter-tr / native-1R", t[CT], "n1r"),
        ("CT    counter-tr / wideVol+EOD", t[CT], "weod"),
        ("NEU   neutral / native-1R   ", t[neu], "n1r"),
    ]
    for name, df, col in books:
        print(f"{name:32s} {stat(df, col)}")

    # full 2E stack on the with-trend book
    stack = t[WT & (t.gap <= GAP_MAX) & (t.hour.isin(GOOD))]
    print("\nFULL 2E STACK (WT + gap<=0.54% + hours 09-13):")
    for col, lab in [("n1r", "native-1R"), ("neod", "stop+EOD"), ("weod", "wideVol+EOD")]:
        print(f"  {lab:14s} {stat(stack, col)}")

    # headline book year-by-year: pick WT wideVol+EOD (the 2E-style exit)
    print("\nYEAR-BY-YEAR  —  WT / wideVol+EOD (headline):")
    hb = t[WT]
    for yr in sorted(hb.year.unique()):
        print(f"  {yr}  {stat(hb[hb.year == yr], 'weod')}")
    print("\nYEAR-BY-YEAR  —  WT / native-1R (for comparison):")
    for yr in sorted(hb.year.unique()):
        print(f"  {yr}  {stat(hb[hb.year == yr], 'n1r')}")


if __name__ == "__main__":
    main()
