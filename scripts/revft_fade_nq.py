"""NQ cross-instrument test of the FAILED-EMA-RECLAIM fade feature. 2026-07-25 (S85, confirms 0015d).

Tests whether "f2EL fade works better when price is ABOVE the 20-EMA at entry (failed reclaim)"
replicates on NQ — the way to move the ES result (PF 2.78, n=25, perm-p 0.06) to confirmed-or-dead.

Instrument-agnostic design: the fade's ES-specific 4pt stop makes no sense on NQ (~4x range), so the
fade uses an ADR-scaled tight stop (STOP_FRAC x ADR10, ~= the ES 4pt/ADR ratio) and the outcome is
reported in R (points / stop-distance). Also re-runs ES with the SAME normalized stop as a bridge —
if the feature reproduces on ES-normalized AND appears on NQ, it is real.

NQ 5M RTH bars are built from ticks (resample 5min left/closed-left, 08:30-15:10, same as ES).
Engine (pt_new + detect_entries_causal) is instrument-agnostic. Single chronological pass (rolling ADR).

    python scripts/revft_fade_nq.py
"""
import sys
from pathlib import Path
from bisect import bisect_right
from datetime import time
from collections import deque
import numpy as np, pandas as pd

MAIN = Path(r"C:/Users/Admin/myquant")
WT = Path(r"C:/Users/Admin/myquant-regime")
sys.path.insert(0, str(WT / "scripts"))
from regime_2e_causal_check import detect_entries_causal   # noqa: E402
from regime_engine_ab import pt_new                         # noqa: E402

TICK = 0.25
GOOD = {"09", "10", "11", "12", "13"}
STOP_FRAC = 0.067          # ~ ES 4pt / ES ADR(~60pt); ADR-scaled tight fade stop
EMA_N = 20; TRAIN_END = "2023-12-31"
RNG = np.random.default_rng(20260725)


def pf(v):
    v = np.asarray(v, float); gp = v[v > 0].sum(); gl = -v[v < 0].sum()
    return gp / gl if gl > 0 else float("inf")


def gline(v):
    v = np.asarray(v, float)
    if not len(v):
        return "n=0"
    return f"n={len(v):4d}  netR={v.sum():>7.1f}  R/tr={v.mean():+5.2f}  PF={pf(v):4.2f}  win={100*(v>0).mean():4.1f}%"


def build_bars_from_ticks(tk):
    tk = tk.set_index("DateTime")
    o = tk["Price"].resample("5min", label="left", closed="left").agg(["first", "max", "min", "last"])
    o.columns = ["Open", "High", "Low", "Close"]
    o = o.dropna().reset_index()
    o = o[(o.DateTime.dt.time >= time(8, 30)) & (o.DateTime.dt.time <= time(15, 10))]
    return o.reset_index(drop=True)


def fade_records(g, tP, tbar, adr10):
    """replicate the run_books FADE branch with an ADR-scaled stop; outcome in R. + above_ema flag."""
    H, Lo, C = g["High"].values, g["Low"].values, g["Close"].values
    n = len(g); gdt = g["DateTime"].values
    ema = pd.Series(C).ewm(span=EMA_N, adjust=False).mean().values
    trans = pt_new(H, Lo, n, tP, tbar)
    tr_ix = [t for (t, _) in trans]; tr_md = [m for (_, m) in trans]
    stop_dist = max(round(STOP_FRAC * adr10 / TICK) * TICK, TICK)
    out = []
    for (fb, sb, dr, cnt, trig) in detect_entries_causal(g, tP, tbar):
        if cnt != 2 or dr != "L":
            continue
        a = np.searchsorted(tbar, fb, "left"); z = np.searchsorted(tbar, fb, "right")
        hit = np.nonzero(tP[a:z] >= trig)[0]
        if not len(hit):
            continue
        jf = a + int(hit[0]); reg = tr_md[bisect_right(tr_ix, jf) - 1]
        if reg != "BEAR":
            continue
        fail = Lo[sb] - TICK; zl = np.searchsorted(tbar, fb + 3, "left")
        w = np.nonzero(tP[jf:zl] <= fail)[0]
        if not len(w):
            continue
        jx = jf + int(w[0]); fb2 = int(tbar[jx])
        if sb >= fb2 or fb2 >= n:
            continue
        if pd.Timestamp(gdt[min(fb2, n - 1)]).strftime("%H") not in GOOD:
            continue
        fill = fail - TICK; stop = fill + stop_dist; seg = tP[jx:]
        js = np.nonzero(seg >= stop)[0]; ex = stop if len(js) else seg[-1]
        netR = (fill - ex) / stop_dist
        above = (fb2 >= 1 and C[fb2 - 1] >= ema[fb2 - 1])       # causal
        out.append((netR, above))
    return out


def run_instrument(kind):
    rows = []
    if kind == "ES":
        b = pd.read_parquet(MAIN / "data" / "bars" / "_continuous.parquet")
        b["Date"] = b["DateTime"].dt.date.astype(str)
        tickd = MAIN / "data" / "ticks_continuous"
        days = sorted(b["Date"].unique())
        get_bars = lambda d: b[b["Date"] == d].sort_values("DateTime").reset_index(drop=True)
    else:
        tickd = MAIN / "data" / "ticks_continuous_NQ"
        days = sorted(p.stem for p in tickd.glob("*.parquet"))
        get_bars = None
    ranges = deque(maxlen=10); prev_close = None
    for i, dstr in enumerate(days):
        tp = tickd / f"{dstr}.parquet"
        if not tp.exists():
            continue
        tk = pd.read_parquet(tp).sort_values("DateTime")
        if tk.empty:
            continue
        g = get_bars(dstr) if get_bars else build_bars_from_ticks(tk)
        if len(g) < 30:
            continue
        adr10 = np.mean(ranges) if len(ranges) == 10 else np.nan
        dayH, dayL, dayO, dayC = g["High"].max(), g["Low"].min(), g["Open"].iloc[0], g["Close"].iloc[-1]
        gap = abs((dayO - prev_close) / prev_close * 100) if prev_close else np.nan
        if np.isfinite(adr10) and (not np.isfinite(gap) or gap <= 0.54):
            tP = tk["Price"].values
            tbar = np.searchsorted(g["DateTime"].values, tk["DateTime"].values, "right") - 1
            try:
                for (netR, above) in fade_records(g, tP, tbar, adr10):
                    rows.append((dstr, int(dstr[:4]), netR, above))
            except Exception as e:
                print(dstr, kind, "ERR", repr(e)[:60], flush=True)
        ranges.append(dayH - dayL); prev_close = dayC
        if (i + 1) % 300 == 0:
            print(f"  [{kind} {i+1}/{len(days)}] fades={len(rows)}", flush=True)
    return pd.DataFrame(rows, columns=["Date", "year", "netR", "above"])


def report(t, name):
    A = t[t.above]; B = t[~t.above]; tr = t.Date <= TRAIN_END
    k = A.shape[0]
    if k >= 8 and k < len(t):
        obs = A.netR.mean(); idx = np.arange(len(t)); nv = t.netR.values
        p = (np.array([nv[RNG.permutation(idx)[:k]].mean() for _ in range(5000)]) >= obs).mean()
    else:
        p = np.nan
    print(f"\n===== {name}  (fade outcome in R, ADR-scaled stop, hold-EOD) =====")
    print(f"  ALL fades                 {gline(t.netR)}")
    print(f"  ABOVE EMA (failed reclaim) {gline(A.netR)}   perm-p={p:.4f}")
    print(f"     train {gline(A[A.Date<=TRAIN_END].netR)}   holdout {gline(A[A.Date>TRAIN_END].netR)}")
    print(f"  BELOW EMA (weak bounce)    {gline(B.netR)}")
    if len(A):
        print("  year (above): " + " ".join(f"{y}:{A[A.year==y].netR.sum():+.1f}" for y in sorted(t.year.unique())))


def main():
    for kind in ("ES", "NQ"):
        t = run_instrument(kind)
        t.to_parquet(MAIN / "data" / "regime" / f"revft_fade_{kind.lower()}_reclaim_20260725.parquet", index=False)
        report(t, kind + " (normalized stop)")


if __name__ == "__main__":
    main()
