"""f2EL fade x EMA cross — RECENCY-AWARE feature (fixes the stale-cross flaw). 2026-07-25 (S85).

Samir's correction: on a 5M, a strong cross 15-20 bars ago is meaningless if price already crossed
BACK the other way. The 0015d `cross_str` took the MAX-strength cross anywhere in a K-bar window, so
large K tagged fades with stale/already-reversed crosses -> the K-sweep 'inversion' was a bad-feature
artifact, not proof the idea is noise.

FIX: anchor on the MOST-RECENT downside 20-EMA cross that is STILL INTACT at the fade (price has not
crossed back above the EMA since). Features: recency = bars from that cross to the fade; strength =
(swing-high just before the cross - lowest low from the cross to the fade) / ATR of the episode.
'stale/none' = current state is above the EMA, or the last cross was an up-cross. Then test net by
recency x strength — recency is the axis, as it should be.

Reads the frozen-fade parquet (Date, fill_bar, net) + bars; no engine re-run.
    python scripts/revft_fade_ema_recency.py
"""
from pathlib import Path
import numpy as np, pandas as pd

ROOT = Path(__file__).resolve().parent.parent
BARS = ROOT / "data" / "bars" / "_continuous.parquet"
FADE = ROOT / "data" / "regime" / "revft_fade_ema_frozen_20260725.parquet"
OUT = ROOT / "data" / "regime" / "revft_fade_ema_recency_20260725.parquet"
EMA_N = 20; MAXBACK = 25; TRAIN_END = "2023-12-31"
RNG = np.random.default_rng(20260725)


def pf(v):
    v = np.asarray(v, float); gp = v[v > 0].sum(); gl = -v[v < 0].sum()
    return gp / gl if gl > 0 else float("inf")


def g(v):
    v = np.asarray(v, float)
    if not len(v):
        return "n=0"
    return f"n={len(v):4d} ${v.sum():>8,.0f} ${v.mean():6.1f}/tr PF={pf(v):4.2f} win={100*(v>0).mean():4.1f}%"


def recent_downcross(ema, H, L, C, fb):
    """Most-recent STILL-INTACT downside cross before fb. Returns (recency, strength) or (None,None)
    if price is above the EMA at fb (no valid down-state) or the last cross was up."""
    if fb < 2 or C[fb-1] >= ema[fb-1]:
        return None, None                       # not below EMA -> no intact down-state
    xc = None
    for i in range(fb-1, max(1, fb-MAXBACK)-1, -1):
        up_prev = C[i-1] >= ema[i-1]
        if up_prev and C[i] < ema[i]:           # down-cross at i (above -> below)
            xc = i; break
        if (not up_prev) and C[i] >= ema[i]:     # an UP-cross is more recent -> down-state broke
            return None, None
    if xc is None:
        return None, None                        # been below the whole lookback (stale/old trend)
    recency = fb - xc
    a = max(1, xc-5)
    hiBefore = H[a:xc+1].max()
    loAfter = L[xc:fb+1].min()
    atr = np.mean(H[a:fb] - L[a:fb]) or 1.0
    return recency, float((hiBefore - loAfter) / atr)


def main():
    b = pd.read_parquet(BARS); b["Date"] = b["DateTime"].dt.date.astype(str)
    f = pd.read_parquet(FADE)[["Date", "fill_bar", "net", "year"]].copy()
    f["Date"] = f.Date.astype(str)
    rec, strn = [], []
    for dstr, de in f.groupby("Date"):
        gd = b[b["Date"] == dstr].sort_values("DateTime").reset_index(drop=True)
        C = gd["Close"].values; H = gd["High"].values; L = gd["Low"].values
        ema = pd.Series(C).ewm(span=EMA_N, adjust=False).mean().values
        for idx, e in de.iterrows():
            r, s = recent_downcross(ema, H, L, C, int(e.fill_bar))
            rec.append((idx, r)); strn.append((idx, s))
    f["recency"] = pd.Series(dict(rec)); f["strength"] = pd.Series(dict(strn))
    f.to_parquet(OUT, index=False)
    intact = f.recency.notna()
    print(f"fades n={len(f)}  base {g(f.net)}")
    print(f"  intact recent down-state: {intact.sum()}  |  stale/above-EMA (no valid down-cross): {(~intact).sum()}\n")

    print("="*84); print("A. RECENCY of the most-recent INTACT down-cross (the axis that matters)"); print("="*84)
    fi = f[intact]
    print(f"  stale/none (above EMA or old trend) {g(f[~intact].net)}")
    for lab, m in (("cross <=3 bars ago", fi.recency <= 3), ("4-6 bars", (fi.recency>=4)&(fi.recency<=6)),
                   ("7-10 bars", (fi.recency>=7)&(fi.recency<=10)), (">10 bars", fi.recency>10)):
        print(f"  {lab:22s} {g(fi[m].net)}")

    print("\n"+"="*84); print("B. STRENGTH (within intact down-crosses)"); print("="*84)
    q = fi.strength.quantile([1/3, 2/3]).values
    for lab, m in (("weak", fi.strength<=q[0]), ("mid", (fi.strength>q[0])&(fi.strength<=q[1])), ("STRONG", fi.strength>q[1])):
        print(f"  {lab:8s} {g(fi[m].net)}")

    print("\n"+"="*84); print("C. RECENT & STRONG  (recency<=R AND strength>=thr) + perm-null + train/holdout"); print("="*84)
    tr = f.Date <= TRAIN_END
    def perm(mask):
        mask=np.asarray(mask,bool); k=mask.sum()
        if k<8 or k>=len(f): return np.nan
        obs=f.net.values[mask].mean(); idx=np.arange(len(f))
        return (np.array([f.net.values[RNG.permutation(idx)[:k]].mean() for _ in range(4000)])>=obs).mean()
    for R in (4, 6, 8):
        for thr in (1.5, 2.0, 2.5):
            m = intact & (f.recency<=R) & (f.strength>=thr)
            if m.sum() < 8: continue
            p = perm(m.values)
            print(f"  recency<={R} & str>={thr}: {g(f[m].net)}  perm-p={p:.3f}  | train {g(f[m&tr].net)} hold {g(f[m&~tr].net)}  {'<sig' if p<0.05 else ''}")

    print("\n"+"="*84); print("D. stale-cross check (Samir's point): strong-but-STALE should NOT help"); print("="*84)
    print(f"  strong(>=2) & recency<=6 (fresh) {g(f[intact & (f.strength>=2.0) & (f.recency<=6)].net)}")
    print(f"  strong(>=2) & recency>10 (stale)  {g(f[intact & (f.strength>=2.0) & (f.recency>10)].net)}")
    print(f"  above-EMA / no down-state         {g(f[~intact].net)}")

    # ---- headline: price ABOVE EMA at entry = failed EMA-reclaim short. NO lookback K. ----
    print("\n"+"="*84); print("E. HEADLINE: price ABOVE the EMA at the fade (failed reclaim) — lookback-FREE"); print("="*84)
    b2 = pd.read_parquet(BARS); b2["Date"] = b2["DateTime"].dt.date.astype(str)
    above = {}
    for dstr, de in f.groupby("Date"):
        gd = b2[b2["Date"] == dstr].sort_values("DateTime").reset_index(drop=True)
        C = gd["Close"].values; ema = pd.Series(C).ewm(span=EMA_N, adjust=False).mean().values
        for idx, e in de.iterrows():
            fb = int(e.fill_bar); above[idx] = (fb >= 1 and C[fb-1] >= ema[fb-1])   # causal (prior close)
    f["above_ema"] = pd.Series(above)
    tr = f.Date <= TRAIN_END
    A, Bm = f.above_ema == True, f.above_ema == False
    def perm(mask):
        mask=np.asarray(mask,bool); k=mask.sum()
        if k<8 or k>=len(f): return np.nan
        obs=f.net.values[mask].mean(); idx=np.arange(len(f))
        return (np.array([f.net.values[RNG.permutation(idx)[:k]].mean() for _ in range(5000)])>=obs).mean()
    print(f"  ABOVE EMA (failed reclaim) {g(f[A].net)}  perm-p={perm(A.values):.4f}")
    print(f"    train {g(f[A&tr].net)}   holdout {g(f[A&~tr].net)}")
    print(f"  BELOW EMA (weak bounce)    {g(f[Bm].net)}")
    print("  year (above-EMA): " + " ".join(f"{y}:{f[A&(f.year==y)].net.sum():+,.0f}" for y in sorted(f.year.unique())))
    f.to_parquet(OUT, index=False)


if __name__ == "__main__":
    main()
