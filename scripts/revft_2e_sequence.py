"""RevFT -> 2E sequence edge. 2026-07-25 (S85).

Samir's hypothesis: a RevFT signal firing in NEUTRAL regime sometimes PRECEDES a trend change —
soon after we get a f2EL (FADE-S) or 2ES (WT-S) as price pushes through the EMA the other way.
Test whether a RevFT signal in the prior X bars is a CONFLUENCE signal for the 2E entry, and
whether the EMA cross between them marks it.

Data: bars _continuous (main), RevFT signals (Sneaky excl), 2E three-book entries
(combined_books_20260724.csv, excl dead FADE-L). RevFT regime via pt_new (from revft_regime_full).
Alignment: 2E `fill_bar` and RevFT signal bar `sb` are both indices into the same RTH-day bars g.

    python scripts/revft_2e_sequence.py
"""
import sys
from pathlib import Path
from bisect import bisect_right
import numpy as np, pandas as pd

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))
from revft_regime_full import pt_new, load_day, BARS, SIG   # noqa: E402
WT = Path(r"C:/Users/Admin/myquant-regime")
CB = WT / "data" / "regime" / "combined_books_20260724.csv"
XBARS = [6, 12, 24]           # look-back windows (bars) from the 2E entry
EMA_N = 20


def pf(v):
    v = np.asarray(v, float); gp = v[v > 0].sum(); gl = -v[v < 0].sum()
    return gp / gl if gl > 0 else float("inf")


def stat(v):
    v = np.asarray(v, float)
    if not len(v):
        return "n=0"
    return f"n={len(v):4d}  tot=${v.sum():>8,.0f}  $/tr={v.mean():6.1f}  PF={pf(v):4.2f}  win={100*(v>0).mean():4.1f}%"


def main():
    b = pd.read_parquet(BARS); b["Date"] = b["DateTime"].dt.date.astype(str)
    cb = pd.read_csv(CB); cb["Date"] = cb.Date.astype(str); cb = cb[cb.book != "FADE-L"]
    sig = pd.read_parquet(SIG); sig = sig[sig.SignalType != "Sneaky"].copy()
    sig["Date"] = sig["Date"].astype(str); sig["DateTime"] = pd.to_datetime(sig["DateTime"])

    recs = []          # one row per 2E entry, enriched with preceding-RevFT info
    fwd = []           # one row per RevFT signal: did a 2E follow within 24 bars?
    days = sorted(set(cb.Date) & set(sig.Date))
    for dstr in days:
        g, tP, tbar = load_day(b, dstr)
        if g is None:
            continue
        nB = len(g); gdt = g["DateTime"].values
        trans = pt_new(g["High"].values, g["Low"].values, nB, tP, tbar)
        tr_ix = [t for (t, _) in trans]; tr_md = [m for (_, m) in trans]
        ema = pd.Series(g["Close"].values).ewm(span=EMA_N, adjust=False).mean().values
        close = g["Close"].values
        # RevFT signals -> (sb, reg, dir)
        rsig = []
        for _, s in sig[sig.Date == dstr].iterrows():
            sb = int(np.searchsorted(gdt, np.datetime64(s.DateTime), "right") - 1)
            if sb < 1 or sb >= nB - 1:
                continue
            zt = int(np.searchsorted(tbar, sb, "right") - 1)
            reg = tr_md[bisect_right(tr_ix, zt) - 1] if zt >= 0 else "na"
            rsig.append((sb, reg, "L" if s.Direction == "Long" else "S"))
        rbars = np.array([r[0] for r in rsig]) if rsig else np.array([], int)

        # 2E entries this day
        de = cb[cb.Date == dstr]
        for _, e in de.iterrows():
            fb = int(e.fill_bar)
            if fb <= 0 or fb >= nB:
                continue
            for X in XBARS:
                prev = [r for r in rsig if fb - X <= r[0] <= fb]
                pre = len(prev) > 0
                pre_neu = any(r[1] == "NEUTRAL" for r in prev)
                # EMA cross between earliest preceding RevFT and the 2E entry
                emax = False
                if prev:
                    s0 = min(r[0] for r in prev)
                    seg_above = close[s0:fb+1] > ema[s0:fb+1]
                    emax = seg_above.any() and (~seg_above).any()   # crossed at least once
                recs.append(dict(Date=dstr, book=e.book, edir=e.dir, X=X, net=e.net,
                                 pre=pre, pre_neu=pre_neu, emax=emax))
        # forward: for each RevFT signal, did a 2E fill within 24 bars after?
        for (sb, reg, rdir) in rsig:
            nxt = de[(de.fill_bar > sb) & (de.fill_bar <= sb + 24)]
            fwd.append(dict(Date=dstr, sb=sb, reg=reg, rdir=rdir,
                            followed=len(nxt) > 0,
                            book=(nxt.iloc[0].book if len(nxt) else None),
                            net=(nxt.iloc[0].net if len(nxt) else np.nan),
                            gap=(int(nxt.iloc[0].fill_bar - sb) if len(nxt) else np.nan)))

    R = pd.DataFrame(recs); F = pd.DataFrame(fwd)
    R.to_parquet(ROOT / "data" / "regime" / "revft_2e_sequence_20260725.parquet", index=False)

    print("="*90); print("A. 2E entries — does a preceding RevFT signal change the 2E outcome? (confluence)"); print("="*90)
    for X in XBARS:
        r = R[R.X == X]
        print(f"\n within {X} bars:  (of {len(r)} 2E entries, {r.pre.mean()*100:.0f}% preceded by a RevFT, "
              f"{r.pre_neu.mean()*100:.0f}% by a NEUTRAL RevFT)")
        print(f"   preceded=YES      {stat(r[r.pre].net)}")
        print(f"   preceded=NO       {stat(r[~r.pre].net)}")
        print(f"   preceded-NEUTRAL  {stat(r[r.pre_neu].net)}")
        print(f"   preceded + EMAx   {stat(r[r.pre & r.emax].net)}")

    print("\n"+"="*90); print("B. by 2E book (X=12): the f2EL(FADE-S)/2ES(WT-S) short-trend-change idea"); print("="*90)
    r = R[R.X == 12]
    for bk in ("WT-S", "FADE-S", "WT-L"):
        rb = r[r.book == bk]
        print(f"\n {bk}:  all {stat(rb.net)}")
        print(f"   preceded by RevFT        {stat(rb[rb.pre].net)}")
        print(f"   preceded by NEUTRAL RevFT{stat(rb[rb.pre_neu].net)}")
        print(f"   preceded NEUTRAL + EMAx  {stat(rb[rb.pre_neu & rb.emax].net)}")

    print("\n"+"="*90); print("C. forward: after a RevFT signal, does a 2E follow within 24 bars? (by RevFT regime)"); print("="*90)
    for reg in ("NEUTRAL", "BULL", "BEAR"):
        fr = F[F.reg == reg]
        if not len(fr):
            continue
        rate = fr.followed.mean() * 100
        fol = fr[fr.followed]
        print(f"\n RevFT in {reg:8s} (n={len(fr)}):  2E follows within 24b {rate:.0f}%  "
              f"(median gap {fol.gap.median():.0f}b)")
        for bk in ("WT-S", "FADE-S", "WT-L"):
            fb = fol[fol.book == bk]
            if len(fb):
                print(f"     -> {bk:7s} {stat(fb.net)}")


if __name__ == "__main__":
    main()
