"""RevFT x regime — ENTRY-OFFSET sweep + gap/hour ablation. 2026-07-25 (S85, follow-up to 0015)

Note 0015 used a native next-tick entry. The S83 2E book instead rests a LIMIT k ticks back from
the trigger and cancels after M bars. Here we sweep k (not fixed at 6) and ablate the 2E day/time
filters, on the two headline gates (drop-CT and neg-gamma & drop-CT), wide-vol+EOD exit.

Fill model: after the signal bar sb closes, rest a limit at SignalPrice -/+ k ticks (buy below /
sell above). Fill = first tick in bars sb+1..sb+M that touches it (fill AT the limit; touched=filled,
no queue). Then exit from the fill tick: stop 0.30xADR (never moved), hold to session close (EOD flat).
k=0 = limit at SignalPrice. Native (market next-tick) figures are in the 0015 parquet for reference.

    python scripts/revft_regime_entry.py [--limit N]
Output: data/regime/revft_regime_entry_20260725.parquet + printed tables.
"""
import sys
from pathlib import Path
from bisect import bisect_right
import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))
from revft_regime_full import (pt_new, load_day, TICK, PT, COMM, SLIP, FLOOR, GOOD,  # noqa: E402
                               GAP_MAX, BARS, SIG, MQ)

OFFS = [0, 2, 4, 6, 8, 12, 16]     # ticks back for the resting limit
MBARS = 6                          # cancel unfilled after M bars (2E default)
OUT = ROOT / "data" / "regime" / "revft_regime_entry_20260725.parquet"


def main():
    limit = int(sys.argv[sys.argv.index("--limit") + 1]) if "--limit" in sys.argv else None
    b = pd.read_parquet(BARS); b["Date"] = b["DateTime"].dt.date.astype(str)
    dly = b.groupby("Date").agg(dO=("Open", "first"), dC=("Close", "last"),
                                dH=("High", "max"), dL=("Low", "min")).reset_index()
    dly["adr10"] = (dly.dH - dly.dL).rolling(10).mean().shift(1)
    dly["gap"] = ((dly.dO - dly.dC.shift(1)) / dly.dC.shift(1) * 100).abs()
    gm = dly.set_index("Date")[["adr10", "gap"]]
    mq = pd.read_csv(MQ)[["date", "regime"]]; mq["date"] = mq["date"].astype(str)
    mqmap = mq.set_index("date")["regime"]

    sig = pd.read_parquet(SIG); sig = sig[sig.SignalType != "Sneaky"].copy()
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
        trans = pt_new(H, Lo, nB, tP, tbar)
        tr_ix = [t for (t, _) in trans]; tr_md = [m for (_, m) in trans]
        gdt = g["DateTime"].values
        wide = max(round(0.30 * adr / TICK) * TICK, FLOOR)
        mqreg = str(mqmap.loc[dstr]) if dstr in mqmap.index else "na"
        for _, s in sig[sig.Date == dstr].iterrows():
            sb = np.searchsorted(gdt, np.datetime64(s.DateTime), "right") - 1
            if sb < 1 or sb >= nB - 1:
                continue
            zt = np.searchsorted(tbar, sb, "right") - 1
            if zt < 0:
                continue
            reg = tr_md[bisect_right(tr_ix, zt) - 1]
            long = (s.Direction == "Long")
            sp = float(s.SignalPrice); stopx = float(s.StopPrice)
            # tick window for the resting limit: bars sb+1 .. sb+MBARS
            a = np.searchsorted(tbar, sb + 1, "left")
            zwin = np.searchsorted(tbar, sb + 1 + MBARS, "left")
            if a >= len(tP):
                continue
            win = tP[a:zwin]
            base = dict(Date=dstr, year=int(dstr[:4]), dir=("L" if long else "S"),
                        reg=reg, mq=mqreg, hour=pd.Timestamp(gdt[sb + 1]).strftime("%H"),
                        gap=round(float(gapv), 3))
            for k in OFFS:
                lp = sp - k * TICK if long else sp + k * TICK
                # first touch of the limit within the window
                hit = np.nonzero(win <= lp)[0] if long else np.nonzero(win >= lp)[0]
                if not len(hit):
                    rows.append({**base, "k": k, "filled": 0, "weod": np.nan, "R": np.nan})
                    continue
                fi = a + int(hit[0]); entry = lp
                R = (entry - stopx) if long else (stopx - entry)
                if R <= 0:                      # limit sits at/through the extreme
                    rows.append({**base, "k": k, "filled": 0, "weod": np.nan, "R": np.nan})
                    continue
                seg = tP[fi:]
                st = entry - wide if long else entry + wide
                sh = np.nonzero(seg <= st)[0] if long else np.nonzero(seg >= st)[0]
                ex = st if len(sh) else seg[-1]
                pnl = round(((ex - entry) if long else (entry - ex)) * PT - COMM - SLIP, 1)
                rows.append({**base, "k": k, "filled": 1, "weod": pnl, "R": round(R, 2)})
        if (di + 1) % 200 == 0:
            print(f"[{di+1}/{len(days)}] rows={len(rows)}", flush=True)

    t = pd.DataFrame(rows)
    t.to_parquet(OUT, index=False)
    print(f"\nsaved {OUT}  ({t.Date.nunique()} days)\n")
    report(t)


def stat(df):
    f = df[df.filled == 1]
    v = f.weod.values
    if len(v) == 0:
        return "n=0"
    gp = v[v > 0].sum(); gl = -v[v < 0].sum(); pf = gp / gl if gl > 0 else float("inf")
    fillrate = f.shape[0] / df.shape[0] * 100
    return f"fill={fillrate:4.0f}%  n={len(v):5d}  tot=${v.sum():>9,.0f}  $/tr={v.mean():>6.1f}  PF={pf:4.2f}  win={100*(v>0).mean():4.1f}%"


def report(t):
    L, S = t.dir == "L", t.dir == "S"
    bull, bear, neu = t.reg == "BULL", t.reg == "BEAR", t.reg == "NEUTRAL"
    WT = (L & bull) | (S & bear); notCT = WT | neu
    neg = t.mq == "negative_gamma"
    tr = t.Date <= "2023-12-31"

    print("="*96); print("ENTRY-OFFSET SWEEP (wide-vol+EOD exit, cancel after 6 bars)  —  DROP-CT gate"); print("="*96)
    print("k=ticks back from SignalPrice for the resting limit (k=0 = at SignalPrice; native next-tick in 0015):")
    for k in OFFS:
        m = notCT & (t.k == k)
        print(f"  k={k:2d}t   {stat(t[m])}")
    print("\nsame, NEG-gamma & DROP-CT gate:")
    for k in OFFS:
        m = neg & notCT & (t.k == k)
        print(f"  k={k:2d}t   {stat(t[m])}")

    print("\n"+"="*96); print("TRAIN/HOLDOUT + YEAR for the best-looking k on each gate"); print("="*96)
    for gate_name, gate in (("DROP-CT", notCT), ("NEG&DROP-CT", neg & notCT)):
        # pick k with best $/tr among filled, min 150 fills
        best = None
        for k in OFFS:
            f = t[gate & (t.k == k) & (t.filled == 1)]
            if len(f) >= 150 and (best is None or f.weod.mean() > best[1]):
                best = (k, f.weod.mean())
        if best is None:
            continue
        k = best[0]; m = gate & (t.k == k)
        print(f"\n{gate_name}  best k={k}t:")
        print(f"  ALL     {stat(t[m])}")
        print(f"  train   {stat(t[m & tr])}")
        print(f"  holdout {stat(t[m & ~tr])}")
        f = t[m & (t.filled == 1)]
        yl = "  yr " + " ".join(f"{y}:{f[f.year==y].weod.sum():>7,.0f}" for y in sorted(f.year.unique()))
        print(yl)

    print("\n"+"="*96); print("GAP / HOUR ablation (DROP-CT gate, wide+EOD; native-entry k=0 for comparability)"); print("="*96)
    base = notCT & (t.k == 6)      # use k=6 (2E default) as the ablation base
    variants = [
        ("k=6 all", base),
        ("k=6 + gap-skip(|gap|<=0.54)", base & (t.gap <= GAP_MAX)),
        ("k=6 + hours 09-13", base & (t.hour.isin(GOOD))),
        ("k=6 + gap-skip + hours", base & (t.gap <= GAP_MAX) & (t.hour.isin(GOOD))),
    ]
    for name, m in variants:
        print(f"  {name:34s} {stat(t[m])}")
    print("\nsame ablation on NEG&DROP-CT:")
    base2 = neg & notCT & (t.k == 6)
    for name, extra in (("all", base2), ("+gap-skip", base2 & (t.gap <= GAP_MAX)),
                        ("+hours", base2 & (t.hour.isin(GOOD))),
                        ("+gap+hours", base2 & (t.gap <= GAP_MAX) & (t.hour.isin(GOOD)))):
        print(f"  {name:34s} {stat(t[extra])}")


if __name__ == "__main__":
    main()
