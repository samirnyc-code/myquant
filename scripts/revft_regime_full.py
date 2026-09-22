"""RevFT x REGIME — COMPREHENSIVE rescue matrix.  2026-07-25 (S85)  "leave no leaf unturned"

Supersedes revft_regime_2e.py. One tick-replay pass over every RevFT signal day exports a
rich per-trade table (all exit outcomes + every gating feature); all slicing is done in
pandas afterward. Then an honest verdict: train(<=2023)/holdout(2024+), year-by-year, and a
block-bootstrap CI on any book that looks alive.

REGIME SOURCES applied to RevFT:
  1 pt_new  — intraday tick phase-machine (latest engine, 2nd-PC 1760ffd, vendored). Gives a
              per-bar BULL/BEAR/NEUTRAL trend state -> the with-trend/counter-trend gate.
  2 pt_old  — prior phase-machine (imported from worktree if available) for A/B.
  3 MQ      — daily gamma regime (mq_regime_daily_2007_2026_v2.csv): positive_gamma
              (dealers dampen -> reversion-friendly) vs negative_gamma (amplify -> trend).
              Orthogonal to #1; the natural gate for a REVERSAL signal.

EXITS precomputed per trade ($, $5 RT + 1t slip, EOD flat): native stop (=rejected extreme)
at 1R/2R/3R and hold-EOD; wide vol stop 0.20/0.30/0.50xADR hold-EOD; wide-0.30 + 1R/2R/3R
target. Plus MFE/MAE (pts) for trail/partial analysis.

    python scripts/revft_regime_full.py [--limit N]
Output: data/regime/revft_regime_full_YYYYMMDD.parquet + printed report.
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
MQ = DATA / "regime" / "mq_regime_daily_2007_2026_v2.csv"
STAMP = "20260725"
OUT = DATA / "regime" / f"revft_regime_full_{STAMP}.parquet"

TICK = 0.25; PT = 50.0; COMM = 5.0; SLIP = 12.5
FLOOR = 8 * TICK
GOOD = {"09", "10", "11", "12", "13"}
GAP_MAX = 0.54
TRAIN_END = "2023-12-31"

# optional A/B: prior engine from the regime worktree (graceful skip)
pt_old = None
try:
    sys.path.insert(0, r"C:/Users/Admin/myquant-regime/scripts")
    from regime_second_entry_study import phase_transitions as pt_old  # noqa: E402
except Exception as e:  # pragma: no cover
    print("pt_old unavailable (A/B skipped):", repr(e)[:80])


# ============ pt_new — vendored verbatim (see revft_regime_2e.py header) ============
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
    return g, tk["Price"].values, np.searchsorted(g["DateTime"].values, tk["DateTime"].values, "right") - 1


def regime_at(trans, tick_ix):
    tr_ix = [t for (t, _) in trans]; tr_md = [m for (_, m) in trans]
    return tr_md[bisect_right(tr_ix, tick_ix) - 1]


def first_touch(seg, thr, up):
    """index of first tick >= thr (up) / <= thr (down); None."""
    hit = np.nonzero(seg >= thr)[0] if up else np.nonzero(seg <= thr)[0]
    return int(hit[0]) if len(hit) else None


def exit_px(seg, long, stop, target):
    il = first_touch(seg, stop, not long)                 # stop hit (adverse)
    iw = first_touch(seg, target, long) if target is not None else None
    if il is None and iw is None:
        return seg[-1]
    if iw is None:
        return stop
    if il is None:
        return target
    return stop if il <= iw else target                   # tie -> stop (conservative)


def dol(entry, ex, long):
    return round(((ex - entry) if long else (entry - ex)) * PT - COMM - SLIP, 1)


def main():
    limit = int(sys.argv[sys.argv.index("--limit") + 1]) if "--limit" in sys.argv else None
    b = pd.read_parquet(BARS); b["Date"] = b["DateTime"].dt.date.astype(str)
    dly = b.groupby("Date").agg(dO=("Open", "first"), dC=("Close", "last"),
                                dH=("High", "max"), dL=("Low", "min")).reset_index()
    dly["adr10"] = (dly.dH - dly.dL).rolling(10).mean().shift(1)
    dly["gap"] = ((dly.dO - dly.dC.shift(1)) / dly.dC.shift(1) * 100).abs()
    gm = dly.set_index("Date")[["adr10", "gap"]]

    mq = pd.read_csv(MQ)[["date", "regime", "net_total_gex"]]
    mq["date"] = mq["date"].astype(str)
    mqmap = mq.set_index("date")

    sig = pd.read_parquet(SIG)
    sig = sig[sig.SignalType != "Sneaky"].copy()
    sig["Date"] = sig["Date"].astype(str); sig["DateTime"] = pd.to_datetime(sig["DateTime"])
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
        H, Lo = g["High"].values, g["Low"].values; nB = len(g)
        tn = pt_new(H, Lo, nB, tP, tbar)
        to = pt_old(H, Lo, nB, tP, tbar) if pt_old else None
        gdt = g["DateTime"].values
        mqreg = mqmap.loc[dstr, "regime"] if dstr in mqmap.index else "na"
        mqgex = mqmap.loc[dstr, "net_total_gex"] if dstr in mqmap.index else np.nan
        wides = {m: max(round(m * adr / TICK) * TICK, FLOOR) for m in (0.20, 0.30, 0.50)}
        for _, s in sig[sig.Date == dstr].iterrows():
            sb = np.searchsorted(gdt, np.datetime64(s.DateTime), "right") - 1
            if sb < 1 or sb >= nB - 1:
                continue
            zt = np.searchsorted(tbar, sb, "right") - 1
            if zt < 0:
                continue
            a = np.searchsorted(tbar, sb + 1, "left")
            if a >= len(tP):
                continue
            entry = tP[a]; seg = tP[a:]
            long = (s.Direction == "Long")
            stopx = float(s.StopPrice)
            R = (entry - stopx) if long else (stopx - entry)
            if R <= 0:
                continue
            mfe = (seg.max() - entry) if long else (entry - seg.min())
            mae = (entry - seg.min()) if long else (seg.max() - entry)
            rec = dict(
                Date=dstr, year=int(dstr[:4]), dir=("L" if long else "S"),
                stype=str(s.SignalType), hour=pd.Timestamp(gdt[sb + 1]).strftime("%H"),
                gap=round(float(gapv), 3), R=round(R, 2), adr=round(float(adr), 2),
                mfe=round(float(mfe), 2), mae=round(float(mae), 2),
                reg=regime_at(tn, zt), reg_old=(regime_at(to, zt) if to else "na"),
                mq=str(mqreg), gex=float(mqgex),
                # native-stop exits
                n1r=dol(entry, exit_px(seg, long, stopx, entry + (R if long else -R)), long),
                n2r=dol(entry, exit_px(seg, long, stopx, entry + (2 * R if long else -2 * R)), long),
                n3r=dol(entry, exit_px(seg, long, stopx, entry + (3 * R if long else -3 * R)), long),
                neod=dol(entry, exit_px(seg, long, stopx, None), long),
            )
            # wide-vol stops, hold EOD
            for m, w in wides.items():
                st = entry - w if long else entry + w
                rec[f"w{int(m*100)}eod"] = dol(entry, exit_px(seg, long, st, None), long)
            # wide-0.30 stop + R-multiple targets
            w30 = wides[0.30]; st30 = entry - w30 if long else entry + w30
            for k in (1, 2, 3):
                tg = entry + (k * R if long else -k * R)
                rec[f"w30_{k}r"] = dol(entry, exit_px(seg, long, st30, tg), long)
            rows.append(rec)
        if (di + 1) % 200 == 0:
            print(f"[{di+1}/{len(days)}] rows={len(rows)}", flush=True)

    t = pd.DataFrame(rows)
    t.to_parquet(OUT, index=False)
    print(f"\nsaved {OUT}  ({len(t)} trades, {t.Date.nunique()} days)\n")
    report(t)


def stat(v):
    v = np.asarray(v, float)
    if not len(v):
        return "n=0"
    gp = v[v > 0].sum(); gl = -v[v < 0].sum()
    pf = gp / gl if gl > 0 else float("inf")
    return f"n={len(v):5d}  tot=${v.sum():>10,.0f}  $/tr={v.mean():>6.1f}  PF={pf:4.2f}  win={100*(v>0).mean():4.1f}%"


def boot_ci(v, nboot=2000):
    v = np.asarray(v, float)
    if len(v) < 20:
        return (np.nan, np.nan)
    rng = np.random.default_rng(7)
    means = [rng.choice(v, len(v), replace=True).mean() for _ in range(nboot)]
    return (round(np.percentile(means, 2.5), 1), round(np.percentile(means, 97.5), 1))


def report(t):
    L, S = t.dir == "L", t.dir == "S"
    bull, bear, neu = t.reg == "BULL", t.reg == "BEAR", t.reg == "NEUTRAL"
    WT = (L & bull) | (S & bear); CT = (L & bear) | (S & bull)
    posg, negg = t.mq == "positive_gamma", t.mq == "negative_gamma"
    tr = t.Date <= TRAIN_END

    def line(name, mask, col):
        print(f"  {name:30s} {stat(t.loc[mask, col])}")

    print("=" * 100)
    print(f"REGIME MIX  |  phase-machine: BULL {bull.mean()*100:.0f}%  BEAR {bear.mean()*100:.0f}%  NEUTRAL {neu.mean()*100:.0f}%"
          f"   |  MQ gamma: pos {posg.mean()*100:.0f}%  neg {negg.mean()*100:.0f}%")
    print("=" * 100)

    print("\n### A. BASELINE (no gate)")
    for col in ("n1r", "n2r", "n3r", "neod", "w30eod"):
        line(f"all / {col}", pd.Series(True, t.index), col)

    print("\n### B. PHASE-MACHINE trend gate")
    for tag, m in (("WT with-trend", WT), ("CT counter-trend", CT), ("NEUTRAL", neu)):
        for col in ("n1r", "neod", "w30eod", "w20eod", "w50eod"):
            line(f"{tag} / {col}", m, col)
        print()

    print("### C. MQ GAMMA gate (reversal thesis: fades work in positive_gamma)")
    for tag, m in (("POS gamma / all", posg), ("NEG gamma / all", negg),
                   ("POS gamma / WT", posg & WT), ("POS gamma / CT", posg & CT),
                   ("NEG gamma / WT", negg & WT), ("NEG gamma / CT", negg & CT)):
        for col in ("n1r", "neod", "w30eod"):
            line(f"{tag} / {col}", m, col)
        print()

    print("### D. SETUP TYPE x with-trend (note 0013 flagged BO/IB)")
    for st in sorted(t.stype.unique()):
        m = WT & (t.stype == st)
        line(f"{st} / WT / neod", m, "neod")

    print("\n### E. best-looking books — train/holdout + year + bootstrap CI")
    cands = [
        ("WT / neod", WT, "neod"), ("WT / w30eod", WT, "w30eod"),
        ("POSg / neod", posg, "neod"), ("POSg / n1r", posg, "n1r"),
        ("POSg&WT / w30eod", posg & WT, "w30eod"), ("CT / neod", CT, "neod"),
    ]
    for name, m, col in cands:
        v = t.loc[m, col]; vtr = t.loc[m & tr, col]; vho = t.loc[m & ~tr, col]
        ci = boot_ci(v.values)
        print(f"\n  {name}:  ALL {stat(v)}  95%CI$/tr[{ci[0]},{ci[1]}]")
        print(f"     train {stat(vtr)}")
        print(f"     holdo {stat(vho)}")
        yl = "     yr: " + "  ".join(f"{yr}:{t.loc[m & (t.year==yr), col].sum():>8,.0f}"
                                     for yr in sorted(t.year.unique()))
        print(yl)

    if (t.reg_old != "na").any():
        print("\n### F. engine A/B (pt_new vs pt_old) on the WT/neod book")
        WTo = (L & (t.reg_old == "BULL")) | (S & (t.reg_old == "BEAR"))
        line("pt_new WT / neod", WT, "neod")
        line("pt_old WT / neod", WTo, "neod")


if __name__ == "__main__":
    main()
