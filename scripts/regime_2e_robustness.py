"""P6 ROBUSTNESS of the S83 headline stack (WT 2E + retest + fixed stop + EOD + TOD).

Perturbs every parameter one at a time around the headline configuration and
re-sims on ticks. If the edge is real it should degrade GRACEFULLY, not vanish.

  retest depth : 2t / 4t* / 6t / 8t
  stop         : 3pt / 4pt* / 5pt / 6pt / sb1
  window       : 09-12 / 09-13* / 10-13 / all
  filter       : WT* / WT+ER / WT+mchan-ER (autopsy survivor overlay)
  (* = headline)

Also: per-year net, running max drawdown (closed-trade equity), long/short split
for the headline config. Train/test columns throughout (split 2023-12-31).

Output: data/regime/robustness_20260723.csv + stdout.
  python scripts/regime_2e_robustness.py [--limit N]
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

OUT = WT_ROOT / "data" / "regime" / "robustness_20260723.csv"
TRAIN_END = "2023-12-31"
RETESTS = [2, 4, 6, 8]                      # ticks back from trigger
STOPS = [12, 16, 20, 24, None]              # ticks from fill; None = sb1


def main():
    limit = None
    if "--limit" in sys.argv:
        limit = int(sys.argv[sys.argv.index("--limit") + 1])
    b = pd.read_parquet(DATA / "bars" / "_continuous.parquet")
    b["Date"] = b["DateTime"].dt.date.astype(str)
    days = sorted(b["Date"].unique())
    if limit:
        days = days[:limit]

    ft = pd.read_csv(WT_ROOT / "data" / "regime" / "second_entries_features_20260723.csv")
    ft = ft[ft["count"] == 2].set_index("entry_id")[["er10"]]
    au = pd.read_csv(WT_ROOT / "data" / "regime" / "autopsy_features_20260723.csv")
    au = au.set_index("entry_id")[["mchan"]]

    rows = []
    t0 = time.time()
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
            regime = tr_md[bisect_right(tr_ix, jf) - 1]
            wtok = (regime == "BEAR") if short else (regime == "BULL")
            if not wtok:
                continue                       # all variants here are with-trend
            eid = f"{dstr}_{fb+1}{dr}2"
            for rt in RETESTS:
                lim = trig + rt * TICK if short else trig - rt * TICK
                seg0 = tP[jf:]
                jl_ = np.nonzero(seg0 >= lim)[0] if short else np.nonzero(seg0 <= lim)[0]
                if not len(jl_):
                    continue
                jfl = jf + int(jl_[0])
                fill = lim
                fill_bar = int(tbar[jfl])
                hh = pd.Timestamp(g_dt[min(fill_bar, n - 1)]).strftime("%H")
                seg = tP[jfl:]
                for st in STOPS:
                    stop = (H[sb] + TICK if short else L[sb] - TICK) if st is None else \
                        (fill + st * TICK if short else fill - st * TICK)
                    R = (stop - fill) if short else (fill - stop)
                    if R <= 0:
                        continue
                    js_ = np.nonzero(seg >= stop)[0] if short else np.nonzero(seg <= stop)[0]
                    ex = stop if len(js_) else seg[-1]           # EOD hold
                    pnl = (fill - ex) if short else (ex - fill)
                    rows.append((eid, dstr, dr, hh, rt,
                                 "sb1" if st is None else f"{st//4}p",
                                 pnl * PT - COMM))
        del tP, tbar; gc.collect()
        if (di + 1) % 150 == 0:
            print(f"[{di+1}/{len(days)}] rows={len(rows)} ({time.time()-t0:.0f}s)", flush=True)

    df = pd.DataFrame(rows, columns=["entry_id", "Date", "dir", "hh", "retest", "stop", "net"])
    df = df.join(ft, on="entry_id").join(au, on="entry_id")
    df.to_csv(OUT.with_suffix(".trades.csv"), index=False)
    df["is_tr"] = df.Date <= TRAIN_END

    def pf(s):
        gp = s[s > 0].sum(); gl = -s[s < 0].sum()
        return gp / gl if gl > 0 else float("inf")

    WINDOWS = {"h09-12": {"09", "10", "11", "12"}, "h09-13": {"09", "10", "11", "12", "13"},
               "h10-13": {"10", "11", "12", "13"}, "all": None}
    er_med = df[df.is_tr].er10.median()
    mch_q3 = df[df.is_tr].mchan.quantile(0.75)
    FILTS = {"WT": pd.Series(True, df.index),
             "WT+ER": df.er10 >= er_med,
             "WT+mchanER": (df.er10 >= er_med) & (df.mchan >= mch_q3)}
    out = []
    for wname, wset in WINDOWS.items():
        wmask = df.hh.isin(wset) if wset else pd.Series(True, df.index)
        for fname, fmask in FILTS.items():
            for rt in RETESTS:
                for stp in df["stop"].unique():
                    x = df[wmask & fmask & (df.retest == rt) & (df["stop"] == stp)]
                    trn = x[x.is_tr]; tst = x[~x.is_tr]
                    if len(trn) < 100 or len(tst) < 60:
                        continue
                    out.append((wname, fname, rt, stp, len(trn), round(trn.net.sum()),
                                round(pf(trn.net), 3), len(tst), round(tst.net.sum()),
                                round(pf(tst.net), 3)))
    res = pd.DataFrame(out, columns=["window", "filter", "retest", "stop", "n_tr",
                                     "net_tr", "PF_tr", "n_te", "net_te", "PF_te"])
    res.to_csv(OUT, index=False)
    print("\n== headline neighborhood (WT, EOD hold) ==")
    print(res[res["filter"] == "WT"].to_string(index=False))
    print("\n== filter overlays ==")
    print(res[res["filter"] != "WT"].to_string(index=False))
    green = res[(res.PF_tr > 1) & (res.PF_te > 1)]
    print(f"\ngreen-in-both: {len(green)}/{len(res)} cells")

    # headline detail: per-year, DD, long/short
    h = df[(df.retest == 4) & (df["stop"] == "4p") & df.hh.isin(WINDOWS["h09-13"])].copy()
    h = h.sort_values(["Date", "entry_id"])
    h["yr"] = h.Date.str[:4]
    print("\n== HEADLINE (WT | h09-13 | retest4 | 4p | EOD) per-year ==")
    print(h.groupby("yr").net.agg(n="size", net="sum",
                                  pf=lambda s: round(pf(s), 2)).to_string())
    eq = h.net.cumsum()
    dd = (eq - eq.cummax()).min()
    print(f"\ntotal net ${h.net.sum():,.0f}  trades {len(h)}  "
          f"max closed-trade DD ${dd:,.0f}")
    print("\nby dir:")
    print(h.groupby("dir").net.agg(n="size", net="sum",
                                   pf=lambda s: round(pf(s), 2)).to_string())


if __name__ == "__main__":
    main()
