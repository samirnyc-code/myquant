"""Can the PRECEDING-RevFT confluence improve the 2E book? Per-book, with the 0015b treatment.
2026-07-25 (S85). Reads data/regime/revft_2e_sequence_20260725.parquet (one row per 2E entry x X).

Question (Samir): benefit from a RevFT firing shortly before a 2E entry — whole book, or only 1-2 of
the 3 setups (WT-L=2EL, WT-S=2ES, FADE-S=f2EL)? For each book x window: preceded vs not, the LIFT,
a permutation-null on the lift (is 'preceded' informative or a lucky subset?), train/holdout, year,
EMA-cross refinement, and the FILTER/SIZER $ impact.

    python scripts/revft_2e_confluence.py
"""
from pathlib import Path
import numpy as np, pandas as pd

ROOT = Path(__file__).resolve().parent.parent
SEQ = ROOT / "data" / "regime" / "revft_2e_sequence_20260725.parquet"
TRAIN_END = "2023-12-31"
RNG = np.random.default_rng(20260725)


def pf(v):
    v = np.asarray(v, float); gp = v[v > 0].sum(); gl = -v[v < 0].sum()
    return gp / gl if gl > 0 else float("inf")


def g(v):
    v = np.asarray(v, float)
    return f"n={len(v):4d} ${v.sum():>8,.0f} ${v.mean():6.1f}/tr PF={pf(v):4.2f} win={100*(v>0).mean():4.1f}%"


def perm_lift_p(net, pre, nperm=4000):
    """observed lift = mean(pre) - mean(~pre); null permutes pre labels. p = P(null>=obs)."""
    pre = pre.astype(bool).values; net = net.values
    npre = pre.sum()
    if npre < 10 or (~pre).sum() < 10:
        return np.nan, np.nan
    obs = net[pre].mean() - net[~pre].mean()
    null = np.empty(nperm)
    idx = np.arange(len(net))
    for i in range(nperm):
        p = RNG.permutation(idx)[:npre]
        m = np.zeros(len(net), bool); m[p] = True
        null[i] = net[m].mean() - net[~m].mean()
    return obs, (null >= obs).mean()


def main():
    R = pd.read_parquet(SEQ)
    R["year"] = R.Date.str[:4].astype(int)
    print(f"{R[R.X==12].shape[0]} 2E entries; books {R[R.X==12].book.value_counts().to_dict()}\n")

    for X in (6, 12, 24):
        print("="*94); print(f"WINDOW X={X} bars"); print("="*94)
        r = R[R.X == X]
        # pooled
        obs, p = perm_lift_p(r.net, r.pre)
        print(f"POOLED (all books): pre {g(r[r.pre].net)}")
        print(f"                    not {g(r[~r.pre].net)}")
        print(f"    lift=${obs:+.1f}/tr  perm-null p(lift>=obs)={p:.4f}  {'*** informative' if p<0.05 else 'ns'}")
        for bk in ("WT-S", "FADE-S", "WT-L"):
            rb = r[r.book == bk]
            obs, p = perm_lift_p(rb.net, rb.pre)
            tag = "*** informative" if (p is not None and p < 0.05) else ("ns" if not np.isnan(p) else "small")
            print(f"\n  {bk}:")
            print(f"    preceded    {g(rb[rb.pre].net)}")
            print(f"    NOT prec    {g(rb[~rb.pre].net)}")
            print(f"    lift=${obs:+.1f}/tr   perm-null p={p:.4f}  {tag}")

    print("\n"+"="*94); print("PER-BOOK DETAIL at X=12 — train/holdout + year + EMA refine + FILTER/SIZER $"); print("="*94)
    r = R[R.X == 12]; tr = r.Date <= TRAIN_END
    for bk in ("FADE-S", "WT-L", "WT-S"):
        rb = r[r.book == bk]; pre = rb.pre
        print(f"\n### {bk}  (book all: {g(rb.net)})")
        print(f"  preceded train {g(rb[pre & (rb.Date<=TRAIN_END)].net)}")
        print(f"  preceded holdo {g(rb[pre & (rb.Date>TRAIN_END)].net)}")
        yl = "  lift by yr: " + " ".join(
            f"{y}:${rb[(rb.year==y)&pre].net.mean()-rb[(rb.year==y)&~pre].net.mean():+.0f}"
            for y in sorted(rb.year.unique())
            if (rb[(rb.year==y)&pre].shape[0] and rb[(rb.year==y)&~pre].shape[0]))
        print(yl)
        print(f"  preceded + EMAx {g(rb[pre & rb.emax].net)}   preceded no-EMAx {g(rb[pre & ~rb.emax].net)}")
        # FILTER: only preceded.  SIZER: 2x preceded + 1x not.
        allnet = rb.net.sum(); filt = rb[pre].net.sum()
        sizer = 2*rb[pre].net.sum() + rb[~pre].net.sum()
        drop_unpre = rb[pre].net.sum()   # = filter
        print(f"  $ impact:  take-all ${allnet:,.0f}   FILTER(only preceded) ${filt:,.0f}   "
              f"SIZER(2x pre +1x not) ${sizer:,.0f}")

    print("\n"+"="*94); print("BOOK-SELECTIVE STRATEGIES (X=12) — apply confluence only where it helps"); print("="*94)
    r = R[R.X == 12]
    def book_net(mask): return r[mask].net.sum()
    base = r.net.sum()
    # S1: filter FADE-S to preceded-only, keep WT-L/WT-S as-is
    s1 = book_net((r.book=="FADE-S")&r.pre) + book_net(r.book.isin(["WT-L","WT-S"]))
    # S2: filter FADE-S + WT-L to preceded, WT-S as-is
    s2 = book_net(r.book.isin(["FADE-S","WT-L"])&r.pre) + book_net(r.book=="WT-S")
    # S3: drop WT-S preceded (confluence hurts it) — keep WT-S not-preceded only, others all
    s3 = book_net((r.book=="WT-S")&~r.pre) + book_net(r.book.isin(["WT-L","FADE-S"]))
    # S4: FADE-S preceded-only + WT-S not-preceded-only + WT-L all
    s4 = book_net((r.book=="FADE-S")&r.pre) + book_net((r.book=="WT-S")&~r.pre) + book_net(r.book=="WT-L")
    print(f"  BASE take-all three books:                              ${base:,.0f}  PF {pf(r.net):.2f}")
    print(f"  S1 FADE-S->preceded-only, WT-L/WT-S all:                ${s1:,.0f}")
    print(f"  S2 FADE-S&WT-L->preceded-only, WT-S all:                ${s2:,.0f}")
    print(f"  S3 WT-S->not-preceded-only, WT-L/FADE-S all:            ${s3:,.0f}")
    print(f"  S4 FADE-S=preceded, WT-S=not-preceded, WT-L=all:        ${s4:,.0f}")
    # PF of S4
    s4mask = ((r.book=="FADE-S")&r.pre) | ((r.book=="WT-S")&~r.pre) | (r.book=="WT-L")
    print(f"     S4 detail: {g(r[s4mask].net)}")


if __name__ == "__main__":
    main()
