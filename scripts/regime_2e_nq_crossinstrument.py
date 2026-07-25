"""STRESS #10 (cross-instrument, no Databento) — run the core WT book on NQ.
Builds a front-month-continuous NQ 5-min series (per day = the contract with max
volume), then runs the EXACT with-trend three-book WT engine (2EL BULL + 2ES BEAR,
S61 2nd entry, retest 6t limit, 0.30xADR stop floor 8t, gap<=0.54%, 09-13, EOD hold)
with NQ economics. Fade excluded (its 4pt stop is ES-structural, not scale-invariant).
Question: does the regime x 2E edge REPLICATE on NQ, or was it ES-curve-fit?

  python scripts/regime_2e_nq_crossinstrument.py
"""
import sys, gc, time
from pathlib import Path
from bisect import bisect_right
import numpy as np, pandas as pd
sys.path.insert(0, str(Path(__file__).resolve().parent))
import regime_second_entry_study as R                                    # noqa: E402
# CRITICAL: point load_day at the NQ tick dir (else it reads ES ticks vs NQ bars -> garbage)
R.TICKD = Path(r"C:/Users/Admin/myquant/data/ticks_continuous_NQ")
from regime_second_entry_study import phase_transitions, load_day       # noqa: E402
from regime_2e_causal_check import detect_entries_causal                # noqa: E402

TICK = 0.25; PT = 20.0; COMM = 5.0; SLIP = 0.25 * PT     # NQ: $20/pt, 1-tick slip = $5
WT = Path(__file__).resolve().parent.parent
NQTICKS = Path(r"C:/Users/Admin/myquant/data/ticks_continuous_NQ")
NQBARS = WT / "data" / "regime" / "_nq_bars_5m.parquet"
GOOD = {"09", "10", "11", "12", "13"}; FLOOR = 8 * TICK; TRAIN_END = "2023-12-31"
SCALED = "--scaled" in sys.argv   # scale retest depth to %-of-ADR (fair cross-instrument)


def build_nq_bars():
    if NQBARS.exists():
        return pd.read_parquet(NQBARS)
    frames = []
    for f in sorted(NQTICKS.glob("*.parquet")):
        tk = pd.read_parquet(f)[["DateTime", "Price", "Volume"]].set_index("DateTime")
        o = tk.Price.resample("5min").ohlc().dropna()
        o["Volume"] = tk.Volume.resample("5min").sum()
        o = o.reset_index().rename(columns={"open": "Open", "high": "High", "low": "Low", "close": "Close"})
        o["Date"] = f.stem
        frames.append(o[["DateTime", "Open", "High", "Low", "Close", "Volume", "Date"]])
    b = pd.concat(frames, ignore_index=True)
    b.to_parquet(NQBARS)
    return b


def pf(s):
    s = np.asarray(s, float); gp = s[s > 0].sum(); gl = -s[s < 0].sum(); return round(gp/gl, 2) if gl else 0
def mdd(v):
    e = np.cumsum(np.asarray(v, float)); return float((e - np.maximum.accumulate(e)).min())


def main():
    t0 = time.time()
    global PT, SLIP
    ES = "--es" in sys.argv
    global_scaled = None                    # control: reproduce ES WT via the SAME harness
    if ES:
        PT = 50.0; SLIP = 0.25 * PT            # ES: 1-tick slip = $12.5
        R.TICKD = Path(r"C:/Users/Admin/myquant/data/ticks_continuous")
        b = pd.read_parquet(Path(r"C:/Users/Admin/myquant/data/bars/_continuous.parquet"))
        b["Date"] = b.DateTime.dt.date.astype(str)
        print(f"ES CONTROL: {len(b)} bars ({time.time()-t0:.0f}s)  [SLIP note: uses NQ slip const, tiny diff]")
    else:
        b = build_nq_bars()
        print(f"NQ 5m bars (from NQ ticks): {len(b)} bars, {b.Date.nunique()} days {b.Date.min()}..{b.Date.max()} "
              f"({time.time()-t0:.0f}s)")
    dly = b.groupby("Date").agg(dO=("Open", "first"), dC=("Close", "last"), dH=("High", "max"), dL=("Low", "min")).reset_index()
    dly["adr10"] = (dly.dH - dly.dL).rolling(10).mean().shift(1)
    dly["gap"] = ((dly.dO - dly.dC.shift(1)) / dly.dC.shift(1) * 100).abs()
    gmap = dly.set_index("Date")[["adr10", "gap"]]
    days = sorted(b.Date.unique())

    rows = []
    for di, dstr in enumerate(days):
        if dstr not in gmap.index:
            continue
        adr, gapv = gmap.loc[dstr, "adr10"], gmap.loc[dstr, "gap"]
        if not np.isfinite(adr) or gapv > 0.54:
            continue
        g, tP, tbar = load_day(b, dstr)
        if g is None:
            continue
        H, L = g["High"].values, g["Low"].values; n = len(g); g_dt = g["DateTime"].values
        try:
            trans = phase_transitions(H, L, n, tP, tbar); entries = detect_entries_causal(g, tP, tbar)
        except Exception:
            continue
        tr_ix = [t for (t, _) in trans]; tr_md = [m for (_, m) in trans]
        sd = max(round(0.30 * adr / TICK) * TICK, FLOOR)
        # retest depth: 6t on ES = 2.64% of ES median ADR (56.8pt). --scaled makes it that
        # fraction of THIS day's ADR (fair cross-instrument geometry); else literal 6 ticks.
        rt = max(round(0.0264 * adr / TICK) * TICK, TICK) if SCALED else 6 * TICK
        for (fb, sb, dr, cnt, trig) in entries:
            if cnt != 2:
                continue
            short = dr == "S"
            a = np.searchsorted(tbar, fb, "left"); z = np.searchsorted(tbar, fb, "right")
            s = tP[a:z]; hit = np.nonzero(s <= trig)[0] if short else np.nonzero(s >= trig)[0]
            if not len(hit):
                continue
            jf = a + int(hit[0]); reg = tr_md[bisect_right(tr_ix, jf) - 1]
            want = "BEAR" if short else "BULL"
            if reg != want:                       # WT only (with-trend)
                continue
            lim = trig + rt if short else trig - rt
            seg0 = tP[jf:]
            jl = np.nonzero(seg0 > lim)[0] if short else np.nonzero(seg0 < lim)[0]
            if not len(jl):
                continue
            jfl = jf + int(jl[0])
            if int(tbar[jfl]) - fb > 6:
                continue
            hh = pd.Timestamp(g_dt[min(int(tbar[jfl]), n-1)]).strftime("%H")
            if hh not in GOOD:
                continue
            fill = lim; stop = fill + sd if short else fill - sd; seg = tP[jfl:]
            js = np.nonzero(seg >= stop)[0] if short else np.nonzero(seg <= stop)[0]
            ex = stop if len(js) else seg[-1]
            rows.append((dstr, "S" if short else "L", round(((fill-ex) if short else (ex-fill))*PT-COMM-SLIP, 1)))
        del tP, tbar; gc.collect()
        if (di+1) % 300 == 0:
            print(f"[{di+1}/{len(days)}] trades={len(rows)} ({time.time()-t0:.0f}s)", flush=True)

    d = pd.DataFrame(rows, columns=["Date", "dir", "net"]); d["yr"] = d.Date.str[:4]; d["tr"] = d.Date <= TRAIN_END
    d.to_csv(WT / "data" / "regime" / "nq_wt_20260725.csv", index=False)
    print(f"\nDONE {time.time()-t0:.0f}s  NQ WT trades={len(d)}")
    print(f"NQ WT: net ${d.net.sum():+,.0f}  PF {pf(d.net)}  $/tr {d.net.mean():+.0f}  maxDD ${mdd(d.net):+,.0f}  "
          f"train {pf(d[d.tr].net)} / test {pf(d[~d.tr].net)}")
    print(f"  longs  n={len(d[d.dir=='L'])} PF {pf(d[d.dir=='L'].net)}   shorts n={len(d[d.dir=='S'])} PF {pf(d[d.dir=='S'].net)}")
    print("per-year:")
    for y in sorted(d.yr.unique()):
        x = d[d.yr == y]; print(f"  {y}: n={len(x):3d}  net ${x.net.sum():+8,.0f}  PF {pf(x.net)}")
    print("\nES WT reference (same book, from config): PF ~1.45, green every year. Compare above.")


if __name__ == "__main__":
    main()
