"""TICK-PROXY FIDELITY TEST — decide whether a 1-MINUTE backfill (e.g. Databento
pre-2021 OHLCV) is a trustworthy substitute for real ticks in the regime engine.

The regime engine is tick-driven: it resolves intrabar break-ORDER (which prior-bar
extreme is hit first) — OHLC alone can't. 1-min bars are a proxy: 5 sub-samples per
5M bar. This measures the fidelity loss on 2021-2026, where we have BOTH real ticks
AND 1-min bars, by running the identical PHASE-gate with-trend 2E book two ways:

  REAL  — real ticks (ticks_continuous/<d>.parquet)  = the ground-truth baseline.
  PROXY — pseudo-ticks reconstructed from _continuous_1m.parquet: each 1-min bar ->
          O,(L,H)|(H,L),C  (low-first if up-close, high-first if down-close), in time
          order, mapped onto the SAME 5M bar grid. Everything downstream identical.

Reports: (a) per-5M-bar regime-label AGREEMENT real-vs-proxy, (b) the WT book PnL
side by side (n, net, PF, train/test, maxDD, per-year). If PROXY reproduces REAL,
a cheap 1-min pre-2021 backfill is trustworthy and no tick purchase is needed.

  python scripts/regime_2e_tickproxy_fidelity.py [--limit N]
Output: data/regime/tickproxy_fidelity_20260725.csv + tables + PNG.
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
from regime_second_entry_study import phase_transitions as pt_old, load_day, TICKD  # noqa: E402
from regime_2e_causal_check import detect_entries_causal                           # noqa: E402

OUT = WT / "data" / "regime" / "tickproxy_fidelity_20260725.csv"
M1 = DATA / "bars" / "_continuous_1m.parquet"
GOOD = {"09", "10", "11", "12", "13"}
FLOOR = 8 * TICK
TRAIN_END = "2023-12-31"
rng = np.random.default_rng(83)


def proxy_ticks(g, m1day):
    """Reconstruct pseudo-ticks from 1-min OHLC onto g's 5M bar grid."""
    gdt = g["DateTime"].values
    O = m1day["Open"].values; H = m1day["High"].values
    L = m1day["Low"].values; C = m1day["Close"].values
    mdt = m1day["DateTime"].values
    bars = np.searchsorted(gdt, mdt, side="right") - 1
    px = np.empty(len(m1day) * 4); tb = np.empty(len(m1day) * 4, dtype=np.int64)
    for i in range(len(m1day)):
        seq = (O[i], L[i], H[i], C[i]) if C[i] >= O[i] else (O[i], H[i], L[i], C[i])
        j = i * 4
        px[j:j + 4] = seq; tb[j:j + 4] = bars[i]
    return px, tb


def bar_labels(trans, tbar, n):
    """Per-5M-bar regime label = state active at the last tick of that bar."""
    tr_ix = [t for (t, _) in trans]; tr_md = [m for (_, m) in trans]
    lab = np.array(["NEUTRAL"] * n, dtype=object)
    for i in range(1, n):
        z = int(np.searchsorted(tbar, i, "right"))
        if z == 0:
            continue
        lab[i] = tr_md[bisect_right(tr_ix, z - 1) - 1]
    return lab


def run_wt(g, tP, tbar, adr):
    """PHASE-gate with-trend book (2EL long + 2ES short) on the given tick stream."""
    O, H, L, C = (g[c].values for c in ["Open", "High", "Low", "Close"])
    n = len(g)
    trans = pt_old(H, L, n, tP, tbar)
    tr_ix = [t for (t, _) in trans]; tr_md = [m for (_, m) in trans]
    entries = detect_entries_causal(g, tP, tbar)
    g_dt = g["DateTime"].values
    wide = max(round(0.30 * adr / TICK) * TICK, FLOOR)
    out = []
    for (fb, sb, dr, cnt, trig) in entries:
        if cnt != 2:
            continue
        short = dr == "S"; want = "BEAR" if short else "BULL"
        a = np.searchsorted(tbar, fb, "left"); z = np.searchsorted(tbar, fb, "right")
        hit = np.nonzero(tP[a:z] <= trig)[0] if short else np.nonzero(tP[a:z] >= trig)[0]
        if not len(hit):
            continue
        jf = a + int(hit[0])
        lim = trig + 6 * TICK if short else trig - 6 * TICK; s0 = tP[jf:]
        jl = np.nonzero(s0 > lim)[0] if short else np.nonzero(s0 < lim)[0]
        if not len(jl):
            continue
        jfl = jf + int(jl[0]); fb2 = int(tbar[jfl])
        if fb2 - fb > 6:
            continue
        hh = pd.Timestamp(g_dt[min(fb2, n - 1)]).strftime("%H")
        if hh not in GOOD:
            continue
        reg = tr_md[bisect_right(tr_ix, jf) - 1]
        if reg != want:
            continue
        stop = lim + wide if short else lim - wide; seg = tP[jfl:]
        js = np.nonzero(seg >= stop)[0] if short else np.nonzero(seg <= stop)[0]
        ex = stop if len(js) else seg[-1]
        net = round(((lim - ex) if short else (ex - lim)) * PT - COMM - SLIP, 1)
        out.append(("WT-S" if short else "WT-L", net))
    return out, trans


def main():
    limit = None
    if "--limit" in sys.argv:
        limit = int(sys.argv[sys.argv.index("--limit") + 1])
    b = pd.read_parquet(DATA / "bars" / "_continuous.parquet"); b["Date"] = b["DateTime"].dt.date.astype(str)
    m1 = pd.read_parquet(M1); m1["Date"] = m1["DateTime"].dt.date.astype(str)
    m1g = {d: x.sort_values("DateTime").reset_index(drop=True) for d, x in m1.groupby("Date")}
    dly = b.groupby("Date").agg(dO=("Open", "first"), dC=("Close", "last"), dH=("High", "max"), dL=("Low", "min")).reset_index()
    dly["adr10"] = (dly.dH - dly.dL).rolling(10).mean().shift(1)
    dly["gap"] = ((dly.dO - dly.dC.shift(1)) / dly.dC.shift(1) * 100).abs()
    gm = dly.set_index("Date")[["adr10", "gap"]]
    days = sorted(b["Date"].unique())
    if limit:
        days = days[:limit]
    rows = []; lab_agree = 0; lab_tot = 0; ndays = 0; t0 = time.time()
    for di, dstr in enumerate(days):
        if dstr not in gm.index:
            continue
        adr, gapv = gm.loc[dstr, "adr10"], gm.loc[dstr, "gap"]
        if not np.isfinite(adr) or gapv > 0.54:
            continue
        g, tP, tbar = load_day(b, dstr)   # real ticks
        if g is None or dstr not in m1g:
            continue
        m1day = m1g[dstr]
        m1day = m1day[(m1day.DateTime >= g["DateTime"].values[0])]
        if len(m1day) < 30:
            continue
        try:
            tP2, tbar2 = proxy_ticks(g, m1day)
            real_out, real_tr = run_wt(g, tP, tbar, adr)
            proxy_out, proxy_tr = run_wt(g, tP2, tbar2, adr)
            n = len(g)
            lr = bar_labels(real_tr, tbar, n); lp = bar_labels(proxy_tr, tbar2, n)
            m = slice(1, n)
            lab_agree += int((lr[m] == lp[m]).sum()); lab_tot += (n - 1); ndays += 1
            for (bk, net) in real_out:
                rows.append((dstr, "REAL", bk, net))
            for (bk, net) in proxy_out:
                rows.append((dstr, "PROXY", bk, net))
        except Exception as e:
            print(dstr, "ERR", repr(e), flush=True)
        del tP, tbar; gc.collect()
        if (di + 1) % 150 == 0:
            print(f"[{di+1}/{len(days)}] rows={len(rows)} labAgree={lab_agree/max(lab_tot,1):.3f} ({time.time()-t0:.0f}s)", flush=True)
    df = pd.DataFrame(rows, columns=["Date", "src", "book", "net"]); df.to_csv(OUT, index=False)
    df["is_tr"] = df.Date <= TRAIN_END

    def pf(s):
        s = np.asarray(s); gp = s[s > 0].sum(); gl = -s[s < 0].sum()
        return round(gp / gl, 2) if gl > 0 else 0

    def mdd(x):
        e = x.sort_values("Date").net.cumsum(); return float((e - e.cummax()).min())

    print(f"\nDONE {time.time()-t0:.0f}s")
    print(f"\nregime-label agreement (per RTH 5M bar, real vs 1-min proxy): "
          f"{lab_agree/max(lab_tot,1)*100:.2f}%  ({lab_agree:,}/{lab_tot:,} bars, {ndays:,} days)\n")
    col = {}
    for src in ("REAL", "PROXY"):
        e = df[df.src == src]
        trn, tst = e[e.is_tr], e[~e.is_tr]
        v = e.sort_values("Date").net.values
        dds = np.array([(lambda c: (c - np.maximum.accumulate(c)).min())(np.cumsum(rng.permutation(v))) for _ in range(3000)])
        wl = e[e.book == "WT-L"]; ws = e[e.book == "WT-S"]
        col[src] = {
            "trades (n)":        f"{len(e):,}",
            "net $":             f"{e.net.sum():+,.0f}",
            "$/trade":           f"{e.net.mean():+.1f}",
            "PF":                f"{pf(e.net):.2f}",
            "PF train (<=2023)": f"{pf(trn.net):.2f}",
            "PF test (2024+)":   f"{pf(tst.net):.2f}",
            "win %":             f"{100*(e.net>0).mean():.1f}",
            "maxDD $":           f"{mdd(e):+,.0f}",
            "MC worst-1% DD $":  f"{np.percentile(dds,1):+,.0f}",
            "2EL long net (PF)": f"{wl.net.sum():+,.0f} ({pf(wl.net)})",
            "2ES short net (PF)":f"{ws.net.sum():+,.0f} ({pf(ws.net)})",
        }
    metrics = list(col["REAL"].keys()); w0 = max(len(m) for m in metrics)
    print(f"{'metric':<{w0}}  {'REAL ticks':>16s}{'1-min PROXY':>16s}")
    print("-" * (w0 + 2 + 32))
    for mt in metrics:
        print(f"{mt:<{w0}}  {col['REAL'][mt]:>16s}{col['PROXY'][mt]:>16s}")
    print("\nPF by year:")
    print(df.pivot_table(index=df.Date.str[:4], columns="src", values="net", aggfunc=pf).reindex(columns=["REAL", "PROXY"]).to_string())
    print("\nnet by year:")
    print(df.pivot_table(index=df.Date.str[:4], columns="src", values="net", aggfunc="sum").reindex(columns=["REAL", "PROXY"]).round(0).to_string())

    fig, ax = plt.subplots(figsize=(12, 6), dpi=115)
    for src, c in (("REAL", "#2a78d6"), ("PROXY", "#e08a1e")):
        x = df[df.src == src].sort_values("Date")
        ax.plot(range(len(x)), x.net.cumsum().values, lw=2, color=c,
                label=f"{src}: {x.net.sum():+,.0f}$  PF {pf(x.net)}  n={len(x)}")
    ax.axhline(0, color="#c3c2b7", lw=1); ax.legend(frameon=False)
    ax.grid(axis="y", color="#eceeed", lw=0.7)
    for s_ in ("top", "right"): ax.spines[s_].set_visible(False)
    ax.set_title(f"Tick-proxy fidelity — WT 2E book: real ticks vs 1-min proxy "
                 f"(label agree {lab_agree/max(lab_tot,1)*100:.1f}%)", fontweight="bold")
    fig.tight_layout()
    p = WT / "docs" / "living" / "tickproxy_fidelity_20260725.png"
    fig.savefig(p, facecolor="white"); print("\nsaved", p)


if __name__ == "__main__":
    main()
