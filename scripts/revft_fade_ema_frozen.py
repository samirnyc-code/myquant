"""FROZEN f2EL fade x strong-move-through-EMA — the deciding test. 2026-07-25 (S85, follows 0015d).

0015d found the EMA-thrust filter rescues the WEAK near-final fade (combined_books FADE-S, breakeven).
This re-runs it on the FROZEN f2EL: regenerate the fade entries WITH their fill bars by replaying the
worktree engine (detect_entries_causal + pt_new + the FADE branch of run_books), then apply the same
causal cross_str feature. Decides Samir's question: FILTER (only strong fades) vs SIZER (all fades,
bigger on strong) — i.e. are the non-strong fades dead (filter) or still profitable (size)?

Frozen f2EL geometry (from run_books, engine_ab.py): a 2E LONG candidate whose regime at fill is BEAR,
that then fails (trades to L[sb]-1t within 3 bars) -> short at fail-1t, 4pt (16t) stop, hold to EOD,
hours 09-13, gap-skip |gap|>0.54.

    python scripts/revft_fade_ema_frozen.py
"""
import sys
from pathlib import Path
from bisect import bisect_right
import numpy as np, pandas as pd

MAIN = Path(__file__).resolve().parent.parent
WT = Path(r"C:/Users/Admin/myquant-regime")
sys.path.insert(0, str(WT / "scripts"))
from regime_second_entry_study import load_day          # noqa: E402
from regime_2e_causal_check import detect_entries_causal  # noqa: E402
from regime_engine_ab import pt_new                      # noqa: E402

TICK = 0.25; PT = 50.0; COMM = 5.0; SLIP = 12.5
GOOD = {"09", "10", "11", "12", "13"}
FADE_STOP_T = 16                 # 4pt tight fade stop
KS = [5, 8, 10, 15, 20]          # lookback sweep — is K=10 arbitrary?
EMA_N = 20; TRAIN_END = "2023-12-31"
BARS = MAIN / "data" / "bars" / "_continuous.parquet"
OUT = MAIN / "data" / "regime" / "revft_fade_ema_frozen_20260725.parquet"
RNG = np.random.default_rng(20260725)


def pf(v):
    v = np.asarray(v, float); gp = v[v > 0].sum(); gl = -v[v < 0].sum()
    return gp / gl if gl > 0 else float("inf")


def gg(v):
    v = np.asarray(v, float)
    if not len(v):
        return "n=0"
    return f"n={len(v):4d} ${v.sum():>8,.0f} ${v.mean():6.1f}/tr PF={pf(v):4.2f} win={100*(v>0).mean():4.1f}%"


def cross_str(ema, high, low, close, fb, K):
    """strength of the most recent DOWNSIDE EMA cross in [fb-K, fb), in ATR14 units."""
    a = max(1, fb - K); h, l, c, e = high[a:fb], low[a:fb], close[a:fb], ema[a:fb]
    if len(c) < 3:
        return 0.0
    atr = np.mean(h - l) or 1.0
    above = c > e; best = 0.0
    for i in range(1, len(c)):
        if above[i-1] and not above[i]:
            best = max(best, (h[:i+1].max() - l[i:].min()) / atr)
    return float(best)


def perm_p(net, mask, nperm=4000):
    mask = np.asarray(mask, bool); k = mask.sum()
    if k < 10 or k >= len(net):
        return np.nan
    obs = net[mask].mean(); idx = np.arange(len(net))
    null = np.array([net[RNG.permutation(idx)[:k]].mean() for _ in range(nperm)])
    return (null >= obs).mean()


def main():
    b = pd.read_parquet(BARS); b["Date"] = b["DateTime"].dt.date.astype(str)
    dly = b.groupby("Date").agg(dO=("Open", "first"), dC=("Close", "last")).reset_index()
    dly["gap"] = ((dly.dO - dly.dC.shift(1)) / dly.dC.shift(1) * 100).abs()
    gap = dly.set_index("Date")["gap"]
    days = sorted(b["Date"].unique())
    rows = []
    for dstr in days:
        if dstr not in gap.index or not np.isfinite(gap[dstr]) or gap[dstr] > 0.54:
            continue
        g, tP, tbar = load_day(b, dstr)
        if g is None:
            continue
        H, Lo, C = g["High"].values, g["Low"].values, g["Close"].values
        n = len(g); gdt = g["DateTime"].values
        ema = pd.Series(C).ewm(span=EMA_N, adjust=False).mean().values
        trans = pt_new(H, Lo, n, tP, tbar)
        tr_ix = [t for (t, _) in trans]; tr_md = [m for (_, m) in trans]
        for (fb, sb, dr, cnt, trig) in detect_entries_causal(g, tP, tbar):
            if cnt != 2 or dr != "L":
                continue
            a = np.searchsorted(tbar, fb, "left"); z = np.searchsorted(tbar, fb, "right")
            hit = np.nonzero(tP[a:z] >= trig)[0]
            if not len(hit):
                continue
            jf = a + int(hit[0]); reg = tr_md[bisect_right(tr_ix, jf) - 1]
            if reg != "BEAR":
                continue                                   # fade fires only when the long is in BEAR
            fail = Lo[sb] - TICK; zl = np.searchsorted(tbar, fb + 3, "left")
            w = np.nonzero(tP[jf:zl] <= fail)[0]
            if not len(w):
                continue
            jx = jf + int(w[0]); fb2 = int(tbar[jx])
            if sb >= fb2:
                continue
            if pd.Timestamp(gdt[min(fb2, n - 1)]).strftime("%H") not in GOOD:
                continue
            fill = fail - TICK; stop = fill + FADE_STOP_T * TICK; seg = tP[jx:]
            js = np.nonzero(seg >= stop)[0]; ex = stop if len(js) else seg[-1]
            net = round((fill - ex) * PT - COMM - SLIP, 1)
            rec = dict(Date=dstr, year=int(dstr[:4]), net=net, fill_bar=fb2)
            for k in KS:
                rec[f"cs{k}"] = cross_str(ema, H, Lo, C, fb2, k)
            rows.append(rec)
    t = pd.DataFrame(rows); t.to_parquet(OUT, index=False)
    print(f"FROZEN f2EL fade regenerated: n={len(t)}  base {gg(t.net)}  (target ~n141 PF1.28 wf_dataset)\n")
    tr = t.Date <= TRAIN_END

    print("="*90); print("LOOKBACK-K SWEEP — is K=10 arbitrary? (strong = cs>=2.0 ATR, wide/EOD fade)"); print("="*90)
    print(f"  {'K':>3s} {'strong n':>9s} {'strong $/tr':>12s} {'strong PF':>10s} {'perm-p':>7s} {'rest $/tr':>10s} {'rest PF':>8s} {'hold PF':>8s}")
    for k in KS:
        col = f"cs{k}"; strong = t[col] >= 2.0; rest = ~strong
        if strong.sum() < 10:
            continue
        p = perm_p(t.net.values, strong.values)
        hpf = pf(t[strong & ~tr].net) if (strong & ~tr).sum() else float('nan')
        print(f"  {k:>3d} {strong.sum():>9d} {t[strong].net.mean():>12.1f} {pf(t[strong].net):>10.2f} "
              f"{p:>7.3f} {t[rest].net.mean():>10.1f} {pf(t[rest].net):>8.2f} {hpf:>8.2f}")
    # keep the primary K=10 column as `cross_str` for downstream compatibility
    t["cross_str"] = t["cs10"]

    print("="*90); print("TERCILE of cross_str (strong move through EMA)"); print("="*90)
    q = t.cross_str.quantile([1/3, 2/3]).values
    for lab, m in (("weak", t.cross_str <= q[0]), ("mid", (t.cross_str > q[0]) & (t.cross_str <= q[1])),
                   ("STRONG", t.cross_str > q[1])):
        print(f"  {lab:8s} {gg(t[m].net)}")

    print("\n"+"="*90); print("THRESHOLD sweep + perm-null + train/holdout  (does non-strong = dead?)"); print("="*90)
    for thr in (1.0, 1.5, 2.0, 2.5, 3.0):
        strong = t.cross_str >= thr; weak = ~strong
        if strong.sum() < 10:
            continue
        p = perm_p(t.net.values, strong.values)
        print(f"  >={thr:.1f}: STRONG {gg(t[strong].net)}  perm-p={p:.3f}  {'<sig' if p<0.05 else ''}")
        print(f"          rest  {gg(t[weak].net)}   | STRONG train {gg(t[strong&tr].net)} hold {gg(t[strong&~tr].net)}")

    print("\n"+"="*90); print("DECISION: FILTER vs SIZER at cross_str>=2.0"); print("="*90)
    strong = t.cross_str >= 2.0; weak = ~strong
    base = t.net.sum()
    filt = t[strong].net.sum()
    sizer2 = 2 * t[strong].net.sum() + t[weak].net.sum()      # 2x strong, 1x rest
    print(f"  base take-all fades:                {gg(t.net)}")
    print(f"  FILTER strong-only:                 {gg(t[strong].net)}")
    print(f"  the REST (weak/mid) alone:          {gg(t[weak].net)}  <- if this is +$ & PF>1, DON'T filter, SIZE")
    print(f"  SIZER 2x-strong + 1x-rest ($ tot):  ${sizer2:,.0f}")
    print("\n  year-by-year, strong-only (>=2.0):")
    for y in sorted(t.year.unique()):
        print(f"    {y}: {gg(t[strong & (t.year==y)].net)}")


if __name__ == "__main__":
    main()
