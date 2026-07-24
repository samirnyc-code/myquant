"""GAP-DAY ALTERNATIVE SIGNALS — S83. What CAN be traded on the skipped days?

GAP DAY (exact definition): |RTH open(08:30 bar Open) - prior RTH close| / prior
RTH close * 100  >  0.540%  (= 75th percentile of the TRAIN years 2021-2023,
fit once, applied to all years).

On those days only, tests (all: fills h09-13, EOD flat, $5 RT + 1t exit slip, 1 ES):
  1E-WT      : our FIRST entries, with-trend, chase and retest6 variants
  RevFT      : MyReversals export (Sneaky/Trap), enter first tick after signal
               time +1t slip, by direction and type
  MC         : MyMicroChannel export (CC*), same treatment
  stops      : native (export's own stop distance, offset-invariant) and 0.30xADR10

Output: data/regime/gapday_alt_signals_20260724.csv + tables.
  python scripts/gapday_alt_signals.py [--limit N]
"""
import re, sys, gc, time
from datetime import datetime
from pathlib import Path
from bisect import bisect_right
import numpy as np
import pandas as pd

TICK = 0.25; PT = 50.0; COMM = 5.0; SLIP = 12.5
WT_ROOT = Path(__file__).resolve().parent.parent
DATA = Path(r"C:/Users/Admin/myquant/data")
sys.path.insert(0, str(WT_ROOT / "scripts"))
from regime_second_entry_study import phase_transitions, load_day   # noqa: E402
from regime_2e_causal_check import detect_entries_causal            # noqa: E402

OUT = WT_ROOT / "data" / "regime" / "gapday_alt_signals_20260724.csv"
GOOD_HOURS = {"09", "10", "11", "12", "13"}
TRAIN_END = "2023-12-31"
GAP_Q3 = 0.540
FLOOR = 8 * TICK
SIG_REV = DATA / "signals" / "MyReversals Signal Export - ES SEP26 - 5 Minute from 02.07.2026 - 1850 Days.txt"
SIG_MC = DATA / "signals" / "MyMicroChannel Signal Export - ES SEP26 - 5 Minute from 02.07.2026 - 1850 Days.txt"


def parse_signals(path):
    rows = []
    with open(path, encoding="utf-8", errors="ignore") as fh:
        for line in fh:
            line = line.rstrip()
            if not line or line.startswith("-") or not line[0].isdigit():
                continue
            line = re.sub(r"(\d),(\d)", r"\1\2", line)
            parts = line.split()
            if len(parts) < 8:
                continue
            try:
                rows.append(dict(
                    SignalType=parts[1], Direction=parts[2],
                    DateTime=datetime.strptime(f"{parts[3]} {parts[4]}", "%d/%m/%Y %H:%M:%S"),
                    StopDist=abs(float(parts[6]) - float(parts[7]))))
            except (ValueError, IndexError):
                continue
    df = pd.DataFrame(rows)
    df["Date"] = pd.to_datetime(df.DateTime).dt.date.astype(str)
    return df.sort_values("DateTime").reset_index(drop=True)


def main():
    limit = None
    if "--limit" in sys.argv:
        limit = int(sys.argv[sys.argv.index("--limit") + 1])
    b = pd.read_parquet(DATA / "bars" / "_continuous.parquet")
    b["Date"] = b["DateTime"].dt.date.astype(str)
    dly = b.groupby("Date").agg(dO=("Open", "first"), dC=("Close", "last"),
                                dH=("High", "max"), dL=("Low", "min")).reset_index()
    dly["rng"] = dly.dH - dly.dL
    dly["adr10"] = dly.rng.rolling(10).mean().shift(1)
    dly["gap_pct"] = (dly.dO - dly.dC.shift(1)) / dly.dC.shift(1) * 100
    dly["is_gap"] = dly.gap_pct.abs() > GAP_Q3
    gap_days = set(dly[dly.is_gap].Date)
    adr_map = dly.set_index("Date")["adr10"].to_dict()
    print(f"gap days: {len(gap_days)} of {len(dly)} "
          f"(up {int((dly[dly.is_gap].gap_pct>0).sum())} / down {int((dly[dly.is_gap].gap_pct<0).sum())})")

    rev = parse_signals(SIG_REV); mc = parse_signals(SIG_MC)
    rev_by_day = {d_: g_ for d_, g_ in rev.groupby("Date")}
    mc_by_day = {d_: g_ for d_, g_ in mc.groupby("Date")}

    days = sorted(gap_days)
    if limit:
        days = days[:limit]
    rows = []; t0 = time.time()
    for di, dstr in enumerate(days):
        g, tP, tbar = load_day(b, dstr)
        if g is None:
            continue
        adr = adr_map.get(dstr, np.nan)
        if not np.isfinite(adr):
            continue
        O, H, L, C = (g[c].values for c in ["Open", "High", "Low", "Close"])
        n = len(g)
        g_dt = g["DateTime"].values
        tk_dt = None
        sdistA = max(round(0.30 * adr / TICK) * TICK, FLOOR)
        try:
            transitions = phase_transitions(H, L, n, tP, tbar)
            entries = detect_entries_causal(g, tP, tbar)
        except Exception as e:
            print(dstr, "ERR", repr(e), flush=True)
            continue
        tr_ix = [t for (t, _) in transitions]; tr_md = [m for (_, m) in transitions]

        def book_from(j0, fill, short, sdist):
            fb2 = int(tbar[min(j0, len(tbar) - 1)])
            hh_ = pd.Timestamp(g_dt[min(fb2, n - 1)]).strftime("%H")
            if hh_ not in GOOD_HOURS:
                return None
            stop = fill + sdist if short else fill - sdist
            seg = tP[j0:]
            js_ = np.nonzero(seg >= stop)[0] if short else np.nonzero(seg <= stop)[0]
            ex = stop if len(js_) else seg[-1]
            return ((fill - ex) if short else (ex - fill)) * PT - COMM - SLIP

        # ---- our 1E with-trend ----
        for (fb, sb, dr, cnt, trig) in entries:
            if cnt != 1:
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
            pnl = book_from(jf, trig - TICK if short else trig + TICK, short, sdistA)
            if pnl is not None:
                rows.append((dstr, "1E-WT", "chase", dr, round(pnl, 1)))
            lim = trig + 6 * TICK if short else trig - 6 * TICK
            seg0 = tP[jf:]
            jl_ = np.nonzero(seg0 > lim)[0] if short else np.nonzero(seg0 < lim)[0]
            if len(jl_) and int(tbar[jf + int(jl_[0])]) - fb <= 6:
                pnl = book_from(jf + int(jl_[0]), lim, short, sdistA)
                if pnl is not None:
                    rows.append((dstr, "1E-WT", "retest6", dr, round(pnl, 1)))

        # ---- external signal exports (RevFT / MC) ----
        if tk_dt is None:
            tk_dt = g_dt  # bar starts; signal DateTime = bar close; enter next tick after
        for src, sigs in (("RevFT", rev_by_day.get(dstr)), ("MC", mc_by_day.get(dstr))):
            if sigs is None:
                continue
            tk_times = None
            for t_ in sigs.itertuples():
                short = t_.Direction.lower().startswith("s")
                st = np.datetime64(t_.DateTime)
                if tk_times is None:
                    tk_times = pd.read_parquet(
                        DATA / "ticks_continuous" / f"{dstr}.parquet")["DateTime"].values
                j0 = int(np.searchsorted(tk_times, st, side="left"))
                if j0 >= len(tP) - 10:
                    continue
                fill = tP[j0] - TICK if short else tP[j0] + TICK
                nat = max(round(t_.StopDist / TICK) * TICK, FLOOR)
                for smode, sdist in (("natstop", nat), ("adrstop", sdistA)):
                    pnl = book_from(j0, fill, short, sdist)
                    if pnl is not None:
                        rows.append((dstr, f"{src}:{t_.SignalType}", smode, dr_lab(short),
                                     round(pnl, 1)))
        del tP, tbar; gc.collect()
        if (di + 1) % 60 == 0:
            print(f"[{di+1}/{len(days)}] rows={len(rows)} ({time.time()-t0:.0f}s)", flush=True)

    df = pd.DataFrame(rows, columns=["Date", "signal", "variant", "dir", "net"])
    df.to_csv(OUT, index=False)
    df["is_tr"] = df.Date <= TRAIN_END

    def pf(s):
        gp = s[s > 0].sum(); gl = -s[s < 0].sum()
        return round(gp / gl, 2) if gl > 0 else float("inf")

    print(f"\nDONE {time.time()-t0:.0f}s rows={len(df)} -> {OUT}")
    print("\nsignal            variant   dir  n    $/tr   PF    train        | test")
    for (sig, var, dr), x in sorted(df.groupby(["signal", "variant", "dir"]),
                                    key=lambda kv: -len(kv[1])):
        if len(x) < 30:
            continue
        trn, tst = x[x.is_tr], x[~x.is_tr]
        print(f"{sig:16s} {var:8s} {dr:3s} {len(x):4d} {x.net.mean():+7.1f} {pf(x.net):5.2f} "
              f"{trn.net.sum():+8.0f}/{pf(trn.net):4.2f} | {tst.net.sum():+8.0f}/{pf(tst.net):4.2f}")
    print("\n-- aggregates (all types) --")
    for key, x in df.assign(src=df.signal.str.split(':').str[0]).groupby(["src", "variant", "dir"]):
        if len(x) < 40:
            continue
        trn, tst = x[x.is_tr], x[~x.is_tr]
        print(f"{key[0]:8s} {key[1]:8s} {key[2]:3s} {len(x):4d} {x.net.mean():+7.1f} {pf(x.net):5.2f} "
              f"{trn.net.sum():+8.0f}/{pf(trn.net):4.2f} | {tst.net.sum():+8.0f}/{pf(tst.net):4.2f}")


def dr_lab(short):
    return "S" if short else "L"


if __name__ == "__main__":
    main()
