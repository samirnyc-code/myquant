"""Two sweeps in one tick pass — S83 '+10%' program continued.

A) GAP-DAY RESCUE: on the skipped days (|gap| > train-q3), the trend leaves without
   a pullback — test entry depth there: chase (stop-entry at trigger, 1t slip),
   retest 2t / 4t / 6t (strict through-fill). Stop 0.30xADR10, EOD, h09-13, WT.
B) LIMIT LIFETIME: on NORMAL days (|gap| <= q3), the retest6 limit currently lives
   to the window end. Cancel it N bars after the trigger bar: N in {1,2,3,6,12,ALL}.

Net of $5 RT + 1t exit slip. Train <=2023 / test 2024+.
Output: data/regime/gapday_cancel_20260724.csv + tables + PNG.
  python scripts/regime_2e_gapday_cancel.py [--limit N]
"""
import sys, gc, time
from pathlib import Path
from bisect import bisect_right
import numpy as np
import pandas as pd
import matplotlib; matplotlib.use("Agg")
import matplotlib.pyplot as plt

TICK = 0.25; PT = 50.0; COMM = 5.0; SLIP = 12.5
WT_ROOT = Path(__file__).resolve().parent.parent
DATA = Path(r"C:/Users/Admin/myquant/data")
sys.path.insert(0, str(WT_ROOT / "scripts"))
from regime_second_entry_study import phase_transitions, load_day   # noqa: E402
from regime_2e_causal_check import detect_entries_causal            # noqa: E402

OUT = WT_ROOT / "data" / "regime" / "gapday_cancel_20260724.csv"
GOOD_HOURS = {"09", "10", "11", "12", "13"}
TRAIN_END = "2023-12-31"
FLOOR = 8 * TICK
CANCELS = [1, 2, 3, 6, 12, 999]


def main():
    limit = None
    if "--limit" in sys.argv:
        limit = int(sys.argv[sys.argv.index("--limit") + 1])
    b = pd.read_parquet(DATA / "bars" / "_continuous.parquet")
    b["Date"] = b["DateTime"].dt.date.astype(str)
    dly = b.groupby("Date").agg(dO=("Open", "first"), dH=("High", "max"),
                                dL=("Low", "min"), dC=("Close", "last")).reset_index()
    dly["rng"] = dly.dH - dly.dL
    dly["adr10"] = dly.rng.rolling(10).mean().shift(1)
    dly["gap_abs"] = (dly.dO - dly.dC.shift(1)).abs() / dly.dC.shift(1) * 100
    q3 = dly[dly.Date <= TRAIN_END].gap_abs.quantile(0.75)
    print(f"train gap q3 = {q3:.3f}%")
    adr_map = dly.set_index("Date")["adr10"].to_dict()
    gap_map = dly.set_index("Date")["gap_abs"].to_dict()
    days = sorted(b["Date"].unique())
    if limit:
        days = days[:limit]

    rows = []; t0 = time.time()
    for di, dstr in enumerate(days):
        g, tP, tbar = load_day(b, dstr)
        if g is None:
            continue
        adr = adr_map.get(dstr, np.nan)
        gapv = gap_map.get(dstr, np.nan)
        if not np.isfinite(adr) or not np.isfinite(gapv):
            continue
        is_gap = gapv > q3
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
        sdist = max(round(0.30 * adr / TICK) * TICK, FLOOR)
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

            def book(jfl, fill):
                fb2 = int(tbar[jfl])
                hh_ = pd.Timestamp(g_dt[min(fb2, n - 1)]).strftime("%H")
                if hh_ not in GOOD_HOURS:
                    return None
                stop = fill + sdist if short else fill - sdist
                seg = tP[jfl:]
                js_ = np.nonzero(seg >= stop)[0] if short else np.nonzero(seg <= stop)[0]
                ex = stop if len(js_) else seg[-1]
                return ((fill - ex) if short else (ex - fill)) * PT - COMM - SLIP

            if is_gap:
                # chase: fill at trigger +1t adverse slip at the trigger tick
                fillc = trig - TICK if short else trig + TICK
                pnl = book(jf, fillc)
                if pnl is not None:
                    rows.append((dstr, "GAP", "chase", round(pnl, 1)))
                for rt in (2, 4, 6):
                    lim = trig + rt * TICK if short else trig - rt * TICK
                    seg0 = tP[jf:]
                    jl_ = np.nonzero(seg0 > lim)[0] if short else np.nonzero(seg0 < lim)[0]
                    if not len(jl_):
                        continue
                    pnl = book(jf + int(jl_[0]), lim)
                    if pnl is not None:
                        rows.append((dstr, "GAP", f"retest{rt}", round(pnl, 1)))
            else:
                lim = trig + 6 * TICK if short else trig - 6 * TICK
                seg0 = tP[jf:]
                jl_ = np.nonzero(seg0 > lim)[0] if short else np.nonzero(seg0 < lim)[0]
                if not len(jl_):
                    continue
                jfl = jf + int(jl_[0])
                fill_bar = int(tbar[jfl])
                for N in CANCELS:
                    if fill_bar - fb > N:
                        continue                     # limit already cancelled
                    pnl = book(jfl, lim)
                    if pnl is not None:
                        rows.append((dstr, "NRM", f"cxl{N}", round(pnl, 1)))
        del tP, tbar; gc.collect()
        if (di + 1) % 150 == 0:
            print(f"[{di+1}/{len(days)}] rows={len(rows)} ({time.time()-t0:.0f}s)", flush=True)

    df = pd.DataFrame(rows, columns=["Date", "scope", "variant", "net"])
    df.to_csv(OUT, index=False)
    df["is_tr"] = df.Date <= TRAIN_END

    def pf(s):
        gp = s[s > 0].sum(); gl = -s[s < 0].sum()
        return round(gp / gl, 2) if gl > 0 else float("inf")

    print(f"\nDONE {time.time()-t0:.0f}s rows={len(df)} -> {OUT}")
    for scope, label in (("GAP", "A) GAP DAYS (|gap|>q3) - entry depth"),
                         ("NRM", "B) NORMAL DAYS - retest6 limit lifetime (bars)")):
        print(f"\n== {label} ==")
        print("variant   n    $/tr   PF   win%  maxDD    train        | test")
        for v in sorted(df[df.scope == scope].variant.unique(),
                        key=lambda s: (len(s), s)):
            x = df[(df.scope == scope) & (df.variant == v)].sort_values("Date")
            eq = x.net.cumsum(); dd = (eq - eq.cummax()).min()
            trn, tst = x[x.is_tr], x[~x.is_tr]
            print(f"{v:8s} {len(x):4d} {x.net.mean():+7.1f} {pf(x.net):5.2f} "
                  f"{(x.net>0).mean()*100:5.1f} {dd:+9.0f}  "
                  f"{trn.net.sum():+8.0f}/{pf(trn.net):4.2f} | {tst.net.sum():+8.0f}/{pf(tst.net):4.2f}")

    fig, axes = plt.subplots(1, 2, figsize=(14, 5.5), dpi=115)
    for ax, scope, ttl in ((axes[0], "GAP", "Gap days: entry depth"),
                           (axes[1], "NRM", "Normal days: limit lifetime")):
        for v in sorted(df[df.scope == scope].variant.unique(), key=lambda s: (len(s), s)):
            x = df[(df.scope == scope) & (df.variant == v)].sort_values("Date")
            ax.plot(range(len(x)), x.net.cumsum().values, lw=1.6,
                    label=f"{v} ({x.net.sum():+,.0f}$)")
        ax.axhline(0, color="#c3c2b7", lw=1); ax.legend(frameon=False, fontsize=8.5)
        ax.grid(axis="y", color="#eceeed", lw=0.7); ax.set_title(ttl, fontweight="bold")
        for s_ in ("top", "right"): ax.spines[s_].set_visible(False)
    fig.tight_layout()
    p = WT_ROOT / "docs" / "living" / "gapday_cancel_20260724.png"
    fig.savefig(p, facecolor="white")
    print("saved", p)


if __name__ == "__main__":
    main()
