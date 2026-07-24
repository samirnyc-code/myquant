"""Regime x 2E on VOLUME BARS — S83. The audited stack on 6500-contract bars.

Bars built from the RTH tick cache (price + volume): a bar closes when cumulative
volume crosses the bar size. Machine + causal S61 2E + WT gate at trigger +
retest 4t THROUGH-fill + 4pt stop + EOD flat + fills h09-13 (fill TIME window —
bar counts don't apply to volume bars). Train <=2023 / test 2024+.

  python scripts/regime_2e_volbars.py [SIZE] [--limit N]     (default SIZE=6500)
Output: data/regime/volbars<SIZE>_2e_20260724.csv
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
from regime_second_entry_study import phase_transitions        # noqa: E402
from regime_2e_causal_check import detect_entries_causal        # noqa: E402

SIZE = int(sys.argv[1]) if len(sys.argv) > 1 and sys.argv[1].isdigit() else 6500
OUT = WT_ROOT / "data" / "regime" / f"volbars{SIZE}_2e_20260724.csv"
GOOD_HOURS = {"09", "10", "11", "12", "13"}
TRAIN_END = "2023-12-31"


def vol_bars(tk, size):
    """OHLC volume bars + per-tick bar index."""
    v = tk["Volume"].values.astype(np.int64)
    cs = np.cumsum(v)
    bar_ix = (cs - v) // size
    p = tk["Price"].values
    dt = tk["DateTime"].values
    df = pd.DataFrame({"b": bar_ix, "p": p, "dt": dt})
    g = df.groupby("b", sort=True)
    bars = pd.DataFrame({
        "DateTime": g["dt"].first(),
        "Open": g["p"].first(), "High": g["p"].max(),
        "Low": g["p"].min(), "Close": g["p"].last()}).reset_index(drop=True)
    return bars, bar_ix.astype(np.int64)


def main():
    limit = None
    if "--limit" in sys.argv:
        limit = int(sys.argv[sys.argv.index("--limit") + 1])
    b5 = pd.read_parquet(DATA / "bars" / "_continuous.parquet")
    b5["Date"] = b5["DateTime"].dt.date.astype(str)
    days = sorted(b5["Date"].unique())
    if limit:
        days = days[:limit]

    rows = []; t0 = time.time(); nd = 0; nbars = []
    for di, dstr in enumerate(days):
        p = DATA / "ticks_continuous" / f"{dstr}.parquet"
        if not p.exists():
            continue
        tk = pd.read_parquet(p).sort_values("DateTime")
        if len(tk) < 1000:
            continue
        g, tbar = vol_bars(tk, SIZE)
        n = len(g)
        if n < 30:
            continue
        nbars.append(n)
        tP = tk["Price"].values
        H, L = g["High"].values, g["Low"].values
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
            stop = fill + 16 * TICK if short else fill - 16 * TICK
            seg = tP[jfl:]
            js_ = np.nonzero(seg >= stop)[0] if short else np.nonzero(seg <= stop)[0]
            ex = stop if len(js_) else seg[-1]
            pnl = (fill - ex) if short else (ex - fill)
            rows.append((dstr, dr, round(pnl * PT - COMM, 1)))
        nd += 1
        del tk, tP, tbar; gc.collect()
        if (di + 1) % 150 == 0:
            print(f"[{di+1}/{len(days)}] rows={len(rows)} ({time.time()-t0:.0f}s)", flush=True)

    df = pd.DataFrame(rows, columns=["Date", "dir", "net"])
    df.to_csv(OUT, index=False)
    df["is_tr"] = df.Date <= TRAIN_END

    def pf(s):
        gp = s[s > 0].sum(); gl = -s[s < 0].sum()
        return gp / gl if gl > 0 else float("inf")

    print(f"\nDONE {time.time()-t0:.0f}s days={nd} bars/day~{int(np.median(nbars))} rows={len(df)} -> {OUT}")
    for scope, m in (("ALL", pd.Series(True, df.index)), ("L", df["dir"] == "L"),
                     ("S", df["dir"] == "S")):
        x = df[m]; trn = x[x.is_tr]; tst = x[~x.is_tr]
        if not len(x):
            continue
        print(f"{scope:3s}  n={len(x):5d}  train {trn.net.sum():+9,.0f} PF {pf(trn.net):5.2f}  |  "
              f"test {tst.net.sum():+9,.0f} PF {pf(tst.net):5.2f}")


if __name__ == "__main__":
    main()
