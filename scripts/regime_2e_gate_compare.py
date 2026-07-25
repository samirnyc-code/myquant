"""GATE COMPARISON — the same with-trend 2E book (2EL long + 2ES short) run through
three different regime gates, identical entries/stops/gap/retest/EOD otherwise:

  1. PHASE  — validated tick phase-machine regime (the baseline, pt_old), with-trend.
  2. NONE   — no regime gate at all: take every qualifying 2EL and 2ES fill.
  3. EMA20  — regime = price vs 20-EMA of 5M closes (causal: prior-bar EMA at fill),
              with-trend (long only above EMA20, short only below).

One tick pass per day computes all three gates on the SAME entries so the only
difference is the gate. WT sleeve only (fade is inherently regime-defined -> excluded).

  python scripts/regime_2e_gate_compare.py [--limit N]
Output: data/regime/gate_compare_20260725.csv + tables + PNG.
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

OUT = WT / "data" / "regime" / "gate_compare_20260725.csv"
GOOD = {"09", "10", "11", "12", "13"}
FLOOR = 8 * TICK
TRAIN_END = "2023-12-31"
GATES = ("PHASE", "NONE", "EMA20")
rng = np.random.default_rng(83)


def run_wt(g, tP, tbar, adr):
    """Return list of (gate, book, net) for the with-trend book under each gate."""
    O, H, L, C = (g[c].values for c in ["Open", "High", "Low", "Close"])
    n = len(g)
    trans = pt_old(H, L, n, tP, tbar)
    tr_ix = [t for (t, _) in trans]; tr_md = [m for (_, m) in trans]
    ema20 = pd.Series(C).ewm(span=20, adjust=False).mean().values
    entries = detect_entries_causal(g, tP, tbar)
    g_dt = g["DateTime"].values
    wide = max(round(0.30 * adr / TICK) * TICK, FLOOR)
    out = []
    for (fb, sb, dr, cnt, trig) in entries:
        if cnt != 2:
            continue
        short = dr == "S"
        want = "BEAR" if short else "BULL"
        a = np.searchsorted(tbar, fb, "left"); z = np.searchsorted(tbar, fb, "right")
        hit = np.nonzero(tP[a:z] <= trig)[0] if short else np.nonzero(tP[a:z] >= trig)[0]
        if not len(hit):
            continue
        jf = a + int(hit[0])
        # retest limit fill
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
        # regime label at fill under each gate
        reg_phase = tr_md[bisect_right(tr_ix, jf) - 1]
        ema_prev = ema20[max(fb2 - 1, 0)]
        reg_ema = "BULL" if lim > ema_prev else "BEAR"
        gate_reg = {"PHASE": reg_phase, "NONE": want, "EMA20": reg_ema}
        # trade PnL is identical across gates that pass (same entry/stop/exit)
        stop = lim + wide if short else lim - wide; seg = tP[jfl:]
        js = np.nonzero(seg >= stop)[0] if short else np.nonzero(seg <= stop)[0]
        ex = stop if len(js) else seg[-1]
        net = round(((lim - ex) if short else (ex - lim)) * PT - COMM - SLIP, 1)
        bk = "WT-S" if short else "WT-L"
        for gt in GATES:
            if gate_reg[gt] == want:
                out.append((gt, bk, net))
    return out


def main():
    limit = None
    if "--limit" in sys.argv:
        limit = int(sys.argv[sys.argv.index("--limit") + 1])
    b = pd.read_parquet(DATA / "bars" / "_continuous.parquet"); b["Date"] = b["DateTime"].dt.date.astype(str)
    dly = b.groupby("Date").agg(dO=("Open", "first"), dC=("Close", "last"), dH=("High", "max"), dL=("Low", "min")).reset_index()
    dly["adr10"] = (dly.dH - dly.dL).rolling(10).mean().shift(1)
    dly["gap"] = ((dly.dO - dly.dC.shift(1)) / dly.dC.shift(1) * 100).abs()
    gm = dly.set_index("Date")[["adr10", "gap"]]
    days = sorted(b["Date"].unique())
    if limit:
        days = days[:limit]
    rows = []; t0 = time.time()
    for di, dstr in enumerate(days):
        if dstr not in gm.index:
            continue
        adr, gapv = gm.loc[dstr, "adr10"], gm.loc[dstr, "gap"]
        if not np.isfinite(adr) or gapv > 0.54:
            continue
        g, tP, tbar = load_day(b, dstr)
        if g is None:
            continue
        try:
            for (gt, bk, net) in run_wt(g, tP, tbar, adr):
                rows.append((dstr, gt, bk, net))
        except Exception as e:
            print(dstr, "ERR", repr(e), flush=True)
        del tP, tbar; gc.collect()
        if (di + 1) % 150 == 0:
            print(f"[{di+1}/{len(days)}] rows={len(rows)} ({time.time()-t0:.0f}s)", flush=True)
    df = pd.DataFrame(rows, columns=["Date", "gate", "book", "net"]); df.to_csv(OUT, index=False)
    df["is_tr"] = df.Date <= TRAIN_END

    def pf(s):
        s = np.asarray(s); gp = s[s > 0].sum(); gl = -s[s < 0].sum()
        return round(gp / gl, 2) if gl > 0 else 0

    def mdd(x):
        e = x.sort_values("Date").net.cumsum(); return float((e - e.cummax()).min())

    print(f"\nDONE {time.time()-t0:.0f}s\n")
    # 3-column table: one column per gate, metrics as rows
    col = {}
    for gt in GATES:
        e = df[df.gate == gt]
        trn, tst = e[e.is_tr], e[~e.is_tr]
        v = e.sort_values("Date").net.values
        dds = np.array([(lambda c: (c - np.maximum.accumulate(c)).min())(np.cumsum(rng.permutation(v))) for _ in range(3000)])
        wl = e[e.book == "WT-L"]; ws = e[e.book == "WT-S"]
        wins = e.net[e.net > 0]; loss = e.net[e.net < 0]
        col[gt] = {
            "trades (n)":        f"{len(e):,}",
            "net $":             f"{e.net.sum():+,.0f}",
            "$/trade":           f"{e.net.mean():+.1f}",
            "PF":                f"{pf(e.net):.2f}",
            "PF train (<=2023)": f"{pf(trn.net):.2f}",
            "PF test (2024+)":   f"{pf(tst.net):.2f}",
            "win %":             f"{100*(e.net>0).mean():.1f}",
            "avg win $":         f"{wins.mean():+,.0f}" if len(wins) else "-",
            "avg loss $":        f"{loss.mean():+,.0f}" if len(loss) else "-",
            "payoff (W/L)":      f"{(wins.mean()/-loss.mean()):.2f}" if len(loss) and len(wins) else "-",
            "maxDD $":           f"{mdd(e):+,.0f}",
            "MC worst-1% DD $":  f"{np.percentile(dds,1):+,.0f}",
            "net/maxDD":         f"{e.net.sum()/-mdd(e):.2f}" if mdd(e) < 0 else "-",
            "2EL long net (PF)": f"{wl.net.sum():+,.0f} ({pf(wl.net)})",
            "2ES short net (PF)":f"{ws.net.sum():+,.0f} ({pf(ws.net)})",
        }
    metrics = list(col[GATES[0]].keys())
    w0 = max(len(m) for m in metrics)
    print(f"{'metric':<{w0}}  " + "".join(f"{gt:>14s}" for gt in GATES))
    print("-" * (w0 + 2 + 14 * len(GATES)))
    for m in metrics:
        print(f"{m:<{w0}}  " + "".join(f"{col[gt][m]:>14s}" for gt in GATES))
    print("\nPF by year:")
    py = df.pivot_table(index=df.Date.str[:4], columns="gate", values="net", aggfunc=pf)
    ny = df.pivot_table(index=df.Date.str[:4], columns="gate", values="net", aggfunc="count")
    print(py.reindex(columns=list(GATES)).to_string())
    print("\ntrade count by year:")
    print(ny.reindex(columns=list(GATES)).to_string())

    fig, ax = plt.subplots(figsize=(12, 6), dpi=115)
    for gt, c in (("PHASE", "#2a78d6"), ("NONE", "#c0392b"), ("EMA20", "#27a35a")):
        x = df[df.gate == gt].sort_values("Date")
        ax.plot(range(len(x)), x.net.cumsum().values, lw=2, color=c,
                label=f"{gt}: {x.net.sum():+,.0f}$  PF {pf(x.net)}  n={len(x)}")
    ax.axhline(0, color="#c3c2b7", lw=1); ax.legend(frameon=False)
    ax.grid(axis="y", color="#eceeed", lw=0.7)
    for s_ in ("top", "right"): ax.spines[s_].set_visible(False)
    ax.set_title("2E with-trend book — regime gate comparison: PHASE vs NONE vs EMA20",
                 fontweight="bold")
    fig.tight_layout()
    p = WT / "docs" / "living" / "gate_compare_20260725.png"
    fig.savefig(p, facecolor="white"); print("\nsaved", p)


if __name__ == "__main__":
    main()
