"""Do the f2EL FADE-S trades work better after a STRONG move THROUGH the EMA? 2026-07-25 (S85).

Samir's idea: only take the fades when a strong move through the 20-EMA precedes them (a forceful
bear thrust that broke the EMA, then a failed counter-trend long we fade). Price-action filter, NOT
the RevFT-conditioning that failed in 0015c.

PRIMARY feature (pre-committed to avoid over-search): `cross_str` = strength of the most recent
DOWNSIDE EMA cross in the prior K bars, in ATR14 units = (swing-high before the down-cross − swing-low
after it) / ATR, within [fb-K, fb). Secondary: `pen_atr` = deepest close-below-EMA in the window /ATR.
Both are strictly causal (bars before the fade fill_bar fb).

Test bed: FADE-S entries from combined_books_20260724 (near-final; that fade is ~breakeven, so this
asks whether the EMA filter RESCUES it). Rigor: threshold sweep + permutation-null (is the filtered
subset better than a random same-size subset?) + train/holdout + year. Same bar RevFT Book B cleared.

    python scripts/revft_fade_ema.py
"""
import sys
from pathlib import Path
import numpy as np, pandas as pd

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))
from revft_regime_full import load_day, BARS         # noqa: E402
WT = Path(r"C:/Users/Admin/myquant-regime")
CB = WT / "data" / "regime" / "combined_books_20260724.csv"
OUT = ROOT / "data" / "regime" / "revft_fade_ema_20260725.parquet"
K = 10; EMA_N = 20; ATR_N = 14
TRAIN_END = "2023-12-31"
RNG = np.random.default_rng(20260725)


def pf(v):
    v = np.asarray(v, float); gp = v[v > 0].sum(); gl = -v[v < 0].sum()
    return gp / gl if gl > 0 else float("inf")


def g(v):
    v = np.asarray(v, float)
    if not len(v):
        return "n=0"
    return f"n={len(v):4d} ${v.sum():>8,.0f} ${v.mean():6.1f}/tr PF={pf(v):4.2f} win={100*(v>0).mean():4.1f}%"


def perm_p(net, mask, nperm=4000):
    """is the filtered subset's mean better than a random same-size subset? p=P(null>=obs)."""
    mask = mask.astype(bool).values; net = net.values; k = mask.sum()
    if k < 10 or k >= len(net):
        return np.nan
    obs = net[mask].mean()
    idx = np.arange(len(net))
    null = np.array([net[RNG.permutation(idx)[:k]].mean() for _ in range(nperm)])
    return (null >= obs).mean()


def cross_features(ema, high, low, close, fb):
    """causal EMA-through strength in bars [fb-K, fb)."""
    a = max(1, fb - K); w = slice(a, fb)
    e, h, l, c = ema[w], high[w], low[w], close[w]
    if len(c) < 3:
        return 0.0, 0.0, False
    atr = np.mean(h - l) if len(h) else 1.0
    atr = atr if atr > 0 else 1.0
    above = c > e
    # most recent downside cross: above then below
    cross_str = 0.0; crossed = False
    for i in range(1, len(c)):
        if above[i-1] and not above[i]:              # down-cross
            crossed = True
            hi = h[:i+1].max(); lo = l[i:].min()
            cross_str = max(cross_str, (hi - lo) / atr)
    pen_atr = float(np.max((e - l) / atr)) if len(l) else 0.0   # deepest poke below EMA
    return float(cross_str), pen_atr, crossed


def main():
    b = pd.read_parquet(BARS); b["Date"] = b["DateTime"].dt.date.astype(str)
    cb = pd.read_csv(CB); cb["Date"] = cb.Date.astype(str)
    fade = cb[cb.book == "FADE-S"].copy()
    rows = []
    for dstr, de in fade.groupby("Date"):
        g_, tP, tbar = load_day(b, dstr)
        if g_ is None:
            continue
        H, Lo, C = g_["High"].values, g_["Low"].values, g_["Close"].values
        ema = pd.Series(C).ewm(span=EMA_N, adjust=False).mean().values
        for _, e in de.iterrows():
            fb = int(e.fill_bar)
            if fb < 3 or fb >= len(g_):
                continue
            cs, pen, crossed = cross_features(ema, H, Lo, C, fb)
            rows.append(dict(Date=dstr, year=int(dstr[:4]), net=float(e.net),
                             cross_str=cs, pen_atr=pen, crossed=crossed))
    t = pd.DataFrame(rows); t.to_parquet(OUT, index=False)
    print(f"FADE-S entries with EMA features: {len(t)}   base {g(t.net)}\n")

    tr = t.Date <= TRAIN_END
    print("="*88); print("PRIMARY: cross_str (strength of down-move through EMA, ATR units), K=10"); print("="*88)
    print(f"  distribution: median {t.cross_str.median():.2f}  p75 {t.cross_str.quantile(.75):.2f}  p90 {t.cross_str.quantile(.9):.2f}  crossed={t.crossed.mean()*100:.0f}%")
    print(f"\n  by tercile of cross_str:")
    q = t.cross_str.quantile([1/3, 2/3]).values
    for lab, m in (("weak (low)", t.cross_str <= q[0]),
                   ("mid", (t.cross_str > q[0]) & (t.cross_str <= q[1])),
                   ("STRONG (high)", t.cross_str > q[1])):
        print(f"    {lab:14s} {g(t[m].net)}")
    print(f"\n  FILTER cross_str >= threshold (sweep) + permutation-null p + train/holdout:")
    for thr in (0.5, 1.0, 1.5, 2.0, 2.5, 3.0):
        m = t.cross_str >= thr
        if m.sum() < 10:
            continue
        p = perm_p(t.net, m)
        print(f"    >={thr:.1f}: {g(t[m].net)}  perm-p={p:.3f}  | train {g(t[m & tr].net)} | holdout {g(t[m & ~tr].net)}  {'<== sig' if p<0.05 else ''}")

    print("\n"+"="*88); print("SECONDARY: pen_atr (deepest close/low below EMA in prior K bars, ATR units)"); print("="*88)
    q = t.pen_atr.quantile([1/3, 2/3]).values
    for lab, m in (("shallow", t.pen_atr <= q[0]), ("mid", (t.pen_atr > q[0]) & (t.pen_atr <= q[1])),
                   ("DEEP thrust", t.pen_atr > q[1])):
        print(f"    {lab:14s} {g(t[m].net)}")
    for thr in (0.5, 1.0, 1.5, 2.0):
        m = t.pen_atr >= thr
        if m.sum() < 10:
            continue
        p = perm_p(t.net, m)
        print(f"    pen>={thr:.1f}: {g(t[m].net)}  perm-p={p:.3f} | train {g(t[m & tr].net)} | holdout {g(t[m & ~tr].net)}  {'<== sig' if p<0.05 else ''}")

    print("\n"+"="*88); print("YEAR-BY-YEAR of the best-looking strong-EMA fade filter"); print("="*88)
    # pick the cross_str threshold with best $/tr among perm-p<0.10 & n>=30, else best $/tr n>=30
    best = None
    for thr in (0.5, 1.0, 1.5, 2.0, 2.5, 3.0):
        m = t.cross_str >= thr
        if m.sum() >= 30:
            mu = t[m].net.mean(); p = perm_p(t.net, m)
            if best is None or mu > best[1]:
                best = (thr, mu, p, m)
    if best:
        thr, mu, p, m = best
        print(f"  cross_str>={thr}: {g(t[m].net)}  perm-p={p:.3f}")
        for y in sorted(t.year.unique()):
            print(f"    {y}: {g(t[m & (t.year==y)].net)}")
    print("\n(NOTE: threshold was swept -> the best cell's perm-p is optimistic; demand it hold OOS + a")
    print(" coherent tercile gradient, not just one lucky cutoff.)")


if __name__ == "__main__":
    main()
