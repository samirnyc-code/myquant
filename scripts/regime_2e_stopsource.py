"""STOP-SOURCE sweep (Q2) — WT book (2EL/2ES), all else equal to the committed spec.

Tests whether an INTRADAY-adaptive stop beats the once-at-open 0.30xADR10, which
can't see a session's volatility expansion when the prior 10 days were compressed.

Stop variants (distance set AT the entry bar, from intraday info available then):
  adr30   : 0.30 x ADR10 (fixed at open)                      [BASELINE]
  atr     : kA x ATR14 of 5-min bars up to the signal bar     (kA calibrated to
            match the adr30 MEDIAN, so only ADAPTIVITY differs, not average size)
  hybMax  : max(adr30, kA x ATR14)  -- never tighter, WIDER when today runs hot
  hybMax15: max(adr30, 1.5*kA x ATR14)
  expand  : adr30 x max(1, range_so_far / ADR10 at the signal) -- scale by today's
            realized expansion vs the 10-day expectation
All: gap<=0.54 skip, retest6 through-fill, EOD, h09-13, $5 RT + 1t exit slip.

Output: data/regime/stopsource_20260724.csv + tables + PNG.
  python scripts/regime_2e_stopsource.py [--limit N]
"""
import sys, gc, time
from pathlib import Path
from bisect import bisect_right
import numpy as np
import pandas as pd
import matplotlib; matplotlib.use("Agg")
import matplotlib.pyplot as plt

TICK = 0.25; PT = 50.0; COMM = 5.0; SLIP = 12.5
WTR = Path(__file__).resolve().parent.parent
DATA = Path(r"C:/Users/Admin/myquant/data")
sys.path.insert(0, str(WTR / "scripts"))
from regime_second_entry_study import phase_transitions, load_day   # noqa: E402
from regime_2e_causal_check import detect_entries_causal            # noqa: E402

OUT = WTR / "data" / "regime" / "stopsource_20260724.csv"
GOOD = {"09", "10", "11", "12", "13"}
TRAIN_END = "2023-12-31"
FLOOR = 8 * TICK
ATR_N = 14


def atr_series(H, L, C):
    n = len(C); tr = np.zeros(n)
    for i in range(1, n):
        tr[i] = max(H[i] - L[i], abs(H[i] - C[i-1]), abs(L[i] - C[i-1]))
    return pd.Series(tr).rolling(ATR_N, min_periods=1).mean().values


def collect(days, gmap, b, kA):
    """kA=None -> calibration pass (return atr/adr ratios); else -> sim rows."""
    rows = []; ratios = []
    for dstr in days:
        if dstr not in gmap.index:
            continue
        adr, gapv = gmap.loc[dstr, "adr10"], gmap.loc[dstr, "gap"]
        if not np.isfinite(adr) or gapv > 0.54:
            continue
        g, tP, tbar = load_day(b, dstr)
        if g is None:
            continue
        O, H, L, C = (g[c].values for c in ["Open", "High", "Low", "Close"])
        n = len(g)
        atr = atr_series(H, L, C)
        try:
            trans = phase_transitions(H, L, n, tP, tbar)
            entries = detect_entries_causal(g, tP, tbar)
        except Exception:
            continue
        tr_ix = [t for (t, _) in trans]; tr_md = [m for (_, m) in trans]
        g_dt = g["DateTime"].values
        adr30 = max(round(0.30 * adr / TICK) * TICK, FLOOR)
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
            reg = tr_md[bisect_right(tr_ix, jf) - 1]
            want = "BEAR" if short else "BULL"
            if reg != want:
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
            atr_sig = atr[fb]               # intraday ATR at the signal bar (causal)
            rsf = (H[:fb].max() - L[:fb].min()) if fb >= 1 else 0.0
            if kA is None:
                if atr_sig > 0:
                    ratios.append(adr30 / atr_sig)
                continue
            seg = tP[jfl:]

            def run(sdist, tag):
                sdist = max(round(sdist / TICK) * TICK, FLOOR)
                stop = lim + sdist if short else lim - sdist
                js = np.nonzero(seg >= stop)[0] if short else np.nonzero(seg <= stop)[0]
                ex = stop if len(js) else seg[-1]
                pnl = ((lim - ex) if short else (ex - lim)) * PT - COMM - SLIP
                rows.append((dstr, tag, round(pnl, 1), round(sdist, 2)))

            run(adr30, "adr30")
            run(kA * atr_sig, "atr")
            run(max(adr30, kA * atr_sig), "hybMax")
            run(max(adr30, 1.5 * kA * atr_sig), "hybMax15")
            run(adr30 * max(1.0, rsf / adr if adr > 0 else 1.0), "expand")
        del tP, tbar; gc.collect()
    return rows, ratios


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

    t0 = time.time()
    print("calibration pass (match ATR-stop median to ADR-stop median)...", flush=True)
    _, ratios = collect(days, gmap, b, kA=None)
    kA = float(np.median(ratios)) if ratios else 3.5
    print(f"kA = {kA:.2f}  (so kA*ATR14 has the same median as 0.30*ADR10)", flush=True)
    rows, _ = collect(days, gmap, b, kA=kA)

    df = pd.DataFrame(rows, columns=["Date", "variant", "net", "stop_pts"])
    df.to_csv(OUT, index=False)
    df["is_tr"] = df.Date <= TRAIN_END

    def pf(s):
        gp = s[s > 0].sum(); gl = -s[s < 0].sum()
        return round(gp / gl, 2) if gl > 0 else 0

    def mdd(x):
        e = x.sort_values("Date").net.cumsum(); return float((e - e.cummax()).min())

    print(f"\nDONE {time.time()-t0:.0f}s  trades/variant={len(df[df.variant=='adr30'])}")
    print("\nvariant    med-stop  n     net       $/tr   PF    maxDD     train|test")
    for v in ["adr30", "atr", "hybMax", "hybMax15", "expand"]:
        x = df[df.variant == v]
        if not len(x):
            continue
        trn, tst = x[x.is_tr], x[~x.is_tr]
        star = "  <= BASELINE" if v == "adr30" else ""
        print(f"{v:9s}  {x.stop_pts.median():6.1f}p  {len(x):4d}  {x.net.sum():+8,.0f}  "
              f"{x.net.mean():+6.1f}  {pf(x.net):4.2f}  {mdd(x):+8,.0f}  "
              f"{pf(trn.net):4.2f}|{pf(tst.net):4.2f}{star}")
    # per-year for the leaders
    print("\nPF by year:")
    py = df.pivot_table(index=df.Date.str[:4], columns="variant", values="net", aggfunc=pf)
    print(py[["adr30", "atr", "hybMax", "expand"]].to_string())

    fig, ax = plt.subplots(figsize=(12, 6), dpi=115)
    for v, c in (("adr30", "#8b8f96"), ("atr", "#eb6834"), ("hybMax", "#2a78d6"),
                 ("hybMax15", "#1baf7a"), ("expand", "#eda100")):
        x = df[df.variant == v].sort_values("Date")
        ax.plot(range(len(x)), x.net.cumsum().values, lw=2 if v == "adr30" else 1.5,
                color=c, label=f"{v}: {x.net.sum():+,.0f}$ PF {pf(x.net)}")
    ax.axhline(0, color="#c3c2b7", lw=1); ax.legend(frameon=False)
    ax.grid(axis="y", color="#eceeed", lw=0.7)
    for s_ in ("top", "right"): ax.spines[s_].set_visible(False)
    ax.set_title("Stop source: daily ADR10 vs intraday-adaptive (WT book, median-matched)",
                 fontweight="bold")
    fig.tight_layout()
    p = WTR / "docs" / "living" / "stopsource_20260724.png"
    fig.savefig(p, facecolor="white"); print("\nsaved", p)


if __name__ == "__main__":
    main()
