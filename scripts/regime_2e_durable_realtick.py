"""DURABLE on REAL NT TICKS (2021-26) — confirm the durable improvement is not a 1-min-proxy
artifact. Runs the actual tick engine (real ticks_continuous) over the modern era and compares:

  FROZEN symmetric : longs+shorts with-trend, 0.30xADR stop  (should reproduce ~+$86.8k gate_compare)
  DURABLE          : longs with-trend 0.40xADR (all) + shorts with-trend 0.30xADR ONLY below 50d SMA

Same entries/gap/retest/window/EOD. If DURABLE > FROZEN on REAL ticks as it is on the Databento
proxy, the short-gate improvement is real (it is a daily-regime filter, fill-fidelity-independent).

  python scripts/regime_2e_durable_realtick.py [--limit N]
Output: data/regime/durable_realtick_20260725.csv + table.
"""
import sys, gc, time
from pathlib import Path
from bisect import bisect_right
import numpy as np
import pandas as pd

TICK = 0.25; PT = 50.0; COMM = 5.0; SLIP = 12.5; FLOOR = 8 * TICK
WT = Path(__file__).resolve().parent.parent
DATA = Path(r"C:/Users/Admin/myquant/data")
sys.path.insert(0, str(WT / "scripts"))
from regime_second_entry_study import phase_transitions as pt_old, load_day   # noqa: E402
from regime_2e_causal_check import detect_entries_causal                      # noqa: E402

OUT = WT / "data" / "regime" / "durable_realtick_20260725.csv"
GOOD = {"09", "10", "11", "12", "13"}


def run_day(g, tP, tbar, adr, below50):
    O, H, L, C = (g[c].values for c in ["Open", "High", "Low", "Close"])
    n = len(g)
    trans = pt_old(H, L, n, tP, tbar)
    tr_ix = [t for (t, _) in trans]; tr_md = [m for (_, m) in trans]
    entries = detect_entries_causal(g, tP, tbar)
    g_dt = g["DateTime"].values
    out = []
    for (fb, sb, dr, cnt, trig) in entries:
        if cnt != 2:
            continue
        short = dr == "S"; want = "BEAR" if short else "BULL"
        a = np.searchsorted(tbar, fb, "left"); z = np.searchsorted(tbar, fb, "right")
        hit = np.nonzero(tP[a:z] <= trig)[0] if short else np.nonzero(tP[a:z] >= trig)[0]
        if not len(hit):
            continue
        jf = a + int(hit[0]); reg = tr_md[bisect_right(tr_ix, jf) - 1]
        if reg != want:
            continue
        lim = trig + 6 * TICK if short else trig - 6 * TICK; s0 = tP[jf:]
        jl = np.nonzero(s0 > lim)[0] if short else np.nonzero(s0 < lim)[0]
        if not len(jl):
            continue
        jfl = jf + int(jl[0]); fb2 = int(tbar[jfl])
        if fb2 - fb > 6 or pd.Timestamp(g_dt[min(fb2, n - 1)]).strftime("%H") not in GOOD:
            continue
        seg = tP[jfl:]
        # FROZEN: 0.30 both. DURABLE40: long 0.40 + gated short. DURABLE30: long 0.30 + gated short.
        for (label, mult, keep) in (("FROZEN", 0.30, True),
                                    ("DURABLE40", 0.40 if not short else 0.30,
                                     (not short) or below50),
                                    ("DURABLE30", 0.30, (not short) or below50)):
            if not keep:
                continue
            wide = max(round(mult * adr / TICK) * TICK, FLOOR)
            stop = lim + wide if short else lim - wide
            js = np.nonzero(seg >= stop)[0] if short else np.nonzero(seg <= stop)[0]
            ex = stop if len(js) else seg[-1]
            net = round(((lim - ex) if short else (ex - lim)) * PT - COMM - SLIP, 1)
            out.append((label, "WT-S" if short else "WT-L", net))
    return out


def main():
    limit = None
    if "--limit" in sys.argv:
        limit = int(sys.argv[sys.argv.index("--limit") + 1])
    b = pd.read_parquet(DATA / "bars" / "_continuous.parquet"); b["Date"] = b["DateTime"].dt.date.astype(str)
    dly = b.groupby("Date").agg(dO=("Open", "first"), dC=("Close", "last"), dH=("High", "max"), dL=("Low", "min")).reset_index().sort_values("Date")
    dly["adr10"] = (dly.dH - dly.dL).rolling(10).mean().shift(1)
    dly["gap"] = ((dly.dO - dly.dC.shift(1)) / dly.dC.shift(1) * 100).abs()
    dly["sma50"] = dly.dC.rolling(50).mean()
    dly["below50"] = (dly.dC < dly.sma50).shift(1)   # causal prior-day
    gm = dly.set_index("Date")[["adr10", "gap", "below50"]]
    days = sorted(b["Date"].unique())
    if limit:
        days = days[:limit]
    rows = []; t0 = time.time()
    for di, dstr in enumerate(days):
        if dstr not in gm.index:
            continue
        adr, gapv, bel = gm.loc[dstr, "adr10"], gm.loc[dstr, "gap"], gm.loc[dstr, "below50"]
        if not np.isfinite(adr) or gapv > 0.54:
            continue
        g, tP, tbar = load_day(b, dstr)
        if g is None:
            continue
        try:
            for (lab, bk, net) in run_day(g, tP, tbar, adr, bool(bel) if pd.notna(bel) else False):
                rows.append((dstr, lab, bk, net))
        except Exception as e:
            print(dstr, "ERR", repr(e), flush=True)
        del tP, tbar; gc.collect()
        if (di + 1) % 300 == 0:
            print(f"[{di+1}/{len(days)}] rows={len(rows)} ({time.time()-t0:.0f}s)", flush=True)
    df = pd.DataFrame(rows, columns=["Date", "spec", "book", "net"]); df.to_csv(OUT, index=False)

    def pf(s):
        s = np.asarray(s, float); gp = s[s > 0].sum(); gl = -s[s < 0].sum()
        return round(gp / gl, 2) if gl > 0 else 0.0

    def mdd(x):
        e = x.sort_values("Date").net.cumsum(); return float((e - e.cummax()).min())

    print(f"\nDONE {time.time()-t0:.0f}s  (REAL NT ticks, {df.Date.min()}..{df.Date.max()})\n")
    for spec in ("FROZEN", "DURABLE40", "DURABLE30"):
        e = df[df.spec == spec]
        print(f"{spec:<9} n={len(e):5d}  net {e.net.sum():+9,.0f}  PF {pf(e.net):4.2f}  "
              f"win {100*(e.net>0).mean():4.1f}%  maxDD {mdd(e):+8,.0f}  net/DD {e.net.sum()/-mdd(e):4.2f}  "
              f"L {pf(e[e.book=='WT-L'].net)}/S {pf(e[e.book=='WT-S'].net)}")
    print("\n(compare to Databento-proxy 2021+: FROZEN post +$90.4k/1.38, DURABLE post +$68.5k/1.44 "
          "— note proxy 'FROZEN' used 0.30 both; real-tick FROZEN here should ~match gate_compare +$86.8k)")


if __name__ == "__main__":
    main()
